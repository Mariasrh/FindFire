"""Validate tracked zones against the Copernicus EMS (EMSR533) burned-area maps.

    python scripts/validate_emsr.py                                        # default: Kabylie 2021
    python scripts/validate_emsr.py --csv data/raw/firms_algeria.csv       # a saved FIRMS CSV (offline)
    python scripts/validate_emsr.py --event 2021-08-08 2021-08-16          # FIRMS *_SP archive (needs FIRMS_MAP_KEY)

The EMSR533 vector products must be unzipped under data/emsr533/<Product>/ (not in git) and the FIRMS window must
reach the last product (16 Aug 2021). There is no synthetic fallback: the reference is a real burn scar.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from findfire.config import DATA_DIR, FIRMS_SP_SOURCES, STUDY_BBOX
from findfire.detection.filters import load_exclusions
from findfire.ingestion import firms
from findfire.validation import validate
from findfire.zones.tracking import run_tracking

a = argparse.ArgumentParser()
a.add_argument("--csv", help="a saved FIRMS CSV")
a.add_argument("--event", nargs=2, metavar=("START", "END"), help="FIRMS archive event, YYYY-MM-DD YYYY-MM-DD")
a.add_argument("--step-hours", type=float, default=12); a.add_argument("--window-days", type=float, default=7)
a.add_argument("--link-hours", type=float, default=72); a.add_argument("--min-neighbors", type=int, default=1)
a.add_argument("--min-zone-ha", type=float, default=0.0,
               help="ignore zones smaller than this many hectares when comparing (validation only)")
a.add_argument("--out", default=str(DATA_DIR / "results"))
a = a.parse_args()
if not a.csv and not a.event:
    a.event = ["2021-08-08", "2021-08-16"]

if a.csv:
    viirs, source = firms.load_csv(a.csv), f"FIRMS {Path(a.csv).name}"
elif a.event:
    s, e = (dt.date.fromisoformat(x) for x in a.event)
    viirs, source = firms.fetch_range(FIRMS_SP_SOURCES, s, e), f"FIRMS archive {s} to {e}"
else:
    a.error("give --csv (offline) or --event START END (FIRMS archive)")
dropped = int(getattr(viirs, "attrs", {}).get("non_vegetation_dropped", 0))
w, s_, e_, n = STUDY_BBOX
viirs = viirs[viirs.latitude.between(s_, n) & viirs.longitude.between(w, e_)].reset_index(drop=True)
res = run_tracking(viirs, None, load_exclusions(), step=pd.Timedelta(hours=a.step_hours),
                   window=pd.Timedelta(days=a.window_days), link_dt=pd.Timedelta(hours=a.link_hours),
                   min_neighbors=a.min_neighbors)
print(f"{len(viirs)} hotspots in the study box | {len(res['steps'])} steps | "
      f"{len(res['snaps'][-1]['zones']) if res['snaps'] else 0} zones at the end"
      + (f" | {dropped} non-vegetation hotspots dropped" if dropped else ""))
validate(res, source, last_data=viirs.acq_dt.max(), out=Path(a.out), min_zone_ha=a.min_zone_ha)
