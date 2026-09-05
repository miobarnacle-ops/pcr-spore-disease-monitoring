"""Pure validation for the Web/vehicle mission-status contract.

The ROS node can keep publishing its existing native status payload while an
adapter maps it to this contract for rosbridge.  Keeping this module ROS-free
lets both repositories validate shared offline fixtures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional


CONTRACT_VERSION = "1.0"
VALID_SOURCE_MODES = frozenset({"mock", "replay", "rosbridge"})
VALID_MISSION_STATES = frozenset(
    {
        "idle", "loaded", "running", "approaching", "sampling", "paused",
        "returning", "finished", "failed", "cancelled",
    }
)


@dataclass(frozen=True)
class MissionStatus:
    source_mode: str
    timestamp_ms: float
    field_id: str
    mission_id: str
    route_id: str
    state: str
    current_waypoint_index: Optional[int]
    current_waypoint_seq: Optional[int]
    sample_id: Optional[str]
    progress_pct: float
    eta_s: Optional[float]
    obstacle_stop: bool
    fault_code: Optional[str]
    message: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _nonempty_string(value: Any, name: str, *, nullable: bool = False) -> Optional[str]:
    if nullable and value is None:
        return None
    _require(isinstance(value, str) and bool(value), f"{name} must be a non-empty string")
    return value


def _finite(value: Any, name: str, *, nullable: bool = False) -> Optional[float]:
    if nullable and value is None:
        return None
    _require(not isinstance(value, bool) and isinstance(value, (int, float)), f"{name} must be a number")
    number = float(value)
    _require(math.isfinite(number), f"{name} must be finite")
    return number


def _nonnegative_integer(value: Any, name: str, *, nullable: bool = False) -> Optional[int]:
    number = _finite(value, name, nullable=nullable)
    if number is None:
        return None
    _require(number.is_integer() and number >= 0, f"{name} must be a non-negative integer")
    return int(number)


def parse_mission_status(data: Mapping[str, Any]) -> MissionStatus:
    """Validate a canonical ``mission_status`` fixture or adapter payload."""
    _require(isinstance(data, Mapping), "mission status must be an object")
    _require(data.get("contract_version") == CONTRACT_VERSION, "unsupported contract_version")
    _require(data.get("kind") == "mission_status", "kind must be mission_status")
    source_mode = _nonempty_string(data.get("source_mode"), "source_mode")
    _require(source_mode in VALID_SOURCE_MODES, "unsupported source_mode")
    state = _nonempty_string(data.get("state"), "state")
    _require(state in VALID_MISSION_STATES, "unsupported state")
    progress_pct = _finite(data.get("progress_pct"), "progress_pct")
    _require(0.0 <= progress_pct <= 100.0, "progress_pct must be between 0 and 100")
    obstacle_stop = data.get("obstacle_stop")
    _require(isinstance(obstacle_stop, bool), "obstacle_stop must be a boolean")
    return MissionStatus(
        source_mode=source_mode,
        timestamp_ms=_finite(data.get("timestamp_ms"), "timestamp_ms"),
        field_id=_nonempty_string(data.get("field_id"), "field_id"),
        mission_id=_nonempty_string(data.get("mission_id"), "mission_id"),
        route_id=_nonempty_string(data.get("route_id"), "route_id"),
        state=state,
        current_waypoint_index=_nonnegative_integer(data.get("current_waypoint_index"), "current_waypoint_index", nullable=True),
        current_waypoint_seq=_nonnegative_integer(data.get("current_waypoint_seq"), "current_waypoint_seq", nullable=True),
        sample_id=_nonempty_string(data.get("sample_id"), "sample_id", nullable=True),
        progress_pct=progress_pct,
        eta_s=_finite(data.get("eta_s"), "eta_s", nullable=True),
        obstacle_stop=obstacle_stop,
        fault_code=_nonempty_string(data.get("fault_code"), "fault_code", nullable=True),
        message=_nonempty_string(data.get("message"), "message"),
    )


def is_fresh(timestamp_ms: float, now_ms: float, max_age_ms: float) -> bool:
    """Freshness policy shared with the Web validator; future timestamps fail."""
    return all(math.isfinite(value) for value in (timestamp_ms, now_ms, max_age_ms)) and timestamp_ms <= now_ms and 0.0 <= now_ms - timestamp_ms <= max_age_ms


__all__ = ["CONTRACT_VERSION", "MissionStatus", "parse_mission_status", "is_fresh"]
