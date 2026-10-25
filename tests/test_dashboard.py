import json
import threading
import urllib.request

import pandas as pd
import pytest
from shapely.geometry import box, mapping

from findfire.dashboard.cards import build_cards, dashboard_payload, forecast_steps, perimeter_m, zones_from_state
from findfire.dashboard.server import Dashboard, make_server

STATIONS = pd.read_csv("tests/data/sample_stations.csv")


def feature(zone_id, status, area_ha, bbox):
    return {"type": "Feature", "geometry": mapping(box(*bbox)),
            "properties": {"zone_id": zone_id, "status": status, "area_ha": area_ha}}


def sample_state():
    return {"sample": True, "zones": [
        feature(1, "new", 15.0, (4.000, 36.700, 4.004, 36.704)),
        feature(2, "active", 420.0, (4.300, 36.550, 4.330, 36.580)),
        feature(3, "inactive", 50.0, (4.100, 36.600, 4.110, 36.610)),
    ]}


def test_zones_from_state_keeps_the_properties():
    zones = zones_from_state(sample_state())
    assert [z["zone_id"] for z in zones] == [1, 2, 3]
    assert zones[0]["geometry"].centroid.x == pytest.approx(4.002)


def test_cards_are_sorted_by_severity_and_skip_inactive():
    payload = dashboard_payload(sample_state(), STATIONS)
    assert [c["zone_id"] for c in payload["cards"]] == [2, 1]
    assert payload["inactive"] == 1 and payload["sample"] is True and payload["errors"] == []


def test_a_bad_zone_is_reported_not_raised():
    state = sample_state()
    state["zones"].append(feature(9, "active", 10.0, (500000, 4000000, 500100, 4000100)))
    payload = dashboard_payload(state, STATIONS)
    assert len(payload["cards"]) == 2 and any("zone 9" in e for e in payload["errors"])


def test_card_has_water_stations_and_trucks():
    card = dashboard_payload(sample_state(), STATIONS)["cards"][1]
    for key in ("flow_l_min", "volume_l", "nearest_station", "trucks_needed_now", "trucks_sent",
                "eta_last_truck_min", "autonomy_min", "needs_reinforcement", "terrain_assumed"):
        assert key in card
    assert card["terrain_assumed"] is True and card["forecast"] == []


def test_perimeter_of_a_small_square():
    # 0.001 degree square at 36.7 N: about 89 m wide and 111 m high -> about 400 m around
    assert 380 < perimeter_m(box(4.0, 36.7, 4.001, 36.701)) < 420


def test_forecast_steps_use_the_ellipse_perimeter():
    entry = {"wind_speed_ms": 6.0, "steps": [
        {"minutes": 30, "area_ha": 40.0, "geometry": box(4.0, 36.70, 4.01, 36.71)},
        {"minutes": 60, "area_ha": 90.0, "geometry": mapping(box(4.0, 36.70, 4.02, 36.71))}]}
    steps = forecast_steps(entry, "forest")
    assert [s["minutes"] for s in steps] == [30, 60]
    assert steps[1]["area_ha"] == 90.0 and steps[0]["flow_l_min"] > 0


def test_cards_with_a_forecast_carry_the_wind():
    zones = zones_from_state(sample_state())
    forecast = [{"zone_id": 1, "wind_speed_ms": 5.0, "wind_from_deg": 270.0, "spread_to_deg": 90.0,
                 "steps": [{"minutes": 30, "area_ha": 30.0, "geometry": box(4.0, 36.70, 4.01, 36.71)}]}]
    cards, errors, _ = build_cards(zones, STATIONS, forecast)
    card = next(c for c in cards if c["zone_id"] == 1)
    assert card["wind"]["from_deg"] == 270.0 and len(card["forecast"]) == 1 and errors == []


@pytest.fixture
def server(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(sample_state()), encoding="utf-8")
    dash = Dashboard(state, "tests/data/sample_stations.csv", forecast=False)
    srv = make_server(dash, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, state
    srv.shutdown()


def get(srv, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}{path}", timeout=10) as r:
        return r.status, r.read()


def test_server_serves_the_page_and_the_cards(server):
    srv, _ = server
    status, body = get(srv, "/")
    assert status == 200 and b"FindFire" in body
    status, body = get(srv, "/api/cards")
    data = json.loads(body)
    assert status == 200 and [c["zone_id"] for c in data["cards"]] == [2, 1]


def test_server_unknown_path_is_404(server):
    srv, _ = server
    with pytest.raises(urllib.error.HTTPError) as err:
        get(srv, "/nope")
    assert err.value.code == 404


def test_missing_state_file_gives_a_warning(tmp_path):
    dash = Dashboard(tmp_path / "missing.json", "tests/data/sample_stations.csv", forecast=False)
    payload = dash.payload()
    assert payload["cards"] == [] and "not found" in payload["warnings"][0]


def test_forecast_failure_does_not_break_the_dashboard(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no network")

    monkeypatch.setattr("findfire.dashboard.server.compute_forecast", boom)
    state = tmp_path / "state.json"
    state.write_text(json.dumps(sample_state()), encoding="utf-8")
    payload = Dashboard(state, "tests/data/sample_stations.csv", forecast=True).payload()
    assert len(payload["cards"]) == 2
    assert any("forecast unavailable" in w for w in payload["warnings"])


def test_forecast_is_attached_to_the_cards(tmp_path, monkeypatch):
    fake = [{"zone_id": 1, "wind_speed_ms": 4.0, "wind_from_deg": 90.0, "spread_to_deg": 270.0,
             "steps": [{"minutes": 60, "area_ha": 55.0, "geometry": box(4.0, 36.70, 4.01, 36.71)}]}]
    monkeypatch.setattr("findfire.dashboard.server.compute_forecast", lambda *a, **k: fake)
    state = tmp_path / "state.json"
    state.write_text(json.dumps(sample_state()), encoding="utf-8")
    payload = Dashboard(state, "tests/data/sample_stations.csv", forecast=True).payload()
    card = next(c for c in payload["cards"] if c["zone_id"] == 1)
    assert card["forecast"][0]["minutes"] == 60 and payload["warnings"] == []