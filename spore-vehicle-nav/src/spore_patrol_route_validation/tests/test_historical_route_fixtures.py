"""Read-only regression checks for archived vehicle trial routes.

The files in ``results/`` are evidence inputs, never rewritten by this test.
"""

from pathlib import Path

from spore_patrol_route_validation.route_model import load_route


RESULTS = Path(__file__).resolve().parents[3] / "results"


def test_archived_sample_and_full_trial_routes_remain_parseable():
    sample = load_route(str(RESULTS / "sample_route.json"))
    full_trial = load_route(str(RESULTS / "trial6_full_route.json"))
    assert len(sample.path) == 3
    assert full_trial.path[-1].sample_id == "S4"
