"""Fuel dryness for the forecast: how much faster (or slower) a fire spreads because the fine fuel is dry (issue F6).

Source: the Canadian Forest Fire Weather Index System. Van Wagner, C.E. and Pickett, T.L. (1985), "Equations and FORTRAN
Program for the Canadian Forest Fire Weather Index System", Forestry Technical Report 33, equations 1-10 (Fine Fuel
Moisture Code, FFMC) and 25 (spread factor). Equations as implemented in the open-source IMPROVER library (Met Office).

In plain words
  1. Once a day, at local noon, the fine-fuel moisture is updated from temperature, humidity, wind and the rain of the last
     24 h (FFMC: high = dry fuel, low = wet fuel). Yesterday's value is carried over, so a few days of weather are needed.
  2. The moisture gives a spread factor f(m) (equation 25): drier fuel, faster fire.
  3. The forecast uses fuel_factor = f(m) / f(m of the reference FFMC), so 1.0 means "the reference dryness".

What is deliberately NOT used: the wind function of the Initial Spread Index (equation 24). The forecast already has its own
wind effect (spread.WIND_GAIN); using both would count the wind twice.

LIMITS (say them in the report)
  * FFMC was built for Canadian pine forest. Using it for Algerian shrub and forest is an approximation.
  * The reference FFMC is a convention (the system's own start-up value, 85), not a measurement of Algerian fuel.
  * The base spread rates (spread.BASE_ROS_M_MIN) are still placeholders: this factor scales them, it does not replace them.
  * Temperature, humidity, wind and rain come from a weather model (Open-Meteo), not from a station at the fire.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd
import requests

from findfire.forecast.wind import (ARCHIVE_URL, MAX_PAST_DAYS, RECENT_DAYS, TIMEOUT_S, URL, _get, _utc)

log = logging.getLogger(__name__)

FFMC_START = 85.0          # the system's start-up value (Van Wagner & Pickett 1985)
REF_FFMC = 85.0            # fuel_factor = 1.0 at this dryness (convention, see LIMITS)
SPINUP_DAYS = 7            # days of weather before the asked day: FFMC forgets its start value within a few days
MIN_DAYS = 3               # fewer days than this: refuse, the start value would still dominate
# The FFMC is defined at 12:00 local standard time. Algeria is UTC+1 all year, so noon = 11:00 UTC. ASSUMPTION for Algeria.
NOON_UTC_HOUR = 11


@dataclass(frozen=True)
class Fuel:
    ffmc: float              # Fine Fuel Moisture Code, 0-101 (higher = drier)
    moisture: float          # fine-fuel moisture content, % of dry weight
    factor: float            # spread multiplier, 1.0 = reference dryness
    source: str = "open-meteo"    # "open-meteo" or "default" (no weather data: factor 1)


def moisture_from_ffmc(f: float) -> float:
    """Equation 1: fine-fuel moisture content (%) from the FFMC."""
    return 147.2 * (101.0 - f) / (59.5 + f)


def ffmc_from_moisture(m: float) -> float:
    """Equation 10."""
    return min(101.0, max(0.0, 59.5 * (250.0 - m) / (147.2 + m)))


def ffmc_day(f_prev: float, temp_c: float, rh: float, wind_kmh: float, rain_mm: float) -> float:
    """One daily FFMC step (equations 1-10). Inputs at local noon; rain = the last 24 h."""
    rh = min(100.0, max(0.0, rh))
    m = moisture_from_ffmc(f_prev)
    if rain_mm > 0.5:                                           # equations 2, 3a, 3b
        rf = rain_mm - 0.5
        adj = 42.5 * rf * math.exp(-100.0 / (251.0 - m)) * (1.0 - math.exp(-6.93 / rf))
        if m > 150.0:
            adj += 0.0015 * (m - 150.0) ** 2 * math.sqrt(rf)
        m = min(250.0, m + adj)
    e_d = 0.942 * rh ** 0.679 + 11.0 * math.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - temp_c) * (1.0 - math.exp(-0.115 * rh))
    e_w = 0.618 * rh ** 0.753 + 10.0 * math.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - temp_c) * (1.0 - math.exp(-0.115 * rh))
    if m > e_d:                                                 # drying, equations 6a, 6b, 8
        k0 = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind_kmh) * (1.0 - (rh / 100.0) ** 8)
        m = e_d + (m - e_d) * 10.0 ** (-(k0 * 0.581 * math.exp(0.0365 * temp_c)))
    elif m < e_w:                                               # wetting, equations 7a, 7b, 9
        k1 = 0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind_kmh) * (1.0 - ((100.0 - rh) / 100.0) ** 8)
        m = e_w - (e_w - m) * 10.0 ** (-(k1 * 0.581 * math.exp(0.0365 * temp_c)))
    return ffmc_from_moisture(m)


def spread_factor(m: float) -> float:
    """Equation 25: fuel-moisture part of the Initial Spread Index (drier = larger)."""
    return 91.9 * math.exp(-0.1386 * m) * (1.0 + m ** 5.31 / 4.93e7)


def fuel_from_ffmc(ffmc: float, source: str = "open-meteo") -> Fuel:
    m = moisture_from_ffmc(ffmc)
    return Fuel(ffmc=ffmc, moisture=m, factor=spread_factor(m) / spread_factor(moisture_from_ffmc(REF_FFMC)), source=source)


# No weather data: the reference dryness, so the forecast is exactly what it was without this module.
NEUTRAL_FUEL = Fuel(ffmc=REF_FFMC, moisture=moisture_from_ffmc(REF_FFMC), factor=1.0, source="default")


def ffmc_from_payload(payload: dict, when) -> float:
    """FFMC at the last local noon at or before `when`, from an Open-Meteo hourly answer (UTC, wind in km/h).
    Needs temperature_2m, relative_humidity_2m, precipitation and wind_speed_10m. Raises ValueError if the data is not enough."""
    h = payload["hourly"]
    t = pd.to_datetime(pd.Series(h["time"]))
    df = pd.DataFrame({"t": t, "T": h["temperature_2m"], "RH": h["relative_humidity_2m"],
                       "P": h["precipitation"], "W": h["wind_speed_10m"]}).set_index("t")
    when = _utc(when).tz_localize(None)
    noons = [d for d in pd.date_range(df.index.min().floor("D"), df.index.max().floor("D"))
             if (d + pd.Timedelta(hours=NOON_UTC_HOUR)) <= when]
    f, used = FFMC_START, 0
    for d in noons:
        noon = d + pd.Timedelta(hours=NOON_UTC_HOUR)
        if noon not in df.index:
            continue
        row = df.loc[noon]
        if row[["T", "RH", "W"]].isna().any():
            continue
        rain = df.loc[noon - pd.Timedelta(hours=23):noon, "P"].fillna(0.0).sum()
        f = ffmc_day(f, float(row["T"]), float(row["RH"]), float(row["W"]), float(rain))
        used += 1
    if used < MIN_DAYS:
        raise ValueError(f"only {used} day(s) of weather before {when}: not enough for the fuel moisture")
    return f


def _request(lat: float, lon: float, when, timeout: float = TIMEOUT_S) -> dict:
    """Open-Meteo hourly weather for the SPINUP_DAYS before `when` and the day itself."""
    now = pd.Timestamp.now(tz="UTC")
    when = now if when is None else _utc(when)
    params = {"latitude": lat, "longitude": lon, "timezone": "GMT", "wind_speed_unit": "kmh",
              "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"}
    if now - when > pd.Timedelta(days=RECENT_DAYS):
        url = ARCHIVE_URL
        params |= {"start_date": f"{(when - pd.Timedelta(days=SPINUP_DAYS)):%Y-%m-%d}", "end_date": f"{when:%Y-%m-%d}"}
    else:
        url = URL
        back = (now.floor("D") - when.floor("D")).days if when < now else 0
        params["past_days"] = min(MAX_PAST_DAYS, back + SPINUP_DAYS)
    return _get(url, params, timeout).json()


def fetch_fuel(lat: float, lon: float, when=None, timeout: float = TIMEOUT_S) -> Fuel:
    """Fuel dryness at (lat, lon) for `when` (default now). Needs internet, no key."""
    when = pd.Timestamp.now(tz="UTC") if when is None else when
    return fuel_from_ffmc(ffmc_from_payload(_request(lat, lon, when, timeout), when))


@lru_cache(maxsize=256)
def _payload(lat: float, lon: float, day: str) -> dict:
    return _request(lat, lon, pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=23))


def cached_fuel(lat: float, lon: float, when=None) -> Fuel:
    """Same as fetch_fuel, but zones in the same 0.1 degree cell and day share one request."""
    when = _utc(pd.Timestamp.now(tz="UTC") if when is None else when)
    return fuel_from_ffmc(ffmc_from_payload(_payload(round(lat, 1), round(lon, 1), f"{when:%Y-%m-%d}"), when))


def fuel_or_default(lat: float, lon: float, when=None, default: Fuel = NEUTRAL_FUEL) -> Fuel:
    """Fuel from Open-Meteo, or `default` (factor 1, source="default") if it cannot be used. Never raises on network or
    data problems; the caller sees `fuel.source` and can say so."""
    try:
        return cached_fuel(lat, lon, when)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        log.warning("no fuel moisture for (%.2f, %.2f): %s. Using the reference dryness.", lat, lon, exc)
        return default
