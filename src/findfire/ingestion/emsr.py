"""Load EMSR533 (Copernicus rapid-mapping) fire perimeters for comparison."""
from pathlib import Path

import geopandas as gpd

EMSR_DIR = Path(__file__).resolve().parents[3] / "data" / "emsr533"

PRODUCT = "EMSR533_AOI01_DEL"
LAYERS = {
    "delineation": ("Delineation", "PRODUCT", "observedEventA_r1_v2"),
    "monit01": ("Monit01", "MONIT01", "observedEventA_r1_v1"),
    "monit02": ("Monit02", "MONIT02", "observedEventA_r1_v1"),
    "monit03": ("Monit03", "MONIT03", "observedEventA_r1_v1"),
    "monit04": ("Monit04", "MONIT04", "observedEventA_r1_v1"),
}


def load_perimeter(stage: str = "delineation") -> gpd.GeoDataFrame:
    """Return the burned-area polygons of one EMSR533 stage.

    stage: delineation | monit01 | monit02 | monit03 | monit04
    """
    folder, tag, tail = LAYERS[stage]
    return gpd.read_file(EMSR_DIR / folder / f"{PRODUCT}_{tag}_{tail}.shp")


def load_aoi() -> gpd.GeoDataFrame:
    return gpd.read_file(EMSR_DIR / "Delineation" / f"{PRODUCT}_PRODUCT_areaOfInterestA_r1_v2.shp")