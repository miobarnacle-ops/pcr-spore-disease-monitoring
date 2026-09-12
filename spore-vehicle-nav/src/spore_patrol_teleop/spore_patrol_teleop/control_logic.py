"""Pure keyboard-to-velocity logic used by the ROS 2 teleop node.

The module deliberately has no ROS dependency so its behavior can be tested
before the Raspberry Pi or the vehicle is powered on.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True)
class TeleopCommand:
    """A planar velocity command in the base frame."""

    linear_x: float = 0.0
    angular_z: float = 0.0

    @property
    def is_zero(self) -> bool:
        return self.linear_x == 0.0 and self.angular_z == 0.0


class TeleopController:
    """Translate simple keys into bounded commands with an input timeout."""

    MOTION_KEYS = frozenset(("w", "a", "s", "d"))

    def __init__(
        self,
        *,
        linear_speed_mps: float = 0.05,
        angular_speed_radps: float = 0.15,
        linear_step_mps: float = 0.01,
        angular_step_radps: float = 0.03,
        max_linear_speed_mps: float = 0.15,
        max_angular_speed_radps: float = 0.30,
        input_timeout_s: float = 0.25,
    ) -> None:
        values = (
            linear_speed_mps,
            angular_speed_radps,
            linear_step_mps,
            angular_step_radps,
            max_linear_speed_mps,
            max_angular_speed_radps,
            input_timeout_s,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("teleop parameters must be finite")
        if (
            linear_speed_mps <= 0.0
            or angular_speed_radps <= 0.0
            or linear_step_mps <= 0.0
            or angular_step_radps <= 0.0
            or max_linear_speed_mps <= 0.0
            or max_angular_speed_radps <= 0.0
            or input_timeout_s <= 0.0
        ):
            raise ValueError("teleop parameters must be positive")
        if linear_speed_mps > max_linear_speed_mps:
            raise ValueError("linear speed cannot exceed its maximum")
        if angular_speed_radps > max_angular_speed_radps:
            raise ValueError("angular speed cannot exceed its maximum")

        self.linear_speed_mps = linear_speed_mps
        self.angular_speed_radps = angular_speed_radps
        self.linear_step_mps = linear_step_mps
        self.angular_step_radps = angular_step_radps
        self.max_linear_speed_mps = max_linear_speed_mps
        self.max_angular_speed_radps = max_angular_speed_radps
        self.input_timeout_s = input_timeout_s
        self._command = TeleopCommand()
        self._last_motion_input: Optional[float] = None

    @property
    def command(self) -> TeleopCommand:
        """Return the last requested command, before timeout evaluation."""

        return self._command

    @property
    def last_motion_input(self) -> Optional[float]:
        return self._last_motion_input

    def handle_key(self, key: str, now: float) -> str:
        """Handle one terminal character and return a small status label."""

        normalized = key.lower()
        if normalized == "w":
            self._set_motion(self.linear_speed_mps, 0.0, now)
            return "forward"
        if normalized == "s":
            self._set_motion(-self.linear_speed_mps, 0.0, now)
            return "reverse"
        if normalized == "a":
            self._set_motion(0.0, self.angular_speed_radps, now)
            return "turn_left"
        if normalized == "d":
            self._set_motion(0.0, -self.angular_speed_radps, now)
            return "turn_right"
        if key in (" ", "x", "X", "0"):
            self.stop()
            return "stopped"
        if key in ("+", "="):
            self._change_speed(1.0)
            self.stop()
            return "speed_up"
        if key in ("-", "_"):
            self._change_speed(-1.0)
            self.stop()
            return "speed_down"
        if normalized == "q":
            self.stop()
            return "quit"

        # Unsupported keys, including partial arrow-key escape sequences, stop
        # the robot instead of leaving the previous motion active.
        self.stop()
        return "stopped"

    def current_command(self, now: float) -> TeleopCommand:
        """Return zero once terminal input has gone quiet."""

        if (
            self._last_motion_input is None
            or now - self._last_motion_input > self.input_timeout_s
        ):
            return TeleopCommand()
        return self._command

    def stop(self) -> None:
        self._command = TeleopCommand()
        self._last_motion_input = None

    def _set_motion(self, linear_x: float, angular_z: float, now: float) -> None:
        self._command = TeleopCommand(linear_x, angular_z)
        self._last_motion_input = now

    def _change_speed(self, direction: float) -> None:
        self.linear_speed_mps = min(
            self.max_linear_speed_mps,
            max(self.linear_step_mps, self.linear_speed_mps + direction * self.linear_step_mps),
        )
        self.angular_speed_radps = min(
            self.max_angular_speed_radps,
            max(self.angular_step_radps, self.angular_speed_radps + direction * self.angular_step_radps),
        )
