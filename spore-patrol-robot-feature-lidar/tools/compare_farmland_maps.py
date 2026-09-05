#!/usr/bin/env python3
"""Compare two canonical simulated farmland maps from repeated runs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys


TOOLS_DIRECTORY = Path(__file__).resolve().parent
if str(TOOLS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIRECTORY))

from validate_farmland_map import check_rows  # noqa: E402
from validate_saved_map import inspect_map  # noqa: E402


@dataclass(frozen=True)
class MapSummary:
    path: Path
    row_centers: tuple[float, ...]
    row_coverages: tuple[float, ...]
    row_spreads: tuple[float, ...]


def compare_maps(
    first_yaml: Path,
    second_yaml: Path,
    layout_path: Path,
    *,
    max_row_shift: float = 0.15,
) -> tuple[MapSummary, MapSummary, list[str]]:
    summaries: list[MapSummary] = []
    errors: list[str] = []
    for yaml_path in (first_yaml, second_yaml):
        try:
            checks, row_errors = check_rows(yaml_path, layout_path)
            stats = inspect_map(yaml_path)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f"{yaml_path}: {exc}")
            continue
        if row_errors:
            errors.extend(f"{yaml_path.name}: {error}" for error in row_errors)
        summaries.append(
            MapSummary(
                yaml_path,
                tuple(check.median_y for check in checks if check.median_y is not None),
                tuple(check.coverage for check in checks),
                tuple(check.spread_y for check in checks if check.spread_y is not None),
            )
        )
        if stats.resolution <= 0:
            errors.append(f"{yaml_path.name}: invalid map resolution")

    if len(summaries) == 2:
        first, second = summaries
        if len(first.row_centers) != len(second.row_centers):
            errors.append("repeated maps contain different numbers of detected rows")
        else:
            for index, (first_y, second_y) in enumerate(
                zip(first.row_centers, second.row_centers), start=1
            ):
                shift = abs(first_y - second_y)
                if shift > max_row_shift:
                    errors.append(
                        f"row {index} center shift {shift:.3f} m exceeds "
                        f"{max_row_shift:.3f} m"
                    )
    if len(summaries) < 2:
        errors.append("two readable map summaries are required")
    return summaries[0], summaries[1], errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_yaml", type=Path)
    parser.add_argument("second_yaml", type=Path)
    parser.add_argument(
        "--layout",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src/spore_patrol_sim/config/farmland_layout.json",
    )
    parser.add_argument("--max-row-shift", type=float, default=0.15)
    args = parser.parse_args(argv)

    try:
        first, second, errors = compare_maps(
            args.first_yaml,
            args.second_yaml,
            args.layout,
            max_row_shift=args.max_row_shift,
        )
    except (IndexError, ValueError) as exc:
        print(f"FAIL repeated farmland maps: {exc}")
        return 1

    if errors:
        print("FAIL repeated farmland maps")
        for error in errors:
            print(f"- {error}")
        return 1

    shifts = [
        abs(first_y - second_y)
        for first_y, second_y in zip(first.row_centers, second.row_centers)
    ]
    print("PASS repeated farmland map consistency")
    print(
        "- row center shifts="
        + ", ".join(f"{shift:.3f}m" for shift in shifts)
        + f" (limit {args.max_row_shift:.3f}m)"
    )
    print(
        "- run1 coverage="
        + ", ".join(f"{value:.1%}" for value in first.row_coverages)
        + "; run2 coverage="
        + ", ".join(f"{value:.1%}" for value in second.row_coverages)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
