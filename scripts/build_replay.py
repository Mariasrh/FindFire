"""Build the historical replay (data/replay/replay.html).

    python scripts/build_replay.py --from-store                       # what run_live.py collected (last 7 days)
    python scripts/build_replay.py --csv data/raw/firms_algeria.csv   # a saved FIRMS CSV
    python scripts/build_replay.py --event 2023-07-24 2023-07-28      # archive event from FIRMS (*_SP sources, needs FIRMS_MAP_KEY)
Options: --step-hours 12  --window-days 7  --link-hours 72  --min-neighbors 1
"""
import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from findfire.config import DATA_DIR, FIRMS_SP_SOURCES, STUDY_BBOX
from findfire.detection.filters import load_exclusions
from findfire.ingestion import firms
from findfire.live.replay import render_replay
from findfire.live.store import Store
from findfire.zones.tracking import run_tracking

a = argparse.ArgumentParser()
a.add_argument("--from-store", action="store_true"); a.add_argument("--csv"); a.add_argument("--event", nargs=2)
a.add_argument("--step-hours", type=float, default=12); a.add_argument("--window-days", type=float, default=7)
a.add_argument("--link-hours", type=float, default=72); a.add_argument("--min-neighbors", type=int, default=1)
a.add_argument("--out", default=str(DATA_DIR / "replay"))
a = a.parse_args()

mtg = None
if a.csv:
    viirs, title = firms.load_csv(a.csv), f"Replay: {Path(a.csv).name}"
elif a.event:
    s, e = (dt.date.fromisoformat(x) for x in a.event)
    viirs, title = firms.fetch_range(FIRMS_SP_SOURCES, s, e), f"Replay: {s} to {e}"
else:
    st = Store(DATA_DIR / "live"); viirs, mtg, title = st.load("viirs"), st.load("mtg"), "Replay: last 7 days"
w, s_, e_, n = STUDY_BBOX
viirs = viirs[viirs.latitude.between(s_, n) & viirs.longitude.between(w, e_)]
if mtg is not None and len(mtg) == 0:
    mtg = None
excl = load_exclusions()
res = run_tracking(viirs, mtg, excl, pd.Timedelta(hours=a.step_hours), pd.Timedelta(days=a.window_days),
                   pd.Timedelta(hours=a.link_hours), a.min_neighbors)
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
render_replay(res, out / "replay.html", excl, title)
last = res["snaps"][-1]["zones"] if res["snaps"] else []
print(f"{len(res['steps'])} steps, {len(last)} zones at the end, merges: {len(res['merges'])} -> {out / 'replay.html'}")
