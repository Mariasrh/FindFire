"""Central configuration loaded from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()

FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")
EUMETSAT_KEY = os.getenv("EUMETSAT_KEY", "")
EUMETSAT_SECRET = os.getenv("EUMETSAT_SECRET", "")

# Algeria bounding box: west, south, east, north
ALGERIA_BBOX = (-8.7, 19.0, 12.0, 37.1)