"""Zone tracking over time: persistent zone IDs, cumulative footprints, merges and splits.

At each step t (12 h by default) all hotspots of the last `window` are clustered again with the pixel-aware,
time-limited clustering (`link_dt`: two hotspots further apart in time than this are never linked, so an old burn scar
cannot glue itself to a new fire). Each new cluster then inherits a zone ID from the previous step by shared hotspots:
  * a cluster that contains several old zones merges them; the OLDEST id wins
  * an old zone that is spread over several clusters keeps its id in the biggest one; the others start new zones
  * a cluster with no old zone is a new zone
Zones are cumulative (they only grow while their hotspots stay in the window), so a missed satellite pass never shrinks one.
MTG alerts are evaluated as of each step, using only data that existed at that time."""
from __future__ import annotations

import numpy as np
import pandas as pd

from findfire.config import ALPHA_SCALE, CORE_MIN_NEIGHBORS, EDGE_FRACTION, FOOTPRINT_METHOD
from findfire.detection.filters import apply_exclusions, mark_redetections
from findfire.live.pipeline import INACTIVE, NEW_FOR, build_alerts
from findfire.zones.clustering import cluster_hotspots
from findfire.zones.footprint import zone_footprint


def _status(first, last, t):
    return "new" if first > t - NEW_FOR else "active" if last > t - INACTIVE else "inactive"


def run_tracking(viirs: pd.DataFrame, mtg: pd.DataFrame | None = None, exclusions=None,
                 step=pd.Timedelta(hours=12), window=pd.Timedelta(days=7), link_dt=pd.Timedelta(hours=72),
                 min_neighbors: int = CORE_MIN_NEIGHBORS, footprint: str = FOOTPRINT_METHOD,
                 alpha_scale: float = ALPHA_SCALE, edge_fraction: float = EDGE_FRACTION):
    v = apply_exclusions(viirs, exclusions) if exclusions is not None and len(viirs) else viirs
    v = mark_redetections(v.reset_index(drop=True)).sort_values("acq_dt")
    if v.empty:
        return dict(steps=[], snaps=[], merges=[])
    times = pd.date_range(v.acq_dt.min().floor("12h") + step, v.acq_dt.max().floor("12h") + step, freq=step)
    members, first_seen, next_id, merges, snaps, cache = {}, {}, 1, [], [], {}
    for t in times:
        sub = v[(v.acq_dt <= t) & (v.acq_dt > t - window)]
        lab = cluster_hotspots(sub, max_dt=link_dt, min_neighbors=min_neighbors)
        clusters = {c: set(sub.index[lab == c]) for c in set(lab) if c >= 0}
        best = {}                                                    # old zone -> the cluster holding most of it
        for zid, mem in members.items():
            ov = {c: len(mem & cs) for c, cs in clusters.items()}
            if ov and max(ov.values()) > 0:
                best[zid] = max(ov, key=ov.get)
        new_members, owner = {}, {}
        for c, cs in clusters.items():
            olds = sorted((z for z, b in best.items() if b == c), key=lambda z: (first_seen[z], z))
            if olds:
                keep = olds[0]
                for z in olds[1:]:
                    merges.append((t, z, keep)); first_seen[keep] = min(first_seen[keep], first_seen[z])
            else:
                keep = next_id; next_id += 1; first_seen[keep] = sub.loc[list(cs)].acq_dt.min()
            new_members[keep] = cs
            for i in cs: owner[i] = keep
        members = new_members
        zones = []
        for zid, cs in members.items():
            g = sub.loc[sorted(cs)]
            key = (zid, tuple(sorted(cs)))
            if key not in cache:
                cache[key] = zone_footprint(g.longitude.values, g.latitude.values, g.scan.values, g.track.values,
                                            footprint, alpha_scale=alpha_scale, edge_fraction=edge_fraction)
            geom, area, per = cache[key]
            prim = g[g.dup_of == -1]
            zones.append(dict(zone_id=zid, status=_status(g.acq_dt.min(), g.acq_dt.max(), t), area_ha=area,
                              perimeter_km=per, n_hotspots=len(prim), frp_total_mw=float(g.frp.sum()),
                              first_detected=first_seen[zid], last_detected=g.acq_dt.max(), geometry=geom,
                              new_hotspots=int(((prim.acq_dt > t - step)).sum())))
        hot = sub[sub.acq_dt > t - step].copy()
        hot["zone_id"] = [owner.get(i, -1) for i in hot.index]
        alerts = pd.DataFrame()
        if mtg is not None and len(mtg):
            sofar = sub.assign(zone_id=[owner.get(i, -1) for i in sub.index])
            alerts = build_alerts(mtg[mtg.acq_dt <= t], sofar, t, sub.acq_dt.max(), exclusions)
        snaps.append(dict(time=t, zones=zones, hotspots=hot, alerts=alerts))
    return dict(steps=list(times), snaps=snaps, merges=merges)
