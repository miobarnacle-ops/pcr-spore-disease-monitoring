"""Pure ``field/local_enu`` -> ``map/odom`` transform (no ROS imports).

Input
-----
Field coordinates ``(xf, yf)`` plus a vehicle start pose
``(x_start, y_start, yaw_start)`` expressed in ``map``/``odom``.

Output
------
Map coordinates ``(xm, ym)`` and an optional target yaw, using the static
transform frozen in CONVENTIONS §3::

    xm = x_start + xf*cos(yaw_start) - yf*sin(yaw_start)
    ym = y_start + xf*sin(yaw_start) + yf*cos(yaw_start)
    yaw_target = yaw_start + yaw_rad        (when yaw_rad is not None)

Completion criteria
-------------------
Every function here is a pure function of its arguments (no ROS, no state) and
is therefore directly unit-testable with pytest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .route_model import Route, Waypoint


@dataclass(frozen=True)
class StartPose:
    """Vehicle start pose in ``map``/``odom`` (metres, radians)."""

    x: float
    y: float
    yaw: float


def field_to_map_xy(
    xf: float,
    yf: float,
    x_start: float,
    y_start: float,
    yaw_start: float,
) -> Tuple[float, float]:
    """Transform a single field point to map coordinates."""
    cos_yaw = math.cos(yaw_start)
    sin_yaw = math.sin(yaw_start)
    xm = x_start + xf * cos_yaw - yf * sin_yaw
    ym = y_start + xf * sin_yaw + yf * cos_yaw
    return xm, ym


def field_to_map(
    xf: float, yf: float, start_pose: StartPose
) -> Tuple[float, float]:
    """Transform a single field point using a :class:`StartPose`."""
    return field_to_map_xy(xf, yf, start_pose.x, start_pose.y, start_pose.yaw)


def map_yaw(yaw_rad: Optional[float], yaw_start: float) -> Optional[float]:
    """Return the target map yaw, or ``None`` when the waypoint yaw is null."""
    if yaw_rad is None:
        return None
    return yaw_start + yaw_rad


def transform_point(
    xf: float,
    yf: float,
    yaw_rad: Optional[float],
    start_pose: StartPose,
) -> Tuple[float, float, Optional[float]]:
    """Transform a point and its (optional) yaw from field to map."""
    xm, ym = field_to_map(xf, yf, start_pose)
    return xm, ym, map_yaw(yaw_rad, start_pose.yaw)


def transform_waypoint(waypoint: Waypoint, start_pose: StartPose) -> Waypoint:
    """Return a copy of ``waypoint`` with map-frame coordinates/yaw."""
    xm, ym, yaw_m = transform_point(
        waypoint.x_m, waypoint.y_m, waypoint.yaw_rad, start_pose
    )
    return replace(waypoint, x_m=xm, y_m=ym, yaw_rad=yaw_m)


def transform_route(route: Route, start_pose: StartPose) -> Route:
    """Return a copy of ``route`` whose ``path`` waypoints are map-frame."""
    return replace(
        route,
        path=[transform_waypoint(wp, start_pose) for wp in route.path],
    )


__all__ = [
    "StartPose",
    "field_to_map_xy",
    "field_to_map",
    "map_yaw",
    "transform_point",
    "transform_waypoint",
    "transform_route",
]
