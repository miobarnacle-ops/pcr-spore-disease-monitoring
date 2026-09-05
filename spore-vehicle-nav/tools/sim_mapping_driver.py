#!/usr/bin/env python3
"""Drive the simulated robot through mapping waypoints using /odom feedback.

This is deliberately a simulation-only helper. It publishes to the local
Gazebo robot's ``/cmd_vel`` and has no serial, rosbridge, or hardware path.
The waypoints use world x/y velocity components because the simplified
``gazebo_ros_planar_move`` model is used for this mapping smoke test.
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
from rclpy.duration import Duration
from rclpy.node import Node


WAYPOINTS = (
    (3.0, -0.71),
    (3.0, 2.20),
    (-3.0, 2.20),
    (-3.0, -2.20),
    (3.0, -2.20),
    (3.0, 0.71),
    (-3.0, 0.71),
    (-3.0, -0.71),
    (-2.0, -0.71),
)


class MappingDriver(Node):
    def __init__(self, speed: float, tolerance: float, segment_timeout: float, log_path: Optional[Path]):
        super().__init__("sim_mapping_driver")
        self.speed = speed
        self.tolerance = tolerance
        self.segment_timeout = segment_timeout
        self.publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self.create_timer(0.10, self._tick)
        self.x: Optional[float] = None
        self.y: Optional[float] = None
        self.waypoint_index = 0
        self.segment_started = self.get_clock().now()
        self.hold_until = self.segment_started
        self.finished = False
        self.failed = False
        self.log_path = log_path
        self.log_file = log_path.open("w", encoding="utf-8") if log_path else None
        self._log(f"waypoints={len(WAYPOINTS)} speed={speed:.3f} tolerance={tolerance:.3f}")

    def _log(self, message: str) -> None:
        line = f"{self.get_clock().now().nanoseconds / 1e9:.3f} {message}"
        print(line, flush=True)
        if self.log_file:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def _on_odom(self, message: Odometry) -> None:
        self.x = float(message.pose.pose.position.x)
        self.y = float(message.pose.pose.position.y)

    def _publish(self, x: float = 0.0, y: float = 0.0) -> None:
        command = Twist()
        command.linear.x = x
        command.linear.y = y
        self.publisher.publish(command)

    def _tick(self) -> None:
        if self.finished or self.failed:
            self._publish()
            return
        if self.x is None or self.y is None:
            self._publish()
            return

        now = self.get_clock().now()
        if now < self.hold_until:
            self._publish()
            return

        target_x, target_y = WAYPOINTS[self.waypoint_index]
        delta_x = target_x - self.x
        delta_y = target_y - self.y
        distance = math.hypot(delta_x, delta_y)
        if distance <= self.tolerance:
            self._log(
                f"reached index={self.waypoint_index} "
                f"target=({target_x:.2f},{target_y:.2f}) "
                f"pose=({self.x:.2f},{self.y:.2f})"
            )
            self.waypoint_index += 1
            self.hold_until = now + Duration(seconds=0.4)
            self.segment_started = now
            if self.waypoint_index >= len(WAYPOINTS):
                self._log("completed all mapping waypoints")
                self.finished = True
            self._publish()
            return

        elapsed = (now - self.segment_started).nanoseconds / 1e9
        if elapsed > self.segment_timeout:
            self._log(
                f"failed timeout index={self.waypoint_index} "
                f"target=({target_x:.2f},{target_y:.2f}) "
                f"pose=({self.x:.2f},{self.y:.2f}) distance={distance:.2f}"
            )
            self.failed = True
            self._publish()
            return

        scale = self.speed / max(distance, 1e-9)
        self._publish(delta_x * scale, delta_y * scale)

    def close(self) -> None:
        for _ in range(10):
            self._publish()
        if self.log_file:
            self.log_file.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.20, help="simulation-only planar command magnitude")
    parser.add_argument("--tolerance", type=float, default=0.18)
    parser.add_argument("--segment-timeout", type=float, default=25.0)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args(argv)
    if args.speed <= 0 or args.tolerance <= 0 or args.segment_timeout <= 0:
        parser.error("speed, tolerance and segment-timeout must be positive")

    rclpy.init()
    driver = MappingDriver(args.speed, args.tolerance, args.segment_timeout, args.log)
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
