"""Land cover of every zone in the live state (ESA WorldCover 10 m, 2021).

    python scripts/landcover_zones.py                  # reads data/live/state.json, writes data/live/landcover.json
    python scripts/landcover_zones.py --write-state    # also puts `land_cover` into each zone's properties in state.json
    python scripts/landcover_zones.py --tiles D:/worldcover   # use local tiles (same file names) when present
Needs internet for tiles that are not local: only the pixels under each zone are fetched (public COG, no account).
A zone whose land cover cannot be read gets land_cover = null and a land_cover_error: nothing is guessed.
land_cover_error exists only when land_cover is null (see docs/landcover.md).
"""
import argparse
import json
from pathlib import Path

from shapely.geometry import shape

from findfire.config import DATA_DIR
from findfire.landcover.worldcover import annotate_zones

STALE = ("land_cover", "land_cover_error")      # written by an earlier run: never carried over

ap = argparse.ArgumentParser()
ap.add_argument("--state", default=str(DATA_DIR / "live" / "state.json"))
ap.add_argument("--out", default=str(DATA_DIR / "live" / "landcover.json"))
ap.add_argument("--tiles"); ap.add_argument("--no-remote", action="store_true"); ap.add_argument("--write-state", action="store_true")
a = ap.parse_args()

state = json.loads(Path(a.state).read_text())
zones = [dict({k: v for k, v in f["properties"].items() if k not in STALE}, geometry=shape(f["geometry"]))
         for f in state["zones"]]
annotate_zones(zones, a.tiles, remote=not a.no_remote)
print(f"{'zone':>5} {'area ha':>8}  {'label':<9} {'dominant share':>14}  shares")
out = {}
for z, f in zip(zones, state["zones"]):
    lc, err = z["land_cover"], z.get("land_cover_error")
    out[z["zone_id"]] = lc if lc else {"land_cover": None, "error": err}
    if lc:
        print(f"{z['zone_id']:>5} {z['area_ha']:>8.1f}  {lc['label']:<9} {lc['dominant_share']:>14.2f}  {lc['shares']}"
              + ("" if lc["majority"] else "  (mixed)"))
    else:
        print(f"{z['zone_id']:>5} {z['area_ha']:>8.1f}  unavailable: {err}")
    if a.write_state:
        f["properties"]["land_cover"] = lc
        if lc is None and err:
            f["properties"]["land_cover_error"] = err
        else:
            f["properties"].pop("land_cover_error", None)
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
Path(a.out).write_text(json.dumps(out, indent=1))
if a.write_state:
    Path(a.state).write_text(json.dumps(state))
print(f"-> {a.out}\nData: (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021), CC BY 4.0. Overall accuracy 76.7 %.")