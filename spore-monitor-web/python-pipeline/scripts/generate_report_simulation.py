"""Generate a transparent synthetic benchmark for the final report.

The synthetic reference is an independent time-integrated Gaussian-puff field
with time-varying wind, source strength, UV/deposition loss and optional rain
scavenging.  It is not field data.  A coarse time-stepped Eulerian solver is
used as an offline analogue of the reworked dispersion core, while a single
steady Gaussian plume represents the traditional baseline.

Both candidate models receive the same weather/source inputs and one scalar
calibration fitted only on training sensors. Metrics are evaluated on held-out
sensors. Every random operation is seeded for reproducibility.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "report-comparison-v1"
SEED = 20260906

X_MIN, X_MAX = -2_000.0, 18_000.0
Y_MIN, Y_MAX = -7_000.0, 7_000.0
DX = 250.0
DT = 60.0
DURATION_HOURS = 6.0
SOURCE_X, SOURCE_Y = 0.0, 0.0
LOG_FLOOR = 1e-6


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    name_zh: str
    description: str


SCENARIOS = [
    Scenario(
        "S1_steady_dry",
        "稳定风场（对照）",
        "近似稳定的东向输送、无降雨，用于检验简单条件下高斯烟羽是否仍具竞争力。",
    ),
    Scenario(
        "S2_wind_shift",
        "风向转折",
        "六小时内风向由偏南转为偏北，形成弯折和叠加的传播带。",
    ),
    Scenario(
        "S3_rain_front",
        "风向变化与阵雨清除",
        "风向缓慢转折，中段出现约一小时阵雨，同时释放强度具有时段变化。",
    ),
]


def _timeline(scenario_id: str, times: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return wind speed, mathematical direction, rainfall and source rate."""
    hours = times / 3600.0
    if scenario_id == "S1_steady_dry":
        speed = 1.75 + 0.12 * np.sin(2 * np.pi * hours / 3.0)
        direction = 2.5 * np.sin(2 * np.pi * hours / 4.0)
        rain = np.zeros_like(hours)
        source = 8_000.0 * (1.0 + 0.12 * np.sin(2 * np.pi * hours / 2.5))
    elif scenario_id == "S2_wind_shift":
        speed = 1.65 + 0.22 * np.sin(2 * np.pi * hours / 2.8)
        transition = 1.0 / (1.0 + np.exp(-(hours - 3.0) / 0.42))
        direction = -28.0 + 58.0 * transition + 4.0 * np.sin(2 * np.pi * hours / 1.8)
        rain = np.zeros_like(hours)
        source = 7_500.0 * (1.0 + 0.18 * np.sin(2 * np.pi * (hours - 0.4) / 3.0))
    elif scenario_id == "S3_rain_front":
        speed = 1.85 + 0.28 * np.sin(2 * np.pi * hours / 3.5)
        transition = 1.0 / (1.0 + np.exp(-(hours - 3.2) / 0.55))
        direction = -15.0 + 38.0 * transition + 5.0 * np.sin(2 * np.pi * hours / 2.2)
        rain = np.where((hours >= 2.6) & (hours <= 3.7), 5.5 * np.sin(np.pi * (hours - 2.6) / 1.1), 0.0)
        morning_pulse = 0.55 + 0.85 * np.exp(-((hours - 1.5) / 0.85) ** 2)
        source = 8_200.0 * morning_pulse
    else:
        raise ValueError(f"unknown scenario: {scenario_id}")
    return speed, np.deg2rad(direction), rain, source


def _loss_rate(rain_mm_h: np.ndarray, *, truth: bool) -> np.ndarray:
    base_uv_and_deposition = 1.05e-5 if truth else 1.15e-5
    rain_coefficient = 3.0e-5 if truth else 2.7e-5
    return base_uv_and_deposition + rain_coefficient * rain_mm_h


