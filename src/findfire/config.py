"""Central configuration loaded from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")
EUMETSAT_KEY = os.getenv("EUMETSAT_KEY", "")
EUMETSAT_SECRET = os.getenv("EUMETSAT_SECRET", "")

DATA_DIR = Path(os.getenv("FINDFIRE_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))

# Algeria bounding box: west, south, east, north
ALGERIA_BBOX = (-8.7, 19.0, 12.0, 37.1)

# Study area for the MVP: northern Algeria (west, south, east, north).
# The whole-country box above also covers the Sahara gas fields, whose permanent flares show up as fires.
STUDY_BBOX = (-2.0, 34.0, 8.5, 37.5)

# ---------------------------------------------------------------- FIRMS (VIIRS)
# NRT = last days, SP = archive that is only complete weeks/months later (check /api/data_availability).
FIRMS_NRT_SOURCES = ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "VIIRS_NOAA21_NRT"]
FIRMS_SP_SOURCES = ["VIIRS_NOAA20_SP", "VIIRS_SNPP_SP"]
MIN_CONFIDENCE = "n"            # VIIRS classes: l < n < h

# ---------------------------------------------------------------- False-alarm filters
# Keep only FIRMS `type == 0` (presumed vegetation fire): drops volcanoes (1), other static land sources
# such as gas flares, refineries and industry (2), and offshore detections (3). The field only exists in the
# standard-quality products and saved CSVs, not in NRT, so live NRT rows pass through unchanged.
VEGETATION_ONLY = os.getenv("FINDFIRE_VEGETATION_ONLY", "1").lower() not in ("0", "false", "no")

# ---------------------------------------------------------------- EUMETSAT MTG
MTG_FIR_COLLECTION = "EO:EUM:DAT:0682"   # FCI L2 Active Fire Monitoring (netCDF), 2 km, 10 min, pre-operational

# ---------------------------------------------------------------- Zone building (tune on real events)
CLOSE_M = 750            # closes small gaps inside a zone polygon (metres)
LINK_GAP_M = 750         # two hotspots are linked when the gap between their pixel footprints is <= this ...
LINK_GAP_PIXELS = 2.0    # ... or <= this many pixel widths (= up to two missed pixels in a row), whichever is larger
CORE_MIN_NEIGHBORS = 1   # DBSCAN-style core rule: 1 = any linked pair forms a cluster, 2-3 = resists chaining
REDETECTION_H = 3.0      # same pixel seen by another satellite within this many hours = one observation

# ---------------------------------------------------------------- Zone footprint
FOOTPRINT_METHOD = "alpha"   # "alpha" (FEDS-style alpha shape) | "close" (morphological closing) | "boxes" (pixels only)
ALPHA_SCALE = 1.5            # alpha shape radius = this x mean nearest-neighbour distance of the zone's hotspots
EDGE_FRACTION = 0.5          # footprint = alpha shape of pixel centres buffered by this x half pixel (1 = full pixel)
