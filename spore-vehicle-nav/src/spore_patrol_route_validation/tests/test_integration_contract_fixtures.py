"""Vehicle-side verification of shared Web/vehicle integration fixtures."""

import json
from pathlib import Path

import pytest

from spore_patrol_route_validation.mission_contract import is_fresh, parse_mission_status


FIXTURES = Path(__file__).resolve().parents[4] / "spore-monitor-web" / "tests" / "fixtures" / "contracts"


def read_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_shared_normal_mission_fixture_is_accepted():
    status = parse_mission_status(read_fixture("mission-status-valid.json"))
    assert status.state == "running"
    assert status.sample_id == "R1-P2"
    assert is_fresh(status.timestamp_ms, status.timestamp_ms + 500, 1000)


def test_unknown_state_and_missing_id_are_rejected():
    with pytest.raises(ValueError, match="unsupported state"):
        parse_mission_status(read_fixture("mission-status-unknown-state.json"))
    payload = read_fixture("mission-status-valid.json")
    del payload["mission_id"]
    with pytest.raises(ValueError, match="mission_id"):
        parse_mission_status(payload)
    assert not is_fresh(1000, 1600, 500)
