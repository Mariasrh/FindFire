import math

import numpy as np
import pandas as pd
import pytest
import shapely
from shapely.geometry import Point

from findfire.forecast.spread import (WIND_ADJUSTMENT, forecast_zone, forecast_zones, grow, length_breadth, rates)
from findfire.forecast.wind import Wind, parse_wind
from findfire.zones.geometry import _transformers, utm_epsg

ZONE_AREA_HA = 100.0
R0 = math.sqrt(ZONE_AREA_HA * 1e4 / math.pi)


def zone(lon=4.0, lat=36.0, area=ZONE_AREA_HA):
    return dict(zone_id=7, area_ha=area, geometry=Point(lon, lat).buffer(0.005))


def test_wind_direction_is_where_it_blows_from():
    assert Wind(5, 270).to_deg == 90          # a west wind pushes the fire east
    assert Wind(5, 90).to_deg == 270
    assert Wind(5, 0).to_deg == 180


def test_parse_wind_takes_the_nearest_hour():
    payload = {"hourly": {"time": ["2026-10-19T10:00", "2026-10-19T11:00", "2026-10-19T12:00"],
                          "wind_speed_10m": [2.0, 4.0, 6.0], "wind_direction_10m": [90, 180, 270]}}
    w = parse_wind(payload, pd.Timestamp("2026-10-19 11:20", tz="UTC"))
    assert (w.speed_ms, w.from_deg) == (4.0, 180.0)


def test_parse_wind_refuses_data_far_from_the_asked_time():
    payload = {"hourly": {"time": ["2026-10-19T10:00"], "wind_speed_10m": [2.0], "wind_direction_10m": [90]}}
    with pytest.raises(ValueError):
        parse_wind(payload, pd.Timestamp("2026-10-20 10:00", tz="UTC"))


def test_parse_wind_refuses_a_missing_value():
    payload = {"hourly": {"time": ["2026-10-19T10:00"], "wind_speed_10m": [None], "wind_direction_10m": [90]}}
    with pytest.raises(ValueError):
        parse_wind(payload, pd.Timestamp("2026-10-19 10:00", tz="UTC"))


def test_no_wind_gives_a_circle():
    assert length_breadth(0.0) == pytest.approx(1.0, abs=1e-3)
    r = rates(Wind(0, 0), "shrub")
    assert r["back_m_min"] == pytest.approx(r["head_m_min"], rel=1e-3)


def test_more_wind_stretches_the_fire_and_speeds_the_head():
    calm, windy = rates(Wind(2, 0), "shrub"), rates(Wind(10, 0), "shrub")
    assert windy["length_breadth"] > calm["length_breadth"]
    assert windy["head_m_min"] > calm["head_m_min"]
    assert windy["back_m_min"] < windy["head_m_min"]


def test_vegetation_changes_the_speed():
    assert rates(Wind(5, 0), "grass")["head_m_min"] > rates(Wind(5, 0), "forest")["head_m_min"]
    with pytest.raises(ValueError):
        rates(Wind(5, 0), "desert")


def test_circle_growth_matches_the_hand_calculation():
    g = grow(ZONE_AREA_HA, Wind(0, 0), "shrub", 60)
    radius = R0 + 2.0 * 60                      # shrub base rate 2 m/min, no wind
    assert g["area_ha"] == pytest.approx(math.pi * radius ** 2 / 1e4, rel=1e-3)
    assert g["shift_m"] == pytest.approx(0, abs=0.5)


def test_the_head_reaches_r0_plus_head_rate_times_time():
    w = Wind(8, 270)
    g, r = grow(ZONE_AREA_HA, w, "grass", 60), rates(w, "grass")
    assert g["shift_m"] + g["a_m"] == pytest.approx(R0 + r["head_m_min"] * 60, rel=1e-6)
    assert g["a_m"] - g["shift_m"] == pytest.approx(R0 + r["back_m_min"] * 60, rel=1e-6)


def test_forecast_has_three_growing_steps_that_never_shrink():
    f = forecast_zone(zone(), Wind(6, 270), "shrub")
    areas = [s["area_ha"] for s in f["steps"]]
    assert [s["minutes"] for s in f["steps"]] == [30, 60, 120]
    assert ZONE_AREA_HA < areas[0] < areas[1] < areas[2]
    assert f["zone_id"] == 7 and f["spread_to_deg"] == 90


def test_polygon_area_matches_the_reported_area():
    f = forecast_zone(zone(), Wind(6, 270), "shrub")
    for s in f["steps"]:
        fwd, _ = _transformers(utm_epsg(4.0, 36.0))
        utm = shapely.transform(s["geometry"], lambda c: np.column_stack(fwd(c[:, 0], c[:, 1])))
        assert utm.area / 1e4 == pytest.approx(s["area_ha"], rel=0.01)


def test_west_wind_moves_the_fire_east_and_north_wind_moves_it_south():
    east = forecast_zone(zone(), Wind(8, 270), "grass")["steps"][-1]["geometry"].centroid
    south = forecast_zone(zone(), Wind(8, 0), "grass")["steps"][-1]["geometry"].centroid
    assert east.x > 4.0 and east.y == pytest.approx(36.0, abs=1e-3)
    assert south.y < 36.0 and south.x == pytest.approx(4.0, abs=1e-3)


def test_water_function_is_called_with_the_forecast_area():
    seen = []
    f = forecast_zone(zone(), Wind(6, 270), water_fn=lambda ha: seen.append(ha) or dict(volume_l=ha * 10))
    assert seen == [s["area_ha"] for s in f["steps"]]
    assert f["steps"][0]["water"]["volume_l"] == pytest.approx(seen[0] * 10)


def test_forecast_zones_asks_the_wind_at_each_zone():
    asked = []
    out = forecast_zones([zone(4.0, 36.0), zone(2.0, 35.5)], lambda lat, lon: asked.append((lat, lon)) or Wind(5, 90))
    assert len(out) == 2
    assert asked[0] == pytest.approx((36.0, 4.0), abs=0.01) and asked[1] == pytest.approx((35.5, 2.0), abs=0.01)


def test_wind_adjustment_is_below_one():
    assert 0 < WIND_ADJUSTMENT < 1


def test_length_breadth_matches_the_published_formula_in_m_per_s():
    assert length_breadth(2.0) == pytest.approx(0.936 * math.exp(0.5132) + 0.461 * math.exp(-0.3096) - 0.397, rel=1e-9)
    assert length_breadth(2.0) == pytest.approx(1.505, abs=0.002)


def test_length_breadth_is_capped_at_8():
    assert length_breadth(50.0) == 8.0


def test_head_to_back_ratio_matches_finney():
    r = rates(Wind(10, 0), "grass")
    lb = r["length_breadth"]
    hb = (lb + math.sqrt(lb * lb - 1)) / (lb - math.sqrt(lb * lb - 1))
    assert r["head_m_min"] / r["back_m_min"] == pytest.approx(hb, rel=1e-9)
