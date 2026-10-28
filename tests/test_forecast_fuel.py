"""Fuel dryness (forecast.fuel). The weather service is always faked: no network in the tests."""
import math

import pandas as pd
import pytest
import requests

from findfire.forecast import fuel as FU
from findfire.forecast import spread as S
from findfire.forecast import wind as W
from findfire.forecast.wind import Wind


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    monkeypatch.setattr(W.time, "sleep", lambda s: None)
    FU._payload.cache_clear()


def weather(day0="2021-08-03", days=8, temp=30.0, rh=30.0, wind=15.0, rain_on=None):
    """Hourly Open-Meteo-like answer, constant weather, optional rain (mm in the hour before noon) on given days."""
    times = pd.date_range(f"{day0} 00:00", periods=24 * days, freq="h")
    rain_on = rain_on or {}
    precip = [rain_on.get(t.strftime("%Y-%m-%d"), 0.0) if t.hour == 8 else 0.0 for t in times]
    n = len(times)
    return {"hourly": {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times], "temperature_2m": [temp] * n,
                       "relative_humidity_2m": [rh] * n, "precipitation": precip, "wind_speed_10m": [wind] * n}}


# ---- the equations -----------------------------------------------------------------------------------------------

def test_published_example_values():
    # Canadian FWI system example inputs: T 17, RH 42, wind 25 km/h, no rain, previous FFMC 85 (the system's start value).
    f = FU.ffmc_day(85.0, 17.0, 42.0, 25.0, 0.0)
    assert f == pytest.approx(87.69, abs=0.02)
    isi = 0.208 * FU.spread_factor(FU.moisture_from_ffmc(f)) * math.exp(0.05039 * 25.0)     # eq. 24-26 with the wind part
    assert isi == pytest.approx(10.85, abs=0.02)


def test_moisture_and_ffmc_are_nearly_inverse():
    # equations 1 and 10 of the system are not exact inverses (rounded constants); the difference is below 0.1 FFMC
    for f in (30, 60, 85, 95):
        assert FU.ffmc_from_moisture(FU.moisture_from_ffmc(f)) == pytest.approx(f, abs=0.1)


def test_the_reference_dryness_has_factor_one():
    assert FU.fuel_from_ffmc(FU.REF_FFMC).factor == pytest.approx(1.0)
    assert FU.NEUTRAL_FUEL.factor == 1.0 and FU.NEUTRAL_FUEL.source == "default"


def test_drier_fuel_spreads_faster():
    factors = [FU.fuel_from_ffmc(f).factor for f in (50, 70, 85, 92, 97)]
    assert factors == sorted(factors) and factors[0] < 1.0 < factors[-1]


def test_rain_wets_the_fuel_and_dry_weather_dries_it():
    dry = FU.ffmc_day(85.0, 32.0, 20.0, 10.0, 0.0)
    wet = FU.ffmc_day(85.0, 32.0, 20.0, 10.0, 15.0)
    assert dry > 85.0 > wet


def test_hot_dry_beats_cool_humid():
    assert FU.ffmc_day(85.0, 35.0, 15.0, 10.0, 0.0) > FU.ffmc_day(85.0, 12.0, 80.0, 10.0, 0.0)


def test_ffmc_stays_in_its_range():
    for t, rh, w, p in [(50, 0, 80, 0), (-10, 100, 0, 200), (20, 50, 10, 0.6)]:
        assert 0.0 <= FU.ffmc_day(85.0, t, rh, w, p) <= 101.0


# ---- from an Open-Meteo answer -----------------------------------------------------------------------------------

