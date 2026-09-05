"""ROS 2 node gluing route parsing, transform, smoothing, Pure Pursuit and FSM.

This is the ONLY module that imports ``rclpy``; all pure logic lives in the
sibling modules (``route_model``, ``field_map_transform``, ``path_smoothing``,
``pure_pursuit``, ``sampling_state_machine``) which stay offline-pytestable.

Input (ROS)
-----------
- ``/odometry/filtered`` (EKF, preferred) with fallback to ``/odom``.

Output (ROS)
------------
- ``/cmd_vel`` (``geometry_msgs/Twist``) at ``control_rate_hz`` (>= 5 Hz).  A
  zero twist is published whenever the robot is stopped so the base_driver
  0.30 s ``cmd_vel`` watchdog never trips (CONVENTIONS §4).
- ``/mission/status`` (``std_msgs/String`` JSON) on every state transition and
  sampling event.

Completion criteria
-------------------
- The route file is parsed, validated, transformed field->map with the
  ``start_pose_*`` params, then smoothed (Chaikin) and equal-arc resampled
  before any tracking begins.
- The task is complete (``TASK_FINISHED``) once every waypoint has been
  visited and every sampling waypoint's dwell has elapsed.
"""

from __future__ import annotations

import json
import math
import time
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist as TwistMsg
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from .field_map_transform import StartPose, transform_route
from .path_smoothing import prepare_path
from .pure_pursuit import Pose, PurePursuitController
from .route_model import MAX_SPEED_LIMIT_MPS, Route, load_route
from .safety_decision import decide_motion_safety
from .sampling_state_machine import MissionState, SamplingStateMachine, StateEvent


def quaternion_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    """Convert a quaternion to a yaw angle (radians)."""
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


def odom_to_pose(msg: Odometry) -> Pose:
    orientation = msg.pose.pose.orientation
    yaw = quaternion_to_yaw(
        orientation.x, orientation.y, orientation.z, orientation.w
    )
    return Pose(
        x=float(msg.pose.pose.position.x),
        y=float(msg.pose.pose.position.y),
        yaw=yaw,
    )


