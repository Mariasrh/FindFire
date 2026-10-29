import time

import pandas as pd
from shapely.geometry import box

from findfire.dashboard import server
from findfire.dashboard.server import compute_forecast
from findfire.forecast.wind import Wind


def zones(n, step_deg=0.6):
    return [dict(zone_id=i, status="active", area_ha=30.0, new_hotspots=2,
                 geometry=box(3.0 + i * step_deg, 36.7, 3.004 + i * step_deg, 36.704)) for i in range(n)]


def test_winds_are_looked_up_in_parallel_and_once_per_grid_cell(monkeypatch):
    server._NO_WIND.clear()
    calls = []

    def slow_wind(lat, lon, when=None):
        calls.append((lat, lon))
        time.sleep(0.2)
        return Wind(5.0, 200.0)

    monkeypatch.setattr("findfire.forecast.wind.cached_wind", slow_wind)
    zs = zones(12) + zones(2, step_deg=0.05)                  # two more zones that fall in cells already asked
    start = time.time()
    result = compute_forecast(zs, "shrub", when="2021-08-09T12:00:00+00:00")
    elapsed = time.time() - start
    assert len(result) == 14 and len(calls) == len(set(calls)) <= 12
    assert elapsed < 1.6                                       # 12 requests of 0.2 s in series would take 2.4 s


def test_a_played_replay_works_offline_from_the_wind_cache(monkeypatch, tmp_path):
    server._NO_WIND.clear()
    monkeypatch.setattr(server, "WIND_CACHE_PATH", tmp_path / "wind_cache.json")
    monkeypatch.setattr("findfire.forecast.wind.cached_wind", lambda lat, lon, when=None: Wind(7.5, 190.0))
    first = compute_forecast(zones(3), "shrub", when="2021-08-09T12:00:00+00:00")
    assert (tmp_path / "wind_cache.json").exists() and first[0]["wind_speed_ms"] == 7.5

    def offline(lat, lon, when=None):
        raise ConnectionError("offline")

    monkeypatch.setattr("findfire.forecast.wind.cached_wind", offline)
    problems = []
    second = compute_forecast(zones(3), "shrub", when="2021-08-09T12:00:00+00:00", problems=problems)
    assert [r["wind_speed_ms"] for r in second] == [7.5, 7.5, 7.5] and problems == []


def test_the_wind_of_today_is_never_written_to_disk(monkeypatch, tmp_path):
    server._NO_WIND.clear()
    monkeypatch.setattr(server, "WIND_CACHE_PATH", tmp_path / "wind_cache.json")
    monkeypatch.setattr("findfire.forecast.wind.cached_wind", lambda lat, lon, when=None: Wind(4.0, 90.0))
    compute_forecast(zones(2), "shrub")
    assert not (tmp_path / "wind_cache.json").exists()


def test_no_disk_cache_unless_a_path_is_set(monkeypatch):
    server._NO_WIND.clear()
    monkeypatch.setattr(server, "WIND_CACHE_PATH", None)
    monkeypatch.setattr("findfire.forecast.wind.cached_wind", lambda lat, lon, when=None: Wind(4.0, 90.0))
    assert compute_forecast(zones(2), "shrub", when="2021-08-09T12:00:00+00:00")[0]["wind_speed_ms"] == 4.0