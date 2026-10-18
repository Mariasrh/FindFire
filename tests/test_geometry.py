import pytest

from findfire.zones.geometry import utm_epsg, zone_geometry


def test_one_km_square_is_100_ha_and_4_km_around():
    _, area_ha, perimeter_km = zone_geometry([4.0], [36.0], [1.0], [1.0])
    assert area_ha == pytest.approx(100, abs=1)
    assert perimeter_km == pytest.approx(4, abs=0.05)


def test_same_square_in_two_neighbouring_utm_zones_agrees():
    _, in_31, _ = zone_geometry([5.9], [36.0], [1.0], [1.0], epsg=32631)
    _, in_32, _ = zone_geometry([5.9], [36.0], [1.0], [1.0], epsg=32632)
    assert abs(in_31 - in_32) / in_31 < 0.01


def test_utm_zone_across_algeria():
    assert utm_epsg(-7.0, 30.0) == 32629   # far west
    assert utm_epsg(-1.0, 36.0) == 32630
    assert utm_epsg(4.5, 36.0) == 32631
    assert utm_epsg(8.5, 36.0) == 32632


def test_two_close_pixels_form_one_polygon():
    polygon, area_ha, _ = zone_geometry([4.0, 4.006], [36.0, 36.0], [0.4, 0.4], [0.4, 0.4])
    assert polygon.geom_type == "Polygon"                      # the gap between them is closed
    assert 32 < area_ha < 40                                    # two 0.4 km pixels (2 x 16 ha) plus the closed gap