def _truth_puff_field(
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    speed: np.ndarray,
    direction: np.ndarray,
    rain: np.ndarray,
    source: np.ndarray,
    dt: float,
) -> np.ndarray:
    """Independent fine-time Gaussian-puff reference field at the final time."""
    u = speed * np.cos(direction)
    v = speed * np.sin(direction)
    loss = _loss_rate(rain, truth=True)
    displacement_x = np.cumsum((u[::-1] * dt))[::-1]
    displacement_y = np.cumsum((v[::-1] * dt))[::-1]
    cumulative_loss = np.cumsum((loss[::-1] * dt))[::-1]
    n = len(speed)
    field = np.zeros_like(x_grid, dtype=float)
    for index in range(0, n, 5):
        age = max(dt, (n - index) * dt)
        cx = SOURCE_X + displacement_x[index]
        cy = SOURCE_Y + displacement_y[index]
        travel_angle = np.arctan2(displacement_y[index], displacement_x[index])
        cos_a, sin_a = np.cos(travel_angle), np.sin(travel_angle)
        rx, ry = x_grid - cx, y_grid - cy
        along = rx * cos_a + ry * sin_a
        cross = -rx * sin_a + ry * cos_a
        sigma_along = np.sqrt(110.0**2 + 2.0 * 58.0 * age)
        sigma_cross = np.sqrt(80.0**2 + 2.0 * 32.0 * age)
        emitted_mass = source[index] * dt * 5.0
        surviving_mass = emitted_mass * np.exp(-cumulative_loss[index])
        field += surviving_mass / (2.0 * np.pi * sigma_along * sigma_cross) * np.exp(
            -0.5 * ((along / sigma_along) ** 2 + (cross / sigma_cross) ** 2)
        )
    return field


def _bilinear_sample(
    field: np.ndarray,
    sample_x: np.ndarray,
    sample_y: np.ndarray,
    x_min: float,
    y_min: float,
    dx: float,
) -> np.ndarray:
    gx = (sample_x - x_min) / dx
    gy = (sample_y - y_min) / dx
    valid = (gx >= 0) & (gx <= field.shape[1] - 1) & (gy >= 0) & (gy <= field.shape[0] - 1)
    gx_clip = np.clip(gx, 0, field.shape[1] - 1)
    gy_clip = np.clip(gy, 0, field.shape[0] - 1)
    x0 = np.floor(gx_clip).astype(int)
    y0 = np.floor(gy_clip).astype(int)
    x1 = np.minimum(x0 + 1, field.shape[1] - 1)
    y1 = np.minimum(y0 + 1, field.shape[0] - 1)
    tx, ty = gx_clip - x0, gy_clip - y0
    values = (
        field[y0, x0] * (1 - tx) * (1 - ty)
        + field[y0, x1] * tx * (1 - ty)
        + field[y1, x0] * (1 - tx) * ty
        + field[y1, x1] * tx * ty
    )
    return np.where(valid, values, 0.0)


def _reworked_eulerian_field(
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    speed: np.ndarray,
    direction: np.ndarray,
    rain: np.ndarray,
    source: np.ndarray,
) -> np.ndarray:
    """Coarse dynamic Eulerian analogue of the reworked transport core."""
    field = np.zeros_like(x_grid, dtype=float)
    source_col = int(round((SOURCE_X - X_MIN) / DX))
    source_row = int(round((SOURCE_Y - Y_MIN) / DX))
    alpha = 40.0 * DT / (DX * DX)
    for index in range(len(speed)):
        u = speed[index] * np.cos(direction[index])
        v = speed[index] * np.sin(direction[index])
        advected = _bilinear_sample(field, x_grid - u * DT, y_grid - v * DT, X_MIN, Y_MIN, DX)
        padded = np.pad(advected, 1, mode="constant")
        lap = (
            padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
            - 4.0 * advected
        )
        field = np.maximum(0.0, advected + alpha * lap)
        field *= np.exp(-_loss_rate(np.array([rain[index]]), truth=False)[0] * DT)
        field[source_row, source_col] += source[index] * DT / (DX * DX)
    return field


def _steady_gaussian_field(
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    speed: np.ndarray,
    direction: np.ndarray,
    source: np.ndarray,
) -> np.ndarray:
    """Traditional single-state 2-D Gaussian plume using mean inputs."""
    mean_u = float(np.mean(speed * np.cos(direction)))
    mean_v = float(np.mean(speed * np.sin(direction)))
    wind = max(0.2, float(np.hypot(mean_u, mean_v)))
    angle = float(np.arctan2(mean_v, mean_u))
    rx, ry = x_grid - SOURCE_X, y_grid - SOURCE_Y
    downwind = rx * np.cos(angle) + ry * np.sin(angle)
    crosswind = -rx * np.sin(angle) + ry * np.cos(angle)
    # Match the baseline's lateral spread to the same order of diffusivity as
    # the reference instead of deliberately over-broadening the plume.
    sigma_y = np.sqrt(80.0**2 + 2.0 * 32.0 * np.maximum(downwind, 0.0) / wind)
    decay = 1.15e-5
    plume = (
        float(np.mean(source))
        / (2.0 * np.pi * wind * sigma_y)
        * np.exp(-0.5 * (crosswind / sigma_y) ** 2)
        * np.exp(-decay * np.maximum(downwind, 0.0) / wind)
    )
    return np.where(downwind > 0.0, plume, 0.0)


