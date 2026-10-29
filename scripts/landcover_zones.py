"""Land cover of every zone in a state file (ESA WorldCover 10 m, 2020 or 2021).

    python scripts/landcover_zones.py                  # live state, 2021 map -> data/live/landcover.json
    python scripts/landcover_zones.py --year 2020 --state data/events/kabylie2021/state.json \
                                      --out data/events/kabylie2021/landcover_2020.json    # land BEFORE the Aug 2021 fires
    python scripts/landcover_zones.py --write-state    # also puts `land_cover` into each zone's properties in the state file
    python scripts/landcover_zones.py --tiles D:/worldcover   # use local tiles (same file names) when present
Needs internet for tiles that are not local: only the pixels under each zone are fetched (public COG, no account).
A zone whose land cover cannot be read gets land_cover = null and a land_cover_error: nothing is guessed.
land_cover_error exists only when land_cover is null (see docs/landcover.md).
Add --geojson to write the output as a FeatureCollection that keeps the zone polygons (for the dashboard).
"""
import argparse
import json
from pathlib import Path

from shapely.geometry import shape

from findfire.config import DATA_DIR
from findfire.landcover.worldcover import ACCURACY_PCT, VERSIONS, annotate_zones, source_name

STALE = ("land_cover", "land_cover_error")      # written by an earlier run: never carried over

ap = argparse.ArgumentParser()
ap.add_argument("--state", default=str(DATA_DIR / "live" / "state.json"))
ap.add_argument("--out", default=str(DATA_DIR / "live" / "landcover.json"))
ap.add_argument("--year", type=int, default=2021, choices=sorted(VERSIONS),
                help="WorldCover year; use 2020 for the Aug 2021 Kabylie validation (land before the fires)")
ap.add_argument("--geojson", action="store_true",
                help="write --out as a GeoJSON FeatureCollection (zone polygon + land_cover property) for the dashboard")
ap.add_argument("--tiles"); ap.add_argument("--no-remote", action="store_true"); ap.add_argument("--write-state", action="store_true")
a = ap.parse_args()

state = json.loads(Path(a.state).read_text())
zones = [dict({k: v for k, v in f["properties"].items() if k not in STALE}, geometry=shape(f["geometry"]))
         for f in state["zones"]]
annotate_zones(zones, a.tiles, remote=not a.no_remote, year=a.year)
print(f"WorldCover {a.year} ({VERSIONS[a.year]})")
print(f"{'zone':>5} {'area ha':>8}  {'label':<9} {'dominant share':>14}  shares")
out, feats = {}, []
for z, f in zip(zones, state["zones"]):
    lc, err = z["land_cover"], z.get("land_cover_error")
    out[z["zone_id"]] = lc if lc else {"land_cover": None, "error": err}
    if lc:
        print(f"{z['zone_id']:>5} {z['area_ha']:>8.1f}  {lc['label']:<9} {lc['dominant_share']:>14.2f}  {lc['shares']}"
              + ("" if lc["majority"] else "  (mixed)"))
    else:
        print(f"{z['zone_id']:>5} {z['area_ha']:>8.1f}  unavailable: {err}")
    props = dict(zone_id=z["zone_id"], area_ha=z.get("area_ha"), status=z.get("status"), land_cover=lc)
    if lc is None and err:
        props["land_cover_error"] = err
    feats.append(dict(type="Feature", geometry=f["geometry"], properties=props))
    if a.write_state:
        f["properties"]["land_cover"] = lc
        if lc is None and err:
            f["properties"]["land_cover_error"] = err
        else:
            f["properties"].pop("land_cover_error", None)
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
y = a.year
payload = (dict(type="FeatureCollection", land_cover_year=y, source=source_name(y),
                attribution=f"(c) ESA WorldCover project {y} / Contains modified Copernicus Sentinel data ({y}), CC BY 4.0",
                features=feats) if a.geojson else out)
Path(a.out).write_text(json.dumps(payload, indent=1))
if a.write_state:
    Path(a.state).write_text(json.dumps(state))
print(f"-> {a.out}\nData: (c) ESA WorldCover project {y} / Contains modified Copernicus Sentinel data ({y}), CC BY 4.0. "
      f"Overall accuracy {ACCURACY_PCT[y]} % (global figure" + ("; confirm the 2020 value in the v100 report" if y == 2020 else "") + ").")