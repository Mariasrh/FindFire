"""Forecast the area of every zone at T+30, T+60 and T+120 minutes (issue F6).

    python scripts/forecast_zones.py                                  # zones from data/live/state.json, wind from Open-Meteo (now)
    python scripts/forecast_zones.py --wind-time last_detected        # wind of the moment each zone was last seen (past fire / replay)
    python scripts/forecast_zones.py --as-of 2021-08-10T12:00Z        # wind of one given moment for every zone
    python scripts/forecast_zones.py --wind 6 270                     # fixed wind: 6 m/s blowing FROM the west (270 degrees)
    python scripts/forecast_zones.py --water                          # also water demand at every step (findfire.water)
    python scripts/forecast_zones.py --vegetation grass --out data/live/forecast.json

Run scripts/run_live.py first: it writes data/live/state.json.
No internet or no wind data: the forecast still runs with a calm wind (round fires), and says so in the output.
Zones whose status is "inactive" are skipped (add --include-inactive to forecast them anyway).
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from shapely.geometry import mapping, shape

from findfire.config import DATA_DIR
from findfire.forecast.spread import BASE_ROS_M_MIN, forecast_zones
from findfire.forecast.fuel import fuel_or_default
from findfire.forecast.wind import Wind, wind_or_default

a = argparse.ArgumentParser()
a.add_argument("--state", default=str(DATA_DIR / "live" / "state.json"))
a.add_argument("--out", default=str(DATA_DIR / "live" / "forecast.json"))
a.add_argument("--vegetation", default="shrub", choices=sorted(BASE_ROS_M_MIN))
a.add_argument("--wind", nargs=2, type=float, metavar=("SPEED_MS", "FROM_DEG"), help="fixed wind instead of Open-Meteo")
a.add_argument("--as-of", metavar="ISO_TIME", help="take the wind at this UTC moment for every zone (default: now)")
a.add_argument("--wind-time", choices=("now", "last_detected"), default="now",
               help="last_detected: each zone gets the wind of its own last detection (use it for a past fire)")
a.add_argument("--include-inactive", action="store_true")
a.add_argument("--water", action="store_true", help="add water demand (water_for_forecast) to every step")
a.add_argument("--fuel", action="store_true", help="scale the spread rate by fuel dryness (Canadian FFMC from Open-Meteo weather; needs internet)")
a = a.parse_args()
if a.as_of and a.wind_time != "now":
    raise SystemExit("use either --as-of or --wind-time last_detected, not both")

state = json.loads(Path(a.state).read_text())
zones = [dict(f["properties"], geometry=shape(f["geometry"])) for f in state["zones"]]
if not zones:
    raise SystemExit("no zones in the state file: nothing to forecast")

if a.wind:
    wind_fn = lambda lat, lon, when=None: Wind(*a.wind, source="fixed")
else:
    wind_fn = wind_or_default
when = pd.Timestamp(a.as_of) if a.as_of else (lambda z: pd.Timestamp(z["last_detected"])) if a.wind_time == "last_detected" else None
water_fn = None
if a.water:
    from findfire.water.water_demand import water_for_forecast
    water_fn = water_for_forecast

result = forecast_zones(zones, wind_fn, a.vegetation, water_fn=water_fn, when=when, skip_inactive=not a.include_inactive,
                        fuel_fn=fuel_or_default if a.fuel else None)
skipped = len(zones) - len(result)
if not result:
    raise SystemExit(f"all {len(zones)} zones are inactive: nothing to forecast (--include-inactive to override)")

print(f"{'zone':>5} {'now (ha)':>9} {'+30 min':>9} {'+60 min':>9} {'+120 min':>9}  wind (m/s, from deg, source)" + ("   FFMC  fuel x" if a.fuel else ""))
for r in result:
    s = {x["minutes"]: x["area_ha"] for x in r["steps"]}
    print(f"{r['zone_id']:>5} {r['area_now_ha']:>9.1f} {s[30]:>9.1f} {s[60]:>9.1f} {s[120]:>9.1f}  "
          f"{r['wind_speed_ms']:.1f} from {r['wind_from_deg']:.0f} ({r['wind_source']})"
          + (f"   {r['ffmc']:.0f} {r['fuel_factor']:.2f} ({r['fuel_source']})" if a.fuel else ""))
    for x in r["steps"]:
        x["geometry"] = mapping(x["geometry"])
if skipped:
    print(f"{skipped} inactive zone(s) skipped")
if any(r["wind_source"] == "default" for r in result):
    print("WARNING: no wind data for some zones; they use a calm wind (round fires). Check the internet connection.")
if any(r["fuel_source"] == "default" for r in result):
    print("WARNING: no weather data for some zones; they use the reference fuel dryness (factor 1).")
out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=1, default=str))
print(f"-> {out}")
