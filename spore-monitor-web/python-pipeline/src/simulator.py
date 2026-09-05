"""Deterministic 2-D Eulerian advection-diffusion spore dispersion solver.

State: C (spores/m^2 surface layer) and D (deposited spores/m^2).
Solves, per second-step dt:
  dC/dt = -u*dC/dx + kappa*Lap(C) - (k_uv + k_dep)*C + k_re*D + Q_source
  dD/dt = k_dep*C - k_re*D
with k_uv = uv_kill/3600, k_dep = deposition_velocity/50 (50 m mixing height),
k_re = re_emission/3600, and Q_source = Q/dx^2 injected into the source cell.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FateSubset:
    """The three fate parameters that govern airborne transport losses."""

    deposition_velocity: float
    uv_kill: float
    re_emission: float


def run_eulerian(
    fate: FateSubset,
    q: float,
    wind_u: float,
    horizons_hours: list[int],
    *,
    dx: float = 250.0,
    nx: int = 60,
    ny: int = 30,
    dt: float = 60.0,
) -> dict[int, np.ndarray]:
    """Return {horizon_hour: concentration field (ny, nx) spores/m^2}."""
    kappa = 10.0
    mix_h = 50.0

    k_uv = fate.uv_kill / 3600.0
    k_dep = fate.deposition_velocity / mix_h
    k_re = fate.re_emission / 3600.0

    C = np.zeros((ny, nx))
    D = np.zeros((ny, nx))

    src_i, src_j = ny // 2, 0
    src_rate = q / (dx * dx)

    horizons = sorted(horizons_hours)
    target_steps = {int(round(h * 3600.0 / dt)) for h in horizons}
    n_steps = int(round(max(horizons) * 3600.0 / dt))

    results: dict[int, np.ndarray] = {}
    for step in range(1, n_steps + 1):
        # Upwind advection (u > 0 along +x); zero (clean-air) inflow at left edge.
        c_left = np.zeros_like(C)
        c_left[:, 1:] = C[:, :-1]
        adv = (C - c_left) / dx

        # Explicit 5-point diffusion with open (zero) boundaries via np.pad.
        cp = np.pad(C, 1, mode="constant")
        lap = (cp[0:-2, 1:-1] + cp[2:, 1:-1] + cp[1:-1, 0:-2] + cp[1:-1, 2:] - 4.0 * C) / (dx * dx)

        dC = -wind_u * adv + kappa * lap - (k_uv + k_dep) * C + k_re * D
        dD = k_dep * C - k_re * D

        C = C + dt * dC
        D = D + dt * dD
        C[src_i, src_j] += src_rate * dt

        if step in target_steps:
            results[int(round(step * dt / 3600.0))] = C.copy()

    return results