def _sensor_points() -> tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(750.0, 16_750.0, 10)
    ys = np.linspace(-5_250.0, 5_250.0, 8)
    sx, sy = np.meshgrid(xs, ys)
    return sx.ravel(), sy.ravel()


def _fit_log_scale(pred: np.ndarray, observed: np.ndarray) -> float:
    pred_log = np.log10(np.maximum(pred, LOG_FLOOR))
    obs_log = np.log10(np.maximum(observed, LOG_FLOOR))
    return float(10.0 ** np.mean(obs_log - pred_log))


def _metrics(pred: np.ndarray, observed: np.ndarray, truth_threshold: float) -> dict[str, float]:
    pred_log = np.log10(np.maximum(pred, LOG_FLOOR))
    obs_log = np.log10(np.maximum(observed, LOG_FLOOR))
    residual = pred_log - obs_log
    rmse = float(np.sqrt(np.mean(residual**2)))
    mae = float(np.mean(np.abs(residual)))
    corr = float(np.corrcoef(pred_log, obs_log)[0, 1]) if np.std(pred_log) > 0 and np.std(obs_log) > 0 else 0.0
    pred_hot = pred >= truth_threshold
    obs_hot = observed >= truth_threshold
    union = int(np.count_nonzero(pred_hot | obs_hot))
    iou = float(np.count_nonzero(pred_hot & obs_hot) / union) if union else 1.0
    return {"rmseLog10": rmse, "maeLog10": mae, "pearsonR": corr, "hotspotIoU": iou}