class RouteTrackerNode(Node):
    """Route tracking node: odometry in, ``/cmd_vel`` + status out."""

    def __init__(self) -> None:
        super().__init__("spore_patrol_route_tracker")

        # -- parameters ---------------------------------------------------
        self.declare_parameter("odom_topic", "/odometry/filtered")
        self.declare_parameter("odom_fallback_topic", "/odom")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("mission_status_topic", "/mission/status")
        self.declare_parameter("route_file", "")
        self.declare_parameter("max_linear_mps", 0.12)
        self.declare_parameter("max_angular_radps", 0.30)
        self.declare_parameter("lookahead_m", 0.5)
        self.declare_parameter("min_turn_radius_m", 0.5)
        self.declare_parameter("start_pose_x", 0.0)
        self.declare_parameter("start_pose_y", 0.0)
        self.declare_parameter("start_pose_yaw", 0.0)
        self.declare_parameter("enable_simulation_dwell", True)
        self.declare_parameter("sampling_duration_s", 2.0)
        self.declare_parameter("settle_duration_s", 0.0)
        self.declare_parameter("control_rate_hz", 10.0)
        self.declare_parameter("status_heartbeat_hz", 1.0)
        self.declare_parameter("obstacle_stop_enabled", True)
        self.declare_parameter("obstacle_dist_threshold_m", 0.5)
        self.declare_parameter("scan_timeout_s", 0.5)
        self.declare_parameter("obstacle_forward_half_fov_deg", 90.0)
        self.declare_parameter("path_spacing_m", 0.1)
        self.declare_parameter("smooth_iterations", 3)
        self.declare_parameter("speed_limit_cap_mps", MAX_SPEED_LIMIT_MPS)
        self.declare_parameter("odom_timeout_s", 1.0)

        odom_topic = str(self.get_parameter("odom_topic").value)
        odom_fallback_topic = str(self.get_parameter("odom_fallback_topic").value)
        cmd_vel_topic = str(self.get_parameter("cmd_vel_topic").value)
        mission_status_topic = str(self.get_parameter("mission_status_topic").value)
        route_file = str(self.get_parameter("route_file").value)

        self.max_linear_mps = float(self.get_parameter("max_linear_mps").value)
        self.max_angular_radps = float(self.get_parameter("max_angular_radps").value)
        lookahead_m = float(self.get_parameter("lookahead_m").value)
        min_turn_radius_m = float(self.get_parameter("min_turn_radius_m").value)

        start_pose = StartPose(
            x=float(self.get_parameter("start_pose_x").value),
            y=float(self.get_parameter("start_pose_y").value),
            yaw=float(self.get_parameter("start_pose_yaw").value),
        )

        enable_dwell = bool(self.get_parameter("enable_simulation_dwell").value)
        sampling_duration_s = float(self.get_parameter("sampling_duration_s").value)
        settle_duration_s = float(self.get_parameter("settle_duration_s").value)
        control_rate_hz = float(self.get_parameter("control_rate_hz").value)
        heartbeat_hz = float(self.get_parameter("status_heartbeat_hz").value)
        self.obstacle_stop_enabled = bool(
            self.get_parameter("obstacle_stop_enabled").value
        )
        self.obstacle_dist_threshold_m = float(
            self.get_parameter("obstacle_dist_threshold_m").value
        )
        scan_timeout_s = float(self.get_parameter("scan_timeout_s").value)
        forward_half_fov_rad = math.radians(
            float(self.get_parameter("obstacle_forward_half_fov_deg").value)
        )
        path_spacing_m = float(self.get_parameter("path_spacing_m").value)
        smooth_iterations = int(self.get_parameter("smooth_iterations").value)
        speed_limit_cap_mps = float(self.get_parameter("speed_limit_cap_mps").value)
        self.odom_timeout_s = float(self.get_parameter("odom_timeout_s").value)

        if control_rate_hz < 5.0:
            self.get_logger().warning(
                f"control_rate_hz={control_rate_hz} is below the 5 Hz cmd_vel "
                "watchdog requirement; forcing 10 Hz"
            )
            control_rate_hz = 10.0

        # -- obstacle safety state -----------------------------------------
        self._min_scan_dist: Optional[float] = None
        self._scan_time: Optional[float] = None
        self._scan_timeout_s = scan_timeout_s
        self._forward_half_fov_rad = forward_half_fov_rad
        self._last_obstacle_log: float = 0.0

        # -- state machine & controller -----------------------------------
        self.fsm = SamplingStateMachine(
            sampling_duration_s=sampling_duration_s if enable_dwell else 0.0,
            settle_duration_s=settle_duration_s,
        )
        self.controller = PurePursuitController(
            lookahead_m=lookahead_m,
            max_linear_mps=self.max_linear_mps,
            max_angular_radps=self.max_angular_radps,
            min_turn_radius_m=min_turn_radius_m,
        )

        self.route: Optional[Route] = None
        self.smoothed_path: list = []
        self._load_and_prepare(
            route_file, start_pose, speed_limit_cap_mps, path_spacing_m,
            smooth_iterations, min_turn_radius_m,
        )

        # -- odometry -----------------------------------------------------
        self.pose: Optional[Pose] = None
        self._filtered_pose: Optional[Pose] = None
        self._fallback_pose: Optional[Pose] = None
        self._filtered_time: Optional[float] = None
        self._fallback_time: Optional[float] = None

        self.create_subscription(Odometry, odom_topic, self._odom_filtered_cb, 10)
        self.create_subscription(
            Odometry, odom_fallback_topic, self._odom_fallback_cb, 10
        )
        self.create_subscription(
            LaserScan, "/scan", self._scan_cb, qos_profile_sensor_data
        )

        # -- outputs ------------------------------------------------------
        self.cmd_vel_publisher = self.create_publisher(TwistMsg, cmd_vel_topic, 10)
        self.status_publisher = self.create_publisher(String, mission_status_topic, 10)
        self.control_timer = self.create_timer(
            1.0 / control_rate_hz, self._control_callback
        )
        if heartbeat_hz > 0.0:
            self.create_timer(1.0 / heartbeat_hz, self._heartbeat_callback)
        self._last_state: Optional[MissionState] = None

        self.get_logger().info(
            f"route tracker ready: odom={odom_topic} (fallback {odom_fallback_topic}), "
            f"cmd_vel={cmd_vel_topic} at {control_rate_hz} Hz"
        )

    # -- setup -----------------------------------------------------------
    def _load_and_prepare(
        self,
        route_file: str,
        start_pose: StartPose,
        speed_limit_cap_mps: float,
        path_spacing_m: float,
        smooth_iterations: int,
        min_turn_radius_m: float,
    ) -> None:
        if not route_file:
            self.get_logger().warning("no route_file configured; node idles")
            return
        try:
            field_route = load_route(
                route_file, max_speed_limit_mps=speed_limit_cap_mps
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.get_logger().error(f"failed to load route {route_file}: {exc}")
            self.fsm.fault(f"route load failed: {exc}")
            return

        self.route = transform_route(field_route, start_pose)
        points = [(w.x_m, w.y_m) for w in self.route.path]
        self.smoothed_path = prepare_path(
            points,
            spacing_m=path_spacing_m,
            smooth_iterations=smooth_iterations,
            min_turn_radius_m=min_turn_radius_m,
        )
        self.fsm.load_route(self.route)
        self.get_logger().info(
            f"loaded route {route_file}: {len(self.route.path)} waypoints, "
            f"{len(self.smoothed_path)} smoothed points"
        )

    # -- odometry ---------------------------------------------------------
    def _odom_filtered_cb(self, msg: Odometry) -> None:
        self._filtered_pose = odom_to_pose(msg)
        self._filtered_time = time.time()
        self._refresh_pose()

    def _odom_fallback_cb(self, msg: Odometry) -> None:
        self._fallback_pose = odom_to_pose(msg)
        self._fallback_time = time.time()
        self._refresh_pose()

    def _scan_cb(self, msg: LaserScan) -> None:
        """Track the closest obstacle distance inside the forward sector.

        Rearward returns (cable harness, carrier parts) must never halt the
        vehicle, so only beams whose bearing is within
        ``_forward_half_fov_rad`` of the scan's 0-degree axis are considered.
        """
        hits = []
        for i, v in enumerate(msg.ranges):
            if not math.isfinite(v) or v < msg.range_min or v > msg.range_max:
                continue
            ang = msg.angle_min + i * msg.angle_increment
            ang = math.atan2(math.sin(ang), math.cos(ang))
            if abs(ang) <= self._forward_half_fov_rad:
                hits.append(v)
        if hits:
            self._min_scan_dist = min(hits)
            self._scan_time = time.time()

    def _motion_safety(self, now: float):
        """Fail-safe offline-testable gate for odometry, scan and obstacle input."""
        pose_times = [value for value in (self._filtered_time, self._fallback_time) if value is not None]
        pose_age = now - max(pose_times) if pose_times else None
        scan_age = now - self._scan_time if self._scan_time is not None else None
        return decide_motion_safety(
            self.fsm.state, pose_age, scan_age, self._min_scan_dist,
            odom_timeout_s=self.odom_timeout_s, scan_timeout_s=self._scan_timeout_s,
            obstacle_threshold_m=self.obstacle_dist_threshold_m,
            obstacle_stop_enabled=self.obstacle_stop_enabled,
        )

    def _obstacle_blocked(self) -> bool:
        """Compatibility status bit: true for any safety gate that inhibits motion."""
        return not self._motion_safety(time.time()).allow_motion

    def _refresh_pose(self) -> None:
        now = time.time()
        filtered_fresh = (
            self._filtered_time is not None
            and now - self._filtered_time < self.odom_timeout_s
        )
        fallback_fresh = (
            self._fallback_time is not None
            and now - self._fallback_time < self.odom_timeout_s
        )
        if filtered_fresh:
            self.pose = self._filtered_pose
        elif fallback_fresh:
            self.pose = self._fallback_pose
        # otherwise keep the last known pose.

    # -- control ----------------------------------------------------------
    def _current_target(self):
        if self.route is None:
            return None
        wp = self.fsm.current_waypoint()
        return wp

    def _arrived(self, target) -> bool:
        if self.pose is None or target is None:
            return False
        dx = self.pose.x - target.x_m
        dy = self.pose.y - target.y_m
        distance = math.hypot(dx, dy)
        radius = max(float(target.tolerance_m), 1e-3)
        return distance <= radius

    def _control_callback(self) -> None:
        now = time.time()
        fsm = self.fsm

        if fsm.state is MissionState.TASK_LOADED:
            fsm.start()

        if fsm.state in (MissionState.NAVIGATING, MissionState.RETURNING):
            target = self._current_target()
            if self._arrived(target):
                fsm.arrive_at_waypoint()

        # Drive instantaneous transitions (arrival -> settle -> sample-request
        # -> sampling) until the machine is either driving again or waiting on
        # a dwell, so transit/turn waypoints do not stall the robot.
        for _ in range(8):
            before = fsm.state
            fsm.advance(now)
            if (
                fsm.state is before
                or fsm.state in (MissionState.NAVIGATING, MissionState.TASK_FINISHED)
            ):
                break

        blocked = False
        if fsm.state in (MissionState.NAVIGATING, MissionState.RETURNING) and self.pose is not None:
            target = self._current_target()
            if target is not None:
                self.controller.max_linear_mps = min(
                    self.max_linear_mps, float(target.speed_limit_mps)
                )
            twist = self.controller.compute(self.pose, self.smoothed_path)
            linear, angular = twist.linear, twist.angular
            decision = self._motion_safety(now)
            blocked = not decision.allow_motion
            if blocked and linear > 0.0:
                now_s = time.time()
                if now_s - self._last_obstacle_log > 2.0:
                    self.get_logger().warning(
                        f"SAFETY STOP: {decision.reason}; halting"
                    )
                    self._last_obstacle_log = now_s
                linear, angular = 0.0, 0.0
        else:
            linear, angular = 0.0, 0.0

        self._publish_velocity(linear, angular)
        self._publish_status(now, blocked)

    def _publish_velocity(self, linear: float, angular: float) -> None:
        msg = TwistMsg()
        msg.linear.x = float(linear)
        msg.angular.z = float(angular)
        self.cmd_vel_publisher.publish(msg)

    # -- status -----------------------------------------------------------
    def _heartbeat_callback(self) -> None:
        """Publish the current mission state periodically (1 Hz default).

        The mission monitor / Web console needs a continuous view of the
        robot's state, not just transitions; a steady heartbeat also makes the
        first status message observable to newly-subscribed clients.
        """
        if self.fsm.route is None:
            return
        self._publish_status_message(
            self._state_payload(self.fsm, time.time(), self._obstacle_blocked())
        )

    def _publish_status(self, now: float, blocked: bool = False) -> None:
        fsm = self.fsm
        changed = fsm.state is not self._last_state
        events = fsm.consume_events()
        if not changed and not events:
            return
        self._last_state = fsm.state
        if changed:
            self._publish_status_message(
                self._state_payload(fsm, now, blocked)
            )
        for event in events:
            self._publish_status_message(self._event_payload(event, now))

    @staticmethod
    def _state_payload(
        fsm: SamplingStateMachine, now: float, blocked: bool = False
    ) -> dict:
        wp = fsm.current_waypoint()
        return {
            "event": "state_changed",
            "state": fsm.state.value,
            "waypoint_index": fsm.current_waypoint_index,
            "waypoint_seq": wp.seq if wp is not None else None,
            "sample_id": wp.sample_id if wp is not None else None,
            "total_waypoints": len(fsm.route.path) if fsm.route else 0,
            "obstacle_stop": blocked,
            "timestamp": now,
        }

    @staticmethod
    def _event_payload(event: StateEvent, now: float) -> dict:
        return {
            "event": event.kind,
            "state": event.state.value,
            "waypoint_seq": event.waypoint_seq,
            "sample_id": event.sample_id,
            "message": event.message,
            "timestamp": now,
        }

    def _publish_status_message(self, payload: dict) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        self.status_publisher.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RouteTrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
