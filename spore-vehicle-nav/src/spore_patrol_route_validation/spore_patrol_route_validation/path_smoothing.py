"""Polyline smoothing and equal-arc-length resampling (no ROS imports).

Input
-----
A polyline (list of ``(x, y)`` points) in the robot's map frame, straight from
``transform_route``.

Output
------
A smoothed, equal-arc-length-resampled polyline ready for Pure Pursuit, with
sharp corners rounded so the tracked path honours the chassis minimum turning
radius (~0.5 m).

Completion criteria
-------------------
- Chaikin corner cutting rounds sharp turns without moving the first/last
  endpoints (start and end poses are preserved).
- Resampling yields points spaced ``spacing_m`` apart along the arc so the
  controller advances at a uniform rate.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Point = Tuple[float, float]

_ARC_SPACING_M = 0.02


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _hypot(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def chaikin_smooth(points: Sequence[Point], iterations: int = 3) -> List[Point]:
    """Apply Chaikin corner cutting, keeping the endpoints fixed."""
    if not points:
        return []
    pts: List[Point] = [(float(p[0]), float(p[1])) for p in points]
    for _ in range(max(0, int(iterations))):
        if len(pts) < 3:
            break
        new_pts: List[Point] = [pts[0]]
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            q = (0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by)
            r = (0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by)
            new_pts.append(q)
            new_pts.append(r)
        new_pts.append(pts[-1])
        pts = new_pts
    return pts


def round_corners(points: Sequence[Point], radius: float) -> List[Point]:
    """Replace sharp corners with circular arcs of ``radius`` (fillet).

    For each interior vertex whose turn angle is in ``[10 deg, 150 deg]`` a
    circular arc tangent to both adjacent segments is inserted.  Corners whose
    adjacent segments are too short to fit the full fillet are rounded with the
    largest radius that fits (the controller clamps the rest)."""
    if radius <= 0.0 or len(points) < 3:
        return [(float(p[0]), float(p[1])) for p in points]

    min_angle = math.radians(10.0)
    max_angle = math.radians(150.0)

    out: List[Point] = [(float(points[0][0]), float(points[0][1]))]
    for i in range(1, len(points) - 1):
        p0 = points[i - 1]
        p1 = points[i]
        p2 = points[i + 1]
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1 = math.hypot(*v1)
        l2 = math.hypot(*v2)
        if l1 < 1e-9 or l2 < 1e-9:
            out.append((float(p1[0]), float(p1[1])))
            continue

        u1 = (v1[0] / l1, v1[1] / l1)
        u2 = (v2[0] / l2, v2[1] / l2)
        cross = u1[0] * u2[1] - u1[1] * u2[0]
        dot = _clamp(u1[0] * u2[0] + u1[1] * u2[1], -1.0, 1.0)
        phi = math.acos(dot)  # turn angle (heading change)

        if phi < min_angle or phi > max_angle:
            out.append((float(p1[0]), float(p1[1])))
            continue

        # Tangent distance along each segment for the requested radius.
        radius_used = radius
        d = radius_used * math.tan(phi / 2.0)
        if d > l1 or d > l2:
            # Segment too short: fit the largest fillet that still fits.
            d = min(l1, l2) * 0.999
            radius_used = d / math.tan(phi / 2.0)

        tangent_start = (p1[0] - u1[0] * d, p1[1] - u1[1] * d)
        tangent_end = (p1[0] + u2[0] * d, p1[1] + u2[1] * d)

        # Arc centre: offset from the corner along the turn bisector.
        bisector = (u2[0] - u1[0], u2[1] - u1[1])
        bisector_len = math.hypot(*bisector)
        if bisector_len < 1e-9:
            out.append((float(p1[0]), float(p1[1])))
            continue
        centre_offset = radius_used / math.sin(phi / 2.0)
        centre = (
            p1[0] + bisector[0] / bisector_len * centre_offset,
            p1[1] + bisector[1] / bisector_len * centre_offset,
        )

        a_start = math.atan2(tangent_start[1] - centre[1], tangent_start[0] - centre[0])
        a_end = math.atan2(tangent_end[1] - centre[1], tangent_end[0] - centre[0])
        sweep = a_end - a_start
        if cross > 0.0:
            sweep = sweep % (2.0 * math.pi)
        else:
            sweep = -((-sweep) % (2.0 * math.pi))

        arc_length = abs(radius_used * sweep)
        n = max(1, int(round(arc_length / _ARC_SPACING_M)))
        for k in range(1, n):
            a = a_start + sweep * k / n
            out.append(
                (
                    centre[0] + radius_used * math.cos(a),
                    centre[1] + radius_used * math.sin(a),
                )
            )

    out.append((float(points[-1][0]), float(points[-1][1])))
    return out


def resample_equal_arc_length(
    points: Sequence[Point], spacing_m: float
) -> List[Point]:
    """Resample a polyline so consecutive points are ``spacing_m`` apart."""
    if spacing_m <= 0.0:
        raise ValueError("spacing_m must be positive")
    if not points:
        return []
    if len(points) == 1:
        return [(float(points[0][0]), float(points[0][1]))]

    seg_lens: List[float] = []
    total = 0.0
    for i in range(len(points) - 1):
        ax, ay = points[i]
        bx, by = points[i + 1]
        d = math.hypot(bx - ax, by - ay)
        seg_lens.append(d)
        total += d

    if total <= spacing_m:
        return [(float(points[0][0]), float(points[0][1])),
                (float(points[-1][0]), float(points[-1][1]))]

    out: List[Point] = [(float(points[0][0]), float(points[0][1]))]
    target = spacing_m
    cum = 0.0
    for i in range(len(points) - 1):
        seg = seg_lens[i]
        ax, ay = points[i]
        bx, by = points[i + 1]
        while cum + seg >= target - 1e-9 and target <= total:
            t = _clamp((target - cum) / seg if seg > 1e-12 else 0.0, 0.0, 1.0)
            out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
            target += spacing_m
        cum += seg

    last = (float(points[-1][0]), float(points[-1][1]))
    if math.hypot(out[-1][0] - last[0], out[-1][1] - last[1]) > 1e-9:
        out.append(last)
    return out


def curvature_radii(points: Sequence[Point]) -> List[float]:
    """Return the turning radius at each interior vertex (``inf`` if straight).

    Uses the circumradius of each consecutive triple: a smaller radius means a
    sharper turn."""
    radii: List[float] = []
    for i in range(1, len(points) - 1):
        ax, ay = points[i - 1]
        bx, by = points[i]
        cx, cy = points[i + 1]
        ab = math.hypot(bx - ax, by - ay)
        bc = math.hypot(cx - bx, cy - by)
        ac = math.hypot(cx - ax, cy - ay)
        # Twice the signed area of triangle ABC.
        area2 = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
        if area2 < 1e-12 or ab < 1e-9 or bc < 1e-9 or ac < 1e-9:
            radii.append(float("inf"))
        else:
            radii.append((ab * bc * ac) / (2.0 * area2))
    return radii


def min_turn_radius(points: Sequence[Point]) -> float:
    """Return the smallest (sharpest) turning radius along the polyline."""
    radii = curvature_radii(points)
    if not radii:
        return float("inf")
    return min(radii)


def prepare_path(
    points: Sequence[Point],
    spacing_m: float = 0.1,
    smooth_iterations: int = 2,
    min_turn_radius_m: float = 0.5,
) -> List[Point]:
    """Round sharp corners, smooth, then equal-arc resample a polyline."""
    rounded = round_corners(points, radius=min_turn_radius_m)
    smoothed = chaikin_smooth(rounded, iterations=smooth_iterations)
    return resample_equal_arc_length(smoothed, spacing_m)


__all__ = [
    "chaikin_smooth",
    "round_corners",
    "resample_equal_arc_length",
    "curvature_radii",
    "min_turn_radius",
    "prepare_path",
]
