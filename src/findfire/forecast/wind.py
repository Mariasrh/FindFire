"""Wind for the forecast, from Open-Meteo (free, no key for non-commercial use).

Wind direction follows the weather convention: the direction the wind blows FROM, degrees clockwise from north.
The fire is pushed the opposite way (`Wind.to_deg`).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd
import requests

URL = "https://api.open-meteo.com/v1/forecast"
MAX_GAP = pd.Timedelta(hours=3)          # refuse a wind value that is further than this from the asked time


@dataclass(frozen=True)
class Wind:
    speed_ms: float          # 10 m wind speed, metres per second
    from_deg: float          # direction the wind blows FROM

    @property
    def to_deg(self) -> float:
        """Direction the fire is pushed TOWARDS."""
        return (self.from_deg + 180.0) % 360.0


def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def parse_wind(payload: dict, when) -> Wind:
    """Open-Meteo answer (hourly arrays, timezone=GMT) -> the Wind of the hour closest to `when`."""
    h = payload["hourly"]
    times = pd.DatetimeIndex(pd.to_datetime(h["time"], utc=True))
    when = _utc(when)
    gaps = abs(times - when)
    i = int(gaps.argmin())
    if gaps[i] > MAX_GAP:
        raise ValueError(f"no wind data within {MAX_GAP} of {when}")
    speed, direction = h["wind_speed_10m"][i], h["wind_direction_10m"][i]
    if speed is None or direction is None:
        raise ValueError(f"Open-Meteo has no wind value for {times[i]}")
    return Wind(float(speed), float(direction))


def fetch_wind(lat: float, lon: float, when=None, timeout: float = 20) -> Wind:
    """Wind at (lat, lon) for the hour closest to `when` (default: now, UTC). Needs internet, no key."""
    params = {"latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,wind_direction_10m",
              "wind_speed_unit": "ms", "timezone": "GMT"}
    r = requests.get(URL, params=params, timeout=timeout)
    r.raise_for_status()
    return parse_wind(r.json(), pd.Timestamp.now(tz="UTC") if when is None else when)


@lru_cache(maxsize=256)
def _cached(lat: float, lon: float, hour: str) -> Wind:
    return fetch_wind(lat, lon, hour)


def cached_wind(lat: float, lon: float, when=None) -> Wind:
    """Same as fetch_wind, but zones that are close together share one request (0.1 degree grid, one hour)."""
    when = _utc(pd.Timestamp.now(tz="UTC") if when is None else when)
    return _cached(round(lat, 1), round(lon, 1), when.floor("h").isoformat())
