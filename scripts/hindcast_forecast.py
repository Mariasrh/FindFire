"""Compare the growth model with what the satellites actually saw, on a past event.

    python scripts/hindcast_forecast.py --csv data/raw/firms_study.csv --wind 4 270
    python scripts/hindcast_forecast.py --event 2023-07-24 2023-07-28 --archive-wind

For every active zone and every 12 h step it forecasts the area one step later (720 min) and compares it with the
area the tracking measured then. LIMIT: VIIRS flies over about twice a day, so 30/60/120 min forecasts cannot be
checked with FIRMS; 12 h is the shortest horizon we can score, and it is far beyond what the model is meant for.
Use the result to CALIBRATE the base rates (the ratio below), not as proof the 2 h numbers are right.
"""
import argparse
import datetime as dt

import numpy as np
import pandas as pd

from findfire.config import FIRMS_SP_SOURCES, STUDY_BBOX
from findfire.detection.filters import load_exclusions
from findfire.forecast.spread import BASE_ROS_M_MIN, grow
from findfire.forecast.wind import Wind, cached_wind
from findfire.ingestion import firms
from findfire.zones.tracking import run_tracking

ap = argparse.ArgumentParser()
ap.add_argument("--csv"); ap.add_argument("--event", nargs=2)
ap.add_argument("--wind", nargs=2, type=float, metavar=("SPEED_MS", "FROM_DEG"))
ap.add_argument("--archive-wind", action="store_true", help="Open-Meteo wind at the time of each step; old events use the archive (needs internet)")
ap.add_argument("--vegetation", default="shrub", choices=sorted(BASE_ROS_M_MIN))
ap.add_argument("--step-hours", type=float, default=12)
a = ap.parse_args()
if not (a.wind or a.archive_wind):
    raise SystemExit("give --wind SPEED FROM_DEG or --archive-wind")

if a.csv:
    v = firms.load_csv(a.csv)
else:
    s, e = (dt.date.fromisoformat(x) for x in a.event)
    v = firms.fetch_range(FIRMS_SP_SOURCES, s, e)
w, s_, e_, n = STUDY_BBOX
v = v[v.latitude.between(s_, n) & v.longitude.between(w, e_)]
res = run_tracking(v, None, load_exclusions(), step=pd.Timedelta(hours=a.step_hours))


def wind_for(c, t):
    """Fixed wind, or the real wind of that moment (archive for old events). Raises if Open-Meteo cannot answer."""
    return Wind(*a.wind) if a.wind else cached_wind(c.y, c.x, t)


rows = []
for s0, s1 in zip(res["snaps"][:-1], res["snaps"][1:]):
    later = {z["zone_id"]: z for z in s1["zones"]}
    for z in s0["zones"]:
        if z["status"] == "inactive" or z["zone_id"] not in later:
            continue
        pred = grow(z["area_ha"], wind_for(z["geometry"].centroid, s0["time"]), a.vegetation, a.step_hours * 60)["area_ha"]
        rows.append(dict(zone=z["zone_id"], t=s0["time"], now=z["area_ha"], predicted=pred, observed=later[z["zone_id"]]["area_ha"]))
d = pd.DataFrame(rows)
if d.empty:
    raise SystemExit("no zone is tracked across two steps: use a longer period")
d["pred_growth"] = d.predicted - d.now
d["obs_growth"] = d.observed - d.now
d["ratio"] = d.predicted / d.observed
show = d.copy()
show["t"] = show["t"].dt.strftime("%Y-%m-%d %H:%M")
print(show.round(1).to_string(index=False))
grew = d[d.obs_growth > 0.5]
print(f"\n{len(d)} zone-steps | median predicted/observed area = {d.ratio.median():.2f} (1.00 = perfect)")
print(f"mean absolute error {np.abs(d.predicted - d.observed).mean():.1f} ha | "
      f"zones where observed area did not grow: {(d.obs_growth <= 0.5).mean():.0%}")
if len(grew):
    print(f"ONLY zones that really grew ({len(grew)}): median predicted/observed growth = "
          f"{(grew.pred_growth / grew.obs_growth).median():.1f}x")
else:
    print("no zone grew in the observed data: calibration is not possible on this period")
print("Reading it: ratio > 1 = model grows fires too fast (lower BASE_ROS_M_MIN); < 1 = too slow.")
print("Most zones in a quiet period stop growing, so judge the model on the growing zones and on a real wildfire event.")
print("Observed area is a cumulative hotspot footprint, not a burned-area map: treat it as a rough reference.")