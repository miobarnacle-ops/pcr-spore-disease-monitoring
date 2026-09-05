"""Tests for pure_pursuit.py: convergence, curvature limit, clamps."""

import math

import pytest

from spore_patrol_route_validation.pure_pursuit import (
    Pose,
    PurePursuitController,
    Twist,
    find_lookahead_point,
)


def straight_path(end_x=5.0, step=0.5):
    n = int(round(end_x / step)) + 1
    return [(i * step, 0.0) for i in range(n)]


def step_robot(pose, twist, dt):
    x = pose.x + twist.linear * math.cos(pose.yaw) * dt
    y = pose.y + twist.linear * math.sin(pose.yaw) * dt
    yaw = pose.yaw + twist.angular * dt
    return Pose(x, y, yaw)


def test_controller_returns_twist():
    c = PurePursuitController()
    pose = Pose(0.0, 0.5, 0.0)
    twist = c.compute(pose, straight_path())
    assert isinstance(twist, Twist)
    assert twist.linear >= 0.0


def test_steers_toward_path():
    c = PurePursuitController()
    path = straight_path()
    # Positive cross-track error (robot left of +X path) -> negative omega.
    twist_above = c.compute(Pose(0.0, 0.5, 0.0), path)
    assert twist_above.angular < 0.0
    # Negative cross-track error -> positive omega.
    twist_below = c.compute(Pose(0.0, -0.5, 0.0), path)
    assert twist_below.angular > 0.0


def test_converges_to_straight_line():
    c = PurePursuitController(lookahead_m=0.5, max_linear_mps=0.12)
    path = straight_path(end_x=5.0, step=0.25)
    pose = Pose(0.0, 0.5, 0.0)
    dt = 0.05
    for _ in range(3000):
        if math.hypot(pose.x - 5.0, pose.y - 0.0) < 0.05:
            break
        twist = c.compute(pose, path)
        pose = step_robot(pose, twist, dt)
    # Converged near the end of the path, on the line.
    assert pose.x > 4.5
    assert abs(pose.y) < 0.1


def test_angular_never_exceeds_limit():
    c = PurePursuitController(
        lookahead_m=0.5, max_linear_mps=0.12, max_angular_radps=0.30
    )
    path = straight_path(end_x=5.0)
    pose = Pose(0.0, 1.0, 0.0)
    dt = 0.05
    for _ in range(1000):
        twist = c.compute(pose, path)
        assert abs(twist.angular) <= 0.30 + 1e-9
        pose = step_robot(pose, twist, dt)


def test_respects_min_turn_radius():
    c = PurePursuitController(
        lookahead_m=0.5,
        max_linear_mps=0.12,
        max_angular_radps=0.30,
        min_turn_radius_m=0.5,
    )
    # Robot facing +X, path goes straight up +Y: hardest 90 deg turn.
    pose = Pose(0.0, 0.0, 0.0)
    path = [(0.0, 0.0), (0.0, 10.0)]
    twist = c.compute(pose, path)
    assert abs(twist.angular) <= 0.30 + 1e-9
    if twist.angular != 0.0:
        radius = abs(twist.linear / twist.angular)
        assert radius >= 0.5 - 1e-9
    # Curvature was clamped at the minimum turn radius -> radius == 0.5.
    assert radius == pytest.approx(0.5, abs=1e-6)


def test_slows_down_when_curvature_demands_too_much_angular():
    # Small max_angular forces linear speed reduction on a sharp turn.
    c = PurePursuitController(
        lookahead_m=0.5,
        max_linear_mps=0.5,
        max_angular_radps=0.10,
        min_turn_radius_m=0.5,
    )
    pose = Pose(0.0, 0.0, 0.0)
    path = [(0.0, 0.0), (0.0, 10.0)]
    twist = c.compute(pose, path)
    assert abs(twist.angular) <= 0.10 + 1e-9
    assert twist.linear < 0.5
    if twist.angular != 0.0:
        assert abs(twist.linear / twist.angular) >= 0.5 - 1e-9


def test_stops_at_end_of_path():
    c = PurePursuitController()
    pose = Pose(1.0, 0.0, 0.0)
    path = [(0.0, 0.0), (1.0, 0.0)]
    twist = c.compute(pose, path)
    assert twist.linear == 0.0
    assert twist.angular == 0.0


def test_stops_on_empty_path():
    c = PurePursuitController()
    twist = c.compute(Pose(0.0, 0.0, 0.0), [])
    assert twist.linear == 0.0
    assert twist.angular == 0.0


def test_find_lookahead_point_intersects_circle():
    path = [(i * 1.0, 0.0) for i in range(5)]
    # Circle radius 1.0 centered at (0, 0) meets y=0 at x=1.0.
    goal = find_lookahead_point(path, 0.0, 0.0, 1.0)
    assert goal is not None
    assert goal[0] == pytest.approx(1.0, abs=1e-6)
    assert goal[1] == pytest.approx(0.0, abs=1e-6)


def test_find_lookahead_point_falls_back_to_end():
    path = [(0.0, 0.0), (1.0, 0.0)]
    goal = find_lookahead_point(path, 0.0, 10.0, 0.5)
    assert goal == (1.0, 0.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lookahead_m": 0.0},
        {"lookahead_m": -1.0},
        {"max_linear_mps": 0.0},
        {"max_angular_radps": 0.0},
        {"min_turn_radius_m": 0.0},
    ],
)
def test_invalid_params_raise(kwargs):
    with pytest.raises(ValueError):
        PurePursuitController(**kwargs)
