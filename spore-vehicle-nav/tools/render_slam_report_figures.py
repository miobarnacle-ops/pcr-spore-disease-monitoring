#!/usr/bin/env python3
"""Render report-ready PNG figures from saved SLAM maps and run logs."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.font_manager import FontProperties
import numpy as np
from PIL import Image


WAYPOINT_RE = re.compile(
    r"reached index=(?P<index>\d+)\s+"
    r"target=\((?P<target_x>[-+0-9.]+),(?P<target_y>[-+0-9.]+)\)\s+"
    r"pose=\((?P<pose_x>[-+0-9.]+),(?P<pose_y>[-+0-9.]+)\)"
)

FONT_REGULAR = FontProperties(
    fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
)
FONT_BOLD = FontProperties(
    fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
)


def read_map_yaml(yaml_path: Path) -> tuple[Path, float, float, float]:
    values: dict[str, str] = {}
    for line in yaml_path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    image_path = Path(values["image"])
    if not image_path.is_absolute():
        image_path = yaml_path.parent / image_path
    resolution = float(values["resolution"])
    origin = values["origin"].strip().strip("[]").split(",")
    return image_path, resolution, float(origin[0]), float(origin[1])


def load_map(yaml_path: Path) -> tuple[np.ndarray, float, float, float]:
    image_path, resolution, origin_x, origin_y = read_map_yaml(yaml_path)
    pixels = np.asarray(Image.open(image_path).convert("L"))
    return pixels, resolution, origin_x, origin_y


def load_reached_poses(log_path: Path) -> tuple[np.ndarray, np.ndarray]:
    targets: list[tuple[float, float]] = []
    poses: list[tuple[float, float]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        match = WAYPOINT_RE.search(line)
        if not match:
            continue
        targets.append((float(match["target_x"]), float(match["target_y"])))
        poses.append((float(match["pose_x"]), float(match["pose_y"])))
    if not poses:
        raise ValueError(f"no reached waypoints found in {log_path}")
    return np.asarray(targets), np.asarray(poses)


def map_rgb(pixels: np.ndarray) -> np.ndarray:
    # Nav2 map_saver convention: occupied=dark, free=white, unknown=gray.
    rgb = np.empty((*pixels.shape, 3), dtype=float)
    occupied = pixels <= 100
    free = pixels >= 240
    unknown = ~(occupied | free)
    rgb[occupied] = (0.09, 0.12, 0.16)
    rgb[free] = (0.98, 0.98, 0.97)
    rgb[unknown] = (0.66, 0.70, 0.74)
    return rgb


def map_stats(pixels: np.ndarray) -> tuple[float, float, float]:
    occupied = pixels <= 100
    free = pixels >= 240
    total = pixels.size
    return (
        float((occupied | free).sum() / total),
        float(occupied.sum() / total),
        float(pixels.shape[1]),
    )


def add_route_arrows(ax: plt.Axes, points: np.ndarray, color: str) -> None:
    for start, end in zip(points[:-1], points[1:]):
        midpoint = start + 0.58 * (end - start)
        direction = end - start
        ax.annotate(
            "",
            xy=midpoint + 0.12 * direction / max(np.linalg.norm(direction), 1e-9),
            xytext=midpoint,
            arrowprops={
                "arrowstyle": "-|>",
                "color": color,
                "lw": 1.4,
                "mutation_scale": 12,
            },
        )


def render_figure(
    *,
    output_path: Path,
    title: str,
    subtitle: str,
    yaml_path: Path,
    trajectory_path: Path,
    row_centers: list[float],
    row_length: float,
    field_bounds: tuple[float, float, float, float],
    headland: float,
    extra_lines: list[tuple[float, float, float, float]],
    result_lines: list[str],
    initial_pose: tuple[float, float],
) -> None:
    pixels, resolution, origin_x, origin_y = load_map(yaml_path)
    targets, poses = load_reached_poses(trajectory_path)
    start = np.asarray(initial_pose, dtype=float)
    path_points = poses
    if np.linalg.norm(path_points[0] - start) > 0.05:
        path_points = np.vstack([start, path_points])
    height, width = pixels.shape
    extent = (
        origin_x,
        origin_x + width * resolution,
        origin_y,
        origin_y + height * resolution,
    )
    known_fraction, occupied_fraction, _ = map_stats(pixels)

    fig, ax = plt.subplots(figsize=(12.8, 7.6), dpi=240)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#d5d9de")
    ax.imshow(
        map_rgb(pixels),
        extent=extent,
        origin="upper",
        interpolation="nearest",
        zorder=0,
    )

    field_x_min, field_x_max, field_y_min, field_y_max = field_bounds
    ax.add_patch(
        Rectangle(
            (field_x_min, field_y_min),
            field_x_max - field_x_min,
            field_y_max - field_y_min,
            fill=False,
            edgecolor="#637083",
            linestyle=(0, (4, 3)),
            linewidth=1.2,
            zorder=2,
        )
    )

    row_color = "#d97706"
    route_color = "#1261a0"
    for row_y in row_centers:
        ax.plot(
            [-row_length / 2.0, row_length / 2.0],
            [row_y, row_y],
            color=row_color,
            linestyle=(0, (5, 3)),
            linewidth=1.5,
            zorder=3,
        )

    for x1, y1, x2, y2 in extra_lines:
        ax.plot(
            [x1, x2],
            [y1, y2],
            color="#b45309",
            linestyle=(0, (2, 2)),
            linewidth=1.4,
            zorder=3,
        )

    ax.plot(
        path_points[:, 0],
        path_points[:, 1],
        color=route_color,
        linewidth=2.4,
        marker="o",
        markersize=4.5,
        markerfacecolor="white",
        markeredgewidth=1.4,
        markeredgecolor=route_color,
        zorder=4,
    )
    add_route_arrows(ax, path_points, route_color)
    ax.scatter(
        path_points[0, 0],
        path_points[0, 1],
        s=90,
        marker="s",
        color="#15803d",
        edgecolor="white",
        linewidth=1.0,
        zorder=5,
    )
    ax.scatter(
        path_points[-1, 0],
        path_points[-1, 1],
        s=90,
        marker="X",
        color="#be123c",
        edgecolor="white",
        linewidth=0.8,
        zorder=5,
    )

    ax.set_title(
        title,
        loc="left",
        fontsize=18,
        fontproperties=FONT_BOLD,
        pad=14,
    )
    ax.text(
        0.0,
        1.01,
        subtitle,
        transform=ax.transAxes,
        fontsize=10.5,
        fontproperties=FONT_REGULAR,
        color="#4b5563",
        va="bottom",
    )
    ax.set_xlabel("X / m", fontsize=11, fontproperties=FONT_REGULAR)
    ax.set_ylabel("Y / m", fontsize=11, fontproperties=FONT_REGULAR)
    ax.grid(color="#64748b", alpha=0.18, linewidth=0.6)
    ax.set_aspect("equal", adjustable="box")
    ax.tick_params(labelsize=9)

    map_width = width * resolution
    map_height = height * resolution
    text = "\n".join(
        [
            *result_lines,
            f"地图栅格：{width} × {height} cells",
            f"有效覆盖：{map_width:.2f} × {map_height:.2f} m",
            f"分辨率：{resolution:.2f} m/cell",
            f"已知区域：{known_fraction:.1%}",
            f"占用区域：{occupied_fraction:.1%}",
            f"地头：{headland:.2f} m / 端",
        ]
    )
    ax.text(
        0.985,
        0.03,
        text,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9.5,
        fontproperties=FONT_REGULAR,
        linespacing=1.45,
        color="#1f2937",
        bbox={
            "boxstyle": "round,pad=0.55",
            "facecolor": "white",
            "edgecolor": "#cbd5e1",
            "alpha": 0.92,
        },
        zorder=8,
    )
    handles = [
        Patch(facecolor="#0f172a", edgecolor="none", label="占用/垄体"),
        Patch(facecolor="#f8fafc", edgecolor="#94a3b8", label="已知空闲"),
        Patch(facecolor="#a8b0ba", edgecolor="none", label="未知区域"),
        Line2D([0], [0], color=row_color, linestyle=(0, (5, 3)), label="垄中心线"),
        Line2D([0], [0], color=route_color, marker="o", markersize=4, label="小车行驶路线"),
    ]
    ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.0, -0.13),
        ncol=5,
        frameon=False,
        fontsize=9,
        prop=FONT_REGULAR,
        handlelength=2.2,
        columnspacing=1.4,
    )
    fig.subplots_adjust(left=0.08, right=0.98, top=0.88, bottom=0.20)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=240, facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "results/report_figures"
    parser.add_argument("--output-dir", type=Path, default=output_dir)
    parser.add_argument(
        "--three-ridge-result-dir",
        type=Path,
        default=root / "results/sim_farmland_8x6_20260831",
    )
    parser.add_argument(
        "--single-ridge-result-dir",
        type=Path,
        default=root / "results/20260912_125950_sim_single_ridge_8m",
    )
    args = parser.parse_args()

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Noto Sans CJK TC", "DejaVu Sans"],
            "axes.unicode_minus": False,
        }
    )

    three_ridge = args.three_ridge_result_dir
    single_ridge = args.single_ridge_result_dir
    render_figure(
        output_path=args.output_dir / "slam_sim_farmland_8x6_three_ridges.png",
        title="8 m × 6 m 三垄仿真 SLAM 建图结果",
        subtitle="Gazebo + SLAM Toolbox｜固定低速闭环｜三条平行垄体",
        yaml_path=three_ridge / "sim_farmland_8x6.yaml",
        trajectory_path=three_ridge / "trajectory.log",
        row_centers=[-1.42, 0.0, 1.42],
        row_length=4.80,
        field_bounds=(-4.0, 4.0, -3.0, 3.0),
        headland=1.60,
        extra_lines=[],
        result_lines=["验收：三条垄覆盖率 100% / 100% / 100%", "用途：仿真基准与重复性对照"],
        initial_pose=(-2.00, -0.71),
    )
    render_figure(
        output_path=args.output_dir / "slam_sim_single_ridge_4p8m.png",
        title="4.8 m 单垄仿真 SLAM 建图结果",
        subtitle="Gazebo + SLAM Toolbox｜两侧闭环行驶｜八个 0.6 m 纸箱等效垄体",
        yaml_path=single_ridge / "sim_single_ridge_8m.yaml",
        trajectory_path=single_ridge / "trajectory.log",
        row_centers=[0.0],
        row_length=4.80,
        field_bounds=(-4.0, 4.0, -1.5, 1.5),
        headland=1.60,
        extra_lines=[(-4.0, -1.1, -4.0, 1.1), (4.0, -1.1, 4.0, 1.1)],
        result_lines=["验收：单垄连续检测率 100%", "轨迹散布：0.054 m｜结果：PASS"],
        initial_pose=(-1.80, -0.90),
    )
    print(f"wrote figures to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
