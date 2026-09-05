from pathlib import Path

import pytest

from spore_patrol_gnss.nmea_parser import (
    NmeaParseError,
    NmeaPosition,
    NmeaVelocity,
    parse_nmea_sentence,
)


FIXTURE = Path(__file__).parent / "fixtures" / "atgm336h_nmea.txt"


def test_reported_atgm336h_shaped_fixture_parses_position_and_velocity():
    records = [parse_nmea_sentence(line) for line in FIXTURE.read_text().splitlines()]
    gga, gll, vtg, no_fix_gga, no_fix_gll = records
    assert isinstance(gga, NmeaPosition)
    assert gga.valid
    assert gga.quality == "single"
    assert gga.latitude_deg == pytest.approx(40.0006331667, abs=1e-9)
    assert gga.longitude_deg == pytest.approx(116.3540666667, abs=1e-9)
    assert gga.altitude_m == pytest.approx(51.1)
    assert isinstance(gll, NmeaPosition) and gll.valid
    assert isinstance(vtg, NmeaVelocity)
    assert vtg.speed_mps == pytest.approx(2.0 * 0.514444, rel=1e-6)
    assert vtg.course_deg == pytest.approx(90.0)
    assert isinstance(no_fix_gga, NmeaPosition) and not no_fix_gga.valid
    assert no_fix_gga.latitude_deg is None
    assert isinstance(no_fix_gll, NmeaPosition) and not no_fix_gll.valid


def test_present_bad_checksum_and_required_missing_checksum_are_rejected():
    sentence = "$GNGGA,123519.00,4000.037990,N,11621.244000,E,1,08,0.9,51.1,M,-3.0,M,,*00"
    with pytest.raises(NmeaParseError, match="checksum mismatch"):
        parse_nmea_sentence(sentence)
    without_checksum = sentence.rsplit("*", 1)[0]
    with pytest.raises(NmeaParseError, match="checksum is required"):
        parse_nmea_sentence(without_checksum, require_checksum=True)


def test_unsupported_and_malformed_sentences_fail_closed():
    with pytest.raises(NmeaParseError, match="unsupported"):
        parse_nmea_sentence("$GNRMC,123519.00,A,,,,,,")
    with pytest.raises(NmeaParseError, match="out of range"):
        parse_nmea_sentence("$GNGGA,123519.00,4061.000000,N,11621.244000,E,1,08,0.9,51.1,M,-3.0,M,,")
