import pandas as pd
from shapely.geometry import box, mapping

from findfire.dashboard.cards import dashboard_payload
from findfire.dashboard.dispatch import dispatch
from findfire.dashboard.server import compute_forecast
from findfire.stations.nearest_station import haversine_km, nearest_stations


def stations(rows):
    return pd.DataFrame(rows, columns=["name", "wilaya", "latitude", "longitude", "trucks", "truck_capacity_l"])


def card(zone_id, lat, lon, need, severity="critical", area=500.0, spreading=True):
    return dict(zone_id=zone_id, latitude=lat, longitude=lon, trucks_needed_now=need, severity=severity,
                area_ha=area, spreading=spreading)


def test_vectorised_search_matches_the_scalar_formula():
    st = stations([("A", "x", 36.70, 4.05, 3, 4000), ("B", "x", 36.80, 4.20, 3, 4000), ("C", "x", 35.90, 3.10, 3, 4000)])
    near = nearest_stations(36.71, 4.06, st, n=3)
    assert list(near["name"]) == ["A", "B", "C"]
    assert near.iloc[0]["distance_km"] == round(haversine_km(36.71, 4.06, 36.70, 4.05), 1)


def test_lead_station_is_the_nearest_and_reinforcements_come_after():
    st = stations([("Near", "x", 36.70, 4.05, 3, 4000), ("Far", "x", 36.80, 4.20, 5, 4000)])
    cards = [card(1, 36.71, 4.06, need=6)]
    dispatch(cards, st)
    c = cards[0]
    assert c["lead_station"]["name"] == "Near"
    assert [(a["station"], a["trucks"], a["role"]) for a in c["assignments"]] == [("Near", 3, "lead"), ("Far", 3, "reinforcement")]
    assert c["trucks_sent"] == 6 and c["unmet_trucks"] == 0 and c["needs_reinforcement"] is False


def test_a_truck_is_never_used_for_two_zones():
    st = stations([("Only", "x", 36.70, 4.05, 4, 4000)])
    cards = [card(1, 36.71, 4.06, need=3), card(2, 36.72, 4.07, need=3, severity="medium")]
    out = dispatch(cards, st)
    assert cards[0]["trucks_sent"] == 3 and cards[1]["trucks_sent"] == 1
    assert cards[1]["unmet_trucks"] == 2 and cards[1]["needs_reinforcement"] is True
    assert out["summary"]["trucks_engaged"] == 4 and out["summary"]["trucks_total"] == 4
    assert out["summary"]["fully_served"] == 1 and out["summary"]["partly_served"] == 1


def test_the_most_severe_zone_is_served_first():
    st = stations([("Only", "x", 36.70, 4.05, 2, 4000)])
    cards = [card(1, 36.71, 4.06, need=2, severity="low", area=10), card(2, 36.71, 4.06, need=2, severity="critical")]
    dispatch(cards, st)
    assert cards[1]["trucks_sent"] == 2 and cards[0]["trucks_sent"] == 0


def test_a_zone_that_is_not_spreading_is_watch_only_and_gets_no_truck():
    st = stations([("Only", "x", 36.70, 4.05, 2, 4000)])
    cards = [card(1, 36.71, 4.06, need=2, area=9000, spreading=False), card(2, 36.71, 4.06, need=2, area=50)]
    out = dispatch(cards, st)
    assert cards[1]["trucks_sent"] == 2 and cards[1]["monitoring"] is False
    assert cards[0]["trucks_sent"] == 0 and cards[0]["monitoring"] is True and cards[0]["needs_reinforcement"] is False
    assert cards[0]["unmet_trucks"] == 0 and cards[0]["involved_station_ids"] == []
    assert out["summary"]["zones"] == 1 and out["summary"]["monitoring"] == 1 and out["summary"]["trucks_engaged"] == 2


def test_an_unnamed_osm_station_gets_a_readable_name():
    st = stations([("OSM-1356183694", "x", 36.70, 4.05, 3, 4000)])
    cards = [card(1, 36.71, 4.06, need=2)]
    cards[0]["nearest_station"] = "OSM-1356183694"
    out = dispatch(cards, st)
    assert cards[0]["lead_station"]["name"] == "Unnamed station (OSM-1356183694)"
    assert cards[0]["assignments"][0]["station"] == "Unnamed station (OSM-1356183694)"
    assert cards[0]["nearest_station"] == "Unnamed station (OSM-1356183694)"
    assert out["stations"][0]["name"] == "Unnamed station (OSM-1356183694)"


