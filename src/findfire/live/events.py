"""Load a date range of VIIRS detections for the replay, and build the replay JSON for it.

Order: a local CSV that covers the range (offline / demo) -> cached download -> FIRMS (archive *_SP and recent *_NRT
sources are both asked; whichever has the days answers; duplicates are dropped). Every problem is reported back as a
note instead of silently changing the data."""
from __future__ import annotations

import datetime as dt
import json
import time

import pandas as pd

from findfire.config import DATA_DIR, FIRMS_NRT_SOURCES, FIRMS_SP_SOURCES, STUDY_BBOX
from findfire.detection.filters import load_exclusions
from findfire.ingestion import firms
from findfire.live.replay import to_data
from findfire.zones.tracking import run_tracking

MAX_DAYS = 31
DEFAULT_EVENTS = [dict(name="Kabylie fires", start="2021-08-08", end="2021-08-14")]


def load_events(path=None) -> list[dict]:
    """data/events.json: [{"name":..., "start":"YYYY-MM-DD", "end":"YYYY-MM-DD"}, ...] (edit it to add your CEMS events)."""
    p = path or DATA_DIR / "events.json"
    try:
        return json.loads(open(p, encoding="utf-8").read())
    except FileNotFoundError:
        return DEFAULT_EVENTS


def _in_box(d):
    w, s, e, n = STUDY_BBOX
    return d[d.latitude.between(s, n) & d.longitude.between(w, e)]


def fetch_period(start: dt.date, end: dt.date, local: pd.DataFrame | None = None, cache_dir=None):
    """-> (DataFrame of VIIRS hotspots for [start, end] inclusive, list of notes)."""
    if (end - start).days + 1 > MAX_DAYS or end < start:
        raise ValueError(f"pick a period of 1 to {MAX_DAYS} days")
    notes = []
    t0 = pd.Timestamp(start, tz="UTC"); t1 = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    if local is not None and len(local):
        sub = local[(local.acq_dt >= t0) & (local.acq_dt < t1)]
        if len(sub) and local.acq_dt.min().date() <= start and local.acq_dt.max().date() >= end:   # day-level coverage
            return sub.reset_index(drop=True), ["Using the local file."]
    cache = (cache_dir or DATA_DIR / "archive"); cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"viirs_{start}_{end}.csv"
    if f.exists():
        return firms.load_csv(f), ["From the local download cache."]
    frames = []
    for source in FIRMS_SP_SOURCES + FIRMS_NRT_SOURCES:
        cur, got = start, 0
        while cur <= end:
            n = min(5, (end - cur).days + 1)
            try:
                part = firms.fetch_area(source, STUDY_BBOX, n, cur); got += len(part); frames.append(part)
            except Exception as exc:
                notes.append(f"{source} {cur}: {str(exc)[:80]}")
            cur += dt.timedelta(days=n); time.sleep(0.4)
        notes.append(f"{source}: {got} detections")
    frames = [x for x in frames if len(x)]
    if not frames:
        raise RuntimeError("FIRMS returned no detections for this period. " + " | ".join(notes[:4]))
    raw = pd.concat(frames, ignore_index=True)
    d = firms.prepare(raw)
    d.drop(columns=["acq_dt"]).to_csv(f, index=False) if False else raw.drop_duplicates().to_csv(f, index=False)
    return d, notes


def replay_json(start: dt.date, end: dt.date, local=None, min_neighbors: int = 1, footprint: str = "alpha",
                edge_fraction: float = 0.5, title: str | None = None) -> dict:
    d, notes = fetch_period(start, end, local)
    d = _in_box(d)
    excl = load_exclusions()
    res = run_tracking(d, None, excl, min_neighbors=min_neighbors, footprint=footprint, edge_fraction=edge_fraction)
    out = to_data(res, excl, title or f"Replay {start} to {end}")
    out["notes"] = notes + [f"{len(d)} hotspots, footprint={footprint}, groups={['loose','medium','strict'][min(2, max(0, min_neighbors - 1))]}."]
    return out
