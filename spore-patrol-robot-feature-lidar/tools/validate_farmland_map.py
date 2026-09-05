#!/usr/bin/env python3
"""Check the canonical simulated farmland geometry in a saved Nav2 map.

The generic saved-map checker can prove that a map is non-empty and covers the
requested area.  This checker adds a deterministic geometry gate for the
canonical scene: each expected crop row must be continuously visible and its
occupied trace must remain close to a straight line.  It is intentionally
stdlib-only and works on a development PC without ROS, OpenCV, or Pillow.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys


TOOLS_DIRECTORY = Path(__file__).resolve().parent
if str(TOOLS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIRECTORY))

from validate_saved_map import (  # noqa: E402
    inspect_map,
    read_map_yaml,
    read_pgm,
    validate_map,
)


@dataclass(frozen=True)
class RowCheck:
    expected_y: float
    samples: int
    hits: int
    median_y: float | None
    spread_y: float | None

    @property
    def coverage(self) -> float:
        return self.hits / max(self.samples, 1)

    @property
    def offset(self) -> float | None:
        if self.median_y is None:
            return None
        return abs(self.median_y - self.expected_y)


def _layout_values(layout_path: Path) -> tuple[dict, list[float], float, float]:
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    field = layout["field"]
    rows = layout["rows"]
    centers = [float(value) for value in rows["center_y_m"]]
    return (
        layout,
        centers,
        float(rows["length_m"]),
        float(rows["width_m"]),
    )


def _map_origin(yaml_path: Path) -> tuple[float, float, float]:
    text = yaml_path.read_text(encoding="utf-8")
    marker = "origin:"
    for line in text.splitlines():
        if line.strip().startswith(marker):
            value = line.split(":", 1)[1].strip()
            if value.startswith("[") and value.endswith("]"):
                numbers = [float(item.strip()) for item in value[1:-1].split(",")]
                if len(numbers) >= 3 and all(math.isfinite(item) for item in numbers[:3]):
                    return numbers[0], numbers[1], numbers[2]
    raise ValueError(f"{yaml_path} must contain origin: [x, y, yaw]")


def _grid_cell_for_world(
    x: float,
    y: float,
    *,
    origin_x: float,
    origin_y: float,
    origin_yaw: float,
    resolution: float,
    image_height: int,
) -> tuple[int, int]:
    # The YAML origin is the pose of the map's lower-left cell.  Invert that
    # pose so the checker also handles a small map-frame yaw without silently
    # treating the image row index as a Cartesian y coordinate.
    dx = x - origin_x
    dy = y - origin_y
    cos_yaw = math.cos(origin_yaw)
    sin_yaw = math.sin(origin_yaw)
    grid_x = (cos_yaw * dx + sin_yaw * dy) / resolution
    grid_y = (-sin_yaw * dx + cos_yaw * dy) / resolution
    return int(round(grid_x)), image_height - 1 - int(round(grid_y))


def check_rows(
    yaml_path: Path,
    layout_path: Path,
    *,
    min_coverage: float = 0.75,
    max_spread: float = 0.12,
    max_offset: float = 0.20,
    sample_step: float = 0.05,
) -> tuple[list[RowCheck], list[str]]:
    """Return per-row geometry checks and human-readable failures."""

    _, centers, row_length, row_width = _layout_values(layout_path)
    image_path, resolution = read_map_yaml(yaml_path)
    image = read_pgm(image_path)
    origin_x, origin_y, origin_yaw = _map_origin(yaml_path)
    if sample_step <= 0:
        raise ValueError("sample_step must be positive")

    # Include the row itself plus a margin for the laser's visible near edge
    # and one map cell of scan/noise uncertainty.
    half_band = max(0.30, row_width * 1.5 + resolution)
    sample_count = int(math.floor(row_length / sample_step)) + 1
    checks: list[RowCheck] = []
    errors: list[str] = []

    for expected_y in centers:
        trace_y: list[float] = []
        for index in range(sample_count):
            x = -row_length / 2.0 + min(index * sample_step, row_length)
            occupied_y: list[float] = []
            band_steps = int(math.ceil(half_band / resolution))
            for band_index in range(-band_steps, band_steps + 1):
                candidate_y = expected_y + band_index * resolution
                grid_x, image_row = _grid_cell_for_world(
                    x,
                    candidate_y,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    origin_yaw=origin_yaw,
                    resolution=resolution,
                    image_height=image.height,
                )
                if 0 <= grid_x < image.width and 0 <= image_row < image.height:
                    if image.pixels[image_row * image.width + grid_x] <= 100:
                        occupied_y.append(candidate_y)
            if occupied_y:
                trace_y.append(sum(occupied_y) / len(occupied_y))

        median_y = None
        spread_y = None
        if trace_y:
            ordered = sorted(trace_y)
            middle = len(ordered) // 2
            median_y = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0
            spread_y = math.sqrt(
                sum((value - median_y) ** 2 for value in trace_y) / len(trace_y)
            )
        check = RowCheck(expected_y, sample_count, len(trace_y), median_y, spread_y)
        checks.append(check)

        if check.coverage < min_coverage:
            errors.append(
                f"row y={expected_y:.2f} coverage {check.coverage:.1%} "
                f"is below {min_coverage:.1%}"
            )
        if check.offset is None or check.offset > max_offset:
            actual = "missing" if check.offset is None else f"{check.offset:.3f} m"
            errors.append(
                f"row y={expected_y:.2f} median offset {actual} "
                f"exceeds {max_offset:.3f} m"
            )
        if check.spread_y is None or check.spread_y > max_spread:
            actual = "missing" if check.spread_y is None else f"{check.spread_y:.3f} m"
            errors.append(
                f"row y={expected_y:.2f} trace spread {actual} "
                f"exceeds {max_spread:.3f} m"
            )

    return checks, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_yaml", type=Path, help="saved Nav2 map YAML file")
    parser.add_argument(
        "--layout",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src/spore_patrol_sim/config/farmland_layout.json",
    )
    parser.add_argument("--min-row-coverage", type=float, default=0.75)
    parser.add_argument("--max-row-spread", type=float, default=0.12)
    parser.add_argument("--max-row-offset", type=float, default=0.20)
    args = parser.parse_args(argv)

    try:
        stats = inspect_map(args.map_yaml)
        layout = json.loads(args.layout.read_text(encoding="utf-8"))
        field = layout["field"]
        mapping = layout["mapping"]
        structural_errors = validate_map(
            stats,
            field_length=float(field["length_m"]),
            field_width=float(field["width_m"]),
            coverage_tolerance=float(mapping["coverage_tolerance_m"]),
            min_known_fraction=float(mapping["min_known_fraction"]),
            min_occupied_fraction=float(mapping["min_occupied_fraction"]),
        )
        checks, row_errors = check_rows(
            args.map_yaml,
            args.layout,
            min_coverage=args.min_row_coverage,
            max_spread=args.max_row_spread,
            max_offset=args.max_row_offset,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL farmland map: {exc}")
        return 1

    errors = structural_errors + row_errors
    if errors:
        print("FAIL farmland map")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS farmland map geometry")
    print(
        f"- grid={stats.width}x{stats.height} "
        f"coverage={stats.width * stats.resolution:.2f}x"
        f"{stats.height * stats.resolution:.2f} m"
    )
    print(
        "- rows="
        + ", ".join(
            f"y={check.expected_y:.2f}: {check.coverage:.1%}, "
            f"spread={check.spread_y:.3f}m"
            for check in checks
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
