"""Forecast the area of every zone at T+30, T+60 and T+120 minutes (issue F6).

    python scripts/forecast_zones.py                                  # zones from data/live/state.json, wind from Open-Meteo
    python scripts/forecast_zones.py --wind 6 270                     # offline: wind 6 m/s blowing FROM the west (270 degrees)
    python scripts/forecast_zones.py --vegetation grass --out data/live/forecast.json

Run scripts/run_live.py first: it writes data/live/state.json.
"""
import argparse
import json
from pathlib import Path

from shapely.geometry import mapping, shape

from findfire.config import DATA_DIR
from findfire.forecast.spread import BASE_ROS_M_MIN, forecast_zones
from findfire.forecast.wind import Wind, cached_wind

a = argparse.ArgumentParser()
a.add_argument("--state", default=str(DATA_DIR / "live" / "state.json"))
a.add_argument("--out", default=str(DATA_DIR / "live" / "forecast.json"))
a.add_argument("--vegetation", default="shrub", choices=sorted(BASE_ROS_M_MIN))
a.add_argument("--wind", nargs=2, type=float, metavar=("SPEED_MS", "FROM_DEG"), help="fixed wind instead of Open-Meteo")
a = a.parse_args()

state = json.loads(Path(a.state).read_text())
zones = [dict(f["properties"], geometry=shape(f["geometry"])) for f in state["zones"]]
if not zones:
    raise SystemExit("no zones in the state file: nothing to forecast")
wind_fn = (lambda lat, lon: Wind(*a.wind)) if a.wind else cached_wind
result = forecast_zones(zones, wind_fn, a.vegetation)

print(f"{'zone':>5} {'now (ha)':>9} {'+30 min':>9} {'+60 min':>9} {'+120 min':>9}  wind (m/s, from deg)")
for r in result:
    s = {x["minutes"]: x["area_ha"] for x in r["steps"]}
    print(f"{r['zone_id']:>5} {r['area_now_ha']:>9.1f} {s[30]:>9.1f} {s[60]:>9.1f} {s[120]:>9.1f}  "
          f"{r['wind_speed_ms']:.1f} from {r['wind_from_deg']:.0f}")
    for x in r["steps"]:
        x["geometry"] = mapping(x["geometry"])
out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=1, default=str))
print(f"-> {out}")
