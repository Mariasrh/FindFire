"""Build the online demo for GitHub Pages: docs/demo/index.html, steps.json and logo.png, from the Kabylie replay.

    python scripts/export_static_demo.py

It reads the cached detections and winds in data/archive (copy them from data/demo first), so it needs no key.
Then on GitHub: Settings > Pages > Deploy from a branch > main, /docs.
The demo is at https://<user>.github.io/<repo>/demo/
"""
import datetime as dt
from pathlib import Path

from findfire.config import DATA_DIR, STUDY_BBOX
from findfire.dashboard import server
from findfire.dashboard.static_export import payloads_for, static_page, write_static_demo
from findfire.detection.filters import load_exclusions
from findfire.live.events import fetch_period, load_events
from findfire.zones.tracking import run_tracking

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "src" / "findfire" / "dashboard"
server.WIND_CACHE_PATH = DATA_DIR / "archive" / "wind_cache.json"     # winds of the fire dates, offline

ev = load_events()[0]
start, end = dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"])
viirs, notes = fetch_period(start, end)
print("; ".join(notes))
w, s, e, n = STUDY_BBOX
viirs = viirs[viirs.latitude.between(s, n) & viirs.longitude.between(w, e)]
snaps = run_tracking(viirs, None, load_exclusions())["snaps"]
print(f"{ev['name']}: {len(viirs)} hotspots, {len(snaps)} steps. Computing the dashboard for each step...")
answers = payloads_for(snaps, DATA_DIR / "fire_stations.csv", DATA_DIR / "live", ev["name"])
warnings = sorted({w for a in answers for w in a.get("warnings", [])})
if warnings:
    print("warnings:", warnings[:3])
page = static_page((DASH / "index.html").read_text(encoding="utf-8"))
out = write_static_demo(ROOT / "docs" / "demo", answers, page, DASH / "logo.png")
print(f"done: {out} ({(out / 'steps.json').stat().st_size / 1e6:.1f} MB of steps)")