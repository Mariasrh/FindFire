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

# ---------------------------------------------------------------- EUMETSAT MTG
MTG_FIR_COLLECTION = "EO:EUM:DAT:0682"   # FCI L2 Active Fire Monitoring (netCDF), 2 km, 10 min, pre-operational

# ---------------------------------------------------------------- Zone building (tune on real events)
CLOSE_M = 750            # closes small gaps inside a zone polygon (metres)
LINK_GAP_M = 750         # two hotspots are linked when the gap between their pixel footprints is <= this ...
LINK_GAP_PIXELS = 2.0    # ... or <= this many pixel widths (= up to two missed pixels in a row), whichever is larger
CORE_MIN_NEIGHBORS = 1   # DBSCAN-style core rule: 1 = any linked pair forms a cluster, 2-3 = resists chaining
REDETECTION_H = 3.0      # same pixel seen by another satellite within this many hours = one observation
