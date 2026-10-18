"""MTG FCI active-fire detections (EUMETSAT Data Store, product FIR) as a point table.

Product: "Active Fire Monitoring (netCDF) - MTG - 0 degree", EO:EUM:DAT:0682. A 2 km raster per 10-minute
repeat cycle, one `fire_result` class per pixel (plus `fire_probability`). Files are decoded with satpy's
`fci_l2_nc` reader, which also takes care of the FCI L2 grid orientation, so we do not hand-roll the projection.

We turn the raster into points with the same columns as the VIIRS table (latitude, longitude, acq_dt,
scan, track, confidence, satellite, source), so the same filters and clustering work on both.

NOT verified against a live file here (no EUMETSAT credentials in the sandbox): run scripts/inspect_mtg.py once
and check the class names it prints. `fire_classes()` decides what counts as fire from those names.
"""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer

from findfire.config import DATA_DIR, EUMETSAT_KEY, EUMETSAT_SECRET, MTG_FIR_COLLECTION, STUDY_BBOX

COLUMNS = ["latitude", "longitude", "acq_dt", "scan", "track", "confidence", "fire_probability",
           "frp", "satellite", "source"]
_GEOD = Geod(ellps="WGS84")


# ------------------------------------------------------------------ download
def datastore():
    import eumdac
    return eumdac.DataStore(eumdac.AccessToken((EUMETSAT_KEY, EUMETSAT_SECRET)))


def list_products(start: datetime, end: datetime, store=None):
    """FIR granules whose sensing time falls in [start, end] (UTC, naive datetimes), oldest first."""
    store = store or datastore()
    found = list(store.get_collection(MTG_FIR_COLLECTION).search(dtstart=start, dtend=end))
    return sorted(found, key=lambda p: p.sensing_start)


def download(product, cache_dir: Path | None = None) -> list[Path]:
    """Download one granule (a zip) once, return the .nc files inside.
    Short folder name on purpose: EUMETSAT file names are ~150 characters and Windows paths stop at 260."""
    cache = Path(cache_dir or DATA_DIR / "raw" / "mtg"); cache.mkdir(parents=True, exist_ok=True)
    folder = cache / f"{product.sensing_start:%Y%m%dT%H%M}"
    if not any(folder.rglob("*.nc")):
        folder.mkdir(exist_ok=True)
        blob = folder / "granule.zip"
        with product.open() as src, open(blob, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if zipfile.is_zipfile(blob):
            with zipfile.ZipFile(blob) as z:
                z.extractall(folder)
            blob.unlink()
    return sorted(folder.rglob("*.nc"))


# ------------------------------------------------------------------ decode
def fire_classes(flag_values, flag_meanings) -> dict[int, str]:
    """{class value: "fire" | "potential"} from the product's own enum (no class numbers hard-coded).

    A class counts as fire when its name contains 'fire' and does not start with 'no' ('no_fire', 'non_fire')."""
    out = {}
    for v, m in zip(flag_values, flag_meanings):
        name = str(m).lower()
        if "fire" in name and not name.startswith(("no", "not")):
            out[int(v)] = "potential" if "potential" in name else "fire"
    if not out:
        raise ValueError(f"no fire class found in enum {dict(zip(flag_values, flag_meanings))}: adjust fire_classes()")
    return out


def _km(lon1, lat1, lon2, lat2):
    return _GEOD.inv(lon1, lat1, lon2, lat2)[2] / 1000.0


def fire_pixels(fire_result, fire_probability=None, bbox=STUDY_BBOX, satellite="MTG-I1") -> pd.DataFrame:
    """Raster (xarray DataArray with a pyresample `area` attr, as satpy returns it) -> point table.

    Only the flagged pixels are georeferenced, so this is cheap on the full 5568 x 5568 disc.
    scan / track are the real pixel footprint in km (about 2 km at nadir, larger over Algeria)."""
    attrs = fire_result.attrs
    classes = fire_classes(attrs["flag_values"], attrs["flag_meanings"])
    values = np.asarray(fire_result.values, dtype=float)
    rows, cols = np.nonzero(np.isin(values, list(classes)))
    area = attrs["area"]
    xs, ys = area.get_proj_vectors()
    to_ll = Transformer.from_crs(area.crs, 4326, always_xy=True).transform
    c1 = np.minimum(cols + 1, len(xs) - 1); r1 = np.minimum(rows + 1, len(ys) - 1)
    lon, lat = to_ll(xs[cols], ys[rows])
    lon_e, lat_e = to_ll(xs[c1], ys[rows])
    lon_s, lat_s = to_ll(xs[cols], ys[r1])
    with np.errstate(invalid="ignore"):
        scan, track = _km(lon, lat, lon_e, lat_e), _km(lon, lat, lon_s, lat_s)
    w, s, e, n = bbox
    ok = np.isfinite(lon) & np.isfinite(lat) & (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    when = pd.Timestamp(attrs["start_time"])
    when = when.tz_localize("UTC") if when.tzinfo is None else when.tz_convert("UTC")
    prob = (np.asarray(fire_probability.values, dtype=float)[rows, cols]
            if fire_probability is not None else np.full(len(rows), np.nan))
    df = pd.DataFrame({
        "latitude": lat, "longitude": lon, "acq_dt": when, "scan": scan, "track": track,
        "confidence": [classes[int(v)] for v in values[rows, cols]], "fire_probability": prob,
        "frp": np.nan, "satellite": satellite, "source": "MTG_FIR"})[ok]
    return df.reset_index(drop=True)[COLUMNS]


def read_file(nc_files, bbox=STUDY_BBOX) -> pd.DataFrame:
    """Read the file(s) of ONE repeat cycle."""
    from satpy import Scene
    scn = Scene(filenames=[str(p) for p in nc_files], reader="fci_l2_nc")
    names = [n for n in ("fire_result", "fire_probability") if n in scn.available_dataset_names()]
    if "fire_result" not in names:
        raise RuntimeError(f"fire_result not in {sorted(scn.available_dataset_names())}")
    scn.load(names)
    return fire_pixels(scn["fire_result"], scn["fire_probability"] if "fire_probability" in names else None, bbox)


def fetch_fir(start: datetime, end: datetime, bbox=STUDY_BBOX, cache_dir=None, store=None) -> pd.DataFrame:
    """All FIR detections in [start, end] inside `bbox`, one repeat cycle at a time."""
    frames = []
    for product in list_products(start, end, store):
        files = download(product, cache_dir)
        if files:
            frames.append(read_file(files, bbox))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def fetch_latest(minutes: int = 90, bbox=STUDY_BBOX, **kw) -> pd.DataFrame:
    """The last `minutes` of detections: what the live view polls every 10 minutes."""
    end = datetime.now(timezone.utc).replace(tzinfo=None)
    return fetch_fir(end - timedelta(minutes=minutes), end, bbox, **kw)
