import pandas as pd
import pytest

from findfire.forecast import emsr_compare as E
from findfire.forecast.wind import Wind

TABLE = """
| Product | Sensor | Acquisition Date & Time (UTC) | Burned Area (ha) | Burned Area (km2) |
|---|---|---|---|---|
| **Delineation** | Sentinel-2B (v2) | **2021-08-12 10:40** | **46,361.5 ha** | 463.6 km2 |
| **Monit02** | SPOT 6 | **2021-08-14 10:21** | **55,337.1 ha** | 553.4 km2 |
| **Monit01** | SPOT 7 | **2021-08-13 10:27** | **53,094.0 ha** | 530.9 km2 |
"""
WIND = Wind(5.0, 90.0, source="fixed")


def test_the_table_is_read_and_sorted_by_date():
    t = E.parse_table(TABLE)
    assert list(t.area_ha) == [46361.5, 53094.0, 55337.1]
    assert t.time.is_monotonic_increasing and t.time.iloc[0] == pd.Timestamp("2021-08-12 10:40", tz="UTC")


def test_a_table_without_two_rows_is_refused():
    with pytest.raises(ValueError):
        E.parse_table("| **Delineation** | x | **2021-08-12 10:40** | **46,361.5 ha** |")


def test_implied_factor_recovers_the_factor_used_to_make_the_observation():
    obs = E.predicted_area(46361.5, WIND, 24.0, "shrub", 0.137)
    assert E.implied_factor(46361.5, obs, WIND, 24.0) == pytest.approx(0.137, rel=1e-6)


def test_no_growth_means_factor_zero_and_impossible_growth_means_inf():
    assert E.implied_factor(1000.0, 1000.0, WIND, 24.0) == 0.0
    assert E.implied_factor(1000.0, 1e12, WIND, 24.0) == float("inf")


def test_the_model_grows_more_with_a_larger_factor():
    a = [E.predicted_area(5000.0, WIND, 24.0, "shrub", f) for f in (0.1, 0.5, 1.0)]
    assert a == sorted(a) and a[0] > 5000.0


def test_compare_gives_one_row_per_period_with_real_and_model_rates():
    res = E.compare(E.parse_table(TABLE), lambda t: WIND, factors=(1.0, 0.1))
    assert len(res) == 2
    first = res.iloc[0]
    assert first.observed_ha_per_h == pytest.approx((53094.0 - 46361.5) / ((pd.Timestamp("2021-08-13 10:27") - pd.Timestamp("2021-08-12 10:40")) / pd.Timedelta(hours=1)))
    assert first["model_x1_ha_per_h"] > first["model_x0.1_ha_per_h"] > 0 and first.implied_factor > 0


def test_adaptive_uses_the_previous_period_factor_and_skips_the_first():
    res = E.compare(E.parse_table(TABLE), lambda t: WIND, factors=(1.0,))
    assert pd.isna(res.adaptive_factor.iloc[0]) and pd.isna(res.model_adaptive_ha_per_h.iloc[0])
    assert res.adaptive_factor.iloc[1] == pytest.approx(res.implied_factor.iloc[0])
    assert res.model_adaptive_ha_per_h.iloc[1] > 0


def test_adaptive_is_exact_when_the_fire_keeps_the_same_factor():
    # three mappings produced by the same factor: the previous period's factor predicts the next one exactly
    a0, a1 = 10000.0, E.predicted_area(10000.0, WIND, 24.0, "shrub", 0.2)
    a2 = E.predicted_area(a1, WIND, 24.0, "shrub", 0.2)
    table = pd.DataFrame({"time": pd.to_datetime(["2021-08-01", "2021-08-02", "2021-08-03"], utc=True), "area_ha": [a0, a1, a2]})
    res = E.compare(table, lambda t: WIND, factors=())
    assert res.model_adaptive_ha_per_h.iloc[1] == pytest.approx(res.observed_ha_per_h.iloc[1], rel=1e-6)


def test_typical_error_is_one_when_perfect_and_two_when_always_double_or_half():
    assert E.typical_error([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert E.typical_error([2, 1], [1, 2]) == pytest.approx(2.0)
