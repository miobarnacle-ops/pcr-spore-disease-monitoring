#!/usr/bin/env python3
"""Validate the canonical simulated farmland geometry without ROS.

The checker intentionally uses only the Python standard library so it can be
run on the development PC before a ROS 2/Gazebo environment is available.
It checks both the declarative layout JSON and the SDF world generated from
that layout.  It does not start Gazebo, publish ROS messages, or access any
hardware.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


DEFAULT_LAYOUT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "spore_patrol_sim"
    / "config"
    / "farmland_layout.json"
)
DEFAULT_WORLD = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "spore_patrol_sim"
    / "worlds"
    / "farmland_8x6.world"
)
EPSILON = 1e-6


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_layout(layout: dict) -> tuple[list[str], dict[str, float]]:
    """Return (errors, derived_metrics) for a layout document."""

    errors: list[str] = []
    metrics: dict[str, float] = {}

    _require(layout.get("schema_version") == "1.0", "schema_version must be 1.0", errors)
    field = layout.get("field")
    rows = layout.get("rows")
    robot = layout.get("robot")
    start = layout.get("start")
    boundary = layout.get("boundary")
    mapping = layout.get("mapping")
    for value, label in (
        (field, "field"),
        (rows, "rows"),
        (robot, "robot"),
        (start, "start"),
        (boundary, "boundary"),
        (mapping, "mapping"),
    ):
        _require(isinstance(value, dict), f"{label} must be an object", errors)

    if not all(isinstance(value, dict) for value in (field, rows, robot, start, boundary, mapping)):
        return errors, metrics

    try:
        field_length = _number(field["length_m"], "field.length_m")
        field_width = _number(field["width_m"], "field.width_m")
        x_min = _number(field["x_min_m"], "field.x_min_m")
        x_max = _number(field["x_max_m"], "field.x_max_m")
        y_min = _number(field["y_min_m"], "field.y_min_m")
        y_max = _number(field["y_max_m"], "field.y_max_m")
        row_length = _number(rows["length_m"], "rows.length_m")
        row_width = _number(rows["width_m"], "rows.width_m")
        row_height = _number(rows["height_m"], "rows.height_m")
        corridor_required = _number(
            rows["required_clear_corridor_m"],
            "rows.required_clear_corridor_m",
        )
        headland_min = _number(rows["headland_min_m"], "rows.headland_min_m")
        headland_target = _number(rows["headland_target_m"], "rows.headland_target_m")
        lidar_height = _number(robot["lidar_height_m"], "robot.lidar_height_m")
        robot_width = _number(robot["footprint_width_m"], "robot.footprint_width_m")
        start_x = _number(start["x_m"], "start.x_m")
        start_y = _number(start["y_m"], "start.y_m")
        wall_height = _number(boundary["wall_height_m"], "boundary.wall_height_m")
        resolution = _number(mapping["resolution_m"], "mapping.resolution_m")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
        return errors, metrics

    center_y = rows.get("center_y_m")
    count = rows.get("count")
    _require(rows.get("orientation") == "x", "rows.orientation must be x", errors)
    _require(isinstance(count, int) and not isinstance(count, bool), "rows.count must be an integer", errors)
    if isinstance(count, int) and not isinstance(count, bool):
        _require(2 <= count <= 3, "rows.count must be between 2 and 3", errors)
    _require(isinstance(center_y, list), "rows.center_y_m must be a list", errors)
    if not isinstance(center_y, list):
        return errors, metrics
    _require(len(center_y) == count, "rows.center_y_m length must match rows.count", errors)

    try:
        row_centers = [_number(value, f"rows.center_y_m[{index}]") for index, value in enumerate(center_y)]
    except ValueError as exc:
        errors.append(str(exc))
        return errors, metrics

    _require(field_length > 0 and field_width > 0, "field dimensions must be positive", errors)
    _require(x_max > x_min and y_max > y_min, "field bounds must be increasing", errors)
    _require(abs((x_max - x_min) - field_length) <= EPSILON, "field x bounds do not match length", errors)
    _require(abs((y_max - y_min) - field_width) <= EPSILON, "field y bounds do not match width", errors)
    _require(row_length > 0 and row_width > 0 and row_height > 0, "row dimensions must be positive", errors)
    _require(row_length < field_length, "row length must be shorter than field length", errors)
    _require(corridor_required >= 1.20 - EPSILON, "required corridor must be at least 1.20 m", errors)
    _require(headland_min >= 1.50 - EPSILON, "minimum headland must be at least 1.50 m", errors)
    _require(headland_target >= headland_min - EPSILON, "headland target cannot be below minimum", errors)
    _require(wall_height > lidar_height, "boundary must be visible to the lidar", errors)
    _require(0 < resolution <= 0.10, "mapping resolution must be in (0, 0.10] m", errors)

    headland = (field_length - row_length) / 2.0
    metrics["headland_m"] = headland
    _require(headland >= headland_min - EPSILON, f"computed headland {headland:.3f} m is below minimum", errors)
    _require(headland >= headland_target - EPSILON, f"computed headland {headland:.3f} m is below target", errors)

    if row_centers:
        _require(row_centers == sorted(row_centers), "row centers must be sorted from south to north", errors)
        side_clearance = min(
            row_centers[0] - y_min - row_width / 2.0,
            y_max - row_centers[-1] - row_width / 2.0,
        )
        metrics["side_clearance_m"] = side_clearance
        _require(side_clearance >= 0.50 - EPSILON, f"side clearance {side_clearance:.3f} m is too small", errors)

        clear_corridors = [
            right - left - row_width
            for left, right in zip(row_centers, row_centers[1:])
        ]
        min_corridor = min(clear_corridors) if clear_corridors else field_width
        metrics["min_clear_corridor_m"] = min_corridor
        _require(
            min_corridor >= corridor_required - EPSILON,
            f"minimum clear corridor {min_corridor:.3f} m is below {corridor_required:.3f} m",
            errors,
        )

        start_in_corridor = any(
            left + row_width / 2.0 + EPSILON <= start_y <= right - row_width / 2.0 - EPSILON
            for left, right in zip(row_centers, row_centers[1:])
        )
        _require(start_in_corridor, "start.y_m must be inside a clear corridor", errors)
        _require(x_min <= start_x <= x_max, "start.x_m is outside the field", errors)
        _require(y_min <= start_y <= y_max, "start.y_m is outside the field", errors)

    _require(robot_width < metrics.get("min_clear_corridor_m", 0.0), "robot footprint does not fit the corridor", errors)
    row_base = 0.0
    row_top_height = row_base + row_height
    _require(row_base <= lidar_height <= row_top_height, "lidar height does not intersect crop rows", errors)

    return errors, metrics


def _parse_pose(model: ET.Element) -> tuple[float, float, float]:
    pose = model.findtext("pose", default="").split()
    if len(pose) < 3:
        raise ValueError(f"model {model.get('name')} has an invalid pose")
    return float(pose[0]), float(pose[1]), float(pose[2])


def _box_size(model: ET.Element) -> tuple[float, float, float]:
    size = model.find("./link/collision/geometry/box/size")
    if size is None:
        raise ValueError(f"model {model.get('name')} has no collision box")
    values = size.text.split()
    if len(values) != 3:
        raise ValueError(f"model {model.get('name')} has an invalid box size")
    return tuple(float(value) for value in values)


def validate_world(layout: dict, world_path: Path) -> list[str]:
    """Check that the SDF world contains the layout's field and rows."""

    errors: list[str] = []
    try:
        root = ET.parse(world_path).getroot()
    except (OSError, ET.ParseError) as exc:
        return [f"cannot parse world {world_path}: {exc}"]

    _require(root.tag == "sdf", "world root must be <sdf>", errors)
    world = root.find("world")
    _require(world is not None, "world file has no <world>", errors)
    if world is None:
        return errors

    expected_name = "spore_patrol_farmland_8x6"
    _require(world.get("name") == expected_name, f"world name must be {expected_name}", errors)
    models = {model.get("name"): model for model in world.findall("model")}
    required_models = {
        "soil",
        "field_boundary_west",
        "field_boundary_east",
        "field_boundary_south",
        "field_boundary_north",
        "crop_row_1",
        "crop_row_2",
        "crop_row_3",
    }
    _require(required_models <= models.keys(), "world is missing canonical soil, boundary, or row models", errors)

    field = layout.get("field", {})
    rows = layout.get("rows", {})
    try:
        soil_size = _box_size(models["soil"])
        _require(
            all(abs(actual - expected) <= EPSILON for actual, expected in zip(soil_size, (field["length_m"], field["width_m"], field["soil_thickness_m"]))),
            "soil box does not match layout",
            errors,
        )
        row_centers = rows["center_y_m"]
        for index, expected_y in enumerate(row_centers, start=1):
            model = models[f"crop_row_{index}"]
            pose_x, pose_y, pose_z = _parse_pose(model)
            size_x, size_y, size_z = _box_size(model)
            _require(abs(pose_x) <= EPSILON, f"crop_row_{index} x pose must be 0", errors)
            _require(abs(pose_y - expected_y) <= EPSILON, f"crop_row_{index} y pose does not match layout", errors)
            _require(abs(pose_z - rows["height_m"] / 2.0) <= EPSILON, f"crop_row_{index} z pose is invalid", errors)
            _require(abs(size_x - rows["length_m"]) <= EPSILON, f"crop_row_{index} length does not match layout", errors)
            _require(abs(size_y - rows["width_m"]) <= EPSILON, f"crop_row_{index} width does not match layout", errors)
            _require(abs(size_z - rows["height_m"]) <= EPSILON, f"crop_row_{index} height does not match layout", errors)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"world/layout comparison failed: {exc}")

    return errors


def load_layout(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("layout root must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    args = parser.parse_args(argv)

    try:
        layout = load_layout(args.layout)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL layout: {exc}")
        return 1

    errors, metrics = validate_layout(layout)
    errors.extend(validate_world(layout, args.world))
    if errors:
        print("FAIL simulated farmland layout")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS simulated farmland layout")
    print(f"- field={layout['field']['length_m']:.1f}x{layout['field']['width_m']:.1f} m")
    print(f"- rows={layout['rows']['count']} clear_corridor={metrics['min_clear_corridor_m']:.2f} m")
    print(f"- headland={metrics['headland_m']:.2f} m side_clearance={metrics['side_clearance_m']:.2f} m")
    print(f"- world={args.world}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
