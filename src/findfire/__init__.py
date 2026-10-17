"""FindFire: from FIRMS hotspots to tracked fire zones and a replay."""
from .config import ALGERIA_BBOX, EUMETSAT_KEY, EUMETSAT_SECRET, FIRMS_MAP_KEY
from .ingestion.emsr import load_aoi, load_perimeter
from .ingestion.firms import fetch_fires, save_raw
from .tracking import run_tracking, status_of, utm_epsg, zone_geometry

__all__ = [
    "FIRMS_MAP_KEY",
    "EUMETSAT_KEY",
    "EUMETSAT_SECRET",
    "ALGERIA_BBOX",
    "fetch_fires",
    "save_raw",
    "load_aoi",
    "load_perimeter",
    "run_tracking",
    "status_of",
    "utm_epsg",
    "zone_geometry",
]