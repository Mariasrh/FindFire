"""Fetch active fire detections over Algeria from NASA FIRMS."""
import datetime as dt
import io
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from findfire.config import ALGERIA_BBOX, FIRMS_MAP_KEY

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
DEFAULT_SOURCE = "VIIRS_NOAA20_NRT"  # VIIRS, 375 m resolution
DEFAULT_BBOX = (-2.0, 34.0, 8.5, 37.5)
DEFAULT_SOURCE_ARCHIVE = "VIIRS_SNPP_SP"
DEFAULT_START = dt.date(2021, 8, 8)
DEFAULT_END = dt.date(2021, 8, 16)
RAW_DIR = Path("data/raw")


def fetch_fires(source: str = DEFAULT_SOURCE, days: int = 1) -> pd.DataFrame:
    """Return fire detections inside the Algeria bounding box for the last `days` days."""
    if not FIRMS_MAP_KEY:
        raise RuntimeError("FIRMS_MAP_KEY is missing. Check your .env file.")

    bbox = ",".join(str(v) for v in ALGERIA_BBOX)
    url = f"{BASE_URL}/{FIRMS_MAP_KEY}/{source}/{bbox}/{days}"
    response = requests.get(url, timeout=60)
    if not response.ok:
        raise RuntimeError(f"FIRMS error {response.status_code}: {response.text[:300]}")

    fires = pd.read_csv(io.StringIO(response.text))
    if "latitude" not in fires.columns:
        # FIRMS returns a plain-text error message when something is wrong
        raise RuntimeError(f"Unexpected FIRMS response: {response.text[:200]}")
    return fires


def save_raw(fires: pd.DataFrame, name: str = "firms_algeria.csv") -> Path:
    """Save raw detections to data/raw (ignored by Git)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    fires.to_csv(path, index=False)
    return path


def _fetch_chunk(map_key, bbox, source, start, days):
    w, s, e, n = bbox
    url = f"{BASE_URL}/{map_key}/{source}/{w},{s},{e},{n}/{days}/{start:%Y-%m-%d}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    if not r.text.startswith("latitude"):
        raise RuntimeError(r.text[:200])
    return pd.read_csv(io.StringIO(r.text))


def fetch_firms(start=DEFAULT_START, end=DEFAULT_END, bbox=DEFAULT_BBOX, source=DEFAULT_SOURCE_ARCHIVE, map_key=None):
    """Fetch archive hotspots between two dates, in chunks of max 5 days."""
    map_key = map_key or FIRMS_MAP_KEY
    if not map_key:
        raise RuntimeError("FIRMS_MAP_KEY not set")
    frames, cur = [], start
    while cur <= end:
        days = min(5, (end - cur).days + 1)
        frames.append(_fetch_chunk(map_key, bbox, source, cur, days))
        cur += dt.timedelta(days=days)
        time.sleep(1)
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def make_synthetic(bbox=DEFAULT_BBOX, start=DEFAULT_START, days=9, seed=7):
    """Fake but plausible hotspots: 5 growing fires, two converge and merge, plus false alarms."""
    rng = np.random.default_rng(seed)
    fires = [(36.70, 4.30, 0, 6), (36.72, 4.36, 2, 6), (36.75, 5.70, 1, 6),
             (35.40, 1.20, 2, 3), (36.30, 7.20, 3, 6)]
    rows = []
    for lat0, lon0, d0, d1 in fires:
        d1 = min(d1, days - 1)
        for day in range(d0, d1 + 1):
            spread = 0.004 + 0.003 * (day - d0)
            for hhmm in (130, 1330):
                for _ in range(int(rng.integers(8, 20 + 15 * (day - d0)))):
                    dy, dx = np.clip(rng.normal(0, [spread, spread * 1.2]), [-2.2 * spread, -2.6 * spread], [2.2 * spread, 2.6 * spread])
                    rows.append(dict(
                        latitude=lat0 + dy, longitude=lon0 + dx,
                        acq_date=str(start + dt.timedelta(days=day)), acq_time=hhmm + int(rng.integers(0, 25)),
                        confidence=rng.choice(["n", "h", "l"], p=[0.5, 0.4, 0.1]), frp=float(rng.lognormal(1.6, 0.9)),
                        scan=float(rng.uniform(0.375, 0.7)), track=float(rng.uniform(0.375, 0.6)), satellite="N"))
    for _ in range(10):
        rows.append(dict(latitude=rng.uniform(34.2, 37.3), longitude=rng.uniform(-1.8, 8.3),
                         acq_date=str(start + dt.timedelta(days=int(rng.integers(0, 7)))), acq_time=1330,
                         confidence="n", frp=float(rng.lognormal(0.8, 0.4)),
                         scan=0.5, track=0.45, satellite="N"))
    return pd.DataFrame(rows)


def prepare(raw):
    """Add acq_dt, drop low-confidence rows, ensure scan/track, sort by time."""
    d = raw.copy()
    d["acq_dt"] = pd.to_datetime(d["acq_date"] + " " + d["acq_time"].astype(int).astype(str).str.zfill(4),
                                 format="%Y-%m-%d %H%M", utc=True)
    d = d[d["confidence"].astype(str).str.lower() != "l"]
    for c in ("scan", "track"):
        d[c] = d[c] if c in d else 0.375
    return d.sort_values("acq_dt").reset_index(drop=True)


if __name__ == "__main__":
    fires = fetch_fires(days=2)
    print(f"{len(fires)} hotspots detected in the Algeria area (last 2 days)")
    if not fires.empty:
        print(fires[["latitude", "longitude", "acq_date", "acq_time", "confidence"]].head())
    print(f"Saved to {save_raw(fires)}")