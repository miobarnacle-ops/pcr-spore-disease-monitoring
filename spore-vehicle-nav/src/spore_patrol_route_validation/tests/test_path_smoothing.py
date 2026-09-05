"""Tests for path_smoothing.py: smoothing + equal-arc resampling."""

import math

import pytest

from spore_patrol_route_validation.path_smoothing import (
    chaikin_smooth,
    curvature_radii,
    min_turn_radius,
    prepare_path,
    resample_equal_arc_length,
    round_corners,
)


def spacing_between(points):
    return [
        math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
        for i in range(1, len(points))
    ]


def test_resample_spacing_is_uniform():
    points = [(i * 0.1, 0.0) for i in range(11)]  # 0..1.0
    out = resample_equal_arc_length(points, spacing_m=0.25)
    assert len(out) >= 4
    for d in spacing_between(out)[:-1]:
        assert d == pytest.approx(0.25, abs=1e-6)


def test_resample_preserves_endpoints():
    points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    out = resample_equal_arc_length(points, spacing_m=0.3)
    assert out[0] == pytest.approx((0.0, 0.0))
    assert out[-1] == pytest.approx((1.0, 1.0))


def test_resample_rejects_non_positive_spacing():
    with pytest.raises(ValueError):
        resample_equal_arc_length([(0.0, 0.0), (1.0, 0.0)], spacing_m=0.0)


def test_chaikin_preserves_endpoints():
    points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    out = chaikin_smooth(points, iterations=3)
    assert out[0] == pytest.approx((0.0, 0.0))
    assert out[-1] == pytest.approx((0.0, 1.0))


def test_round_corners_rounds_to_requested_radius():
    corner = [(-1.0, 0.0), (0.0, 0.0), (0.0, 1.0)]
    out = round_corners(corner, radius=0.5)
    assert min_turn_radius(out) == pytest.approx(0.5, abs=0.01)


def test_round_corners_both_turn_directions():
    left = [(-1.0, 0.0), (0.0, 0.0), (0.0, 1.0)]
    right = [(-1.0, 0.0), (0.0, 0.0), (0.0, -1.0)]
    for corner in (left, right):
        assert min_turn_radius(round_corners(corner, 0.5)) == pytest.approx(
            0.5, abs=0.01
        )


def test_round_corners_preserves_endpoints():
    pts = [(-2.0, 0.0), (0.0, 0.0), (0.0, 2.0)]
    out = round_corners(pts, 0.5)
    assert out[0] == (-2.0, 0.0)
    assert out[-1] == (0.0, 2.0)


def test_curvature_radii_straight_line_is_infinite():
    points = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    assert curvature_radii(points) == [float("inf")]


def test_curvature_radii_right_angle_circumradius():
    # Right triangle with legs 1,1: circumradius = sqrt(2)/2.
    points = [(-1.0, 0.0), (0.0, 0.0), (0.0, 1.0)]
    assert curvature_radii(points) == pytest.approx([math.sqrt(2.0) / 2.0])


def test_prepare_path_uniform_spacing_and_endpoints():
    points = [(-2.0, 0.0), (0.0, 0.0), (0.0, 2.0)]
    out = prepare_path(
        points, spacing_m=0.1, smooth_iterations=2, min_turn_radius_m=0.5
    )
    assert out[0] == pytest.approx((-2.0, 0.0))
    assert out[-1] == pytest.approx((0.0, 2.0))
    # Points are 0.1 m apart in arc length; the straight chord distance is
    # never larger than the arc spacing (and never zero / duplicated).
    for d in spacing_between(out):
        assert 0.0 < d <= 0.1 + 1e-6


def test_prepare_path_honours_min_turn_radius():
    points = [(-2.0, 0.0), (0.0, 0.0), (0.0, 2.0)]
    out = prepare_path(
        points, spacing_m=0.1, smooth_iterations=2, min_turn_radius_m=0.5
    )
    assert min_turn_radius(out) >= 0.45
