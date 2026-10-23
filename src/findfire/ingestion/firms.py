"""NASA FIRMS VIIRS hotspots: fetch (NRT or archive), load a CSV, normalise.

Nothing here falls back to fake data: a bad key, an empty answer or a source that is not available yet
raises, so a demo can never silently run on synthetic points.
"""
from __future__ import annotations

import datetime as dt
import io
import time

import pandas as pd
import requests

from findfire.config import FIRMS_MAP_KEY, FIRMS_NRT_SOURCES, MIN_CONFIDENCE, STUDY_BBOX, VEGETATION_ONLY
from findfire.detection.filters import vegetation_only

BASE = "https://firms.modaps.eosdis.nasa.gov/api"
CONF_RANK = {"l": 0, "n": 1, "h": 2}


def _get(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        r = requests.get(url, timeout=60)
        if r.status_code < 500:
            r.raise_for_status()
            return r.text
        time.sleep(2 ** attempt)
    r.raise_for_status()
    return r.text


def fetch_area(source: str, bbox=STUDY_BBOX, days: int = 1, start: dt.date | None = None,
               key: str = FIRMS_MAP_KEY) -> pd.DataFrame:
    """One request: up to 5 days. `start=None` means the most recent `days` days (NRT behaviour)."""
    if not key:
        raise RuntimeError("FIRMS_MAP_KEY is not set (.env)")
    if not 1 <= days <= 5:
        raise ValueError("FIRMS area API allows 1 to 5 days per request")
    w, s, e, n = bbox
    url = f"{BASE}/area/csv/{key}/{source}/{w},{s},{e},{n}/{days}" + (f"/{start:%Y-%m-%d}" if start else "")
    text = _get(url)
    if not text.startswith("latitude"):          # FIRMS answers errors (bad key, bad source) as plain text
        raise RuntimeError(f"FIRMS refused the request for {source}: {text[:200]!r}")
    df = pd.read_csv(io.StringIO(text))
    df["source"] = source
    return df


def fetch_recent(sources=FIRMS_NRT_SOURCES, bbox=STUDY_BBOX, days: int = 2) -> pd.DataFrame:
    """Latest NRT detections from every satellite. This is what the live demo polls."""
    frames = [fetch_area(s, bbox, days) for s in sources]
    return prepare(pd.concat(frames, ignore_index=True))


def fetch_range(sources, start: dt.date, end: dt.date, bbox=STUDY_BBOX) -> pd.DataFrame:
    """Date range (inclusive), 5 days per request. Use *_SP sources for old events, *_NRT for the last weeks."""
    frames = []
    for source in sources:
        cur = start
        while cur <= end:
            n = min(5, (end - cur).days + 1)
            frames.append(fetch_area(source, bbox, n, cur))
            cur += dt.timedelta(days=n)
            time.sleep(0.5)
    return prepare(pd.concat(frames, ignore_index=True))


def availability(key: str = FIRMS_MAP_KEY, sensor: str = "ALL") -> pd.DataFrame:
    """Date range each product currently covers. Check it before asking for an old event."""
    return pd.read_csv(io.StringIO(_get(f"{BASE}/data_availability/csv/{key}/{sensor}")))


def load_csv(path) -> pd.DataFrame:
    """A FIRMS CSV saved earlier (data/raw/*.csv)."""
    return prepare(pd.read_csv(path))


def prepare(raw: pd.DataFrame, min_confidence: str | None = MIN_CONFIDENCE,
            vegetation: bool = VEGETATION_ONLY) -> pd.DataFrame:
    """UTC timestamp, confidence filter, exact duplicates removed, pixel size columns guaranteed.

    With `vegetation=True` (default) only presumed vegetation fires are kept when the FIRMS `type` column is
    present; the number dropped is left in `attrs["non_vegetation_dropped"]`. NRT data has no `type`, so it is
    returned unchanged."""
    d = raw.copy()
    hhmm = d["acq_time"].astype(int).astype(str).str.zfill(4)
    d["acq_dt"] = pd.to_datetime(d["acq_date"].astype(str) + " " + hhmm, format="%Y-%m-%d %H%M", utc=True)
    d["confidence"] = d["confidence"].astype(str).str.lower().str[0]
    if min_confidence:
        d = d[d["confidence"].map(CONF_RANK).fillna(-1) >= CONF_RANK[min_confidence]]
    dropped = 0
    if vegetation:
        d = vegetation_only(d)
        dropped = int(d.attrs.get("non_vegetation_dropped", 0))
    for c in ("scan", "track"):
        if c not in d:
            d[c] = 0.375
    if "satellite" not in d:
        d["satellite"] = ""
    d = d.drop_duplicates(subset=["latitude", "longitude", "acq_dt", "satellite"])
    out = d.sort_values("acq_dt").reset_index(drop=True)
    out.attrs["non_vegetation_dropped"] = dropped
    return out
