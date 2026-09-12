#!/usr/bin/env python3
"""Drive the single-ridge Gazebo scene with a body-frame closed loop.

This is simulation-only.  The robot drives forward in its body frame and
rotates at each headland, which is closer to the real vehicle than translating
sideways in world coordinates.  It publishes only to the Gazebo model's
``/cmd_vel`` and never opens a serial device or sends a command to hardware.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


# The route observes both sides of the 4.8 m ridge. Each segment is travelled
# forward in the robot body frame; the following heading is reached at the
# preceding headland before the next leg starts.
WAYPOINTS = (
    (-1.80, -0.90),
    (3.30, -0.90),
    (3.30, 0.90),
    (-3.30, 0.90),
    (-3.30, -0.90),
    (-1.80, -0.90),
)
LEG_HEADINGS = (0.0, math.pi / 2.0, math.pi, -math.pi / 2.0, 0.0)


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def quaternion_yaw(x: float, y: float, z: float, w: float) -> float:
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class SingleRidgeMappingDriver(Node):
    def __init__(
        self,
        speed: float,
        angular_speed: float,
        tolerance: float,
        heading_tolerance: float,
        segment_timeout: float,
        log_path: Optional[Path],
    ):
        super().__init__("single_ridge_mapping_driver")
        self.speed = speed
        self.angular_speed = angular_speed
        self.tolerance = tolerance
        self.heading_tolerance = heading_tolerance
        self.segment_timeout = segment_timeout
        self.publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self.create_timer(0.10, self._tick)
        self.x: Optional[float] = None
        self.y: Optional[float] = None
        self.yaw: Optional[float] = None
        self.leg_index = 0
        self.state = "align"
        self.segment_started = self.get_clock().now()
        self.finished = False
        self.failed = False
        self.log_path = log_path
        self.log_file = log_path.open("w", encoding="utf-8") if log_path else None
        self._log(
            f"scenario=single_ridge_8m motion=body_forward_with_heading "
            f"waypoints={len(WAYPOINTS)} speed={speed:.3f} "
            f"angular_speed={angular_speed:.3f} tolerance={tolerance:.3f}"
        )

    def _log(self, message: str) -> None:
        line = f"{self.get_clock().now().nanoseconds / 1e9:.3f} {message}"
        print(line, flush=True)
        if self.log_file:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def _on_odom(self, message: Odometry) -> None:
        pose = message.pose.pose
        self.x = float(pose.position.x)
        self.y = float(pose.position.y)
        self.yaw = quaternion_yaw(
            float(pose.orientation.x),
            float(pose.orientation.y),
            float(pose.orientation.z),
            float(pose.orientation.w),
        )

    def _publish(self, forward: float = 0.0, angular: float = 0.0) -> None:
        command = Twist()
        command.linear.x = forward
        command.angular.z = angular
        self.publisher.publish(command)

    def _fail_timeout(self, now, target_x: float, target_y: float) -> None:
        elapsed = (now - self.segment_started).nanoseconds / 1e9
        self._log(
            f"failed timeout state={self.state} leg={self.leg_index} "
            f"target=({target_x:.2f},{target_y:.2f}) "
            f"pose=({self.x:.2f},{self.y:.2f}) yaw={self.yaw:.2f} "
            f"elapsed={elapsed:.1f}"
        )
        self.failed = True
        self._publish()

    def _tick(self) -> None:
        if self.finished or self.failed:
            self._publish()
            return
        if self.x is None or self.y is None or self.yaw is None:
            self._publish()
            return

        now = self.get_clock().now()
        target_x, target_y = WAYPOINTS[self.leg_index + 1]
        desired_heading = LEG_HEADINGS[self.leg_index]

        if self.state == "align":
            heading_error = normalize_angle(desired_heading - self.yaw)
            if abs(heading_error) <= self.heading_tolerance:
                self._log(
                    f"aligned leg={self.leg_index} heading={desired_heading:.2f} "
                    f"yaw={self.yaw:.2f}"
                )
                self.state = "drive"
                self.segment_started = now
                self._publish()
                return
            if (now - self.segment_started).nanoseconds / 1e9 > self.segment_timeout:
                self._fail_timeout(now, target_x, target_y)
                return
            angular = math.copysign(
                min(self.angular_speed, max(0.20, 2.0 * abs(heading_error))),
                heading_error,
            )
            self._publish(angular=angular)
            return

        distance = math.hypot(target_x - self.x, target_y - self.y)
        if distance <= self.tolerance:
            self._log(
                f"reached index={self.leg_index + 1} "
                f"target=({target_x:.2f},{target_y:.2f}) "
                f"pose=({self.x:.2f},{self.y:.2f}) yaw={self.yaw:.2f}"
            )
            self.leg_index += 1
            if self.leg_index >= len(LEG_HEADINGS):
                self._log("completed single-ridge closed loop")
                self.finished = True
            else:
                self.state = "align"
                self.segment_started = now
            self._publish()
            return

        if (now - self.segment_started).nanoseconds / 1e9 > self.segment_timeout:
            self._fail_timeout(now, target_x, target_y)
            return

        # Keep the body aligned with the current row leg while moving forward.
        heading_error = normalize_angle(desired_heading - self.yaw)
        correction = max(-0.25, min(0.25, 2.0 * heading_error))
        self._publish(forward=self.speed, angular=correction)

    def close(self) -> None:
        for _ in range(10):
            self._publish()
        if self.log_file:
            self.log_file.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.12)
    parser.add_argument("--angular-speed", type=float, default=0.80)
    parser.add_argument("--tolerance", type=float, default=0.14)
    parser.add_argument("--heading-tolerance", type=float, default=0.06)
    parser.add_argument("--segment-timeout", type=float, default=55.0)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args(argv)
    if (
        args.speed <= 0
        or args.angular_speed <= 0
        or args.tolerance <= 0
        or args.heading_tolerance <= 0
        or args.segment_timeout <= 0
    ):
        parser.error("all motion and timeout values must be positive")

    rclpy.init()
    driver = SingleRidgeMappingDriver(
        args.speed,
        args.angular_speed,
        args.tolerance,
        args.heading_tolerance,
        args.segment_timeout,
        args.log,
    )
    try:
        while rclpy.ok() and not driver.finished and not driver.failed:
            rclpy.spin_once(driver, timeout_sec=0.2)
    finally:
        driver.close()
        driver.destroy_node()
        rclpy.shutdown()
    return 0 if driver.finished else 1


if __name__ == "__main__":
    sys.exit(main())
