"""Land cover under a zone, from ESA WorldCover 10 m. Two releases are supported: 2020 (v100) and 2021 (v200).

Why two years: a map built from imagery of year Y can already contain burn scars of fires that happened in Y, and a
fresh scar is mapped as bare / sparse vegetation. To label the land BEFORE a fire, use the latest map from a year before
the fire (`year_for`): the Aug 2021 Kabylie validation uses 2020, live fires in 2026 use 2021.

Source (checked in the product documentation): global 10 m land cover from Sentinel-1/2, 11 classes, WGS84, delivered as
3 x 3 degree Cloud-Optimized GeoTIFFs on the public bucket s3://esa-worldcover (eu-central-1, no account), licence CC BY 4.0.
2021 / v200: overall accuracy 76.7 % (independent validation by Wageningen University and IIASA).
2020 / v100: earlier algorithm, lower reported accuracy (74.4 %: VERIFY in the v100 Product Validation Report before quoting).
The two releases are NOT a change-detection pair: part of their difference is the algorithm change, not the land.
Class accuracy varies, so a zone label is an estimate. Attribution: (c) ESA WorldCover project <year> / Contains modified
Copernicus Sentinel data (<year>) processed by ESA WorldCover consortium.

Because the files are COGs, only the pixels under a zone are read over HTTP (no 100 GB download). Tiles can also be placed
in a local folder (same file names; both years can share one folder) and are then read from disk, which is how the tests
and offline demos work.

If a tile cannot be read this module raises `LandCoverUnavailable`; it never falls back to a guess such as "forest".
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import box, mapping

from findfire.config import DATA_DIR

VERSIONS = {2020: "v100", 2021: "v200"}
ACCURACY_PCT = {2020: 74.4, 2021: 76.7}        # global overall accuracy; the 2020 figure must be confirmed in the v100 PVR
DEFAULT_YEAR = 2021
TILE_DEG = 3
YEAR, VERSION = DEFAULT_YEAR, VERSIONS[DEFAULT_YEAR]        # aliases for older imports (grep before removing)
CLASSES = {10: "tree cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built-up", 60: "bare / sparse vegetation",
           70: "snow and ice", 80: "permanent water", 90: "herbaceous wetland", 95: "mangroves", 100: "moss and lichen"}
LABEL = {10: "forest", 20: "scrub", 30: "grass", 40: "crop", 50: "built-up", 60: "bare"}      # everything else -> "other"
FUEL = {10: "forest", 20: "shrub", 30: "grass"}          # the vegetation keys used by the fire-growth forecast


class LandCoverUnavailable(RuntimeError):
    pass


def _version(year: int) -> str:
    try:
        return VERSIONS[year]
    except KeyError:
        raise ValueError(f"WorldCover exists only for {sorted(VERSIONS)}, got {year}") from None


def base_url(year: int) -> str:
    return f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/{_version(year)}/{year}/map"


def source_name(year: int) -> str:
    return f"ESA WorldCover {year} {_version(year)} (10 m)"


def year_for(event_date) -> int:
    """Latest map that does not include the event: the land BEFORE the fire (event_date: date, datetime or Timestamp)."""
    earlier = [y for y in VERSIONS if y < event_date.year]
    if not earlier:
        raise ValueError(f"no WorldCover map predates {event_date}: available years are {sorted(VERSIONS)}")
    return max(earlier)


def tile_id(lat: float, lon: float) -> str:
    """WorldCover tile name of the 3 x 3 degree tile containing (lat, lon): south-west corner, e.g. N36E003."""
    lat0, lon0 = math.floor(lat / TILE_DEG) * TILE_DEG, math.floor(lon / TILE_DEG) * TILE_DEG
    return f"{'N' if lat0 >= 0 else 'S'}{abs(lat0):02d}{'E' if lon0 >= 0 else 'W'}{abs(lon0):03d}"


def tile_filename(tile: str, year: int = DEFAULT_YEAR) -> str:
    return f"ESA_WorldCover_10m_{year}_{_version(year)}_{tile}_Map.tif"


def _tile_box(tile: str):
    lat0 = (1 if tile[0] == "N" else -1) * int(tile[1:3])
    lon0 = (1 if tile[3] == "E" else -1) * int(tile[4:7])
    return box(lon0, lat0, lon0 + TILE_DEG, lat0 + TILE_DEG)


def _tiles_for(geom) -> list[str]:
    w, s, e, n = geom.bounds
    eps = 1e-9
    return sorted({tile_id(lat, lon) for lat in np.arange(math.floor(s / 3) * 3, n + eps, 3) + 1e-6
                   for lon in np.arange(math.floor(w / 3) * 3, e + eps, 3) + 1e-6} |
                  {tile_id(s, w), tile_id(n - eps, e - eps)})


def _counts(geom, source_dir: Path | None, remote: bool, year: int = DEFAULT_YEAR) -> dict[int, int]:
    import rasterio
    import rasterio.mask
    _version(year)                                                      # fail early on an unknown year
    counts: dict[int, int] = {}
    for tile in _tiles_for(geom):
        part = geom.intersection(_tile_box(tile))
        if part.is_empty:
            continue
        name = tile_filename(tile, year)
        local = source_dir / name if source_dir else None
        if local is not None and local.exists():
            path = str(local)
        elif remote:
            path = f"{base_url(year)}/{name}"
        else:
            raise LandCoverUnavailable(f"tile {name} not found in {source_dir}")
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                              GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="1"):
                with rasterio.open(path) as src:
                    try:
                        data, _ = rasterio.mask.mask(src, [mapping(part)], crop=True, filled=False)
                    except ValueError:                                  # the zone part does not overlap this raster
                        continue
        except rasterio.errors.RasterioIOError as exc:
            raise LandCoverUnavailable(f"cannot read {path}: {exc}") from exc
        valid = data[0].compressed()
        for code, n in zip(*np.unique(valid, return_counts=True)):
            counts[int(code)] = counts.get(int(code), 0) + int(n)
    return counts


def summarise(counts: dict[int, int], year: int = DEFAULT_YEAR) -> dict:
    """Class counts -> the land-cover record of a zone."""
    known = {c: n for c, n in counts.items() if c in CLASSES}
    total = sum(known.values())
    if total == 0:
        raise LandCoverUnavailable("no land-cover pixels under this zone (sea, or outside the tile data)")
    classes = {c: n / total for c, n in sorted(known.items())}
    shares: dict[str, float] = {}
    for c, f in classes.items():
        shares[LABEL.get(c, "other")] = shares.get(LABEL.get(c, "other"), 0.0) + f
    top = max(classes, key=classes.get)
    label = LABEL.get(top, "other")
    return dict(label=label, fuel=FUEL.get(top), dominant_class=CLASSES[top], dominant_share=round(shares[label], 4),
                majority=shares[label] > 0.5, shares={k: round(v, 4) for k, v in sorted(shares.items())},
                classes={CLASSES[c]: round(f, 4) for c, f in classes.items()}, n_pixels=total,
                source=source_name(year), year=year)


def zone_land_cover(geometry, source_dir=None, remote: bool = True, year: int = DEFAULT_YEAR) -> dict:
    """Land cover under a zone footprint (shapely Polygon/MultiPolygon in lon/lat), read from the map of `year`.

    label = the class group that covers the largest share of the footprint; `majority` says whether it covers more than half.
    fuel = the forecast's vegetation key (forest / shrub / grass) of the dominant class, or None when it is not vegetation fuel."""
    return summarise(_counts(geometry, Path(source_dir) if source_dir else None, remote, year), year)


# ---------------------------------------------------------------- zones
def _key(geom, year: int = DEFAULT_YEAR) -> str:
    # same formula as before (year + version + wkt), so cache entries written for 2021 stay valid
    return hashlib.sha1(f"{year}{_version(year)}{geom.wkt}".encode()).hexdigest()[:16]


def annotate_zones(zones: list[dict], source_dir=None, remote: bool = True, cache_file=None,
                   year: int = DEFAULT_YEAR) -> list[dict]:
    """Add `land_cover` (record or None) and, when unavailable, `land_cover_error` to every zone dict (needs `geometry`).
    Results are cached by year + footprint so the live loop does not re-read the same zone every cycle."""
    cache_file = Path(cache_file or DATA_DIR / "landcover" / "cache.json")
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    changed = False
    for z in zones:
        geom = z["geometry"]
        k = _key(geom, year)
        if k not in cache:
            try:
                cache[k] = zone_land_cover(geom, source_dir, remote, year); changed = True
            except LandCoverUnavailable as exc:
                z["land_cover"], z["land_cover_error"] = None, str(exc)
                continue
        z["land_cover"] = dict(cache[k], year=year)             # entries cached before `year` existed get it here
    if changed:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache))
    return zones