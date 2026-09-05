"""Pure motion safety gate shared by the ROS control loop and offline tests.

The gate is deliberately fail-safe: absent/stale odometry or scan input while
the mission is moving produces a zero-velocity decision.  It does not replace
the vehicle's physical emergency-stop circuit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from .sampling_state_machine import MissionState


@dataclass(frozen=True)
class SafetyDecision:
    allow_motion: bool
    reason: str


def decide_motion_safety(
    state: Union[MissionState, str],
    pose_age_s: Optional[float],
    scan_age_s: Optional[float],
    min_forward_range_m: Optional[float],
    *,
    odom_timeout_s: float,
    scan_timeout_s: float,
    obstacle_threshold_m: float,
    obstacle_stop_enabled: bool = True,
) -> SafetyDecision:
    """Return a deterministic motion permission for one control tick."""
    try:
        mission_state = state if isinstance(state, MissionState) else MissionState(state)
    except ValueError:
        return SafetyDecision(False, "UNKNOWN_MISSION_STATE")
    if mission_state not in (MissionState.NAVIGATING, MissionState.RETURNING):
        return SafetyDecision(False, "MISSION_NOT_DRIVING")
    if pose_age_s is None or pose_age_s < 0.0 or pose_age_s > odom_timeout_s:
        return SafetyDecision(False, "ODOM_STALE")
    if not obstacle_stop_enabled:
        return SafetyDecision(True, "OK")
    if scan_age_s is None or scan_age_s < 0.0 or scan_age_s > scan_timeout_s:
        return SafetyDecision(False, "SCAN_STALE")
    if min_forward_range_m is not None and min_forward_range_m < obstacle_threshold_m:
        return SafetyDecision(False, "OBSTACLE_STOP")
    return SafetyDecision(True, "OK")


__all__ = ["SafetyDecision", "decide_motion_safety"]
