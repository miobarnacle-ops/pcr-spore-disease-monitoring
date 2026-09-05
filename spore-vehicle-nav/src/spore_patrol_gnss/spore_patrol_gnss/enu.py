"""WGS84 geodetic to local ENU conversion, independent of ROS."""

from __future__ import annotations

import math
from dataclasses import dataclass

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def _finite(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


@dataclass(frozen=True)
class EnuOrigin:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    frame_id: str = "field"

    def __post_init__(self) -> None:
        latitude = _finite(self.latitude_deg, "origin latitude")
        longitude = _finite(self.longitude_deg, "origin longitude")
        altitude = _finite(self.altitude_m, "origin altitude")
        if not -90.0 <= latitude <= 90.0:
            raise ValueError("origin latitude out of range")
        if not -180.0 <= longitude <= 180.0:
            raise ValueError("origin longitude out of range")
        if not self.frame_id:
            raise ValueError("origin frame_id must not be empty")
        object.__setattr__(self, "latitude_deg", latitude)
        object.__setattr__(self, "longitude_deg", longitude)
        object.__setattr__(self, "altitude_m", altitude)


def geodetic_to_ecef(latitude_deg: float, longitude_deg: float, altitude_m: float) -> tuple[float, float, float]:
    latitude = math.radians(_finite(latitude_deg, "latitude"))
    longitude = math.radians(_finite(longitude_deg, "longitude"))
    altitude = _finite(altitude_m, "altitude")
    if not -math.pi / 2 <= latitude <= math.pi / 2:
        raise ValueError("latitude out of range")
    if not -math.pi <= longitude <= math.pi:
        raise ValueError("longitude out of range")
    sin_lat, cos_lat = math.sin(latitude), math.cos(latitude)
    radius = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    return (
        (radius + altitude) * cos_lat * math.cos(longitude),
        (radius + altitude) * cos_lat * math.sin(longitude),
        (radius * (1.0 - WGS84_E2) + altitude) * sin_lat,
    )


def geodetic_to_enu(latitude_deg: float, longitude_deg: float, altitude_m: float, origin: EnuOrigin) -> tuple[float, float, float]:
    """Convert WGS84 latitude/longitude/height to metres in origin ENU."""
    lat0 = math.radians(origin.latitude_deg)
    lon0 = math.radians(origin.longitude_deg)
    x, y, z = geodetic_to_ecef(latitude_deg, longitude_deg, altitude_m)
    x0, y0, z0 = geodetic_to_ecef(origin.latitude_deg, origin.longitude_deg, origin.altitude_m)
    dx, dy, dz = x - x0, y - y0, z - z0
    east = -math.sin(lon0) * dx + math.cos(lon0) * dy
    north = -math.sin(lat0) * math.cos(lon0) * dx - math.sin(lat0) * math.sin(lon0) * dy + math.cos(lat0) * dz
    up = math.cos(lat0) * math.cos(lon0) * dx + math.cos(lat0) * math.sin(lon0) * dy + math.sin(lat0) * dz
    return east, north, up


__all__ = ["EnuOrigin", "geodetic_to_ecef", "geodetic_to_enu"]
