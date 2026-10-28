"""Replay a real fire into the dashboard.

    python scripts/replay_to_state.py --list                       # show the steps, write nothing
    python scripts/replay_to_state.py                              # first event of data/events.json
    python scripts/replay_to_state.py --event 2021-08-08 2021-08-14 --seconds 8
    python scripts/replay_to_state.py --csv data/raw/firms_algeria.csv

In another terminal:  python scripts/serve_dashboard.py --state data/live/replay_state.json --port 8010
The first run downloads the detections (needs FIRMS_MAP_KEY) and caches them in data/archive,
so the replay works offline afterwards.
"""
import argparse
import datetime as dt
from pathlib import Path

from findfire.config import DATA_DIR, STUDY_BBOX
from findfire.dashboard.replay_player import play, step_summary
from findfire.detection.filters import load_exclusions
from findfire.ingestion import firms
from findfire.live.events import fetch_period, load_events
from findfire.zones.tracking import run_tracking

a = argparse.ArgumentParser()
a.add_argument("--event", nargs=2, metavar=("START", "END"))
a.add_argument("--csv")
a.add_argument("--seconds", type=float, default=10.0, help="pause between two steps")
a.add_argument("--first", type=int, default=1, help="start at this step")
a.add_argument("--list", action="store_true", help="only list the steps")
a.add_argument("--out", default=str(DATA_DIR / "live" / "replay_state.json"))
a = a.parse_args()

if a.csv:
    viirs, name = firms.load_csv(a.csv), Path(a.csv).name
else:
    if a.event:
        start, end = (dt.date.fromisoformat(x) for x in a.event)
        name = f"{start} to {end}"
    else:
        ev = load_events()[0]
        start, end, name = dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"]), ev["name"]
    viirs, notes = fetch_period(start, end)
    print("; ".join(notes))
w, s, e, n = STUDY_BBOX
viirs = viirs[viirs.latitude.between(s, n) & viirs.longitude.between(w, e)]
snaps = run_tracking(viirs, None, load_exclusions())["snaps"]
if not snaps:
    raise SystemExit("no tracking step: this period has no usable detections")
print(f"{name}: {len(viirs)} hotspots, {len(snaps)} steps")
if a.list:
    for i, snap in enumerate(snaps, 1):
        sm = step_summary(snap)
        print(f"  step {i:>2}  {sm['time']} UTC  zones {sm['zones']:>3}  active {sm['live']:>3}  largest {sm['max_area_ha']:.0f} ha")
else:
    play(snaps, a.out, a.seconds, name, a.first)
    print(f"done, last state kept in {a.out}")