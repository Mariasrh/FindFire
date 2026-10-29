"""Detection store: CSV files that remember WHEN each detection reached us (ingested_at).

ingested_at - acq_dt is the real latency of each source; the report can quote measured numbers.
Watermarks (last MTG granule processed, last successful polls) live in watermarks.json, so a restart resumes cleanly."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

KEY = ["latitude", "longitude", "acq_dt", "satellite", "source"]


def utcnow() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


class Store:
    def __init__(self, folder, keep_days: int = 7):
        self.dir = Path(folder); self.dir.mkdir(parents=True, exist_ok=True)
        self.keep = pd.Timedelta(days=keep_days)

    def _csv(self, name): return self.dir / f"{name}.csv"

    def load(self, name: str) -> pd.DataFrame:
        p = self._csv(name)
        if not p.exists():
            return pd.DataFrame()
        d = pd.read_csv(p)
        for c in ("acq_dt", "ingested_at"):
            d[c] = pd.to_datetime(d[c], utc=True)
        return d

    def add(self, name: str, new: pd.DataFrame, now: pd.Timestamp | None = None) -> int:
        """Append, keep the FIRST ingested_at of a duplicate, drop old rows. Returns the number of new rows."""
        now = now or utcnow()
        old = self.load(name)
        if new is None or new.empty:
            return 0
        new = new.copy(); new["ingested_at"] = now; new["_new"] = True
        if len(old):
            old = old.assign(_new=False)
        both = pd.concat([old, new], ignore_index=True) if len(old) else new
        both["acq_dt"] = pd.to_datetime(both["acq_dt"], utc=True)
        both = both.drop_duplicates(subset=KEY, keep="first")
        both = both[both["acq_dt"] >= now - self.keep].sort_values("acq_dt")
        added = int(both["_new"].fillna(False).astype(bool).sum())   # new rows still kept, never negative
        both.drop(columns="_new").to_csv(self._csv(name), index=False)
        return added

    def watermarks(self) -> dict:
        p = self.dir / "watermarks.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def set_watermarks(self, **kw):
        w = self.watermarks(); w.update(kw)
        (self.dir / "watermarks.json").write_text(json.dumps(w, indent=1, default=str))
