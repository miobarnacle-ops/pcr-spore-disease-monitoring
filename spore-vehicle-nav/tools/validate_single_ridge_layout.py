#!/usr/bin/env python3
"""Validate the independent single-ridge simulation geometry.

The canonical farmland validator intentionally remains strict for the original
three-row 8 m x 6 m scene.  This checker validates the physical dimensions of
the one-ridge scenario used for the current SLAM feasibility run.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


EPSILON = 1e-6


def _close(actual: float, expected: float, tolerance: float = EPSILON) -> bool:
    return math.isfinite(actual) and abs(actual - expected) <= tolerance


def _numbers(text: str | None, count: int, label: str) -> list[float]:
    if text is None:
        raise ValueError(f"{label} is missing")
    try:
        values = [float(item) for item in text.split()]
    except ValueError as exc:
        raise ValueError(f"{label} must contain numbers") from exc
    if len(values) != count or not all(math.isfinite(item) for item in values):
        raise ValueError(f"{label} must contain {count} finite numbers")
    return values


def _model(world: ET.Element, name: str) -> ET.Element:
    for candidate in world.findall("model"):
        if candidate.get("name") == name:
            return candidate
    raise ValueError(f"world is missing model {name!r}")


def _model_pose(model: ET.Element, name: str) -> list[float]:
    return _numbers(model.findtext("pose"), 6, f"{name}.pose")


def _model_box_size(model: ET.Element, name: str) -> list[float]:
    size = model.find("link/collision/geometry/box/size")
    return _numbers(None if size is None else size.text, 3, f"{name}.collision.box.size")


def load_layout(path: Path) -> dict:
    layout = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(layout, dict):
        raise ValueError("layout root must be an object")
    return layout


def validate_layout(layout: dict) -> tuple[list[str], dict[str, float]]:
    errors: list[str] = []
    try:
        field = layout["field"]
        rows = layout["rows"]
        headland = layout["headland"]
        robot = layout["robot"]
        start = layout["start"]
        mapping = layout["mapping"]
        length = float(field["length_m"])
        width = float(field["width_m"])
        x_min = float(field["x_min_m"])
        x_max = float(field["x_max_m"])
        y_min = float(field["y_min_m"])
        y_max = float(field["y_max_m"])
        row_count = int(rows["count"])
        centers = [float(value) for value in rows["center_y_m"]]
        row_length = float(rows["length_m"])
        row_width = float(rows["width_m"])
        row_height = float(rows["height_m"])
        headland_target = float(rows["headland_target_m"])
        marker_centers = [float(value) for value in headland["marker_center_x_m"]]
        marker_length = float(headland["marker_length_m"])
        marker_thickness = float(headland["marker_thickness_m"])
        marker_height = float(headland["marker_height_m"])
        lidar_height = float(robot["lidar_height_m"])
        start_x = float(start["x_m"])
        start_y = float(start["y_m"])
        resolution = float(mapping["resolution_m"])
    except (KeyError, TypeError, ValueError) as exc:
        return [f"layout schema is incomplete: {exc}"], {}

    if layout.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if row_count != 1 or len(centers) != 1:
        errors.append("single-ridge layout must contain exactly one row center")
    if not _close(length, 8.0) or not _close(width, 3.0):
        errors.append("field must be exactly 8.0 m x 3.0 m")
    if not (_close(x_min, -4.0) and _close(x_max, 4.0) and _close(y_min, -1.5) and _close(y_max, 1.5)):
        errors.append("field bounds must be x=[-4.0, 4.0], y=[-1.5, 1.5]")
    if not _close(row_length, 4.8) or not _close(row_width, 0.4) or not _close(row_height, 0.5):
        errors.append("ridge must be exactly 4.8 m x 0.4 m x 0.5 m")
    if centers and not _close(centers[0], 0.0):
        errors.append("ridge center_y_m must be 0.0")
    if not _close(headland_target, 1.6):
        errors.append("headland_target_m must be 1.6 m")
    expected_headland = (x_max - x_min - row_length) / 2.0
    if not _close(expected_headland, headland_target):
        errors.append("field length and ridge length do not produce the target headland")
    if marker_centers != [-4.0, 4.0]:
        errors.append("headland markers must be centered at x=-4.0 and x=4.0")
    if not _close(marker_length, 2.2) or not _close(marker_thickness, 0.12) or not _close(marker_height, 0.5):
        errors.append("headland marker dimensions must be 0.12 m x 2.2 m x 0.5 m")
    if not (0.0 < lidar_height < row_height):
        errors.append("lidar height must be above the floor and below the ridge top")
    if not (x_min < start_x < x_max and y_min < start_y < y_max):
        errors.append("robot start must lie inside the field")
    if not _close(resolution, 0.05):
        errors.append("mapping resolution must be 0.05 m")

    metrics = {
        "headland_m": expected_headland,
        "row_length_m": row_length,
        "row_width_m": row_width,
        "field_length_m": length,
        "field_width_m": width,
    }
    return errors, metrics


def validate_world(layout: dict, world_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        root = ET.fromstring(world_path.read_text(encoding="utf-8"))
        world = root.find("world")
        if world is None:
            raise ValueError("SDF does not contain a world element")
        if world.get("name") != "spore_patrol_single_ridge_8m":
            errors.append("world name must be spore_patrol_single_ridge_8m")

        field = layout["field"]
        rows = layout["rows"]
        headland = layout["headland"]
        expected = {
            "soil": ([0.0, 0.0, -0.05, 0.0, 0.0, 0.0], [float(field["length_m"]), float(field["width_m"]), float(field["soil_thickness_m"])]),
            "single_ridge": ([0.0, float(rows["center_y_m"][0]), float(rows["height_m"]) / 2.0, 0.0, 0.0, 0.0], [float(rows["length_m"]), float(rows["width_m"]), float(rows["height_m"])]),
            "headland_marker_west": ([float(headland["marker_center_x_m"][0]), 0.0, float(headland["marker_height_m"]) / 2.0, 0.0, 0.0, 0.0], [float(headland["marker_thickness_m"]), float(headland["marker_length_m"]), float(headland["marker_height_m"])]),
            "headland_marker_east": ([float(headland["marker_center_x_m"][1]), 0.0, float(headland["marker_height_m"]) / 2.0, 0.0, 0.0, 0.0], [float(headland["marker_thickness_m"]), float(headland["marker_length_m"]), float(headland["marker_height_m"])]),
        }
        for name, (expected_pose, expected_size) in expected.items():
            model = _model(world, name)
            actual_pose = _model_pose(model, name)
            actual_size = _model_box_size(model, name)
            if any(not _close(actual, expected_value) for actual, expected_value in zip(actual_pose, expected_pose)):
                errors.append(f"{name}.pose does not match layout")
            if any(not _close(actual, expected_value) for actual, expected_value in zip(actual_size, expected_size)):
                errors.append(f"{name} collision size does not match layout")

        unexpected_boundaries = [
            model.get("name")
            for model in world.findall("model")
            if (model.get("name") or "").startswith("field_boundary")
        ]
        if unexpected_boundaries:
            errors.append("single-ridge world must not add continuous field boundaries")
    except (OSError, ET.ParseError, ValueError, KeyError, IndexError) as exc:
        errors.append(f"world could not be validated: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--layout",
        type=Path,
        default=root / "src/spore_patrol_sim/config/single_ridge_layout.json",
    )
    parser.add_argument(
        "--world",
        type=Path,
        default=root / "src/spore_patrol_sim/worlds/single_ridge_8m.world",
    )
    args = parser.parse_args(argv)

    try:
        layout = load_layout(args.layout)
        layout_errors, metrics = validate_layout(layout)
        world_errors = validate_world(layout, args.world)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL single-ridge layout: {exc}")
        return 1

    errors = layout_errors + world_errors
    if errors:
        print("FAIL single-ridge layout")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS single-ridge layout")
    print(
        f"- field={metrics['field_length_m']:.2f}x{metrics['field_width_m']:.2f} m "
        f"ridge={metrics['row_length_m']:.2f}x{metrics['row_width_m']:.2f} m"
    )
    print(f"- headland={metrics['headland_m']:.2f} m each end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
