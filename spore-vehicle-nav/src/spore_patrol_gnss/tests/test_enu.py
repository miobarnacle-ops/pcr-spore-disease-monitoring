import pytest

from spore_patrol_gnss.enu import EnuOrigin, geodetic_to_enu


def test_origin_is_zero_and_small_offsets_are_in_metres():
    origin = EnuOrigin(40.0, 116.0, 50.0)
    assert geodetic_to_enu(40.0, 116.0, 50.0, origin) == pytest.approx((0.0, 0.0, 0.0), abs=1e-7)
    east, north, up = geodetic_to_enu(40.0001, 116.0001, 51.0, origin)
    assert east == pytest.approx(8.54, abs=0.08)
    assert north == pytest.approx(11.12, abs=0.08)
    assert up == pytest.approx(1.0, abs=0.01)


def test_enu_rejects_invalid_origin_and_coordinates():
    with pytest.raises(ValueError, match="latitude"):
        EnuOrigin(91.0, 116.0)
    with pytest.raises(ValueError, match="longitude"):
        geodetic_to_enu(40.0, 181.0, 0.0, EnuOrigin(40.0, 116.0))
