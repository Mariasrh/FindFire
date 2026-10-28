import json

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from findfire.dashboard.replay_player import play, snapshot_to_state, step_summary, write_state
from findfire.dashboard.server import DEFAULT_WIND, Dashboard, compute_forecast

STATIONS = "tests/data/sample_stations.csv"


def zone(zone_id, status, area_ha, bbox=(4.000, 36.700, 4.004, 36.704)):
    return dict(zone_id=zone_id, status=status, area_ha=np.float64(area_ha), perimeter_km=1.5, n_hotspots=np.int64(6),
                frp_total_mw=7.5, first_detected=pd.Timestamp("2021-08-08T10:00:00Z"),
                last_detected=pd.Timestamp("2021-08-09T10:00:00Z"), new_hotspots=2, geometry=box(*bbox))


def snaps():
    t0 = pd.Timestamp("2021-08-09T12:00:00Z")
    return [
        dict(time=t0, zones=[zone(1, "new", 15)]),
        dict(time=t0 + pd.Timedelta(hours=12), zones=[zone(1, "active", 30), zone(2, "new", 120, (4.1, 36.6, 4.11, 36.61))]),
        dict(time=t0 + pd.Timedelta(hours=24), zones=[zone(1, "inactive", 30), zone(2, "active", 150, (4.1, 36.6, 4.11, 36.61))]),
    ]


def test_snapshot_becomes_a_state_with_geojson_zones():
    state = snapshot_to_state(snaps()[1], 1, 3, "Kabylie")
    assert state["replay"] is True and state["step"] == 2 and state["steps"] == 3 and state["event"] == "Kabylie"
    assert state["replay_time"].startswith("2021-08-10T00:00:00")
    feature = state["zones"][0]
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Polygon"
    assert "geometry" not in feature["properties"] and feature["properties"]["zone_id"] == 1


def test_write_state_handles_numpy_and_timestamps_and_leaves_no_temp_file(tmp_path):
    out = tmp_path / "live" / "replay_state.json"
    write_state(out, snapshot_to_state(snaps()[0], 0, 3))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["zones"][0]["properties"]["area_ha"] == 15.0
    assert data["zones"][0]["properties"]["first_detected"].startswith("2021-08-08")
    assert list(out.parent.glob("*.tmp")) == []


def test_play_writes_every_step_and_pauses_between_them(tmp_path):
    out, pauses, lines = tmp_path / "s.json", [], []
    written = play(snaps(), out, seconds=7.0, event="x", sleep=pauses.append, log=lines.append)
    assert written == 3 and pauses == [7.0, 7.0] and len(lines) == 3
    assert json.loads(out.read_text(encoding="utf-8"))["step"] == 3


def test_play_can_start_at_a_later_step(tmp_path):
    out, pauses = tmp_path / "s.json", []
    assert play(snaps(), out, first=2, sleep=pauses.append, log=lambda *_: None) == 2
    assert pauses == [10.0]


def test_step_summary_counts_active_zones():
    s = step_summary(snaps()[2])
    assert s["zones"] == 2 and s["live"] == 1 and s["max_area_ha"] == 150.0


def test_dashboard_follows_the_replay_step_by_step(tmp_path):
    out = tmp_path / "s.json"
    dash = Dashboard(out, STATIONS, forecast=False)
    seen = []
    for i, snap in enumerate(snaps()):
        write_state(out, snapshot_to_state(snap, i, 3, "x"))
        payload = dash.payload()
        seen.append(sorted(c["zone_id"] for c in payload["cards"]))
        assert payload["replay"]["step"] == i + 1 and payload["sample"] is False
    assert seen == [[1], [1, 2], [2]]


def test_replay_time_is_passed_to_the_forecast(tmp_path, monkeypatch):
    got = {}

    def fake(zones, vegetation, fixed_wind=None, when=None, problems=None):
        got["when"] = when
        return []

    monkeypatch.setattr("findfire.dashboard.server.compute_forecast", fake)
    out = tmp_path / "s.json"
    write_state(out, snapshot_to_state(snaps()[0], 0, 3))
    Dashboard(out, STATIONS, forecast=True).payload()
    assert got["when"] == "2021-08-09T12:00:00+00:00"


def test_forecast_with_a_fixed_wind_grows_the_fire():
    zones = [dict(zone(1, "active", 30), geometry=box(4.0, 36.7, 4.004, 36.704))]
    result = compute_forecast(zones, "shrub", fixed_wind=(6.0, 270.0))
    areas = [s["area_ha"] for s in result[0]["steps"]]
    assert areas == sorted(areas) and areas[0] > 30


def test_missing_wind_falls_back_to_the_default_and_says_so(monkeypatch):
    def no_wind(lat, lon, when=None):
        raise ValueError("no wind data within 3:00:00 of 2021-08-09")

    monkeypatch.setattr("findfire.forecast.wind.cached_wind", no_wind)
    problems = []
    zones = [dict(zone(1, "active", 30), geometry=box(4.0, 36.7, 4.004, 36.704))]
    result = compute_forecast(zones, "shrub", when="2021-08-09T12:00:00+00:00", problems=problems)
    assert result[0]["wind_speed_ms"] == DEFAULT_WIND[0] and result[0]["wind_from_deg"] == DEFAULT_WIND[1]
    assert problems and "default wind" in problems[0]


def test_inactive_zones_are_not_forecast():
    zones = [dict(zone(1, "inactive", 30), geometry=box(4.0, 36.7, 4.004, 36.704))]
    assert compute_forecast(zones, "shrub", fixed_wind=(6.0, 270.0)) == []

@pytest.fixture(autouse=True)
def _forget_missing_winds():
    from findfire.dashboard import server
    server._NO_WIND.clear()
    yield
    server._NO_WIND.clear()


def test_a_missing_wind_is_looked_up_once_per_cell_not_once_per_zone(monkeypatch):
    calls = []

    def no_wind(lat, lon, when=None):
        calls.append((lat, lon))
        raise ValueError("no wind data")

    monkeypatch.setattr("findfire.forecast.wind.cached_wind", no_wind)
    problems = []
    zones = [dict(zone(i, "active", 30), geometry=box(4.0 + i * 0.001, 36.7, 4.004 + i * 0.001, 36.704)) for i in range(1, 6)]
    result = compute_forecast(zones, "shrub", when="2021-08-09T12:00:00+00:00", problems=problems)
    assert len(result) == 5 and len(calls) == 1 and len(problems) == 5


def test_live_mode_keeps_asking_for_the_wind(monkeypatch):
    calls = []

    def no_wind(lat, lon, when=None):
        calls.append(1)
        raise ValueError("offline")

    monkeypatch.setattr("findfire.forecast.wind.cached_wind", no_wind)
    zones = [dict(zone(i, "active", 30), geometry=box(4.0, 36.7, 4.004, 36.704)) for i in range(1, 4)]
    compute_forecast(zones, "shrub", problems=[])
    assert len(calls) == 3
