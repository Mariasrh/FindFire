"""Build data/static_sources.csv: permanent heat sources (gas flares, refineries, industry).

FIRMS NRT (what the live map polls) has no `type` field, so the vegetation-only filter cannot run on it. This
script learns where the permanent sources are from SP history (which does have `type` and months of coverage) and
writes a small exclusion list that the live path can apply without any labels.

    python scripts/build_static_mask.py                       # last 12 months of available SP
    python scripts/build_static_mask.py --months 6 --min-days 15
    python scripts/build_static_mask.py --start 2025-06-01 --end 2025-09-30

Run it before the fire season; the mask is stable from year to year.
"""
import argparse
import datetime as dt
import time
from pathlib import Path

import pandas as pd

from findfire.config import DATA_DIR, FIRMS_SP_SOURCES, STUDY_BBOX
from findfire.detection.filters import build_static_mask
from findfire.ingestion import firms

a = argparse.ArgumentParser()
a.add_argument("--start", help="first day (default: end - months)")
a.add_argument("--end", help="last day (default: newest date available in SP)")
a.add_argument("--months", type=float, default=12)
a.add_argument("--min-days", type=int, default=20, help="distinct days a cell must be hot to count as static")
a.add_argument("--cell-deg", type=float, default=0.01, help="grid cell size (~1.1 km)")
a.add_argument("--radius-km", type=float, default=1.5, help="exclusion radius around each cell")
a.add_argument("--out", default=str(DATA_DIR / "static_sources.csv"))
a = a.parse_args()

av = firms.availability()
sp = av[av["data_id"].isin(FIRMS_SP_SOURCES)]
end = dt.date.fromisoformat(a.end) if a.end else pd.to_datetime(sp["max_date"]).max().date()
start = dt.date.fromisoformat(a.start) if a.start else end - dt.timedelta(days=round(a.months * 30.44))
print(f"SP history {start} to {end} over {STUDY_BBOX} (study box)")

frames, seen = [], set()
for source in FIRMS_SP_SOURCES:
    cur, got = start, 0
    while cur <= end:
        n = min(5, (end - cur).days + 1)
        try:
            raw = firms.fetch_area(source, STUDY_BBOX, n, cur)
            d = firms.prepare(raw, vegetation=False)
            d = d[["latitude", "longitude", "acq_dt", "type"]]
            frames.append(d); got += len(d)
        except Exception as exc:
            print(f"  {source} {cur}: {exc}")
        cur += dt.timedelta(days=n); time.sleep(0.4)
    print(f"  {source}: {got} detections")

h = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
if h.empty:
    raise SystemExit("no SP detections returned; check FIRMS availability")
print(f"{len(h)} detections, {h.acq_dt.dt.date.nunique()} distinct days")

mask = build_static_mask(h, min_days=a.min_days, cell_deg=a.cell_deg)
mask["radius_km"] = a.radius_km
out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
mask[["name", "latitude", "longitude", "radius_km", "days_seen"]].to_csv(out, index=False)
print(f"{len(mask)} static sources -> {out}")
