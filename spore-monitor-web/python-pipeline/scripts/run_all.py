"""End-to-end orchestration: calibrate -> A/B -> write JSON artifacts -> figures.

Deterministic: every RNG is seeded with 42. JSON artifacts are validated by
round-tripping through their pydantic models before being written to disk.
"""
from __future__ import annotations

import json
from pathlib import Path

from src import figures
from src.ab_experiment import run_ab
from src.calibration import run_calibration
from src.schemas import (
    ABResultsArtifact,
    FateParamsArtifact,
    InfectionWindowsArtifact,
    INFECTION_WINDOWS,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def _write_json(name: str, model_cls, artifact) -> Path:
    data = artifact.model_dump(by_alias=True, exclude_none=True)
    model_cls.model_validate(data)  # round-trip validation before write
    out = ARTIFACTS / name
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    fate_artifact, obs_log10, pred_log10 = run_calibration()
    _write_json("fate_params.json", FateParamsArtifact, fate_artifact)

    iw_artifact = InfectionWindowsArtifact(diseases=list(INFECTION_WINDOWS))
    _write_json("infection_windows.json", InfectionWindowsArtifact, iw_artifact)

    ab_output = run_ab()
    _write_json("ab_results.json", ABResultsArtifact, ab_output.artifact)

    figures.plot_ab_heatmaps(ab_output.horizon120, ARTIFACTS / "ab_heatmaps.png")
    figures.plot_calibration_scatter(obs_log10, pred_log10, ARTIFACTS / "calibration_scatter.png")
    figures.plot_infection_bars(list(INFECTION_WINDOWS), ARTIFACTS / "infection_bars.png")

    print("wrote artifacts:")
    for p in sorted(ARTIFACTS.iterdir()):
        print(f"  {p.name}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
