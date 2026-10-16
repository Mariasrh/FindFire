"""Fetch active fire detections over Algeria from NASA FIRMS."""
import io
from pathlib import Path

import pandas as pd
import requests

from findfire.config import ALGERIA_BBOX, FIRMS_MAP_KEY

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
DEFAULT_SOURCE = "VIIRS_NOAA20_NRT"  # VIIRS, 375 m resolution
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


if __name__ == "__main__":
    fires = fetch_fires(days=2)
    print(f"{len(fires)} hotspots detected in the Algeria area (last 2 days)")
    if not fires.empty:
        print(fires[["latitude", "longitude", "acq_date", "acq_time", "confidence"]].head())
    print(f"Saved to {save_raw(fires)}")