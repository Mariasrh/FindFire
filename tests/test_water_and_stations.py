import pandas as pd

from findfire.stations.nearest_station import haversine_km, nearest_stations, plan_response
from findfire.water.water_demand import compute_water_demand, severity_from_area


def test_bigger_fire_needs_more_water():
    small = compute_water_demand(10, "forest")
    big = compute_water_demand(100, "forest")
    assert big.volume_l > small.volume_l > 0


def test_severity_levels():
    assert severity_from_area(5) == "low"
    assert severity_from_area(50) == "medium"
    assert severity_from_area(500) == "critical"


def test_strong_wind_increases_demand():
    calm = compute_water_demand(50, "scrub", wind_kmh=5)
    windy = compute_water_demand(50, "scrub", wind_kmh=40)
    assert windy.flow_l_min > calm.flow_l_min


def test_unknown_terrain_raises():
    try:
        compute_water_demand(10, "ice")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_haversine_algiers_oran():
    assert 340 < haversine_km(36.75, 3.06, 35.70, -0.63) < 365


def test_nearest_station_and_plan():
    stations = pd.read_csv("tests/data/sample_stations.csv")
    close = nearest_stations(36.71, 4.05, stations, n=1)
    assert close.iloc[0]["wilaya"] == "Tizi Ouzou"
    plan = plan_response(36.71, 4.05, volume_l=20_000, stations=stations)
    assert plan["loads_needed"] == 5
    assert plan["unmet_loads"] == 0


def test_huge_demand_needs_reinforcement():
    stations = pd.read_csv("tests/data/sample_stations.csv")
    plan = plan_response(36.71, 4.05, volume_l=10_000_000, stations=stations)
    assert plan["needs_reinforcement"] is True

def test_demand_is_capped_for_huge_fires():
    huge = compute_water_demand(5000, "forest")
    bigger = compute_water_demand(50000, "forest")
    assert huge.front_attacked_m == bigger.front_attacked_m
    assert huge.flow_l_min == bigger.flow_l_min


def test_small_fire_attacks_the_whole_perimeter():
    d = compute_water_demand(2, "forest")
    assert d.front_share == 1.0


def test_big_fire_attacks_only_part_of_the_perimeter():
    d = compute_water_demand(2000, "forest")
    assert 0 < d.front_share < 1


def test_parameters_are_marked_as_unconfirmed():
    assert "placeholder" in compute_water_demand(10, "forest").parameters_status


def test_trucks_needed_from_flow():
    from findfire.stations.nearest_station import plan_trucks
    stations = pd.read_csv("tests/data/sample_stations.csv")
    plan = plan_trucks(36.71, 4.05, flow_l_min=9000, stations=stations, pump_l_min=2000)
    assert plan["trucks_needed"] == 5
    assert plan["unmet_trucks"] == 0
    assert plan["needs_reinforcement"] is False


def test_huge_flow_needs_reinforcement_in_trucks():
    from findfire.stations.nearest_station import plan_trucks
    stations = pd.read_csv("tests/data/sample_stations.csv")
    plan = plan_trucks(36.71, 4.05, flow_l_min=1_000_000, stations=stations, pump_l_min=2000)
    assert plan["unmet_trucks"] > 0
    assert plan["needs_reinforcement"] is True


def test_autonomy_is_tank_over_pump_flow():
    from findfire.stations.nearest_station import plan_trucks
    stations = pd.read_csv("tests/data/sample_stations.csv")
    plan = plan_trucks(36.71, 4.05, flow_l_min=4000, stations=stations, pump_l_min=2000)
    assert plan["autonomy_min"] == 2.0


def test_trucks_come_from_more_than_three_stations():
    from findfire.stations.nearest_station import plan_trucks
    stations = pd.read_csv("tests/data/sample_stations.csv")
    plan = plan_trucks(36.71, 4.05, flow_l_min=24000, stations=stations, pump_l_min=2000, max_eta_min=1000)
    assert plan["trucks_sent"] > 9


def test_stations_beyond_the_max_eta_are_ignored():
    from findfire.stations.nearest_station import plan_trucks
    stations = pd.read_csv("tests/data/sample_stations.csv")
    plan = plan_trucks(36.71, 4.05, flow_l_min=24000, stations=stations, pump_l_min=2000, max_eta_min=20)
    assert all(a["eta_min"] <= 20 for a in plan["assignments"])
    assert plan["needs_reinforcement"] is True
