from spore_patrol_route_validation.safety_decision import decide_motion_safety
from spore_patrol_route_validation.sampling_state_machine import MissionState


def safety(**overrides):
    values = dict(
        state=MissionState.NAVIGATING, pose_age_s=0.1, scan_age_s=0.1,
        min_forward_range_m=2.0, odom_timeout_s=0.5, scan_timeout_s=0.5,
        obstacle_threshold_m=0.5,
    )
    values.update(overrides)
    return decide_motion_safety(**values)


def test_safety_allows_only_fresh_motion_inputs():
    assert safety().allow_motion
    assert safety(state=MissionState.RETURNING).allow_motion
    assert safety(state=MissionState.PAUSED).reason == "MISSION_NOT_DRIVING"


def test_safety_fails_closed_for_missing_or_stale_odom_and_scan():
    assert safety(pose_age_s=None).reason == "ODOM_STALE"
    assert safety(pose_age_s=0.51).reason == "ODOM_STALE"
    assert safety(scan_age_s=None).reason == "SCAN_STALE"
    assert safety(scan_age_s=0.51).reason == "SCAN_STALE"


def test_safety_rejects_obstacle_and_unknown_state_but_allows_explicit_disabled_scan_gate():
    assert safety(min_forward_range_m=0.49).reason == "OBSTACLE_STOP"
    assert safety(state="FUTURE_STATE").reason == "UNKNOWN_MISSION_STATE"
    assert safety(scan_age_s=None, obstacle_stop_enabled=False).allow_motion
