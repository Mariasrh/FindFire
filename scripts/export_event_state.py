"""Write the zones of a past event (e.g. Kabylie, Aug 2021) in the state.json layout, so the landcover scripts can read them.

    python scripts/export_event_state.py --event 2021-08-08 2021-08-16 --out data/events/kabylie2021/state.json   # needs FIRMS_MAP_KEY
    python scripts/export_event_state.py --csv data/raw/firms_algeria.csv --out data/events/kabylie2021/state.json

It runs the same tracking as validate_emsr.py and keeps the zones of the LAST step (the zones the validation compares).
`scripts/landcover_zones.py` and `scripts/validate_landcover.py` read data/live/state.json (live zones, built now), so without
this file they would label today's fires, not the 2021 ones.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from findfire.config import FIRMS_SP_SOURCES, STUDY_BBOX
from findfire.detection.filters import load_exclusions
from findfire.ingestion import firms
from findfire.zones.tracking import run_tracking

a = argparse.ArgumentParser()
a.add_argument("--csv"); a.add_argument("--event", nargs=2, metavar=("START", "END"))
a.add_argument("--step-hours", type=float, default=12); a.add_argument("--window-days", type=float, default=7)
a.add_argument("--link-hours", type=float, default=72); a.add_argument("--min-neighbors", type=int, default=1)
a.add_argument("--out", required=True)
a = a.parse_args()
if not a.csv and not a.event:
    a.event = ["2021-08-08", "2021-08-16"]

if a.csv:
    viirs = firms.load_csv(a.csv)
else:
    s, e = (dt.date.fromisoformat(x) for x in a.event)
    viirs = firms.fetch_range(FIRMS_SP_SOURCES, s, e)
w, s_, e_, n = STUDY_BBOX
viirs = viirs[viirs.latitude.between(s_, n) & viirs.longitude.between(w, e_)].reset_index(drop=True)
res = run_tracking(viirs, None, load_exclusions(), step=pd.Timedelta(hours=a.step_hours),
                   window=pd.Timedelta(days=a.window_days), link_dt=pd.Timedelta(hours=a.link_hours),
                   min_neighbors=a.min_neighbors)
zones = res["snaps"][-1]["zones"] if res["snaps"] else []


def plain(o):
    return o.item() if hasattr(o, "item") else str(o)


state = dict(event=a.event or a.csv, first_detection=str(viirs.acq_dt.min()), last_detection=str(viirs.acq_dt.max()),
             zones=[dict(type="Feature", geometry=mapping(z["geometry"]),
                         properties={k: v for k, v in z.items() if k != "geometry"}) for z in zones])
out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(state, default=plain))
print(f"{len(viirs)} hotspots, {len(zones)} zones -> {out}")
