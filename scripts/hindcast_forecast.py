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
ap.add_argument("--rate-scale", nargs="+", type=float, metavar="F",
                help="also try these factors on the base spread rate (e.g. 1 0.5 0.2 0.1) and show where the growth ratio crosses 1")
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
print(f"FIRMS data ready: {len(v)} hotspots. Tracking...", flush=True)
res = run_tracking(v, None, load_exclusions(), step=pd.Timedelta(hours=a.step_hours))


def wind_for(c, t):
    """Fixed wind, or the real wind of that moment (archive for old events). Raises if Open-Meteo cannot answer."""
    if a.wind:
        return Wind(*a.wind)
    # 0.5 degree grid: reanalysis wind is smooth over tens of km, and fewer cells means far fewer slow requests
    return cached_wind(round(c.y * 2) / 2, round(c.x * 2) / 2, t)


print(f"Tracking done: {len(res['snaps'])} steps. Fetching wind (one request per 0.5 degree cell per day)...", flush=True)
rows, skipped, ctx = [], [], []
for s0, s1 in zip(res["snaps"][:-1], res["snaps"][1:]):
    later = {z["zone_id"]: z for z in s1["zones"]}
    for z in s0["zones"]:
        if z["status"] == "inactive" or z["zone_id"] not in later:
            continue
        try:
            wind = wind_for(z["geometry"].centroid, s0["time"])
        except Exception as exc:                      # no wind for this zone-step: leave it out, do not guess a wind
            skipped.append(f"zone {z['zone_id']} {s0['time']:%Y-%m-%d %H:%M}: {type(exc).__name__}")
            continue
        if len(rows) % 10 == 0:
            print(f"  ...{len(rows)} zone-steps done", flush=True)
        pred = grow(z["area_ha"], wind, a.vegetation, a.step_hours * 60)["area_ha"]
        ctx.append((z["area_ha"], wind, later[z["zone_id"]]["area_ha"]))
        rows.append(dict(zone=z["zone_id"], t=s0["time"], now=z["area_ha"], predicted=pred, observed=later[z["zone_id"]]["area_ha"],
                     new_hs=int(z.get("new_hotspots", 0))))
if skipped:
    print(f"WARNING: {len(skipped)} zone-step(s) left out, no wind data (first: {skipped[0]}). Rerun to retry them.")
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
# by zone size: the model adds a minimum amount of area per step, so small zones overshoot most
d["size"] = pd.cut(d.now, [0, 100, 1000, np.inf], labels=["< 100 ha", "100-1000 ha", "> 1000 ha"])
print("\nBy zone size at the start of the step (predicted/observed area, 1.00 = perfect):")
for name, g in d.groupby("size", observed=True):
    gg = g[g.obs_growth > 0.5]
    gr = f"{(gg.pred_growth / gg.obs_growth).median():.1f}x" if len(gg) else "n/a"
    print(f"  {name:>12}: {len(g):4d} zone-steps | median ratio {g.ratio.median():5.2f} | "
          f"growing zones: {len(gg):3d}, predicted/observed growth {gr}")
# by FIRE STATE at the start of the step: new hotspots in the last step = still growing, none = fading.
# This is known when the forecast is made (unlike "the zone grew", which is the answer), so it is the fair way to split.
def _rng(x):
    return f"{np.median(x):5.1f}x  (middle half {np.percentile(x, 25):.1f}x to {np.percentile(x, 75):.1f}x)"


print("\nBy FIRE STATE at the start of the step (known when the forecast is made; the dashboard forecasts the growing ones):")
for name, g in (("growing (new hotspots)", d[d.new_hs > 0]), ("fading (no new hotspots)", d[d.new_hs == 0])):
    gg = g[g.obs_growth > 0.5]
    print(f"  {name}: {len(g)} zone-steps, of which {len(gg)} really grew in the observed data")
    if len(g):
        print(f"      predicted/observed area, all steps: median {g.ratio.median():.2f}")
    if len(gg):
        print(f"      predicted/observed GROWTH, zones that grew: {_rng(gg.pred_growth / gg.obs_growth)}")
        for sz, h in gg.groupby("size", observed=True):
            print(f"          {sz:>12}: {len(h):3d} zones, {_rng(h.pred_growth / h.obs_growth)}")
print("Reading it: 1x to 3x on the growing steps = acceptable for scenarios; much more = too fast. Fading steps are expected to be too fast.")
print("Reading it: ratio > 1 = model grows fires too fast (lower BASE_ROS_M_MIN); < 1 = too slow.")
print("Most zones in a quiet period stop growing, so judge the model on the growing zones and on a real wildfire event.")
print("Observed area is a cumulative hotspot footprint, not a burned-area map: treat it as a rough reference.")

if a.rate_scale:
    # the winds are already fetched, so trying other factors costs no requests
    print("\nSCAN of the base spread rate (zones that grew; 1.0x = prediction matches observed growth):")
    original = dict(BASE_ROS_M_MIN)
    try:
        for f in a.rate_scale:
            for k in original:
                BASE_ROS_M_MIN[k] = original[k] * f
            pg = np.array([grow(area, wd, a.vegetation, a.step_hours * 60)["area_ha"] - area for area, wd, _ in ctx])
            og = np.array([obs - area for area, _, obs in ctx])
            m = og > 0.5
            g = d["new_hs"].to_numpy() > 0
            rr, rg = pg[m] / og[m], pg[m & g] / og[m & g]
            fmt = lambda x: f"{np.median(x):6.1f}x [{np.percentile(x, 25):.1f}-{np.percentile(x, 75):.1f}]" if len(x) else "   n/a"
            print(f"  rate x{f:<5g}: growing steps {fmt(rg)} | all steps that grew {fmt(rr)}   (median [middle half])")
    finally:
        BASE_ROS_M_MIN.update(original)
    print("Remember: the hotspot footprint undercounts real growth, so do not tune to exactly 1.0x. Check against CEMS.")
    print("If you change the speed, report a range (not one number) and say it comes from one fire only.")