def test_a_week_of_hot_dry_weather_gives_a_high_ffmc():
    f = FU.ffmc_from_payload(weather(), pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    assert f > 90.0


def test_recent_rain_lowers_the_ffmc():
    when = pd.Timestamp("2021-08-10 12:00", tz="UTC")
    dry = FU.ffmc_from_payload(weather(), when)
    rainy = FU.ffmc_from_payload(weather(rain_on={"2021-08-10": 12.0}), when)
    assert rainy < dry - 5


def test_it_uses_the_last_noon_before_the_asked_time():
    p = weather(rain_on={"2021-08-10": 12.0})
    before = FU.ffmc_from_payload(p, pd.Timestamp("2021-08-10 09:00", tz="UTC"))      # noon of the 10th (11:00 UTC) not reached yet
    after = FU.ffmc_from_payload(p, pd.Timestamp("2021-08-10 15:00", tz="UTC"))
    assert before > after


def test_too_little_weather_is_refused_not_guessed():
    short = weather(day0="2021-08-09", days=2)
    with pytest.raises(ValueError):
        FU.ffmc_from_payload(short, pd.Timestamp("2021-08-10 12:00", tz="UTC"))


# ---- requests ----------------------------------------------------------------------------------------------------

class Fake:
    def __init__(self, data):
        self.data, self.calls = data, []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        data = self.data

        class R:
            def raise_for_status(self): pass
            def json(self): return data
        return R()


def test_an_old_fire_uses_the_archive_with_a_week_of_history(monkeypatch):
    fake = Fake(weather())
    monkeypatch.setattr(W.requests, "get", fake)
    fuel = FU.fetch_fuel(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    url, params = fake.calls[0]
    assert url == W.ARCHIVE_URL and params["end_date"] == "2021-08-10"
    assert pd.Timestamp(params["end_date"]) - pd.Timestamp(params["start_date"]) == pd.Timedelta(days=FU.SPINUP_DAYS)
    assert params["wind_speed_unit"] == "kmh" and "relative_humidity_2m" in params["hourly"]
    assert fuel.source == "open-meteo" and fuel.ffmc > 90 and fuel.factor > 1


def test_a_recent_fire_uses_the_forecast_api_with_past_days(monkeypatch):
    fake = Fake(weather())
    monkeypatch.setattr(W.requests, "get", fake)
    now = pd.Timestamp.now(tz="UTC")
    FU._request(36.7, 4.5, now - pd.Timedelta(days=3))
    url, params = fake.calls[0]
    assert url == W.URL and params["past_days"] == 3 + FU.SPINUP_DAYS


def test_zones_in_the_same_cell_and_day_share_one_request(monkeypatch):
    fake = Fake(weather())
    monkeypatch.setattr(W.requests, "get", fake)
    when = pd.Timestamp("2021-08-10 12:00", tz="UTC")
    FU.cached_fuel(36.71, 4.52, when)
    FU.cached_fuel(36.74, 4.48, when)
    assert len(fake.calls) == 1


def test_fuel_or_default_is_neutral_and_marked_when_offline(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(W.requests, "get", boom)
    fuel = FU.fuel_or_default(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    assert fuel.source == "default" and fuel.factor == 1.0


def test_fuel_or_default_also_covers_too_little_data(monkeypatch):
    monkeypatch.setattr(W.requests, "get", Fake(weather(day0="2021-08-10", days=1)))
    assert FU.fuel_or_default(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC")).source == "default"


# ---- in the forecast ---------------------------------------------------------------------------------------------

ZONE = dict(zone_id=1, area_ha=100.0, geometry={"type": "Point", "coordinates": [4.5, 36.7]})
WIND = Wind(4.0, 90.0)


def test_without_fuel_nothing_changes():
    base = S.forecast_zone(ZONE, WIND)
    assert base["fuel_factor"] == 1.0 and base["ffmc"] is None and base["fuel_source"] is None
    assert S.forecast_zone(ZONE, WIND, fuel=FU.NEUTRAL_FUEL)["steps"][-1]["area_ha"] == pytest.approx(base["steps"][-1]["area_ha"])


def test_dry_fuel_grows_more_and_wet_fuel_less():
    base = S.forecast_zone(ZONE, WIND)["steps"][-1]["area_ha"]
    dry = S.forecast_zone(ZONE, WIND, fuel=FU.fuel_from_ffmc(95))
    wet = S.forecast_zone(ZONE, WIND, fuel=FU.fuel_from_ffmc(60))
    assert dry["steps"][-1]["area_ha"] > base > wet["steps"][-1]["area_ha"]
    assert dry["ffmc"] == 95 and dry["fuel_factor"] > 1 and dry["fuel_source"] == "open-meteo"


def test_the_factor_scales_the_head_rate_exactly():
    f = FU.fuel_from_ffmc(92)
    assert S.rates(WIND, "shrub", f.factor)["head_m_min"] == pytest.approx(S.rates(WIND, "shrub")["head_m_min"] * f.factor)


def test_forecast_zones_passes_the_zone_time_to_the_fuel_function():
    seen = []

    def fuel_fn(lat, lon, when=None):
        seen.append((lat, lon, when))
        return FU.fuel_from_ffmc(92)

    t = pd.Timestamp("2021-08-10 12:00", tz="UTC")
    out = S.forecast_zones([ZONE], lambda la, lo, w=None: WIND, when=t, fuel_fn=fuel_fn)
    assert seen == [(pytest.approx(36.7), pytest.approx(4.5), t)] and out[0]["fuel_factor"] > 1
    seen.clear()
    S.forecast_zones([ZONE], lambda la, lo, w=None: WIND, fuel_fn=fuel_fn)           # no `when`: called with (lat, lon) only
    assert seen[0][2] is None
