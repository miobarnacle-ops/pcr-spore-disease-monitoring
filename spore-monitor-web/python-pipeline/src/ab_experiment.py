"""A/B experiment: fine-grid truth vs coarse Eulerian vs closed-form Gaussian plume.

TRUTH   = simulator on a fine grid (dx=125 m) at the default parameters.
EULERIAN = simulator on the coarse grid (dx=250 m) at the default parameters.
GAUSSIAN = closed-form steady 2-D plume
           C(x,y) = Q/(2*pi*u*sig_y) * exp(-y^2/(2*sig_y^2)) * exp(-lam*x/u)
           with sig_y^2 = 2*kappa*x/u and lam = k_uv + k_dep.
30 seeded observation points are sampled at horizons [72,120,168] h; per horizon
the log10 RMSE/bias of gaussian-vs-truth and eulerian-vs-truth are reported.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .schemas import ABHorizonResult, ABModelMetrics, ABResultsArtifact, DEFAULT_FATE
from .simulator import FateSubset, run_eulerian

Q = 1e4  # spores/s
WIND_U = 2.0  # m/s
HORIZONS = [72, 120, 168]
FLOOR = 1e-6
KAPPA = 10.0
MIX_H = 50.0
COARSE_DX = 250.0
FINE_DX = 125.0
N_OBS = 30
SEED = 42


@dataclass
class FieldSnapshot:
    name: str
    field: np.ndarray
    x: np.ndarray
    y: np.ndarray


@dataclass
class ABOutput:
    artifact: ABResultsArtifact
    horizon120: list[FieldSnapshot] = field(default_factory=list)


def _lam() -> float:
    k_uv = DEFAULT_FATE.uv_kill_coeff / 3600.0
    k_dep = DEFAULT_FATE.deposition_velocity / MIX_H
    return k_uv + k_dep


def _gaussian_at(x: float, y: float, centerline: float) -> float:
    if x <= 0.0:
        return 0.0
    sig_y = np.sqrt(2.0 * KAPPA * x / WIND_U)
    dy = y - centerline
    return (
        Q / (2.0 * np.pi * WIND_U * sig_y)
        * np.exp(-(dy**2) / (2.0 * sig_y**2))
        * np.exp(-_lam() * x / WIND_U)
    )


def _gaussian_field(dx: float, nx: int, ny: int, centerline: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = (np.arange(nx) + 0.5) * dx
    y = (np.arange(ny) + 0.5) * dx
    X, Y = np.meshgrid(x, y)
    sig_y = np.sqrt(np.maximum(2.0 * KAPPA * X / WIND_U, 1e-12))
    dy = Y - centerline
    C = (
        Q / (2.0 * np.pi * WIND_U * sig_y)
        * np.exp(-(dy**2) / (2.0 * sig_y**2))
        * np.exp(-_lam() * X / WIND_U)
    )
    C[X <= 0.0] = 0.0
    return C, x, y


def _sample(field: np.ndarray, dx: float, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    cols = np.clip((xs / dx).astype(int), 0, field.shape[1] - 1)
    rows = np.clip((ys / dx).astype(int), 0, field.shape[0] - 1)
    return field[rows, cols]


def _metrics(pred_log10: np.ndarray, truth_log10: np.ndarray) -> ABModelMetrics:
    diff = pred_log10 - truth_log10
    rmse = float(np.sqrt(np.mean(diff**2)))
    bias = float(np.mean(diff))
    return ABModelMetrics(rmse_log10=rmse, bias_log10=bias)


def run_ab() -> ABOutput:
    rng = np.random.default_rng(SEED)
    fate = FateSubset(
        DEFAULT_FATE.deposition_velocity,
        DEFAULT_FATE.uv_kill_coeff,
        DEFAULT_FATE.re_emission_base,
    )

    centerline = (30 * COARSE_DX) / 2.0  # 3750 m, shared by both grids

    truth = run_eulerian(fate, Q, WIND_U, HORIZONS, dx=FINE_DX, nx=120, ny=60)
    euler = run_eulerian(fate, Q, WIND_U, HORIZONS, dx=COARSE_DX, nx=60, ny=30)

    xs = rng.uniform(2000.0, 12000.0, N_OBS)
    ys = rng.uniform(1500.0, 6000.0, N_OBS)
    gauss_vals = np.array([_gaussian_at(x, y, centerline) for x, y in zip(xs, ys)])

    horizons: list[ABHorizonResult] = []
    for h in HORIZONS:
        truth_log10 = np.log10(np.maximum(_sample(truth[h], FINE_DX, xs, ys), FLOOR))
        euler_log10 = np.log10(np.maximum(_sample(euler[h], COARSE_DX, xs, ys), FLOOR))
        gauss_log10 = np.log10(np.maximum(gauss_vals, FLOOR))
        horizons.append(
            ABHorizonResult(
                horizon_hours=h,
                n_observations=N_OBS,
                gaussian=_metrics(gauss_log10, truth_log10),
                eulerian=_metrics(euler_log10, truth_log10),
            )
        )

    artifact = ABResultsArtifact(
        horizons=horizons,
        config={
            "dxTruth": int(FINE_DX),
            "dxEuler": int(COARSE_DX),
            "q": float(Q),
            "windU": float(WIND_U),
            "kappa": float(KAPPA),
            "seed": int(SEED),
        },
        notes=(
            "Fine-grid Eulerian solution (dx=125 m) is treated as ground truth; "
            "coarse Eulerian (dx=250 m) and the closed-form Gaussian plume are "
            "benchmarked against it in log10 space."
        ),
    )

    g_field, g_x, g_y = _gaussian_field(COARSE_DX, 60, 30, centerline)
    e_x = (np.arange(60) + 0.5) * COARSE_DX
    e_y = (np.arange(30) + 0.5) * COARSE_DX
    t_x = (np.arange(120) + 0.5) * FINE_DX
    t_y = (np.arange(60) + 0.5) * FINE_DX
    horizon120 = [
        FieldSnapshot("Truth (fine grid)", truth[120], t_x, t_y),
        FieldSnapshot("Eulerian (coarse grid)", euler[120], e_x, e_y),
        FieldSnapshot("Gaussian plume (closed-form)", g_field, g_x, g_y),
    ]
    return ABOutput(artifact=artifact, horizon120=horizon120)