def test_the_lead_station_still_gets_the_alert_when_it_has_no_free_truck():
    st = stations([("Only", "x", 36.70, 4.05, 1, 4000)])
    cards = [card(1, 36.71, 4.06, need=1), card(2, 36.71, 4.06, need=1, severity="medium")]
    out = dispatch(cards, st)
    assert cards[1]["lead_station"]["name"] == "Only" and cards[1]["involved_station_ids"] == [0]
    assert cards[1]["lead_station"]["free_trucks_left"] == 0 and cards[1]["trucks_sent"] == 0
    assert out["summary"]["not_served"] == 1


def test_stations_too_far_are_not_asked():
    st = stations([("Near", "x", 36.70, 4.05, 1, 4000), ("VeryFar", "x", 33.0, 1.0, 10, 4000)])
    cards = [card(1, 36.71, 4.06, need=5)]
    dispatch(cards, st, max_eta_min=60)
    assert [a["station"] for a in cards[0]["assignments"]] == ["Near"] and cards[0]["unmet_trucks"] == 4


def test_each_zone_alerts_only_its_own_stations_and_the_list_has_positions():
    st = stations([("West", "x", 36.0, 1.0, 5, 4000), ("East", "x", 36.0, 7.0, 5, 4000)])
    cards = [card(1, 36.0, 1.05, need=2), card(2, 36.0, 7.05, need=2)]
    out = dispatch(cards, st)
    assert cards[0]["involved_station_ids"] == [0] and cards[1]["involved_station_ids"] == [1]
    assert {s["name"]: s["zones"] for s in out["stations"]} == {"West": 1, "East": 1}
    assert all(abs(s["latitude"] - 36.0) < 1e-9 and "longitude" in s for s in out["stations"])


def test_empty_zone_list():
    out = dispatch([], stations([("A", "x", 36.0, 4.0, 3, 4000)]))
    assert out["summary"]["zones"] == 0 and out["stations"] == []


def feature(zone_id, status, area_ha, bbox, new_hotspots=None):
    props = {"zone_id": zone_id, "status": status, "area_ha": area_ha}
    if new_hotspots is not None:
        props["new_hotspots"] = new_hotspots
    return {"type": "Feature", "geometry": mapping(box(*bbox)), "properties": props}


def test_the_payload_carries_the_dispatch_the_stations_and_the_spreading_flag():
    st = pd.read_csv("tests/data/sample_stations.csv")
    state = {"zones": [feature(1, "active", 500.0, (4.000, 36.700, 4.004, 36.704), new_hotspots=4),
                       feature(2, "active", 600.0, (4.010, 36.700, 4.014, 36.704), new_hotspots=0),
                       feature(3, "active", 300.0, (4.020, 36.700, 4.024, 36.704))]}
    payload = dashboard_payload(state, st)
    by_id = {c["zone_id"]: c for c in payload["cards"]}
    assert payload["dispatch"]["zones"] == 2 and payload["stations"] and payload["errors"] == []
    assert by_id[1]["spreading"] is True and by_id[2]["spreading"] is False and by_id[3]["spreading"] is True
    assert by_id[2]["new_hotspots"] == 0 and by_id[3]["new_hotspots"] is None
    assert by_id[2]["monitoring"] is True and by_id[1]["monitoring"] is False and payload["dispatch"]["monitoring"] == 1
    assert payload["dispatch"]["trucks_engaged"] <= payload["dispatch"]["trucks_total"]


def test_the_forecast_skips_zones_without_new_hotspots():
    zones = [dict(zone_id=1, status="active", area_ha=30.0, new_hotspots=3, geometry=box(4.0, 36.7, 4.004, 36.704)),
             dict(zone_id=2, status="active", area_ha=30.0, new_hotspots=0, geometry=box(4.1, 36.7, 4.104, 36.704)),
             dict(zone_id=3, status="active", area_ha=30.0, geometry=box(4.2, 36.7, 4.204, 36.704))]
    result = compute_forecast(zones, "shrub", fixed_wind=(6.0, 270.0))
    assert sorted(r["zone_id"] for r in result) == [1, 3]