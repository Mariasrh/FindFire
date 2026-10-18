"""Rule-based false-alarm reduction (no ML): redetections, fixed heat sources, persistence.

Typical order on a hotspot table `df` (columns latitude, longitude, acq_dt, scan, track, satellite):
    df = mark_redetections(df)                     # same pixel seen by two satellites = one observation
    df = apply_exclusions(df, load_exclusions())   # curated list: refineries, LNG plants, gas flares, ...
    df = apply_static_mask(df, static_mask)        # places that burn on many different days (built from history)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from findfire.config import DATA_DIR, REDETECTION_H

R_EARTH_M = 6371008.8
_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


def hours_since_epoch(ts: pd.Series) -> np.ndarray:
    """Timestamps -> float hours, independent of the datetime resolution (pandas 3 may use us, not ns)."""
    return ((pd.to_datetime(ts, utc=True) - _EPOCH) / pd.Timedelta(hours=1)).to_numpy(float)


def _pixel_m(df) -> np.ndarray:
    return np.maximum(df["scan"].to_numpy(float), df["track"].to_numpy(float)) * 1000.0


def mark_redetections(df: pd.DataFrame, hours: float = REDETECTION_H) -> pd.DataFrame:
    """Add `dup_of`: index of the earlier detection of the same pixel by ANOTHER satellite (else -1).

    NOAA-20 / SNPP / NOAA-21 pass over the same place within about an hour, so one small fire gives two or three
    rows. Counting them as separate hotspots turns every lone flare into a 'zone'. The same satellite seeing the
    place again 12 h later is NOT a duplicate: that is persistence, a useful signal."""
    d = df.sort_values("acq_dt").copy()
    dup = np.full(len(d), -1, dtype=np.int64)
    if len(d) > 1:
        idx = d.index.to_numpy()
        sat = d["satellite"].astype(str).to_numpy()
        t = hours_since_epoch(d["acq_dt"])
        pix = _pixel_m(d)
        ll = np.radians(d[["latitude", "longitude"]].to_numpy(float))
        near = BallTree(ll, metric="haversine").query_radius(ll, r=(pix.max() * 1.5) / R_EARTH_M, return_distance=True)
        for i, (nb, dist) in enumerate(zip(*near)):
            best = None
            for j, dm in zip(nb, dist * R_EARTH_M):
                if j >= i or sat[j] == sat[i] or dup[j] != -1:        # only link to the EARLIER primary observation
                    continue
                if abs(t[i] - t[j]) <= hours and dm <= max(pix[i], pix[j]) * 1.0:
                    best = j if best is None or t[j] < t[best] else best
            if best is not None:
                dup[i] = idx[best]
    d["dup_of"] = dup
    return d.loc[df.index]


def load_exclusions(path=None) -> pd.DataFrame:
    """data/exclusion_zones.csv with columns name, latitude, longitude, radius_km (kept in git, edited by hand)."""
    p = path or DATA_DIR / "exclusion_zones.csv"
    try:
        return pd.read_csv(p)
    except FileNotFoundError:
        return pd.DataFrame(columns=["name", "latitude", "longitude", "radius_km"])


def apply_exclusions(df: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    """Drop hotspots inside any exclusion circle."""
    if zones.empty or df.empty:
        return df
    tree = BallTree(np.radians(zones[["latitude", "longitude"]].to_numpy(float)), metric="haversine")
    dist, nn = tree.query(np.radians(df[["latitude", "longitude"]].to_numpy(float)), k=1)
    inside = dist[:, 0] * R_EARTH_M / 1000.0 <= zones["radius_km"].to_numpy(float)[nn[:, 0]]
    return df[~inside]


def build_static_mask(history: pd.DataFrame, min_days: int = 20, cell_deg: float = 0.01) -> pd.DataFrame:
    """Places that burn on many different days in a long archive: gas flares, refineries, kilns.

    Needs months of FIRMS history (use the *_SP archive over the study box). A cell of ~1 km seen on at least
    `min_days` distinct dates is a fixed heat source; real wildfires do not stay put that long.
    Returns centres with `radius_km` so it can go through apply_exclusions()."""
    h = history.assign(day=history["acq_dt"].dt.date,
                       gy=np.floor(history["latitude"] / cell_deg).astype(int),
                       gx=np.floor(history["longitude"] / cell_deg).astype(int))
    g = h.groupby(["gy", "gx"]).agg(days=("day", "nunique"), latitude=("latitude", "mean"),
                                    longitude=("longitude", "mean")).reset_index()
    g = g[g["days"] >= min_days]
    return pd.DataFrame({"name": "static", "latitude": g["latitude"], "longitude": g["longitude"],
                         "radius_km": 1.5, "days_seen": g["days"]}).reset_index(drop=True)


apply_static_mask = apply_exclusions


def assign_pass(df: pd.DataFrame, gap_min: float = 30.0) -> pd.Series:
    """Pass number per row: detections of one satellite closer than `gap_min` minutes belong to the same overpass."""
    out = pd.Series(-1, index=df.index, dtype=int)
    n = 0
    for _, g in df.sort_values("acq_dt").groupby(df["satellite"].astype(str)):
        new = g["acq_dt"].diff() > pd.Timedelta(minutes=gap_min)
        out.loc[g.index] = n + new.cumsum().to_numpy()
        n = int(out.loc[g.index].max()) + 1
    return out


def persistence(df: pd.DataFrame, radius_m: float = 1500.0, window_h: float = 48.0) -> pd.Series:
    """Number of DISTINCT overpasses (other than its own) that saw something within `radius_m` in `window_h`.

    A fire is seen again by the next passes; a one-off (sun glint, noise) is not. Use it to promote lone
    hotspots: `df[persistence(df) >= 1]` keeps those re-detected by at least one other overpass."""
    p = assign_pass(df).to_numpy()
    t = hours_since_epoch(df["acq_dt"])
    ll = np.radians(df[["latitude", "longitude"]].to_numpy(float))
    nbrs = BallTree(ll, metric="haversine").query_radius(ll, r=radius_m / R_EARTH_M)
    out = [len({p[j] for j in nb if p[j] != p[i] and abs(t[j] - t[i]) <= window_h}) for i, nb in enumerate(nbrs)]
    return pd.Series(out, index=df.index)
