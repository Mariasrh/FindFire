"""Copernicus EMS (EMSR533) vector products: the mapped burned area used as the validation reference.

The files are NOT in git. Download the *Vector Package (.zip)* of each product of activation EMSR533 (August 2021
Kabylie fires) from https://mapping.emergency.copernicus.eu/activations/EMSR533/ and unzip one product per folder:

    data/emsr533/Delineation/   data/emsr533/Monit01/   ...   data/emsr533/Monit04/

Every product folder holds an `observedEvent` and an `areaOfInterest` shapefile; load_product() merges the areas.
"""
from __future__ import annotations

import pandas as pd
import geopandas as gpd

from findfire.config import DATA_DIR

EMSR_DIR = DATA_DIR / "emsr533"


def _layers(folder, key):
    """All .shp files under `folder` whose name contains `key` (case-insensitive)."""
    return sorted(p for p in folder.rglob("*.shp") if key in p.name.lower())


def load_product(name: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """-> (observed event, area of interest) in lon/lat for one product folder, areas merged."""
    folder = EMSR_DIR / name
    ref_fs, aoi_fs = _layers(folder, "observedevent"), _layers(folder, "areaofinterest")
    if not ref_fs or not aoi_fs:
        found = [p.name for p in folder.rglob("*.shp")]
        raise FileNotFoundError(f"{name}: need 'observedEvent' and 'areaOfInterest' shapefiles. Found: {found}")
    read = lambda fs: pd.concat([gpd.read_file(f).to_crs(4326) for f in fs], ignore_index=True)
    return gpd.GeoDataFrame(read(ref_fs), crs=4326), gpd.GeoDataFrame(read(aoi_fs), crs=4326)
