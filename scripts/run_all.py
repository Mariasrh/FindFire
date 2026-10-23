"""One entry point: fetch detections, rebuild zones/alerts, write the maps.

    python scripts/run_all.py                         # live NRT (2 days), live + debug maps
    python scripts/run_all.py --days 5 --open         # 5 NRT days and open the maps
    python scripts/run_all.py --csv data/raw/firms_algeria.csv   # offline
    python scripts/run_all.py --rebuild-mask          # rebuild static_sources.csv first
    python scripts/run_all.py --replay 2021-08-08 2021-08-14     # also build a historical replay
    python scripts/run_all.py --validate              # also run the default EMSR533 validation
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from findfire.config import DATA_DIR  # noqa: E402

ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(SRC) + (os.pathsep + ENV["PYTHONPATH"] if ENV.get("PYTHONPATH") else "")


def run(cmd: list[str], label: str) -> None:
    print(f"\n== {label} ==", flush=True)
    try:
        subprocess.run(cmd, cwd=ROOT, env=ENV, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"{label} failed with exit code {exc.returncode}") from None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, help="saved VIIRS CSV instead of polling FIRMS")
    ap.add_argument("--days", type=int, default=2, help="NRT days to request (1-5, default 2)")
    ap.add_argument("--mtg", action="store_true", help="also poll MTG (needs EUMETSAT keys)")
    ap.add_argument("--out", type=Path, default=DATA_DIR / "live")
    ap.add_argument("--debug-out", type=Path, default=DATA_DIR / "results" / "detections_map.html")
    ap.add_argument("--no-debug", action="store_true", help="skip the kept/removed detection map")
    ap.add_argument("--rebuild-mask", action="store_true", help="rebuild data/static_sources.csv first")
    ap.add_argument("--replay", nargs=2, metavar=("START", "END"), help="also build a replay for these dates")
    ap.add_argument("--validate", action="store_true", help="also run the default EMSR533 validation (Kabylie 2021)")
    ap.add_argument("--validate-event", nargs=2, metavar=("START", "END"), help="validate a FIRMS archive event")
    ap.add_argument("--validate-csv", type=Path, help="validate a saved FIRMS CSV")
    ap.add_argument("--open", action="store_true", help="open the generated maps in the browser")
    a = ap.parse_args()

    if not 1 <= a.days <= 5:
        ap.error("--days must be between 1 and 5")
    if a.csv and not a.csv.exists():
        ap.error(f"CSV not found: {a.csv}")

    out = a.out.resolve()
    debug_out = a.debug_out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    debug_out.parent.mkdir(parents=True, exist_ok=True)

    mask = DATA_DIR / "static_sources.csv"
    if a.rebuild_mask:
        run([sys.executable, str(ROOT / "scripts" / "build_static_mask.py")], "static source mask")
    elif not mask.exists():
        print(f"warning: {mask} is missing; the live map will not filter static sources")

    live = [sys.executable, str(ROOT / "scripts" / "run_live.py"), "--once", "--out", str(out)]
    if a.csv:
        live += ["--viirs-csv", str(a.csv.resolve()), "--no-firms"]
    else:
        live += ["--firms-days", str(a.days)]
    if not a.mtg:
        live += ["--no-mtg"]
    run(live, "live map")

    detections = a.csv.resolve() if a.csv else out / "viirs.csv"
    wrote_debug = False
    if not a.no_debug:
        if detections.exists():
            run([sys.executable, str(ROOT / "scripts" / "map_detections.py"),
                 "--csv", str(detections), "--out", str(debug_out)], "detection map")
            wrote_debug = True
        else:
            print(f"warning: {detections} not found; skipping the detection map")

    if a.replay:
        run([sys.executable, str(ROOT / "scripts" / "build_replay.py"),
             "--event", *a.replay, "--out", str(DATA_DIR / "replay")], "historical replay")

    if a.validate or a.validate_event or a.validate_csv:
        validation = [sys.executable, str(ROOT / "scripts" / "validate_emsr.py")]
        if a.validate_csv:
            if not a.validate_csv.exists():
                ap.error(f"validation CSV not found: {a.validate_csv}")
            validation += ["--csv", str(a.validate_csv.resolve())]
        elif a.validate_event:
            validation += ["--event", *a.validate_event]
        run(validation, "EMSR533 validation")

    outputs = [out / "map.html"]
    if wrote_debug:
        outputs.append(debug_out)
    if a.replay:
        outputs.append(DATA_DIR / "replay" / "replay.html")

    state = out / "state.json"
    if state.exists():
        s = json.loads(state.read_text(encoding="utf-8"))
        print(f"\nresult: {len(s.get('zones', []))} zones, {len(s.get('alerts', []))} alerts")
    print("outputs:")
    for p in outputs:
        if p.exists():
            print(f"  {p}")

    if a.open:
        for p in outputs:
            if p.exists():
                webbrowser.open(p.as_uri())


if __name__ == "__main__":
    main()
