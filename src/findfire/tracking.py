"""Zone geometry and tracking, ported from the FindFire notebook."""
from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import transform as sh_transform
from shapely.geometry import box
from shapely.ops import unary_union
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree

STEP = pd.Timedelta(hours=12)
LINK_M = 1500
ATTACH_M = 3000
CLOSE_M = 750
INACTIVE = pd.Timedelta(days=3)
NEW_FOR = pd.Timedelta(hours=24)
EARTH_R = 6371008.8


def utm_epsg(lon, lat):
    return 32600 + int((lon + 180) // 6) + 1


@lru_cache(maxsize=8)
def _tf(epsg):
    return (
        Transformer.from_crs(4326, epsg, always_xy=True).transform,
        Transformer.from_crs(epsg, 4326, always_xy=True).transform,
    )


def zone_geometry(lons, lats, scan_km, track_km, epsg=None):
    """-> (polygon in lon/lat, area in ha, perimeter in km) in the local UTM zone."""
    epsg = epsg or utm_epsg(np.mean(lons), np.mean(lats))
    fwd, inv = _tf(epsg)
    sq = []
    for lo, la, s, t in zip(lons, lats, scan_km, track_km):
        x, y = fwd(lo, la)
        sq.append(box(x - s * 500, y - t * 500, x + s * 500, y + t * 500))
    poly = unary_union(sq).buffer(CLOSE_M).buffer(-CLOSE_M)
    geo = sh_transform(poly, lambda c: np.column_stack(inv(c[:, 0], c[:, 1])))
    return geo, poly.area / 1e4, poly.length / 1e3


def _tree(latlon):
    return BallTree(np.radians(latlon), metric="haversine")


def status_of(z, t):
    if z["first"] > t - NEW_FOR:
        return "new"
    if z["last"] > t - INACTIVE:
        return "active"
    return "inactive"


def run_tracking(df):
    """Track zones over 12 h steps; returns (snap GeoDataFrame, zones, merges, step_times, hs_zone)."""
    xy = np.c_[df.latitude.values, df.longitude.values]
    ts = df.acq_dt
    start = ts.min().floor("D")
    step_times = pd.date_range(start + STEP, ts.max().floor("12h") + STEP, freq="12h")
    r = LINK_M / EARTH_R
    ra = ATTACH_M / EARTH_R
    zones, pending, merges, rows, hs_zone, geo_cache = {}, set(), [], [], {}, {}
    next_id = 1

    def active_ids(t):
        return [zid for zid, z in zones.items() if z["merged_into"] is None and z["last"] > t - INACTIVE]

    for t in step_times:
        t0 = t - STEP
        new_idx = set(df.index[(ts > t0) & (ts <= t)])
        pending = {i for i in pending if ts[i] > t - INACTIVE}
        cand = sorted(pending | new_idx)
        touched, still_pending = [], set()

        if cand:
            lab = DBSCAN(eps=r, min_samples=1, metric="haversine",
                         algorithm="ball_tree").fit_predict(np.radians(xy[cand]))
            act = active_ids(t)
            if act:
                pix = [(i, zid) for zid in act for i in zones[zid]["idx"]]
                pidx = np.array([p[0] for p in pix]); pz = np.array([p[1] for p in pix])
                tree = _tree(xy[pidx])
            for k in np.unique(lab):
                members = [cand[j] for j in np.where(lab == k)[0]]
                target = None
                if act:
                    dist, nn = tree.query(np.radians(xy[members]), k=1)
                    if dist.min() <= ra:
                        target = int(pz[nn[dist[:, 0].argmin(), 0]])
                if target is not None:
                    z = zones[target]; z["idx"].update(members)
                    z["last"] = max(z["last"], ts[members].max()); touched += members
                elif len(members) >= 2:
                    zones[next_id] = dict(idx=set(members), first=ts[members].min(),
                                          last=ts[members].max(), merged_into=None)
                    touched += members; next_id += 1
                else:
                    still_pending.update(members)
        pending = still_pending

        act = active_ids(t)
        if touched and len(act) > 1:
            pix = [(i, zid) for zid in act for i in zones[zid]["idx"]]
            pidx = np.array([p[0] for p in pix]); pz = np.array([p[1] for p in pix])
            own = {i: zid for i, zid in pix}
            tree = _tree(xy[pidx]); parent = {zid: zid for zid in act}

            def find(a):
                while parent[a] != a:
                    parent[a] = parent[parent[a]]; a = parent[a]
                return a

            for i, nb in zip(touched, tree.query_radius(np.radians(xy[touched]), r=ra)):
                for j in nb:
                    a, b = find(own[i]), find(int(pz[j]))
                    if a != b:
                        parent[b] = a
            groups = {}
            for zid in act:
                groups.setdefault(find(zid), []).append(zid)
            for g in groups.values():
                if len(g) > 1:
                    keep = min(g, key=lambda q: (zones[q]["first"], q))
                    for s in g:
                        if s == keep:
                            continue
                        zones[keep]["idx"] |= zones[s]["idx"]
                        zones[keep]["first"] = min(zones[keep]["first"], zones[s]["first"])
                        zones[keep]["last"] = max(zones[keep]["last"], zones[s]["last"])
                        zones[s]["merged_into"] = keep; merges.append((t, s, keep))

        step_map = {}
        for zid, z in zones.items():
            if z["merged_into"] is not None:
                continue
            idx = sorted(z["idx"]); key = (zid, len(idx))
            if key not in geo_cache:
                sub = df.loc[idx]
                geo_cache[key] = zone_geometry(sub.longitude.values, sub.latitude.values,
                                               sub.scan.values, sub.track.values)
            geom, area, per = geo_cache[key]
            sub = df.loc[idx]; step_sub = sub[(sub.acq_dt > t0) & (sub.acq_dt <= t)]
            rows.append(dict(step=t, zone_id=zid, status=status_of(z, t), area_ha=area, perimeter_km=per,
                             n_hotspots=len(sub), new_hotspots=len(step_sub), frp_new_mw=step_sub.frp.sum(),
                             frp_total_mw=sub.frp.sum(), first_detected=z["first"], last_detected=z["last"],
                             geometry=geom))
            for i in step_sub.index:
                step_map[i] = zid
        hs_zone[t] = step_map

    snap = (gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326") if rows else
            gpd.GeoDataFrame({"step": [], "zone_id": [], "geometry": []}, geometry="geometry", crs="EPSG:4326"))
    return snap, zones, merges, step_times, hs_zone