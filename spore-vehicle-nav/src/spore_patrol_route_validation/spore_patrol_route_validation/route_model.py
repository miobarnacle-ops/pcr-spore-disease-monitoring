"""Parsing and validation of ``route_v1.json`` task files.

Input
-----
A ``route_v1.json`` document (a plain ``dict``) with the frozen schema defined
in ``spore-monitor-web/ROUTE_SCHEMA.md``::

    {
      "schema_version": "1.0",
      "frame_id": "field",
      "coordinate_type": "local_enu",
      "unit": "m",
      "field_polygon_m": [...],
      "sampling_points": [...],
      "path": [
        {"seq": 0, "x_m": 1.2, "y_m": 0.8, "yaw_rad": null,
         "type": "sampling", "round": 1, "sample_id": "R1-P1",
         "speed_limit_mps": 0.12, "tolerance_m": 0.2},
        ...
      ]
    }

Output
------
A :class:`Route` containing typed :class:`Waypoint` objects (``yaw_rad`` and
``sample_id`` become ``None`` when ``null``).

Completion criteria
-------------------
Parsing succeeds *only* for a fully valid document.  A :class:`ValueError` is
raised for missing/invalid top-level or waypoint fields, an out-of-range
``speed_limit_mps`` (not in ``(0, speed cap]``, default cap ``0.30 m/s`` from
the chassis limit), or a negative ``tolerance_m``.  Coordinates must be finite
numbers; the frozen ``frame_id``/``coordinate_type``/``unit`` are enforced.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Chassis speed cap (see spore-patrol-robot base_driver max_linear_mps logic
# and CONVENTIONS §5).  The web exporter never emits above 0.12 m/s, but the
# vehicle refuses anything above this ceiling.
MAX_SPEED_LIMIT_MPS: float = 0.30

VALID_WAYPOINT_TYPES = frozenset({"start", "transit", "sampling", "turn", "return"})

# Frozen top-level frame / coordinate / unit values (CONVENTIONS §2).
SCHEMA_VERSION = "1.0"
FRAME_ID = "field"
COORDINATE_TYPE = "local_enu"
UNIT = "m"


@dataclass(frozen=True)
class Waypoint:
    """A single validated route waypoint (``field`` frame, metres)."""

    seq: int
    x_m: float
    y_m: float
    yaw_rad: Optional[float]
    type: str
    round: int
    sample_id: Optional[str]
    speed_limit_mps: float
    tolerance_m: float

    @property
    def is_sampling(self) -> bool:
        return self.type == "sampling"


@dataclass(frozen=True)
class Route:
    """A validated ``route_v1.json`` task."""

    schema_version: str
    frame_id: str
    coordinate_type: str
    unit: str
    field_polygon_m: List[Any]
    sampling_points: List[Any]
    path: List[Waypoint]

    @property
    def waypoints(self) -> List[Waypoint]:
        return self.path


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return number


def _optional_number(value: Any, name: str) -> Optional[float]:
    if value is None:
        return None
    return _finite_number(value, name)


def _parse_waypoint(obj: Any, index: int, max_speed_limit_mps: float) -> Waypoint:
    _require(isinstance(obj, dict), f"path[{index}] must be an object, got {obj!r}")
    _require("seq" in obj, f"path[{index}] missing 'seq'")
    _require("x_m" in obj, f"path[{index}] missing 'x_m'")
    _require("y_m" in obj, f"path[{index}] missing 'y_m'")
    _require("yaw_rad" in obj, f"path[{index}] missing 'yaw_rad'")
    _require("type" in obj, f"path[{index}] missing 'type'")
    _require("round" in obj, f"path[{index}] missing 'round'")
    _require("sample_id" in obj, f"path[{index}] missing 'sample_id'")
    _require(
        "speed_limit_mps" in obj, f"path[{index}] missing 'speed_limit_mps'"
    )
    _require("tolerance_m" in obj, f"path[{index}] missing 'tolerance_m'")

    seq = obj["seq"]
    _require(
        isinstance(seq, int) and not isinstance(seq, bool),
        f"path[{index}].seq must be an int, got {seq!r}",
    )

    x_m = _finite_number(obj["x_m"], f"path[{index}].x_m")
    y_m = _finite_number(obj["y_m"], f"path[{index}].y_m")
    yaw_rad = _optional_number(obj["yaw_rad"], f"path[{index}].yaw_rad")

    wtype = obj["type"]
    _require(
        isinstance(wtype, str) and wtype in VALID_WAYPOINT_TYPES,
        f"path[{index}].type must be one of {sorted(VALID_WAYPOINT_TYPES)}, "
        f"got {wtype!r}",
    )

    round_ = obj["round"]
    _require(
        isinstance(round_, int) and not isinstance(round_, bool) and round_ >= 0,
        f"path[{index}].round must be a non-negative int, got {round_!r}",
    )

    sample_id = obj["sample_id"]
    _require(
        sample_id is None or isinstance(sample_id, str),
        f"path[{index}].sample_id must be a string or null, got {sample_id!r}",
    )

    speed = _finite_number(obj["speed_limit_mps"], f"path[{index}].speed_limit_mps")
    _require(
        0.0 < speed <= max_speed_limit_mps,
        f"path[{index}].speed_limit_mps={speed} out of range "
        f"(0, {max_speed_limit_mps}]",
    )

    tolerance = _finite_number(obj["tolerance_m"], f"path[{index}].tolerance_m")
    _require(
        tolerance >= 0.0, f"path[{index}].tolerance_m={tolerance} must be >= 0"
    )

    return Waypoint(
        seq=seq,
        x_m=x_m,
        y_m=y_m,
        yaw_rad=yaw_rad,
        type=wtype,
        round=round_,
        sample_id=sample_id,
        speed_limit_mps=speed,
        tolerance_m=tolerance,
    )


def parse_route(
    data: Any, max_speed_limit_mps: float = MAX_SPEED_LIMIT_MPS
) -> Route:
    """Parse and validate a route document (dict). Raises ``ValueError``."""
    _require(isinstance(data, dict), f"route must be a JSON object, got {type(data)}")
    required = (
        "schema_version",
        "frame_id",
        "coordinate_type",
        "unit",
        "field_polygon_m",
        "sampling_points",
        "path",
    )
    for key in required:
        _require(key in data, f"route missing top-level field '{key}'")

    _require(
        data["schema_version"] == SCHEMA_VERSION,
        f"schema_version must be '{SCHEMA_VERSION}', got {data['schema_version']!r}",
    )
    _require(
        data["frame_id"] == FRAME_ID,
        f"frame_id must be '{FRAME_ID}', got {data['frame_id']!r}",
    )
    _require(
        data["coordinate_type"] == COORDINATE_TYPE,
        f"coordinate_type must be '{COORDINATE_TYPE}', "
        f"got {data['coordinate_type']!r}",
    )
    _require(
        data["unit"] == UNIT, f"unit must be '{UNIT}', got {data['unit']!r}"
    )

    polygon = data["field_polygon_m"]
    _require(
        isinstance(polygon, list),
        f"field_polygon_m must be a list, got {type(polygon)}",
    )
    sampling_points = data["sampling_points"]
    _require(
        isinstance(sampling_points, list),
        f"sampling_points must be a list, got {type(sampling_points)}",
    )

    raw_path = data["path"]
    _require(isinstance(raw_path, list), f"path must be a list, got {type(raw_path)}")
    _require(len(raw_path) > 0, "path must not be empty")

    path = [
        _parse_waypoint(obj, i, max_speed_limit_mps)
        for i, obj in enumerate(raw_path)
    ]
    for index, waypoint in enumerate(path):
        _require(
            waypoint.seq == index,
            f"path[{index}].seq={waypoint.seq} must be continuous and start at 0",
        )
        _require(
            not waypoint.is_sampling or bool(waypoint.sample_id),
            f"path[{index}] sampling waypoint must have sample_id",
        )

    return Route(
        schema_version=data["schema_version"],
        frame_id=data["frame_id"],
        coordinate_type=data["coordinate_type"],
        unit=data["unit"],
        field_polygon_m=polygon,
        sampling_points=sampling_points,
        path=path,
    )


def load_route(
    path: str, max_speed_limit_mps: float = MAX_SPEED_LIMIT_MPS
) -> Route:
    """Load and validate a ``route_v1.json`` file from disk."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_route(document, max_speed_limit_mps=max_speed_limit_mps)


__all__ = [
    "MAX_SPEED_LIMIT_MPS",
    "VALID_WAYPOINT_TYPES",
    "FRAME_ID",
    "COORDINATE_TYPE",
    "UNIT",
    "Waypoint",
    "Route",
    "parse_route",
    "load_route",
]
