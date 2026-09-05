"""Small, dependency-free NMEA-0183 parser for the ATGM336H adapter.

The parser is intentionally separate from ROS and serial I/O so protocol
fixtures can be tested on a machine without a GNSS receiver.  ``quality`` is
an explicit semantic value: ``single`` is ordinary autonomous GNSS and must
not be reported as RTK ``fix``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Union


class NmeaParseError(ValueError):
    """Raised when an NMEA sentence is malformed or unsupported."""


Quality = str


@dataclass(frozen=True)
class NmeaPosition:
    latitude_deg: Optional[float]
    longitude_deg: Optional[float]
    altitude_m: Optional[float]
    utc_time: Optional[str]
    quality: Quality
    raw_quality: Optional[int]
    satellites: Optional[int]
    hdop: Optional[float]
    geoid_separation_m: Optional[float]
    sentence_type: str
    checksum_valid: Optional[bool]

    @property
    def valid(self) -> bool:
        return self.quality != "invalid" and self.latitude_deg is not None and self.longitude_deg is not None


@dataclass(frozen=True)
class NmeaVelocity:
    speed_mps: Optional[float]
    speed_knots: Optional[float]
    speed_kmh: Optional[float]
    course_deg: Optional[float]
    utc_time: Optional[str]
    sentence_type: str
    checksum_valid: Optional[bool]


NmeaRecord = Union[NmeaPosition, NmeaVelocity]


def _optional_float(value: str, name: str) -> Optional[float]:
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise NmeaParseError(f"{name} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise NmeaParseError(f"{name} is not finite: {value!r}")
    return number


def _optional_int(value: str, name: str) -> Optional[int]:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise NmeaParseError(f"{name} is not an integer: {value!r}") from exc


def _coordinate(value: str, hemisphere: str, *, latitude: bool, allow_empty: bool = False) -> Optional[float]:
    if not value and not hemisphere and allow_empty:
        return None
    if not value or hemisphere not in ("N", "S", "E", "W"):
        raise NmeaParseError("coordinate or hemisphere is missing")
    try:
        raw = float(value)
    except ValueError as exc:
        raise NmeaParseError(f"invalid coordinate: {value!r}") from exc
    if not math.isfinite(raw):
        raise NmeaParseError(f"coordinate is not finite: {value!r}")
    degrees = int(raw // 100)
    minutes = raw - degrees * 100
    max_degrees = 90 if latitude else 180
    if degrees > max_degrees or minutes < 0 or minutes >= 60:
        raise NmeaParseError(f"coordinate out of range: {value!r}{hemisphere}")
    result = degrees + minutes / 60.0
    if latitude and result > 90:
        raise NmeaParseError("latitude out of range")
    if hemisphere in ("S", "W"):
        result = -result
    return result


def _checksum(sentence: str) -> tuple[str, Optional[bool]]:
    text = sentence.strip()
    if not text.startswith("$"):
        raise NmeaParseError("NMEA sentence must start with '$'")
    body = text[1:]
    if "*" not in body:
        return body, None
    payload, supplied = body.rsplit("*", 1)
    if len(supplied) != 2:
        raise NmeaParseError("NMEA checksum must contain two hexadecimal digits")
    try:
        expected = int(supplied, 16)
    except ValueError as exc:
        raise NmeaParseError("NMEA checksum is not hexadecimal") from exc
    actual = 0
    for char in payload:
        actual ^= ord(char)
    if actual != expected:
        raise NmeaParseError(
            f"NMEA checksum mismatch: expected {expected:02X}, calculated {actual:02X}"
        )
    return payload, True


def _quality_from_gga(raw: Optional[int]) -> Quality:
    # 1 = autonomous GPS, 2 = differential GNSS; neither is RTK.
    if raw in (1, 2, 3):
        return "single"
    if raw == 4:
        return "fix"
    if raw == 5:
        return "float"
    return "invalid"


def _quality_from_gll(status: str, mode: str) -> Quality:
    if status != "A":
        return "invalid"
    if mode == "F":
        return "float"
    if mode == "R":
        return "fix"
    return "single"


def parse_nmea_sentence(sentence: str, *, require_checksum: bool = False) -> NmeaRecord:
    """Parse one GGA, GLL or VTG sentence.

    Missing checksums are accepted by default because some serial test tools
    omit them; a deployed configuration can set ``require_checksum`` to true.
    Present but incorrect checksums always fail.
    """
    payload, checksum_valid = _checksum(sentence)
    if require_checksum and checksum_valid is None:
        raise NmeaParseError("NMEA checksum is required")
    fields = payload.split(",")
    if not fields or len(fields[0]) < 3:
        raise NmeaParseError("NMEA sentence type is missing")
    sentence_type = fields[0][-3:].upper()

    if sentence_type == "GGA":
        if len(fields) < 10:
            raise NmeaParseError("GGA sentence has too few fields")
        raw_quality = _optional_int(fields[6], "GGA quality")
        return NmeaPosition(
            latitude_deg=_coordinate(fields[2], fields[3], latitude=True, allow_empty=raw_quality in (None, 0)),
            longitude_deg=_coordinate(fields[4], fields[5], latitude=False, allow_empty=raw_quality in (None, 0)),
            altitude_m=_optional_float(fields[9], "GGA altitude"),
            utc_time=fields[1] or None,
            quality=_quality_from_gga(raw_quality),
            raw_quality=raw_quality,
            satellites=_optional_int(fields[7], "GGA satellites"),
            hdop=_optional_float(fields[8], "GGA HDOP"),
            geoid_separation_m=_optional_float(fields[11], "GGA geoid separation") if len(fields) > 11 else None,
            sentence_type=sentence_type,
            checksum_valid=checksum_valid,
        )

    if sentence_type == "GLL":
        if len(fields) < 7:
            raise NmeaParseError("GLL sentence has too few fields")
        mode = fields[7] if len(fields) > 7 else "A"
        return NmeaPosition(
            latitude_deg=_coordinate(fields[1], fields[2], latitude=True, allow_empty=fields[6] != "A"),
            longitude_deg=_coordinate(fields[3], fields[4], latitude=False, allow_empty=fields[6] != "A"),
            altitude_m=None,
            utc_time=fields[5] or None,
            quality=_quality_from_gll(fields[6], mode),
            raw_quality=None,
            satellites=None,
            hdop=None,
            geoid_separation_m=None,
            sentence_type=sentence_type,
            checksum_valid=checksum_valid,
        )

    if sentence_type == "VTG":
        if len(fields) < 8:
            raise NmeaParseError("VTG sentence has too few fields")
        speed_knots = _optional_float(fields[5], "VTG knots")
        speed_kmh = _optional_float(fields[7], "VTG km/h")
        speed_mps = speed_knots * 0.514444 if speed_knots is not None else speed_kmh / 3.6 if speed_kmh is not None else None
        return NmeaVelocity(
            speed_mps=speed_mps,
            speed_knots=speed_knots,
            speed_kmh=speed_kmh,
            course_deg=_optional_float(fields[1], "VTG course"),
            utc_time=None,
            sentence_type=sentence_type,
            checksum_valid=checksum_valid,
        )

    raise NmeaParseError(f"unsupported NMEA sentence: {fields[0]!r}")


__all__ = [
    "NmeaParseError",
    "NmeaPosition",
    "NmeaVelocity",
    "NmeaRecord",
    "parse_nmea_sentence",
]
