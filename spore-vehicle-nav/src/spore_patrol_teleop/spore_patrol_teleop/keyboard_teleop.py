"""Minimal curses keyboard console that publishes geometry_msgs/Twist."""

from __future__ import annotations

import curses
import time
from typing import Optional

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node

from .control_logic import TeleopCommand, TeleopController


class KeyboardTeleopNode(Node):
    """Publish the current keyboard command to the standard /cmd_vel topic."""

    def __init__(self) -> None:
        super().__init__("spore_patrol_keyboard_teleop")

        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("publish_rate_hz", 10.0)
        self.declare_parameter("input_timeout_s", 0.25)
        self.declare_parameter("linear_speed_mps", 0.05)
        self.declare_parameter("angular_speed_radps", 0.15)
        self.declare_parameter("linear_step_mps", 0.01)
        self.declare_parameter("angular_step_radps", 0.03)
        self.declare_parameter("max_linear_speed_mps", 0.15)
        self.declare_parameter("max_angular_speed_radps", 0.30)

        self.cmd_vel_topic = str(self.get_parameter("cmd_vel_topic").value)
        publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        if publish_rate_hz <= 0.0:
            raise ValueError("publish_rate_hz must be positive")

        self.controller = TeleopController(
            linear_speed_mps=float(self.get_parameter("linear_speed_mps").value),
            angular_speed_radps=float(
                self.get_parameter("angular_speed_radps").value
            ),
            linear_step_mps=float(self.get_parameter("linear_step_mps").value),
            angular_step_radps=float(
                self.get_parameter("angular_step_radps").value
            ),
            max_linear_speed_mps=float(
                self.get_parameter("max_linear_speed_mps").value
            ),
            max_angular_speed_radps=float(
                self.get_parameter("max_angular_speed_radps").value
            ),
            input_timeout_s=float(self.get_parameter("input_timeout_s").value),
        )
        self.publisher = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.publish_timer = self.create_timer(
            1.0 / publish_rate_hz, self._publish_current_command
        )
        self.last_status = "stopped"
        self.quit_requested = False
        self._last_published = TeleopCommand()

        self.get_logger().info(
            f"keyboard teleop publishing {self.cmd_vel_topic} at "
            f"{publish_rate_hz:.1f} Hz"
        )

    def handle_key(self, key: str) -> None:
        self.last_status = self.controller.handle_key(key, time.monotonic())
        if self.last_status == "quit":
            self.quit_requested = True

    def current_command(self) -> TeleopCommand:
        return self.controller.current_command(time.monotonic())

    def _publish_current_command(self) -> None:
        self._publish(self.current_command())

    def _publish(self, command: TeleopCommand) -> None:
        message = Twist()
        message.linear.x = command.linear_x
        message.angular.z = command.angular_z
        self.publisher.publish(message)
        self._last_published = command

    def publish_stop_burst(self) -> None:
        """Send several zero commands before the process leaves."""

        self.controller.stop()
        for _ in range(3):
            self._publish(TeleopCommand())
            time.sleep(0.02)


def _draw_screen(screen: "curses.window", node: KeyboardTeleopNode) -> None:
    screen.erase()
    height, width = screen.getmaxyx()

    command = node.current_command()
    state = "MOVING" if not command.is_zero else "STOPPED"
    lines = [
        "Spore Patrol - keyboard teleop",
        f"state: {state}    topic: {node.cmd_vel_topic}",
        f"vx: {command.linear_x:+.2f} m/s    wz: {command.angular_z:+.2f} rad/s",
        f"speed: {node.controller.linear_speed_mps:.2f} m/s, "
        f"{node.controller.angular_speed_radps:.2f} rad/s",
        "",
        "W forward   S reverse   A left   D right",
        "SPACE / X stop   +/- speed   Q quit",
        "",
        "Input timeout automatically sends zero.",
        f"last: {node.last_status}",
    ]
    for row, line in enumerate(lines[: max(0, height - 1)]):
        try:
            screen.addnstr(row, 0, line, max(1, width - 1))
        except curses.error:
            pass
    screen.refresh()


def _run_curses(screen: "curses.window", node: KeyboardTeleopNode) -> None:
    # Some SSH/container pseudo-terminals do not implement cursor visibility.
    # That is only a display limitation and must not prevent teleop startup.
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.nodelay(True)
    screen.keypad(False)

    while rclpy.ok() and not node.quit_requested:
        key = screen.getch()
        if key != -1:
            try:
                node.handle_key(chr(key))
            except (ValueError, OverflowError):
                node.handle_key("?")

        rclpy.spin_once(node, timeout_sec=0.0)
        _draw_screen(screen, node)
        time.sleep(0.02)


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = KeyboardTeleopNode()
    try:
        curses.wrapper(lambda screen: _run_curses(screen, node))
    except KeyboardInterrupt:
        pass
    finally:
        node.publish_stop_burst()
        node.destroy_node()
        rclpy.shutdown()
