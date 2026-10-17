"""FindFire entry point: fetch hotspots, track zones, print results, save outputs.

Usage:  python main.py            (uses FIRMS if FIRMS_MAP_KEY is set, else synthetic demo data)
        python main.py --demo     (force synthetic demo data)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from findfire import run_tracking, validation
from findfire.ingestion.firms import DEFAULT_BBOX, DEFAULT_SOURCE_ARCHIVE, fetch_firms, make_synthetic, prepare

RESULTS_DIR = Path("data/results")


def load_hotspots(demo=False):
    if demo:
        source, raw = "SYNTHETIC DEMO DATA", make_synthetic()
    else:
        try:
            source, raw = "FIRMS", fetch_firms()
        except Exception as exc:
            print(f"Could not fetch FIRMS ({exc}) -> using synthetic demo data")
            source, raw = "SYNTHETIC DEMO DATA", make_synthetic()
    return source, prepare(raw)


if __name__ == "__main__":
    demo = "--demo" in sys.argv
    source, df = load_hotspots(demo)
    snap, zones, merges, step_times, hs_zone = run_tracking(df)
    final = snap[snap.step == step_times[-1]].copy()
    print(f"DATA SOURCE: {source} | {len(df)} hotspots after removing low confidence")
    print(f"{len(step_times)} steps of 12 h | {len(final)} zones at the end | merges: " +
          (", ".join(f"zone {s} into {k}" for _, s, k in merges) or "none"))
    lone_left = len(df) - sum(len(z["idx"]) for z in zones.values() if z["merged_into"] is None)
    print(f"hotspots not in any zone (isolated / possible false alarms): {lone_left}")
    print(final.sort_values("area_ha", ascending=False).drop(columns="geometry")[
        ["zone_id", "status", "area_ha", "perimeter_km", "n_hotspots", "frp_total_mw",
         "first_detected", "last_detected"]].round({"area_ha": 0, "perimeter_km": 1, "frp_total_mw": 0}))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    snap.to_file(RESULTS_DIR / "zones_timeline.geojson", driver="GeoJSON")
    final.drop(columns="geometry").to_csv(RESULTS_DIR / "final_zones.csv", index=False)
    if source != "FIRMS":
        print("\nNote: data is synthetic — EMSR comparison numbers are not meaningful.")
    validation.run(snap, step_times, source, last_data=df.acq_dt.max())
    print(f"saved: {RESULTS_DIR / 'zones_timeline.geojson'}, {RESULTS_DIR / 'final_zones.csv'}")
