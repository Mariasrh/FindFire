"""Write a SAMPLE state file (fake zones near Tizi Ouzou) to try the dashboard and its alert.

    python scripts/make_sample_state.py --step 1     # one zone
    python scripts/make_sample_state.py --step 2     # a second zone appears: the dashboard raises an alert
    python scripts/make_sample_state.py --step 3     # a third zone, an old one becomes inactive

The file is flagged "sample": true and the dashboard shows SAMPLE DATA. It never replaces data/live/state.json.
"""
import argparse
import json

from shapely.geometry import box, mapping

from findfire.config import DATA_DIR

ZONES = [
    dict(zone_id=1, area_ha=15.0, box=(4.000, 36.700, 4.004, 36.704)),
    dict(zone_id=2, area_ha=120.0, box=(4.100, 36.600, 4.110, 36.610)),
    dict(zone_id=3, area_ha=420.0, box=(4.300, 36.550, 4.330, 36.580)),
]
a = argparse.ArgumentParser()
a.add_argument("--step", type=int, choices=[1, 2, 3], default=1)
a = a.parse_args()

features = []
for z in ZONES[:a.step]:
    status = "new" if z["zone_id"] == a.step else "active"
    if a.step == 3 and z["zone_id"] == 1:
        status = "inactive"
    features.append({"type": "Feature", "geometry": mapping(box(*z["box"])),
                     "properties": {"zone_id": z["zone_id"], "status": status, "area_ha": z["area_ha"]}})
out = DATA_DIR / "live" / "sample_state.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"sample": True, "zones": features}, indent=1), encoding="utf-8")
print(f"step {a.step}: {len(features)} zone(s) -> {out}")