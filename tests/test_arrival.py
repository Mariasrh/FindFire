import math

import pandas as pd
from shapely.geometry import box

from findfire.dashboard.cards import build_cards, flow_at, zones_from_state

STATIONS = pd.read_csv("tests/data/sample_stations.csv")


def test_flow_at_interpolates_between_now_and_the_forecast_steps():
    card = {"flow_l_min": 10000.0, "forecast": [{"minutes": 30, "flow_l_min": 16000.0}, {"minutes": 60, "flow_l_min": 20000.0}]}
    assert flow_at(card, 0) == 10000.0
    assert flow_at(card, 15) == 13000.0
    assert flow_at(card, 45) == 18000.0
    assert flow_at(card, 500) == 20000.0


def test_flow_at_without_forecast_is_the_flow_now():
    assert flow_at({"flow_l_min": 12345.0, "forecast": []}, 40) == 12345.0


def small_fire():
    return [dict(zone_id=1, status="active", area_ha=3.0, new_hotspots=2, geometry=box(4.000, 36.700, 4.002, 36.702))]


def test_a_growing_fire_needs_more_water_when_the_truck_arrives():
    forecast = [{"zone_id": 1, "wind_speed_ms": 6.0, "wind_from_deg": 270.0, "spread_to_deg": 90.0,
                 "steps": [{"minutes": 30, "area_ha": 40.0, "geometry": box(4.0, 36.7, 4.02, 36.71)},
                           {"minutes": 60, "area_ha": 90.0, "geometry": box(4.0, 36.7, 4.03, 36.72)},
                           {"minutes": 120, "area_ha": 200.0, "geometry": box(4.0, 36.7, 4.05, 36.74)}]}]
    with_forecast, _, _ = build_cards(small_fire(), STATIONS, forecast)
    without, _, _ = build_cards(small_fire(), STATIONS, None)
    a, b = with_forecast[0], without[0]
    assert a["arrival_min"] == a["nearest_eta_min"] and a["arrival_min"] > 0
    assert a["flow_at_arrival_l_min"] > a["flow_l_min"] and b["flow_at_arrival_l_min"] == b["flow_l_min"]
    assert a["trucks_needed_now"] >= math.ceil(a["flow_l_min"] / 2000.0)
    assert a["trucks_needed_now"] >= b["trucks_needed_now"]