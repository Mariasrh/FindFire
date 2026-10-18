"""Grouping hotspots into zones: a pixel-aware DBSCAN.

Why not plain DBSCAN(eps=1500 m, min_samples=1) on the centres, as the notebook did:
  * min_samples=1 is single linkage: one stray hotspot between two fires chains them into one zone.
  * eps on the centres ignores the pixel size. VIIRS pixels grow from 375 m (nadir) to ~800 m (swath edge), so
    the same fire is one zone at nadir and falls apart near the edge. MTG pixels are 2 km or more: no fixed eps fits both.
  * the same pixel seen by two satellites counts twice, so every lone flare becomes a two-hotspot 'zone'.

Here: two hotspots are linked when the GAP between their pixel rectangles (the same boxes geometry.py uses) is at
most max(gap_m, gap_pixels x pixel size). Cluster membership follows DBSCAN's core / border / noise rule with
`min_neighbors`, counting each real observation once (dup_of from filters.mark_redetections). An optional time
window `max_dt` turns it into ST-DBSCAN, which is what the 10-minute MTG stream needs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree

from findfire.detection.filters import hours_since_epoch
from findfire.config import CORE_MIN_NEIGHBORS, LINK_GAP_M, LINK_GAP_PIXELS

R_EARTH_M = 6371008.8


def _links(df: pd.DataFrame, gap_m: float, gap_pixels: float, max_dt: pd.Timedelta | None):
    """All linked pairs (i, j, gap_m) with i < j."""
    lat, lon = df["latitude"].to_numpy(float), df["longitude"].to_numpy(float)
    sx, sy = df["scan"].to_numpy(float) * 1000.0, df["track"].to_numpy(float) * 1000.0
    size = np.maximum(sx, sy)
    t = hours_since_epoch(df["acq_dt"])
    reach = max(gap_m, gap_pixels * size.max()) + 1.5 * size.max()           # upper bound on the centre distance
    nbrs = BallTree(np.radians(np.c_[lat, lon]), metric="haversine").query_radius(
        np.radians(np.c_[lat, lon]), r=reach / R_EARTH_M)
    i = np.repeat(np.arange(len(df)), [len(n) for n in nbrs]); j = np.concatenate(nbrs) if len(nbrs) else np.array([], int)
    keep = i < j
    i, j = i[keep], j[keep]
    latm = np.radians((lat[i] + lat[j]) / 2)
    dx = np.abs(lon[j] - lon[i]) * np.pi / 180 * R_EARTH_M * np.cos(latm)
    dy = np.abs(lat[j] - lat[i]) * np.pi / 180 * R_EARTH_M
    gx = np.maximum(0, dx - (sx[i] + sx[j]) / 2)                              # scan = x width, track = y height,
    gy = np.maximum(0, dy - (sy[i] + sy[j]) / 2)                              # as in zones.geometry
    gap = np.hypot(gx, gy)
    ok = gap <= np.maximum(gap_m, gap_pixels * (size[i] + size[j]) / 2)
    if max_dt is not None:
        ok &= np.abs(t[i] - t[j]) <= max_dt / pd.Timedelta(hours=1)
    return i[ok], j[ok], gap[ok]


def cluster_hotspots(df: pd.DataFrame, gap_m: float = LINK_GAP_M, gap_pixels: float = LINK_GAP_PIXELS,
                     min_neighbors: int = CORE_MIN_NEIGHBORS, max_dt: pd.Timedelta | None = None) -> np.ndarray:
    """Cluster label per row of `df` (-1 = noise / lone hotspot).

    Needs latitude, longitude, scan, track (km), acq_dt. If a `dup_of` column is present, only primary
    observations are clustered; their re-detections inherit the label."""
    n = len(df)
    labels = np.full(n, -1, dtype=int)
    if n == 0:
        return labels
    pos = {ix: k for k, ix in enumerate(df.index)}
    primary = np.ones(n, bool)
    dup_to = np.full(n, -1)
    if "dup_of" in df:
        for k, d in enumerate(df["dup_of"].to_numpy()):
            if d != -1 and d in pos:
                primary[k], dup_to[k] = False, pos[d]
    P = np.flatnonzero(primary)
    sub = df.iloc[P]
    i, j, gap = _links(sub, gap_m, gap_pixels, max_dt)
    m = len(P)
    degree = np.bincount(i, minlength=m) + np.bincount(j, minlength=m)       # linked real observations
    core = degree >= min_neighbors
    cc = core[i] & core[j]
    _, comp = connected_components(coo_matrix((np.ones(cc.sum()), (i[cc], j[cc])), shape=(m, m)), directed=False)
    sub_labels = np.where(core, comp, -1)
    best = np.full(m, np.inf)                                                # border points join the nearest core
    for a, b, g in zip(np.r_[i, j], np.r_[j, i], np.r_[gap, gap]):
        if not core[a] and core[b] and g < best[a]:
            best[a], sub_labels[a] = g, comp[b]
    uniq = {c: k for k, c in enumerate(sorted(set(sub_labels[sub_labels >= 0])))}
    labels[P] = [uniq.get(c, -1) for c in sub_labels]
    for k in np.flatnonzero(~primary):
        labels[k] = labels[dup_to[k]]
    return labels
