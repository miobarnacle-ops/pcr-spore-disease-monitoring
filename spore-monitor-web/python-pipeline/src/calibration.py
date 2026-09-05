"""Coordinate-wise grid-search calibration of (deposition, uv-kill, re-emission).

Synthetic truth is generated with the simulator at the default parameters;
lognormal noise (sigma=0.15) is added at 20 downwind observation points.
The three fate parameters are fit by coordinate-wise grid search (3 params x
3 passes x 15 points) minimizing log10-space SSE at the observation points.
"""
from __future__ import annotations

import numpy as np

from .schemas import DEFAULT_FATE, FateParamsArtifact, FitReport, SporeFateParams
from .simulator import FateSubset, run_eulerian

GRID_DX = 250.0
Q = 1e4  # spores/s
WIND_U = 2.0  # m/s
HORIZONS = [24, 48, 72, 96]
FLOOR = 1e-6
BOUNDS = {"dep": (0.001, 0.02), "uv": (0.0, 0.02), "re": (0.0, 0.05)}
N_GRID = 15
N_PASSES = 3


def run_calibration() -> tuple[FateParamsArtifact, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    true = FateSubset(
        DEFAULT_FATE.deposition_velocity,
        DEFAULT_FATE.uv_kill_coeff,
        DEFAULT_FATE.re_emission_base,
    )

    xs = rng.uniform(1000.0, 8000.0, 20)
    ys = rng.uniform(500.0, 2500.0, 20)
    obs_locs = [(int(y / GRID_DX), int(x / GRID_DX)) for x, y in zip(xs, ys)]

    truth = run_eulerian(true, Q, WIND_U, HORIZONS)
    observed: list[tuple[int, int, int, float]] = []
    for h in HORIZONS:
        for r, c in obs_locs:
            val = truth[h][r, c] * float(np.exp(rng.normal(0.0, 0.15)))
            observed.append((h, r, c, val))
    observed_log10 = np.log10(np.maximum(np.array([o[3] for o in observed]), FLOOR))

    def objective(subset: FateSubset) -> float:
        fields = run_eulerian(subset, Q, WIND_U, HORIZONS)
        sse = 0.0
        for h, r, c, val in observed:
            pred = max(fields[h][r, c], FLOOR)
            sse += (np.log10(pred) - np.log10(max(val, FLOOR))) ** 2
        return sse

    grids = {key: np.linspace(lo, hi, N_GRID) for key, (lo, hi) in BOUNDS.items()}
    best = {"dep": true.deposition_velocity, "uv": true.uv_kill, "re": true.re_emission}

    def to_subset(vals: dict[str, float]) -> FateSubset:
        return FateSubset(
            deposition_velocity=vals["dep"],
            uv_kill=vals["uv"],
            re_emission=vals["re"],
        )

    best_score = objective(to_subset(best))

    for _ in range(N_PASSES):
        for key in ("dep", "uv", "re"):
            for candidate in grids[key]:
                trial = dict(best)
                trial[key] = candidate
                score = objective(to_subset(trial))
                if score < best_score:
                    best, best_score = trial, score

    fitted = to_subset(best)
    pred_fields = run_eulerian(fitted, Q, WIND_U, HORIZONS)
    predicted_log10 = np.log10(
        np.maximum(np.array([pred_fields[h][r][c] for h, r, c, _ in observed]), FLOOR)
    )

    n = len(observed)
    rmse = float(np.sqrt(best_score / n))
    bias = float(np.mean(predicted_log10 - observed_log10))
    relative_errors = {
        "depositionVelocity": abs(best["dep"] - true.deposition_velocity) / true.deposition_velocity,
        "uvKillCoeff": abs(best["uv"] - true.uv_kill) / true.uv_kill,
        "reEmissionBase": abs(best["re"] - true.re_emission) / true.re_emission,
    }

    calibrated = SporeFateParams(
        deposition_velocity=float(best["dep"]),
        uv_kill_coeff=float(best["uv"]),
        re_emission_base=float(best["re"]),
        citation=DEFAULT_FATE.citation,
    )
    artifact = FateParamsArtifact(
        defaults=DEFAULT_FATE,
        calibrated=calibrated,
        fit_report=FitReport(
            rmse_log10=rmse,
            bias_log10=bias,
            n_observations=n,
            relative_errors=relative_errors,
        ),
    )
    return artifact, observed_log10, predicted_log10
