import pandas as pd
import pytest
from shapely.geometry import box

from findfire.response import response_for_zone, response_table, zone_centre

STATIONS = pd.read_csv("tests/data/sample_stations.csv")


def make_zone(zone_id=1, status="active", area_ha=100.0):
    # small square near Tizi Ouzou, in lon/lat
    return dict(zone_id=zone_id, status=status, area_ha=area_ha,
                geometry=box(4.00, 36.70, 4.01, 36.71))


def test_zone_centre_is_lat_lon():
    lat, lon = zone_centre(make_zone())
    assert lat == pytest.approx(36.705, abs=1e-6)
    assert lon == pytest.approx(4.005, abs=1e-6)


def test_inactive_zone_gets_no_plan():
    assert response_for_zone(make_zone(status="inactive"), STATIONS) is None


def test_active_zone_gets_water_and_station():
    r = response_for_zone(make_zone(), STATIONS)
    assert r["zone_id"] == 1
    assert r["nearest_station"] == "SAMPLE Tizi Ouzou"
    assert r["volume_l"] > 0
    assert r["severity"] == "medium"


def test_bigger_zone_needs_more_loads():
    small = response_for_zone(make_zone(area_ha=20), STATIONS)
    big = response_for_zone(make_zone(area_ha=500), STATIONS)
    assert big["loads_needed"] > small["loads_needed"]


def test_response_table_skips_inactive_zones():
    zones = [make_zone(1, "active", 50), make_zone(2, "inactive", 900), make_zone(3, "new", 300)]
    table = response_table(zones, STATIONS)
    assert list(table.zone_id) == [3, 1]


def test_geometry_that_is_not_lon_lat_is_rejected():
    zone = make_zone()
    zone["geometry"] = box(500000, 4000000, 501000, 4001000)   # looks like UTM metres
    with pytest.raises(ValueError):
        response_for_zone(zone, STATIONS)


def test_no_stations_raises():
    with pytest.raises(ValueError):
        response_for_zone(make_zone(), STATIONS.iloc[0:0])


def test_empty_zone_list_gives_empty_table():
    assert response_table([], STATIONS).empty

def test_table_is_sorted_by_severity_then_area():
    zones = [make_zone(1, "active", 5), make_zone(2, "active", 50), make_zone(3, "active", 400)]
    table = response_table(zones, STATIONS)
    assert list(table.severity) == ["critical", "medium", "low"]
    assert list(table.zone_id) == [3, 2, 1]
