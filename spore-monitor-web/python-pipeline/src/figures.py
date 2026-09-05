"""Matplotlib (Agg) figure generation. English labels throughout."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_ab_heatmaps(panels, out_path) -> None:
    """Three log10-normalized concentration heatmaps (truth / Eulerian / Gaussian)."""
    pos_min = min(f[f > 0].min() for f in (p.field for p in panels))
    pos_max = max(f.max() for f in (p.field for p in panels))

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True, constrained_layout=True)
    for ax, p in zip(axes, panels):
        extent = [p.x[0], p.x[-1], p.y[0], p.y[-1]]
        im = ax.imshow(
            p.field,
            origin="lower",
            aspect="auto",
            extent=extent,
            norm=LogNorm(vmin=pos_min, vmax=pos_max),
            cmap="viridis",
        )
        ax.set_title(p.name, fontsize=10)
        ax.set_xlabel("x (m)")
    axes[0].set_ylabel("y (m)")
    fig.colorbar(im, ax=axes, shrink=0.6, label=r"concentration (spores/m$^2$, log10)")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_calibration_scatter(observed_log10, predicted_log10, out_path) -> None:
    """Predicted-vs-observed log10 scatter with y=x line + residual histogram."""
    residuals = predicted_log10 - observed_log10
    lo = min(observed_log10.min(), predicted_log10.min())
    hi = max(observed_log10.max(), predicted_log10.max())

    fig, (ax_s, ax_r) = plt.subplots(1, 2, figsize=(11, 4.5), gridspec_kw={"width_ratios": [3, 2]})
    ax_s.scatter(observed_log10, predicted_log10, s=24, alpha=0.7, edgecolors="k", linewidths=0.4)
    ax_s.plot([lo, hi], [lo, hi], "r--", lw=1, label="y = x")
    ax_s.set_xlabel("observed log10 concentration")
    ax_s.set_ylabel("predicted log10 concentration")
    ax_s.set_title("Calibration fit (best-fit params)")
    ax_s.legend()

    ax_r.hist(residuals, bins=20, color="steelblue", edgecolor="k", linewidth=0.4)
    ax_r.axvline(0.0, color="r", lw=1)
    ax_r.set_xlabel("residual (log10)")
    ax_r.set_ylabel("count")
    ax_r.set_title("Residual histogram")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_infection_bars(diseases, out_path) -> None:
    """Per-disease heuristic favorability index bar chart.

    Favorability index = weighted normalized sum of three components (each
    min-max normalized to [0,1] across diseases):
      thermal breadth  = temp_max - temp_min        (weight 0.4)
      moisture ease    = 100 - rh_threshold         (weight 0.3)
      spread speed     = 1 / latent_period_days     (weight 0.3)
    """
    thermal = np.array([d.temp_max - d.temp_min for d in diseases])
    moisture = np.array([100.0 - d.rh_threshold for d in diseases])
    speed = np.array([1.0 / d.latent_period_days for d in diseases])

    def norm01(v):
        return (v - v.min()) / (v.max() - v.min()) if v.max() > v.min() else np.zeros_like(v)

    index = 0.4 * norm01(thermal) + 0.3 * norm01(moisture) + 0.3 * norm01(speed)
    labels = [d.disease_name for d in diseases]
    order = np.argsort(index)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh([labels[i] for i in order], index[order], color="seagreen", edgecolor="k", linewidth=0.4)
    ax.set_xlabel("Favorability index (heuristic)")
    ax.set_title("Infection favorability by disease")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
