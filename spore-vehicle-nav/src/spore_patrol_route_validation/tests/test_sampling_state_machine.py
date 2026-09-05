"""Tests for sampling_state_machine.py: transitions, dwell, events."""

import pytest

from spore_patrol_route_validation.route_model import Route, Waypoint
from spore_patrol_route_validation.sampling_state_machine import (
    MissionState,
    SamplingStateMachine,
)


def make_waypoint(seq=0, wtype="transit", sample_id=None):
    return Waypoint(
        seq=seq,
        x_m=float(seq),
        y_m=0.0,
        yaw_rad=None,
        type=wtype,
        round=0,
        sample_id=sample_id,
        speed_limit_mps=0.12,
        tolerance_m=0.2,
    )


def make_route(waypoints):
    return Route(
        schema_version="1.0",
        frame_id="field",
        coordinate_type="local_enu",
        unit="m",
        field_polygon_m=[],
        sampling_points=[],
        path=waypoints,
    )


def step(fsm, now, n=1):
    for _ in range(n):
        fsm.advance(now)


def test_initial_state_is_idle():
    fsm = SamplingStateMachine()
    assert fsm.state is MissionState.IDLE


def test_load_and_start():
    fsm = SamplingStateMachine()
    route = make_route([make_waypoint(0, "start")])
    fsm.load_route(route)
    assert fsm.state is MissionState.TASK_LOADED
    fsm.start()
    assert fsm.state is MissionState.NAVIGATING


def test_full_sampling_sequence():
    fsm = SamplingStateMachine(sampling_duration_s=2.0)
    route = make_route(
        [
            make_waypoint(0, "start"),
            make_waypoint(1, "sampling", sample_id="R1-P1"),
            make_waypoint(2, "return"),
        ]
    )

    fsm.load_route(route)
    fsm.start()
    assert fsm.state is MissionState.NAVIGATING

    # Arrive at the start waypoint (not sampling).
    fsm.arrive_at_waypoint()
    assert fsm.state is MissionState.ARRIVED
    fsm.advance(now=0.0)
    assert fsm.state is MissionState.SETTLING
    fsm.advance(now=0.0)
    assert fsm.state is MissionState.NAVIGATING
    assert fsm.current_waypoint_index == 1

    # Arrive at the sampling waypoint: settle -> sample-requested -> sampling.
    fsm.arrive_at_waypoint()
    fsm.advance(now=0.0)  # ARRIVED -> SETTLING
    assert fsm.state is MissionState.SETTLING
    fsm.advance(now=0.0)  # SETTLING -> SAMPLE_REQUESTED
    assert fsm.state is MissionState.SAMPLE_REQUESTED
    fsm.advance(now=0.0)  # SAMPLE_REQUESTED -> SAMPLING
    assert fsm.state is MissionState.SAMPLING

    # Still sampling before the 2 s dwell elapses.
    fsm.advance(now=1.0)
    assert fsm.state is MissionState.SAMPLING

    # Dwell elapses at t=2 s.
    fsm.advance(now=2.0)
    assert fsm.state is MissionState.SAMPLE_FINISHED
    fsm.advance(now=2.0)  # SAMPLE_FINISHED -> NAVIGATING
    assert fsm.state is MissionState.NAVIGATING
    assert fsm.current_waypoint_index == 2

    # Arrive at the final (return) waypoint -> task finished.
    fsm.arrive_at_waypoint()
    fsm.advance(now=3.0)  # ARRIVED -> SETTLING
    fsm.advance(now=3.0)  # SETTLING -> TASK_FINISHED (not sampling)
    assert fsm.state is MissionState.TASK_FINISHED


def test_sampling_dwell_is_two_seconds():
    fsm = SamplingStateMachine(sampling_duration_s=2.0)
    route = make_route([make_waypoint(0, "sampling", sample_id="S1")])
    fsm.load_route(route)
    fsm.start()
    fsm.arrive_at_waypoint()
    step(fsm, now=10.0, n=3)  # ARRIVED -> SETTLING -> SAMPLE_REQUESTED -> SAMPLING
    assert fsm.state is MissionState.SAMPLING

    fsm.advance(now=11.999)
    assert fsm.state is MissionState.SAMPLING
    fsm.advance(now=12.0)
    assert fsm.state is MissionState.SAMPLE_FINISHED


