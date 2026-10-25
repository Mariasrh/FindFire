"""Sanity checks on a real forecast (data/live/forecast.json from scripts/forecast_zones.py).

    python scripts/check_forecast.py                 # internal checks only (no internet)
    python scripts/check_forecast.py --wind-recheck  # also re-fetches the wind for 3 zones and compares (needs internet)

These checks prove the arithmetic and the geometry are right. They do NOT prove the forecast matches reality:
for that run scripts/hindcast_forecast.py.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

from findfire.config import DATA_DIR
from findfire.forecast.spread import rates
from findfire.forecast.wind import Wind, fetch_wind
from findfire.zones.geometry import _transformers, utm_epsg

ap = argparse.ArgumentParser()
ap.add_argument("--forecast", default=str(DATA_DIR / "live" / "forecast.json"))
ap.add_argument("--state", default=str(DATA_DIR / "live" / "state.json"))
ap.add_argument("--wind-recheck", action="store_true")
a = ap.parse_args()

fc = json.loads(Path(a.forecast).read_text())
state = json.loads(Path(a.state).read_text())
status = {f["properties"]["zone_id"]: f["properties"]["status"] for f in state["zones"]}
bad, warn = [], []


def bearing(lon1, lat1, lon2, lat2):
    d = math.atan2(math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2)),
                   math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
                   - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1)))
    return (math.degrees(d) + 360) % 360


for z in fc:
    zid = z["zone_id"]
    prev = z["area_now_ha"]
    w = Wind(z["wind_speed_ms"], z["wind_from_deg"])
    r = rates(w, z["vegetation"])
    if abs(r["length_breadth"] - z["length_breadth"]) > 1e-6:
        bad.append(f"zone {zid}: stored length/breadth differs from the formula")
    for s in z["steps"]:
        geom = shape(s["geometry"])
        c = geom.centroid
        fwd, _ = _transformers(utm_epsg(c.x, c.y))
        utm = shapely.transform(geom, lambda q: np.column_stack(fwd(q[:, 0], q[:, 1])))
        if abs(utm.area / 1e4 - s["area_ha"]) / s["area_ha"] > 0.01:
            bad.append(f"zone {zid} +{s['minutes']}: polygon area {utm.area / 1e4:.1f} ha, reported {s['area_ha']:.1f} ha")
        if s["area_ha"] < prev:
            bad.append(f"zone {zid} +{s['minutes']}: area shrinks")
        prev = s["area_ha"]
    last = z["steps"][-1]
    c0 = shape(state["zones"][[f["properties"]["zone_id"] for f in state["zones"]].index(zid)]["geometry"]).centroid
    c1 = shape(last["geometry"]).centroid
    if z["wind_speed_ms"] > 2.0:                                  # direction is only meaningful with some wind
        d = abs((bearing(c0.x, c0.y, c1.x, c1.y) - z["spread_to_deg"] + 180) % 360 - 180)
        if d > 10:
            bad.append(f"zone {zid}: fire moves toward {bearing(c0.x, c0.y, c1.x, c1.y):.0f}, wind pushes it toward {z['spread_to_deg']:.0f}")
    if status.get(zid) == "inactive":
        warn.append(f"zone {zid} is inactive (old burn?) but still forecast")
    if last["area_ha"] / z["area_now_ha"] > 3:
        warn.append(f"zone {zid}: area x{last['area_ha'] / z['area_now_ha']:.1f} in 2 h, small fires grow most under this model")
    if z["wind_speed_ms"] > 15:
        warn.append(f"zone {zid}: wind {z['wind_speed_ms']:.0f} m/s is outside what the model was designed for")

if a.wind_recheck:
    for z in fc[:3]:
        c = shape(z["steps"][0]["geometry"]).centroid
        w = fetch_wind(c.y, c.x)
        print(f"zone {z['zone_id']}: stored {z['wind_speed_ms']:.1f} m/s from {z['wind_from_deg']:.0f} | "
              f"fresh {w.speed_ms:.1f} m/s from {w.from_deg:.0f}  (small drift is normal: the hour changes)")

print(f"{len(fc)} zones checked")
for m in bad:
    print("FAIL", m)
for m in warn:
    print("note", m)
print("RESULT:", "all internal checks passed" if not bad else f"{len(bad)} problem(s)")
raise SystemExit(1 if bad else 0)
