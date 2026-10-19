"""Live loop: poll MTG (every few minutes) and FIRMS (every ~10 min), rebuild zones + alerts, write the map.

    python scripts/run_live.py                      # run forever, Ctrl+C to stop
    python scripts/run_live.py --once               # one cycle, then exit (good first test)
    python scripts/run_live.py --once --viirs-csv data/raw/firms_algeria.csv --no-mtg --no-firms   # fully offline

Outputs in data/live/: map.html (open in a browser; refreshes itself), state.json, detections CSVs, watermarks.json.
"""
import argparse
import json
import time
import traceback
from datetime import timedelta
from shapely.geometry import mapping

import pandas as pd

from findfire.config import DATA_DIR, STUDY_BBOX
from findfire.detection.filters import load_exclusions
from findfire.ingestion import firms, mtg
from findfire.live.mapview import render
from findfire.live.pipeline import build_state, latency_minutes
from findfire.live.store import Store, utcnow


def log(msg): print(f"[{utcnow():%H:%M:%S}Z] {msg}", flush=True)


def poll_firms(store, days=2):
    new = store.add("viirs", firms.fetch_recent(days=days))
    store.set_watermarks(firms_last_ok=utcnow().isoformat())
    log(f"FIRMS: {new} new detections")


def poll_mtg(store, backfill_h):
    wm = store.watermarks()
    now = utcnow().tz_localize(None) if utcnow().tzinfo else utcnow()
    since = pd.Timestamp(wm["mtg_last_sensing"]).tz_localize(None) if "mtg_last_sensing" in wm else now - timedelta(hours=backfill_h)
    todo = [p for p in mtg.list_products(since, now) if pd.Timestamp(p.sensing_start) > since]
    total = 0
    for p in todo:                                          # oldest first; stop at the first failure so there are no gaps
        try:
            df = mtg.read_file(mtg.download(p), STUDY_BBOX)
        except Exception as exc:
            log(f"MTG granule {p.sensing_start} failed, will retry: {exc}")
            break
        total += store.add("mtg", df)
        store.set_watermarks(mtg_last_sensing=str(pd.Timestamp(p.sensing_start)), mtg_last_ok=utcnow().isoformat())
    log(f"MTG: {len(todo)} new granules, {total} fire pixels in the study box")


def rebuild(store, out, viirs_csv=None):
    now = utcnow()
    viirs = firms.load_csv(viirs_csv) if viirs_csv else store.load("viirs")
    w, s_, e, n = STUDY_BBOX                                  # a CSV may cover all of Algeria (Sahara flares)
    if len(viirs):
        viirs = viirs[viirs.latitude.between(s_, n) & viirs.longitude.between(w, e)].reset_index(drop=True)
    mtg_df = store.load("mtg")
    zones, hot, alerts, through = build_state(viirs, mtg_df, now, load_exclusions())
    wm = store.watermarks()
    mt = pd.Timestamp(wm["mtg_last_sensing"]) if "mtg_last_sensing" in wm else None
    lat = {"viirs": latency_minutes(viirs), "mtg": latency_minutes(mtg_df)}
    banner = (f"MTG scans up to {mt:%H:%M} UTC" if mt is not None else "MTG: no data") + \
             (f" | newest VIIRS detection {through:%d %b %H:%M} UTC" if through is not None else " | VIIRS: no data") + \
             f" | {len(zones)} zones, {len(alerts)} alerts | built {now:%H:%M} UTC. Estimates only."
    render(zones, hot if len(hot) else pd.DataFrame(columns=["latitude", "longitude", "acq_dt", "satellite", "frp", "zone_id"]),
           alerts, banner, out / "map.html")
    iso = lambda t: None if pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")
    (out / "state.json").write_text(json.dumps(dict(
        built=iso(now), mtg_scans_through=iso(mt) if mt is not None else None, viirs_newest_detection=iso(through),
        latency_min_median_p90=lat,
        zones=[dict(type="Feature", geometry=mapping(z["geometry"]), properties={k: (iso(v) if k.endswith("detected") else v)
               for k, v in z.items() if k != "geometry"}) for z in zones],
        alerts=json.loads(alerts.to_json(orient="records", date_format="iso"))), default=str))
    log(f"rebuilt: {len(zones)} zones, {len(alerts)} alerts -> {out / 'map.html'}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--once", action="store_true"); a.add_argument("--no-mtg", action="store_true")
    a.add_argument("--no-firms", action="store_true"); a.add_argument("--viirs-csv")
    a.add_argument("--mtg-every", type=int, default=150); a.add_argument("--firms-every", type=int, default=600)
    a.add_argument("--backfill-h", type=float, default=3.0); a.add_argument("--out", default=str(DATA_DIR / "live"))
    a = a.parse_args()
    store = Store(a.out); out = store.dir
    next_m = next_f = 0.0
    while True:
        now, changed = time.time(), False
        for flag, name, due, fn in ((a.no_mtg, "mtg", next_m, lambda: poll_mtg(store, a.backfill_h)),
                                    (a.no_firms, "firms", next_f, lambda: poll_firms(store))):
            if not flag and now >= due:
                try:
                    fn(); changed = True
                except Exception:
                    log(f"{name} poll failed (will retry):\n{traceback.format_exc(limit=2)}")
                if name == "mtg": next_m = now + a.mtg_every
                else: next_f = now + a.firms_every
        if changed or a.once:
            rebuild(store, out, a.viirs_csv)
        if a.once:
            break
        time.sleep(15)


if __name__ == "__main__":
    main()
