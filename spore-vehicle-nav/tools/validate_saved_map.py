#!/usr/bin/env python3
"""Perform structural and coverage checks on a saved Nav2 map.

This is an offline checker for ``map.yaml`` + ``map.pgm``. It deliberately
does not need ROS, OpenCV, or Pillow, so the map artifact can be checked on a
development PC immediately after copying it from a ROS 2 machine.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import re
import sys


@dataclass(frozen=True)
class PgmImage:
    width: int
    height: int
    max_value: int
    pixels: bytes


@dataclass(frozen=True)
class MapStats:
    width: int
    height: int
    resolution: float
    occupied: int
    free: int
    unknown: int

    @property
    def total(self) -> int:
        return self.width * self.height

    @property
    def known_fraction(self) -> float:
        return (self.occupied + self.free) / max(self.total, 1)

    @property
    def occupied_fraction(self) -> float:
        return self.occupied / max(self.total, 1)


def _pgm_token(data: bytes, offset: int) -> tuple[bytes, int]:
    length = len(data)
    while offset < length:
        if data[offset] == ord("#"):
            newline = data.find(b"\n", offset)
            offset = length if newline < 0 else newline + 1
        elif data[offset] in b" \t\r\n":
            offset += 1
        else:
            break
    start = offset
    while offset < length and data[offset] not in b" \t\r\n#":
        offset += 1
    if start == offset:
        raise ValueError("unexpected end of PGM header")
    return data[start:offset], offset


def read_pgm(path: Path) -> PgmImage:
    data = path.read_bytes()
    magic, offset = _pgm_token(data, 0)
    width_token, offset = _pgm_token(data, offset)
    height_token, offset = _pgm_token(data, offset)
    max_token, offset = _pgm_token(data, offset)
    try:
        width = int(width_token)
        height = int(height_token)
        max_value = int(max_token)
    except ValueError as exc:
        raise ValueError(f"invalid PGM header in {path}") from exc
    if width <= 0 or height <= 0 or not 0 < max_value <= 255:
        raise ValueError(f"invalid PGM dimensions or max value in {path}")

    if magic == b"P5":
        # The single separator after max_value belongs to the header. Do not
        # strip arbitrary bytes from the binary pixel stream.
        if offset >= len(data) or data[offset] not in b" \t\r\n":
            raise ValueError(f"missing P5 header separator in {path}")
        offset += 1
        if data[offset - 1] == ord("\r") and offset < len(data) and data[offset] == ord("\n"):
            offset += 1
        pixels = data[offset:]
    elif magic == b"P2":
        values: list[int] = []
        while True:
            try:
                token, offset = _pgm_token(data, offset)
            except ValueError:
                break
            values.append(int(token))
        if any(value < 0 or value > max_value for value in values):
            raise ValueError(f"P2 pixel outside max value in {path}")
        pixels = bytes(values)
    else:
        raise ValueError(f"{path} is not a P2/P5 PGM image")

    expected = width * height
    if len(pixels) != expected:
        raise ValueError(
            f"{path} contains {len(pixels)} pixels; expected {expected}"
        )
    return PgmImage(width, height, max_value, pixels)


def read_map_yaml(path: Path) -> tuple[Path, float]:
    text = path.read_text(encoding="utf-8")
    image_match = re.search(r"^\s*image\s*:\s*(\S+)\s*$", text, re.MULTILINE)
    resolution_match = re.search(
        r"^\s*resolution\s*:\s*([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\s*$",
        text,
        re.MULTILINE,
    )
    if image_match is None or resolution_match is None:
        raise ValueError(f"{path} must contain image and resolution fields")
    image_path = Path(image_match.group(1))
    if not image_path.is_absolute():
        image_path = path.parent / image_path
    resolution = float(resolution_match.group(1))
    if not math.isfinite(resolution) or resolution <= 0:
        raise ValueError(f"{path} has an invalid resolution")
    return image_path, resolution


def inspect_map(yaml_path: Path) -> MapStats:
    image_path, resolution = read_map_yaml(yaml_path)
    image = read_pgm(image_path)
    # Nav2 map_saver_cli convention: 0 is occupied, 254 is free and 205 is
    # unknown. Treat intermediate values as unknown conservatively.
    occupied = sum(value <= 100 for value in image.pixels)
    free = sum(value >= 240 for value in image.pixels)
    unknown = image.width * image.height - occupied - free
    return MapStats(image.width, image.height, resolution, occupied, free, unknown)


def validate_map(
    stats: MapStats,
    *,
    field_length: float = 8.0,
    field_width: float = 6.0,
    coverage_tolerance: float = 0.50,
    min_known_fraction: float = 0.25,
    min_occupied_fraction: float = 0.005,
) -> list[str]:
    errors: list[str] = []
    coverage_x = stats.width * stats.resolution
    coverage_y = stats.height * stats.resolution
    if coverage_x + coverage_tolerance < field_length:
        errors.append(f"map x coverage {coverage_x:.2f} m is below field length")
    if coverage_y + coverage_tolerance < field_width:
        errors.append(f"map y coverage {coverage_y:.2f} m is below field width")
    if stats.known_fraction < min_known_fraction:
        errors.append(
            f"known fraction {stats.known_fraction:.3f} is below {min_known_fraction:.3f}"
        )
    if stats.occupied_fraction < min_occupied_fraction:
        errors.append(
            f"occupied fraction {stats.occupied_fraction:.3f} is below "
            f"{min_occupied_fraction:.3f}; map may be blank"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_yaml", type=Path, help="saved Nav2 map YAML file")
    parser.add_argument("--field-length", type=float, default=8.0)
    parser.add_argument("--field-width", type=float, default=6.0)
    parser.add_argument("--coverage-tolerance", type=float, default=0.50)
    parser.add_argument("--min-known-fraction", type=float, default=0.25)
    parser.add_argument("--min-occupied-fraction", type=float, default=0.005)
    args = parser.parse_args(argv)
    try:
        stats = inspect_map(args.map_yaml)
    except (OSError, ValueError) as exc:
        print(f"FAIL saved map: {exc}")
        return 1
    errors = validate_map(
        stats,
        field_length=args.field_length,
        field_width=args.field_width,
        coverage_tolerance=args.coverage_tolerance,
        min_known_fraction=args.min_known_fraction,
        min_occupied_fraction=args.min_occupied_fraction,
    )
    if errors:
        print("FAIL saved map")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS saved map")
    print(
        f"- grid={stats.width}x{stats.height} "
        f"coverage={stats.width * stats.resolution:.2f}x"
        f"{stats.height * stats.resolution:.2f} m "
        f"resolution={stats.resolution:.3f} m/cell"
    )
    print(
        f"- occupied={stats.occupied}({stats.occupied_fraction:.1%}) "
        f"free={stats.free}({stats.free / max(stats.total, 1):.1%}) "
        f"unknown={stats.unknown}({stats.unknown / max(stats.total, 1):.1%})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
