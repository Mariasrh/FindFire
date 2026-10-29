"""Wind for the forecast, from Open-Meteo (free, no key for non-commercial use).

Wind direction follows the weather convention: the direction the wind blows FROM, degrees clockwise from north.
The fire is pushed the opposite way (`Wind.to_deg`).

Which service answers depends on WHEN the wind is asked for:
  * now, the future, or the last RECENT_DAYS days -> forecast API (`past_days` covers the recent past)
  * older than that (a past fire, e.g. Kabylie 2021) -> historical archive API, one day per request
If the service cannot be reached, `wind_or_default` returns a calm wind marked `source="default"` instead of crashing.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd
import requests

URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
RECENT_DAYS = 60                         # older than this -> archive API
MAX_PAST_DAYS = 92                       # Open-Meteo limit of `past_days`
RETRIES = 3                              # tries per request (slow server, VPN hiccup, rate limit)
TIMEOUT_S = 30
MAX_GAP = pd.Timedelta(hours=3)          # refuse a wind value that is further than this from the asked time
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Wind:
    speed_ms: float          # 10 m wind speed, metres per second
    from_deg: float          # direction the wind blows FROM
    source: str = "open-meteo"   # "open-meteo" or "default" (no data: calm wind, no preferred direction)

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


# No wind data available: calm. A calm wind gives a round fire with no invented direction (see forecast.spread).
DEFAULT_WIND = Wind(0.0, 0.0, source="default")


def _get(url: str, params: dict, timeout: float):
    """requests.get with a few retries for timeouts, connection errors, rate limits (429) and server errors (5xx).
    A real client error (400, 404...) is raised at once: retrying would not help."""
    err = None
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError) as exc:
            err = exc
        except requests.HTTPError as exc:
            code = getattr(exc.response, "status_code", 0) or 0
            if code != 429 and code < 500:
                raise
            err = exc
        if attempt < RETRIES - 1:
            time.sleep(2 ** attempt)                     # 1 s, 2 s
    raise err


def _request(lat: float, lon: float, when, timeout: float = TIMEOUT_S) -> dict:
    """One Open-Meteo answer that contains the hour `when` (UTC)."""
    now = pd.Timestamp.now(tz="UTC")
    when = now if when is None else _utc(when)
    params = {"latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,wind_direction_10m",
              "wind_speed_unit": "ms", "timezone": "GMT"}
    age = now - when
    if age > pd.Timedelta(days=RECENT_DAYS):
        url = ARCHIVE_URL
        params |= {"start_date": f"{when:%Y-%m-%d}", "end_date": f"{when:%Y-%m-%d}"}
    else:
        url = URL
        if age > pd.Timedelta(0):
            params["past_days"] = min(MAX_PAST_DAYS, (now.floor("D") - when.floor("D")).days)   # calendar days back
            if params["past_days"] == 0:
                del params["past_days"]
    return _get(url, params, timeout).json()


def fetch_wind(lat: float, lon: float, when=None, timeout: float = TIMEOUT_S) -> Wind:
    """Wind at (lat, lon) for the hour closest to `when` (default: now, UTC). Needs internet, no key."""
    return parse_wind(_request(lat, lon, when, timeout), pd.Timestamp.now(tz="UTC") if when is None else when)


@lru_cache(maxsize=512)
def _payload(lat: float, lon: float, key: str) -> dict:
    """Cached answer. `key` is the day (archive) or the hour (forecast) so zones close together share one request."""
    return _request(lat, lon, key)


def cached_wind(lat: float, lon: float, when=None) -> Wind:
    """Same as fetch_wind, but zones that are close together share one request (0.1 degree grid)."""
    when = _utc(pd.Timestamp.now(tz="UTC") if when is None else when)
    old = pd.Timestamp.now(tz="UTC") - when > pd.Timedelta(days=RECENT_DAYS)
    key = f"{when:%Y-%m-%d}" if old else when.floor("h").isoformat()
    return parse_wind(_payload(round(lat, 1), round(lon, 1), key), when)


def wind_or_default(lat: float, lon: float, when=None, default: Wind = DEFAULT_WIND) -> Wind:
    """Wind from Open-Meteo, or `default` (calm, source="default") if the service cannot be used. Never raises on
    network or data problems, so an offline demo keeps running; the caller can see `wind.source` and say so."""
    try:
        return cached_wind(lat, lon, when)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        log.warning("no wind from Open-Meteo (%s: %s); using the default wind", type(exc).__name__, str(exc)[:120])
        return default