def _plot_heatmaps(records: list[dict], scenario_fields: dict[str, dict[str, np.ndarray]], x: np.ndarray, y: np.ndarray) -> None:
    scenario = next(item for item in SCENARIOS if item.scenario_id == "S2_wind_shift")
    fields = scenario_fields[scenario.scenario_id]
    truth, reworked, gaussian = fields["truth"], fields["reworked"], fields["gaussian"]
    positive = np.concatenate([truth[truth > LOG_FLOOR], reworked[reworked > LOG_FLOOR], gaussian[gaussian > LOG_FLOOR]])
    vmin = max(LOG_FLOOR, float(np.percentile(positive, 2)))
    vmax = float(np.percentile(positive, 99.5))
    extent = [x[0] / 1000.0, x[-1] / 1000.0, y[0] / 1000.0, y[-1] / 1000.0]

    fig, axes = plt.subplots(1, 5, figsize=(18, 4.3), constrained_layout=True)
    concentration_panels = [
        (truth, "Synthetic reference"),
        (reworked, "Reworked dynamic model"),
        (gaussian, "Steady Gaussian plume"),
    ]
    for ax, (field, title) in zip(axes[:3], concentration_panels):
        im = ax.imshow(np.maximum(field, vmin), origin="lower", extent=extent, aspect="auto", cmap="viridis", norm=LogNorm(vmin=vmin, vmax=vmax))
        ax.set_title(title)
        ax.set_xlabel("x (km)")
    axes[0].set_ylabel("y (km)")
    error_reworked = np.abs(np.log10(np.maximum(reworked, LOG_FLOOR)) - np.log10(np.maximum(truth, LOG_FLOOR)))
    error_gaussian = np.abs(np.log10(np.maximum(gaussian, LOG_FLOOR)) - np.log10(np.maximum(truth, LOG_FLOOR)))
    error_max = max(0.5, float(np.percentile(np.concatenate([error_reworked.ravel(), error_gaussian.ravel()]), 95)))
    for ax, field, title in [
        (axes[3], error_reworked, "Reworked |log error|"),
        (axes[4], error_gaussian, "Gaussian |log error|"),
    ]:
        err_im = ax.imshow(field, origin="lower", extent=extent, aspect="auto", cmap="magma", vmin=0.0, vmax=error_max)
        ax.set_title(title)
        ax.set_xlabel("x (km)")
    fig.colorbar(im, ax=axes[:3], shrink=0.72, label="concentration (spores/m², log scale)")
    fig.colorbar(err_im, ax=axes[3:], shrink=0.72, label="absolute log10 error")
    fig.suptitle("S2 wind shift: common scales reveal footprint and error differences", fontsize=12)
    fig.savefig(OUT / "heatmap_wind_shift.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(len(SCENARIOS), 3, figsize=(12, 10), constrained_layout=True, sharex=True, sharey=True)
    for row, scenario in enumerate(SCENARIOS):
        fields = scenario_fields[scenario.scenario_id]
        positive = np.concatenate([f[f > LOG_FLOOR] for f in fields.values()])
        local_min = max(LOG_FLOOR, float(np.percentile(positive, 2)))
        local_max = float(np.percentile(positive, 99.5))
        for col, (key, title) in enumerate([("truth", "Synthetic reference"), ("reworked", "Reworked"), ("gaussian", "Gaussian")]):
            axes[row, col].imshow(np.maximum(fields[key], local_min), origin="lower", extent=extent, aspect="auto", cmap="viridis", norm=LogNorm(vmin=local_min, vmax=local_max))
            if row == 0:
                axes[row, col].set_title(title)
            if col == 0:
                row_labels = ["S1 steady control", "S2 wind shift", "S3 wind + rain"]
                axes[row, col].set_ylabel(f"{row_labels[row]}\ny (km)")
            if row == len(SCENARIOS) - 1:
                axes[row, col].set_xlabel("x (km)")
    fig.suptitle("Scenario comparison with a shared scale within each row", fontsize=12)
    fig.savefig(OUT / "heatmap_all_scenarios.png", dpi=180)
    plt.close(fig)


def _plot_metrics(metrics_rows: list[dict]) -> None:
    names = ["S1 steady control", "S2 wind shift", "S3 wind + rain"]
    reworked = [next(r for r in metrics_rows if r["scenarioId"] == s.scenario_id)["reworked"]["rmseLog10"] for s in SCENARIOS]
    gaussian = [next(r for r in metrics_rows if r["scenarioId"] == s.scenario_id)["gaussian"]["rmseLog10"] for s in SCENARIOS]
    x = np.arange(len(names))
    width = 0.34
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    bars_a = ax.bar(x - width / 2, reworked, width, label="Reworked dynamic model", color="#2a9d8f")
    bars_b = ax.bar(x + width / 2, gaussian, width, label="Steady Gaussian plume", color="#e76f51")
    ax.set_ylabel("Held-out RMSE (log10 concentration)")
    ax.set_title("Independent held-out comparison on synthetic observations")
    ax.set_xticks(x, names)
    ax.legend()
    for index, (a, b) in enumerate(zip(reworked, gaussian)):
        improvement = (b - a) / b * 100.0
        if improvement >= 0:
            annotation = f"Reworked {improvement:.1f}% lower"
        else:
            gaussian_advantage = (a - b) / a * 100.0
            annotation = f"Gaussian {gaussian_advantage:.1f}% lower"
        ax.text(index, max(a, b) + 0.34, annotation, ha="center", va="bottom", fontsize=9)
    ax.bar_label(bars_a, fmt="%.3f", padding=2, fontsize=8)
    ax.bar_label(bars_b, fmt="%.3f", padding=2, fontsize=8)
    ax.set_ylim(0, max(gaussian + reworked) + 0.78)
    fig.savefig(OUT / "metric_comparison.png", dpi=180)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    x = np.arange(X_MIN, X_MAX + DX, DX)
    y = np.arange(Y_MIN, Y_MAX + DX, DX)
    x_grid, y_grid = np.meshgrid(x, y)
    times = np.arange(0.0, DURATION_HOURS * 3600.0, DT)
    sensor_x, sensor_y = _sensor_points()
    rng = np.random.default_rng(SEED)
    indices = np.arange(sensor_x.size)
    rng.shuffle(indices)
    train_indices = set(indices[:20].tolist())

    observation_rows: list[dict] = []
    metrics_rows: list[dict] = []
    scenario_fields: dict[str, dict[str, np.ndarray]] = {}

    for scenario_index, scenario in enumerate(SCENARIOS):
        speed, direction, rain, source = _timeline(scenario.scenario_id, times)
        truth = _truth_puff_field(x_grid, y_grid, speed, direction, rain, source, DT)
        reworked_raw = _reworked_eulerian_field(x_grid, y_grid, speed, direction, rain, source)
        gaussian_raw = _steady_gaussian_field(x_grid, y_grid, speed, direction, source)

        truth_sensor = _bilinear_sample(truth, sensor_x, sensor_y, X_MIN, Y_MIN, DX)
        reworked_sensor = _bilinear_sample(reworked_raw, sensor_x, sensor_y, X_MIN, Y_MIN, DX)
        gaussian_sensor = _bilinear_sample(gaussian_raw, sensor_x, sensor_y, X_MIN, Y_MIN, DX)
        local_rng = np.random.default_rng(SEED + scenario_index * 101)
        observed = np.maximum(LOG_FLOOR, truth_sensor * 10.0 ** local_rng.normal(0.0, 0.12, truth_sensor.size))
        train_mask = np.array([index in train_indices for index in range(sensor_x.size)])
        test_mask = ~train_mask
        reworked_scale = _fit_log_scale(reworked_sensor[train_mask], observed[train_mask])
        gaussian_scale = _fit_log_scale(gaussian_sensor[train_mask], observed[train_mask])
        reworked_sensor *= reworked_scale
        gaussian_sensor *= gaussian_scale
        reworked = reworked_raw * reworked_scale
        gaussian = gaussian_raw * gaussian_scale

        threshold = float(np.percentile(observed[test_mask], 70))
        reworked_metrics = _metrics(reworked_sensor[test_mask], observed[test_mask], threshold)
        gaussian_metrics = _metrics(gaussian_sensor[test_mask], observed[test_mask], threshold)
        improvement = (gaussian_metrics["rmseLog10"] - reworked_metrics["rmseLog10"]) / gaussian_metrics["rmseLog10"] * 100.0
        metrics_rows.append(
            {
                "scenarioId": scenario.scenario_id,
                "scenarioName": scenario.name_zh,
                "description": scenario.description,
                "trainCount": int(train_mask.sum()),
                "testCount": int(test_mask.sum()),
                "reworkedScale": reworked_scale,
                "gaussianScale": gaussian_scale,
                "reworked": reworked_metrics,
                "gaussian": gaussian_metrics,
                "rmseImprovementPct": improvement,
            }
        )
        scenario_fields[scenario.scenario_id] = {"truth": truth, "reworked": reworked, "gaussian": gaussian}
        for index in range(sensor_x.size):
            observation_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "point_id": f"P{index + 1:02d}",
                    "split": "train" if train_mask[index] else "test",
                    "x_m": sensor_x[index],
                    "y_m": sensor_y[index],
                    "synthetic_truth_spores_m2": truth_sensor[index],
                    "synthetic_observed_spores_m2": observed[index],
                    "reworked_pred_spores_m2": reworked_sensor[index],
                    "gaussian_pred_spores_m2": gaussian_sensor[index],
                }
            )

    with (OUT / "synthetic_observations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(observation_rows[0].keys()))
        writer.writeheader()
        writer.writerows(observation_rows)

    flat_metric_rows = []
    for row in metrics_rows:
        flat_metric_rows.append(
            {
                "scenario_id": row["scenarioId"],
                "scenario_name": row["scenarioName"],
                "train_count": row["trainCount"],
                "test_count": row["testCount"],
                "reworked_rmse_log10": row["reworked"]["rmseLog10"],
                "gaussian_rmse_log10": row["gaussian"]["rmseLog10"],
                "rmse_improvement_pct": row["rmseImprovementPct"],
                "reworked_mae_log10": row["reworked"]["maeLog10"],
                "gaussian_mae_log10": row["gaussian"]["maeLog10"],
                "reworked_pearson_r": row["reworked"]["pearsonR"],
                "gaussian_pearson_r": row["gaussian"]["pearsonR"],
                "reworked_hotspot_iou": row["reworked"]["hotspotIoU"],
                "gaussian_hotspot_iou": row["gaussian"]["hotspotIoU"],
            }
        )
    with (OUT / "scenario_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_metric_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_metric_rows)

    artifact = {
        "title": "报告用现实化模拟对比数据 v1",
        "generatedAt": "2026-09-06",
        "dataStatus": "synthetic; not field observations",
        "seed": SEED,
        "domainMeters": {"x": [X_MIN, X_MAX], "y": [Y_MIN, Y_MAX], "gridStep": DX},
        "durationHours": DURATION_HOURS,
        "evaluation": "20 calibration sensors and 60 held-out sensors per scenario; metrics use held-out sensors only",
        "referenceGenerator": "independent time-integrated Gaussian-puff ensemble with dynamic weather and fate",
        "proposedModel": "coarse dynamic Eulerian offline analogue",
        "baselineModel": "single steady Gaussian plume",
        "scenarios": metrics_rows,
        "disclosure": "Results demonstrate controlled synthetic-scenario behavior and must not be presented as real-field accuracy.",
    }
    (OUT / "scenario_metrics.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    _plot_heatmaps(observation_rows, scenario_fields, x, y)
    _plot_metrics(metrics_rows)

    print(f"wrote report benchmark to {OUT}")
    for path in sorted(OUT.iterdir()):
        print(f"  {path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