def test_sample_events_emitted():
    fsm = SamplingStateMachine(sampling_duration_s=2.0)
    route = make_route([make_waypoint(0, "sampling", sample_id="R2-P3")])
    fsm.load_route(route)
    fsm.start()
    fsm.arrive_at_waypoint()

    fsm.consume_events()  # drop state_changed events so far
    kinds = []
    for _ in range(3):
        fsm.advance(now=0.0)
        kinds += [e.kind for e in fsm.consume_events()]
    assert "sample_requested" in kinds

    fsm.advance(now=2.0)
    kinds = [e.kind for e in fsm.consume_events()]
    assert "sample_finished" in kinds


def test_waypoint_arrived_event():
    fsm = SamplingStateMachine()
    route = make_route([make_waypoint(0, "sampling", sample_id="A")])
    fsm.load_route(route)
    fsm.start()
    fsm.arrive_at_waypoint()
    kinds = [e.kind for e in fsm.consume_events()]
    assert "waypoint_arrived" in kinds


def test_task_finished_event_and_terminal():
    fsm = SamplingStateMachine(sampling_duration_s=0.0)
    route = make_route([make_waypoint(0, "return")])
    fsm.load_route(route)
    fsm.start()
    fsm.arrive_at_waypoint()
    step(fsm, now=0.0, n=3)
    assert fsm.state is MissionState.TASK_FINISHED
    events = fsm.consume_events()
    assert any(e.kind == "task_finished" for e in events)
    assert fsm.is_finished
    assert fsm.is_terminal


def test_stop_from_navigating():
    fsm = SamplingStateMachine()
    route = make_route([make_waypoint(0, "transit")])
    fsm.load_route(route)
    fsm.start()
    fsm.stop()
    assert fsm.state is MissionState.STOPPED
    assert fsm.is_terminal


def test_pause_resume_return_and_cancel_are_explicit_and_safe():
    fsm = SamplingStateMachine()
    route = make_route([make_waypoint(0, "start"), make_waypoint(1, "return")])
    fsm.load_route(route)
    fsm.start()
    fsm.pause()
    assert fsm.state is MissionState.PAUSED
    fsm.resume()
    assert fsm.state is MissionState.NAVIGATING
    fsm.return_home()
    assert fsm.state is MissionState.RETURNING
    assert fsm.current_waypoint_index == 1
    fsm.cancel()
    assert fsm.state is MissionState.STOPPED
    assert any(event.kind == "cancelled" for event in fsm.consume_events())


def test_fault_from_idle():
    fsm = SamplingStateMachine()
    fsm.fault("something broke")
    assert fsm.state is MissionState.FAULT
    assert fsm.is_terminal


def test_illegal_transitions_raise():
    fsm = SamplingStateMachine()
    with pytest.raises(RuntimeError):
        fsm.start()  # not TASK_LOADED
    route = make_route([make_waypoint(0, "transit")])
    fsm.load_route(route)
    with pytest.raises(RuntimeError):
        fsm.arrive_at_waypoint()  # not NAVIGATING
    with pytest.raises(RuntimeError):
        fsm.load_route(route)  # already loaded


def test_consume_events_drains():
    fsm = SamplingStateMachine()
    fsm.fault("x")
    assert len(fsm.consume_events()) > 0
    assert fsm.consume_events() == []


def test_zero_dwell_still_visits_sampling_states():
    fsm = SamplingStateMachine(sampling_duration_s=0.0)
    route = make_route([make_waypoint(0, "sampling", sample_id="Z")])
    fsm.load_route(route)
    fsm.start()
    fsm.arrive_at_waypoint()
    step(fsm, now=0.0, n=5)
    assert fsm.state is MissionState.TASK_FINISHED


def test_current_waypoint_returns_waypoint():
    fsm = SamplingStateMachine()
    route = make_route(
        [make_waypoint(0, "start"), make_waypoint(1, "sampling", sample_id="X")]
    )
    fsm.load_route(route)
    assert fsm.current_waypoint().seq == 0
    fsm.start()
    fsm.arrive_at_waypoint()
    step(fsm, now=0.0, n=2)
    assert fsm.current_waypoint_index == 1
    assert fsm.current_waypoint().sample_id == "X"
