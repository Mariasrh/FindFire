"""Rebuild zones (VIIRS) and early alerts (MTG) from the stored detections. Stateless: same input, same output.

VIIRS (375 m, a few passes a day) is the reference: its clusters are the fire ZONES with area and perimeter.
MTG (2 km, every 10 min) gives early ALERTS: a place seen in at least two scans. An alert is `confirmed` when VIIRS
later sees the same place, with the lead time measured; `pending` while the window is open; `not_confirmed` once the
VIIRS data has covered the whole window without a match. MTG alone never creates a zone."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from findfire.config import CORE_MIN_NEIGHBORS
from findfire.detection.filters import apply_exclusions, hours_since_epoch, mark_redetections
from findfire.zones.clustering import cluster_hotspots
from findfire.zones.footprint import zone_footprint

R = 6371008.8
CONF = {"l": 0, "n": 1, "h": 2}
NEW_FOR, INACTIVE = pd.Timedelta(hours=24), pd.Timedelta(days=3)
WINDOW_H = 12.0


def _clean(df, exclusions):
    if df.empty:
        return df
    return apply_exclusions(df, exclusions) if exclusions is not None else df


def build_zones(viirs: pd.DataFrame, now: pd.Timestamp, exclusions=None, min_neighbors=CORE_MIN_NEIGHBORS):
    """-> (zones list of dicts with polygon, hotspots DataFrame with zone_id)."""
    v = _clean(viirs, exclusions).reset_index(drop=True)
    if v.empty:
        return [], v.assign(zone_id=pd.Series(dtype=int), dup_of=pd.Series(dtype=int))
    v = mark_redetections(v)
    v["zone_id"] = cluster_hotspots(v, min_neighbors=min_neighbors)
    zones = []
    for zid, g in v[v.zone_id >= 0].groupby("zone_id"):
        geom, area, per = zone_footprint(g.longitude.values, g.latitude.values, g.scan.values, g.track.values)
        first, last = g.acq_dt.min(), g.acq_dt.max()
        status = "new" if first > now - NEW_FOR else "active" if last > now - INACTIVE else "inactive"
        prim = g[g.dup_of == -1]
        zones.append(dict(zone_id=int(zid), status=status, area_ha=area, perimeter_km=per, n_hotspots=len(prim),
                          frp_total_mw=float(g.frp.sum()), first_detected=first, last_detected=last, geometry=geom))
    return zones, v


def build_alerts(mtg: pd.DataFrame, viirs_hotspots: pd.DataFrame, now: pd.Timestamp, viirs_through: pd.Timestamp | None,
                 exclusions=None, min_conf: str = "n", min_scans: int = 2) -> pd.DataFrame:
    cols = ["alert_id", "latitude", "longitude", "first_detected", "last_detected", "n_scans", "pixel_km",
            "status", "lead_time_min", "confirmed_at", "zone_id"]
    m = _clean(mtg, exclusions)
    if m.empty:
        return pd.DataFrame(columns=cols)
    m = m[m.confidence.map(CONF).fillna(-1) >= CONF[min_conf]].reset_index(drop=True)
    if m.empty:
        return pd.DataFrame(columns=cols)
    m["cluster"] = cluster_hotspots(m, max_dt=pd.Timedelta(hours=2))
    prim = viirs_hotspots[viirs_hotspots["dup_of"] == -1] if len(viirs_hotspots) else viirs_hotspots
    tree = BallTree(np.radians(prim[["latitude", "longitude"]].to_numpy(float)), metric="haversine") if len(prim) else None
    vt = hours_since_epoch(prim.acq_dt) if len(prim) else None
    rows = []
    for cid, g in m[m.cluster >= 0].groupby("cluster"):
        if g.acq_dt.nunique() < min_scans:
            continue
        first, last = g.acq_dt.min(), g.acq_dt.max()
        lat, lon, pk = g.latitude.mean(), g.longitude.mean(), float(max(g.scan.max(), g.track.max()))
        status, lead, at, zone = "pending", np.nan, pd.NaT, pd.NA
        if tree is not None:
            hit = tree.query_radius(np.radians([[lat, lon]]), r=(1.5 * pk * 1000 + 750) / R)[0]
            t0 = hours_since_epoch(pd.Series([first]))[0]
            hit = [h for h in hit if -WINDOW_H <= vt[h] - t0 <= WINDOW_H]
            if hit:
                h = min(hit, key=lambda k: vt[k])
                status, at = "confirmed", prim.acq_dt.iloc[h]
                lead = (at - first) / pd.Timedelta(minutes=1)
                zone = prim.zone_id.iloc[h] if "zone_id" in prim and prim.zone_id.iloc[h] >= 0 else pd.NA
        if status == "pending" and viirs_through is not None and viirs_through >= first + pd.Timedelta(hours=WINDOW_H):
            status = "not_confirmed"          # VIIRS data covers the whole window and saw nothing
        rows.append(dict(latitude=lat, longitude=lon, first_detected=first, last_detected=last,
                         n_scans=g.acq_dt.nunique(), pixel_km=pk, status=status, lead_time_min=lead,
                         confirmed_at=at, zone_id=zone))
    out = pd.DataFrame(rows, columns=cols[1:])
    out.insert(0, "alert_id", np.arange(1, len(out) + 1))
    return out


def build_state(viirs, mtg, now, exclusions=None, **kw):
    zones, hot = build_zones(viirs, now, exclusions)
    through = viirs.acq_dt.max() if len(viirs) else None       # newest VIIRS detection we hold (see README caveat)
    alerts = build_alerts(mtg, hot, now, through, exclusions, **kw)
    return zones, hot, alerts, through


def latency_minutes(df: pd.DataFrame):
    """(median, p90) of ingested_at - acq_dt in minutes, or None."""
    if df.empty or "ingested_at" not in df:
        return None
    lat = (df.ingested_at - df.acq_dt) / pd.Timedelta(minutes=1)
    return float(lat.median()), float(lat.quantile(0.9))
