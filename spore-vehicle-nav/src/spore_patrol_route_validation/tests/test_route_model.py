"""Tests for route_model.py: parse + validate route_v1.json."""

import json

import pytest

from spore_patrol_route_validation.route_model import (
    MAX_SPEED_LIMIT_MPS,
    Route,
    Waypoint,
    load_route,
    parse_route,
)


def make_waypoint(seq=0, **overrides):
    wp = {
        "seq": seq,
        "x_m": 0.0,
        "y_m": 0.0,
        "yaw_rad": None,
        "type": "start",
        "round": 0,
        "sample_id": None,
        "speed_limit_mps": 0.12,
        "tolerance_m": 0.2,
    }
    wp.update(overrides)
    return wp


def make_route(path=None, **overrides):
    route = {
        "schema_version": "1.0",
        "frame_id": "field",
        "coordinate_type": "local_enu",
        "unit": "m",
        "field_polygon_m": [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]],
        "sampling_points": ["R1-P1"],
        "path": path if path is not None else [make_waypoint(0)],
    }
    route.update(overrides)
    return route


def test_parse_good_route():
    route = parse_route(
        make_route(
            path=[
                make_waypoint(0, type="start"),
                make_waypoint(1, x_m=1.0, y_m=2.0, type="transit"),
                make_waypoint(
                    2,
                    x_m=3.0,
                    y_m=4.0,
                    yaw_rad=0.5,
                    type="sampling",
                    round=1,
                    sample_id="R1-P1",
                ),
                make_waypoint(3, type="return"),
            ]
        )
    )
    assert isinstance(route, Route)
    assert route.frame_id == "field"
    assert route.coordinate_type == "local_enu"
    assert route.unit == "m"
    assert len(route.path) == 4

    first = route.path[0]
    assert first.seq == 0
    assert first.type == "start"

    sampling = route.path[2]
    assert sampling.type == "sampling"
    assert sampling.sample_id == "R1-P1"
    assert sampling.yaw_rad == pytest.approx(0.5)
    assert sampling.is_sampling is True


def test_null_yaw_and_sample_id_become_none():
    wp = make_waypoint(0, yaw_rad=None, sample_id=None)
    route = parse_route(make_route(path=[wp]))
    assert route.path[0].yaw_rad is None
    assert route.path[0].sample_id is None


@pytest.mark.parametrize(
    "missing",
    [
        "schema_version",
        "frame_id",
        "coordinate_type",
        "unit",
        "field_polygon_m",
        "sampling_points",
        "path",
    ],
)
def test_reject_missing_top_level_field(missing):
    data = make_route()
    del data[missing]
    with pytest.raises(ValueError):
        parse_route(data)


@pytest.mark.parametrize(
    "missing",
    [
        "seq",
        "x_m",
        "y_m",
        "yaw_rad",
        "type",
        "round",
        "sample_id",
        "speed_limit_mps",
        "tolerance_m",
    ],
)
def test_reject_missing_waypoint_field(missing):
    wp = make_waypoint(0)
    del wp[missing]
    with pytest.raises(ValueError):
        parse_route(make_route(path=[wp]))


def test_reject_speed_over_cap():
    wp = make_waypoint(0, speed_limit_mps=MAX_SPEED_LIMIT_MPS + 0.01)
    with pytest.raises(ValueError):
        parse_route(make_route(path=[wp]))


def test_reject_speed_at_or_below_zero():
    for speed in (0.0, -0.1):
        wp = make_waypoint(0, speed_limit_mps=speed)
        with pytest.raises(ValueError):
            parse_route(make_route(path=[wp]))


def test_reject_negative_tolerance():
    wp = make_waypoint(0, tolerance_m=-0.01)
    with pytest.raises(ValueError):
        parse_route(make_route(path=[wp]))


def test_accept_zero_tolerance():
    wp = make_waypoint(0, tolerance_m=0.0)
    route = parse_route(make_route(path=[wp]))
    assert route.path[0].tolerance_m == 0.0


def test_accept_speed_equal_to_cap():
    wp = make_waypoint(0, speed_limit_mps=MAX_SPEED_LIMIT_MPS)
    route = parse_route(make_route(path=[wp]))
    assert route.path[0].speed_limit_mps == MAX_SPEED_LIMIT_MPS


def test_reject_non_continuous_sequence_and_sampling_without_identity():
    document = make_route(path=[make_waypoint(2)])
    with pytest.raises(ValueError, match="continuous"):
        parse_route(document)
    document = make_route(path=[make_waypoint(0, type="sampling", sample_id=None)])
    with pytest.raises(ValueError, match="sample_id"):
        parse_route(document)


def test_reject_wrong_frame_id():
    with pytest.raises(ValueError):
        parse_route(make_route(frame_id="map"))


def test_reject_wrong_schema_version():
    with pytest.raises(ValueError):
        parse_route(make_route(schema_version=1))


def test_reject_wrong_coordinate_type():
    with pytest.raises(ValueError):
        parse_route(make_route(coordinate_type="utm"))


def test_reject_wrong_unit():
    with pytest.raises(ValueError):
        parse_route(make_route(unit="cm"))


def test_reject_invalid_waypoint_type():
    wp = make_waypoint(0, type="spiral")
    with pytest.raises(ValueError):
        parse_route(make_route(path=[wp]))


def test_reject_non_finite_coordinate():
    wp = make_waypoint(0, x_m=float("nan"))
    with pytest.raises(ValueError):
        parse_route(make_route(path=[wp]))


def test_reject_empty_path():
    with pytest.raises(ValueError):
        parse_route(make_route(path=[]))


def test_reject_non_int_seq():
    wp = make_waypoint(0)
    wp["seq"] = "0"
    with pytest.raises(ValueError):
        parse_route(make_route(path=[wp]))


def test_load_route_from_file(tmp_path):
    data = make_route(path=[make_waypoint(0)])
    file = tmp_path / "route_v1.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    route = load_route(str(file))
    assert isinstance(route, Route)
    assert len(route.path) == 1


def test_waypoint_is_frozen():
    route = parse_route(make_route(path=[make_waypoint(0)]))
    with pytest.raises(Exception):
        route.path[0].x_m = 99.0
