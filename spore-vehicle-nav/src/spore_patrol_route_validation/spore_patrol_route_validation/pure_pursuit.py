"""Pure Pursuit path tracking controller (no ROS imports).

Input
-----
- lookahead distance ``lookahead_m``
- ``max_linear_mps`` / ``max_angular_radps`` velocity limits
- a ``min_turn_radius_m`` (chassis minimum turning radius, ~0.5 m)
- the current :class:`Pose` ``(x, y, yaw)``
- a ``path``: list of ``(x, y)`` points in the robot's map frame

Output
------
A :class:`Twist` ``(linear, angular)`` (m/s, rad/s) steering the robot toward
the lookahead goal point.

Completion criteria
-------------------
- The lookahead goal point is the first intersection of the path polyline with
  a circle of radius ``lookahead_m`` centred on the robot (falling back to the
  path end point), which makes the controller convergent to the path.
- ``|angular|`` is clamped to ``max_angular_radps``.
- The commanded curvature ``angular/linear`` is clamped to
  ``1/min_turn_radius_m`` (so the turn radius is never below ~0.5 m), and the
  linear speed is reduced when the curvature would otherwise demand too much
  angular rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def normalize_angle(angle: float) -> float:
    """Wrap an angle to [-pi, pi)."""
    while angle >= math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class Twist:
    linear: float
    angular: float

    @property
    def v(self) -> float:
        return self.linear

    @property
    def omega(self) -> float:
        return self.angular


def _circle_segment_intersections(
    a: Point, b: Point, center: Point, radius: float
) -> List[Point]:
    """Return intersection points of segment AB with a circle, ordered by
    distance from ``a``."""
    ax, ay = a
    bx, by = b
    cx, cy = center

    dx = bx - ax
    dy = by - ay
    fx = ax - cx
    fy = ay - cy

    aq = dx * dx + dy * dy
    if aq < 1e-12:
        return []
    bq = 2.0 * (fx * dx + fy * dy)
    cq = fx * fx + fy * fy - radius * radius

    disc = bq * bq - 4.0 * aq * cq
    if disc < 0.0:
        return []
    sqrt_disc = math.sqrt(disc)

    hits: List[Point] = []
    for sign in (-1.0, 1.0):
        t = (-bq + sign * sqrt_disc) / (2.0 * aq)
        if -1e-9 <= t <= 1.0 + 1e-9:
            t = clamp(t, 0.0, 1.0)
            hits.append((ax + t * dx, ay + t * dy))
    hits.sort(key=lambda p: (p[0] - ax) ** 2 + (p[1] - ay) ** 2)
    return hits


def find_lookahead_point(
    path: Sequence[Point],
    x: float,
    y: float,
    lookahead: float,
) -> Optional[Point]:
    """Return the lookahead goal point on ``path`` for robot at ``(x, y)``."""
    if not path:
        return None
    if len(path) == 1:
        return (path[0][0], path[0][1])

    # Start searching from the path vertex nearest the robot.
    nearest = 0
    best = float("inf")
    for i, (px, py) in enumerate(path):
        d2 = (px - x) ** 2 + (py - y) ** 2
        if d2 < best:
            best = d2
            nearest = i

    for i in range(nearest, len(path) - 1):
        hits = _circle_segment_intersections(path[i], path[i + 1], (x, y), lookahead)
        if hits:
            # Furthest along the segment (furthest reachable point ahead).
            return hits[-1]

    # No circle intersection: aim for the end of the path.
    last = path[-1]
    return (last[0], last[1])


class PurePursuitController:
    """Pure Pursuit controller producing ``(v, omega)`` from pose + path."""

    def __init__(
        self,
        lookahead_m: float = 0.5,
        max_linear_mps: float = 0.12,
        max_angular_radps: float = 0.30,
        min_turn_radius_m: float = 0.5,
    ) -> None:
        if lookahead_m <= 0.0:
            raise ValueError("lookahead_m must be positive")
        if max_linear_mps <= 0.0:
            raise ValueError("max_linear_mps must be positive")
        if max_angular_radps <= 0.0:
            raise ValueError("max_angular_radps must be positive")
        if min_turn_radius_m <= 0.0:
            raise ValueError("min_turn_radius_m must be positive")

        self.lookahead_m = float(lookahead_m)
        self.max_linear_mps = float(max_linear_mps)
        self.max_angular_radps = float(max_angular_radps)
        self.min_turn_radius_m = float(min_turn_radius_m)
        self.max_curvature = 1.0 / self.min_turn_radius_m

    def curvature_to(self, pose: Pose, path: Sequence[Point]) -> Optional[float]:
        """Signed curvature ``omega/v`` toward the lookahead goal (pre-clamp)."""
        goal = find_lookahead_point(path, pose.x, pose.y, self.lookahead_m)
        if goal is None:
            return None
        dx = goal[0] - pose.x
        dy = goal[1] - pose.y
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            return None
        alpha = normalize_angle(math.atan2(dy, dx) - pose.yaw)
        effective_lookahead = max(self.lookahead_m, dist)
        return 2.0 * math.sin(alpha) / effective_lookahead

    def compute(self, pose: Pose, path: Sequence[Point]) -> Twist:
        """Compute a clamped ``(v, omega)`` for ``pose`` on ``path``."""
        if not path:
            return Twist(0.0, 0.0)

        goal = find_lookahead_point(path, pose.x, pose.y, self.lookahead_m)
        if goal is None:
            return Twist(0.0, 0.0)

        dx = goal[0] - pose.x
        dy = goal[1] - pose.y
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            # Already at the goal.
            return Twist(0.0, 0.0)

        alpha = normalize_angle(math.atan2(dy, dx) - pose.yaw)
        # Use the actual distance when closer than the lookahead so that the
        # final approach does not overshoot the end point.
        effective_lookahead = max(self.lookahead_m, dist)
        curvature = 2.0 * math.sin(alpha) / effective_lookahead

        # Respect the chassis minimum turning radius.
        curvature = clamp(curvature, -self.max_curvature, self.max_curvature)

        # Limit linear speed so |omega| = |v * curvature| stays in bounds.
        linear = self.max_linear_mps
        if abs(curvature) > 1e-12:
            linear = min(linear, self.max_angular_radps / abs(curvature))

        angular = curvature * linear
        angular = clamp(angular, -self.max_angular_radps, self.max_angular_radps)

        return Twist(linear, angular)


__all__ = [
    "clamp",
    "normalize_angle",
    "Pose",
    "Twist",
    "find_lookahead_point",
    "PurePursuitController",
]
