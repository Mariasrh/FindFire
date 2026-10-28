"""Replay a past fire into the dashboard: one state file per tracking step.

The dashboard reads the state file every few seconds, so each new step raises the alert for a new zone and updates
area, water, trucks and forecast, like a live fire. The last state stays in place when the replay ends.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from shapely.geometry import mapping


def _json_default(obj):
    if hasattr(obj, "item"):                       # numpy numbers
        return obj.item()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def snapshot_to_state(snap: dict, index: int, total: int, event: str = "") -> dict:
    """One tracking snapshot (run_tracking) -> the state the dashboard reads. `index` starts at 0."""
    features = []
    for zone in snap["zones"]:
        props = {k: v for k, v in zone.items() if k != "geometry"}
        features.append({"type": "Feature", "geometry": mapping(zone["geometry"]), "properties": props})
    return {"replay": True, "replay_time": snap["time"].isoformat(), "step": index + 1, "steps": total,
            "event": event, "zones": features, "alerts": []}


def write_state(path, state: dict, retries: int = 20) -> None:
    """Atomic write: the dashboard never reads a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, default=_json_default), encoding="utf-8")
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:                    # Windows: the file is being read at this very moment
            time.sleep(0.1)
    raise PermissionError(f"could not replace {path}")


def step_summary(snap: dict) -> dict:
    live = [z for z in snap["zones"] if z.get("status") != "inactive"]
    return dict(time=snap["time"].isoformat()[:16], zones=len(snap["zones"]), live=len(live),
                max_area_ha=max((float(z["area_ha"]) for z in live), default=0.0))


def play(snaps: list[dict], out, seconds: float = 10.0, event: str = "", first: int = 1,
         sleep=time.sleep, log=print) -> int:
    """Write the steps one after the other, `seconds` apart. Returns the number of steps written."""
    total, written = len(snaps), 0
    for i in range(max(first, 1) - 1, total):
        state = snapshot_to_state(snaps[i], i, total, event)
        write_state(out, state)
        s = step_summary(snaps[i])
        log(f"step {i + 1}/{total} {s['time']} UTC: {s['live']} active zone(s), largest {s['max_area_ha']:.0f} ha")
        written += 1
        if i < total - 1:
            sleep(seconds)
    return written