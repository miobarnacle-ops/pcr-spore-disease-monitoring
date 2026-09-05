"""Tests for field_map_transform.py: origin / axis / rotation math."""

import math

import pytest

from spore_patrol_route_validation.field_map_transform import (
    StartPose,
    field_to_map,
    field_to_map_xy,
    map_yaw,
    transform_point,
    transform_route,
)
from spore_patrol_route_validation.route_model import parse_route, Waypoint


def test_identity_at_origin():
    start = StartPose(0.0, 0.0, 0.0)
    xm, ym = field_to_map(1.0, 2.0, start)
    assert xm == pytest.approx(1.0)
    assert ym == pytest.approx(2.0)


def test_pure_translation():
    start = StartPose(5.0, 7.0, 0.0)
    xm, ym = field_to_map(1.0, 0.0, start)
    assert xm == pytest.approx(6.0)
    assert ym == pytest.approx(7.0)


def test_quarter_turn_rotation():
    # yaw = 90 deg maps field +X onto map +Y.
    start = StartPose(0.0, 0.0, math.pi / 2.0)
    xm, ym = field_to_map(1.0, 0.0, start)
    assert xm == pytest.approx(0.0, abs=1e-9)
    assert ym == pytest.approx(1.0, abs=1e-9)


def test_arbitrary_rotation_matches_matrix():
    yaw = 0.7
    start = StartPose(2.0, -3.0, yaw)
    xf, yf = 1.5, -0.8
    xm, ym = field_to_map(xf, yf, start)
    expected_x = 2.0 + xf * math.cos(yaw) - yf * math.sin(yaw)
    expected_y = -3.0 + xf * math.sin(yaw) + yf * math.cos(yaw)
    assert xm == pytest.approx(expected_x)
    assert ym == pytest.approx(expected_y)


def test_field_to_map_xy_equals_field_to_map():
    start = StartPose(1.0, 2.0, 0.5)
    a = field_to_map_xy(3.0, 4.0, start.x, start.y, start.yaw)
    b = field_to_map(3.0, 4.0, start)
    assert a == b


def test_map_yaw_null_passthrough():
    assert map_yaw(None, 1.0) is None


def test_map_yaw_addition():
    assert map_yaw(0.5, 0.3) == pytest.approx(0.8)


def test_transform_point_full():
    start = StartPose(0.0, 0.0, math.pi / 2.0)
    xm, ym, yaw = transform_point(1.0, 0.0, 0.5, start)
    assert xm == pytest.approx(0.0, abs=1e-9)
    assert ym == pytest.approx(1.0, abs=1e-9)
    assert yaw == pytest.approx(math.pi / 2.0 + 0.5)


def test_transform_point_null_yaw():
    start = StartPose(0.0, 0.0, 0.0)
    _, _, yaw = transform_point(1.0, 2.0, None, start)
    assert yaw is None


def test_transform_route_preserves_metadata():
    start = StartPose(0.0, 0.0, 0.0)
    data = {
        "schema_version": "1.0",
        "frame_id": "field",
        "coordinate_type": "local_enu",
        "unit": "m",
        "field_polygon_m": [],
        "sampling_points": [],
        "path": [
            {
                "seq": 0,
                "x_m": 1.0,
                "y_m": 2.0,
                "yaw_rad": None,
                "type": "sampling",
                "round": 1,
                "sample_id": "R1-P1",
                "speed_limit_mps": 0.12,
                "tolerance_m": 0.2,
            }
        ],
    }
    route = parse_route(data)
    transformed = transform_route(route, start)
    wp = transformed.path[0]
    assert wp.type == "sampling"
    assert wp.sample_id == "R1-P1"
    assert wp.x_m == pytest.approx(1.0)
    assert wp.y_m == pytest.approx(2.0)


def test_transform_route_rotates_all_waypoints():
    start = StartPose(0.0, 0.0, math.pi / 2.0)
    wp = Waypoint(
        seq=0,
        x_m=1.0,
        y_m=0.0,
        yaw_rad=0.0,
        type="transit",
        round=0,
        sample_id=None,
        speed_limit_mps=0.12,
        tolerance_m=0.2,
    )
    from spore_patrol_route_validation.field_map_transform import transform_waypoint

    out = transform_waypoint(wp, start)
    assert out.x_m == pytest.approx(0.0, abs=1e-9)
    assert out.y_m == pytest.approx(1.0, abs=1e-9)
    assert out.yaw_rad == pytest.approx(math.pi / 2.0)
