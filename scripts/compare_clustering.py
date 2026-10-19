"""Old notebook clustering vs the pixel-aware one.

1) synthetic cases with KNOWN fires (checks the mechanics, not real-world accuracy)
2) optionally a real FIRMS CSV (descriptive only: there is no ground truth)

    python scripts/compare_clustering.py [data/raw/firms_algeria.csv]
Replace (2) with an archive event you know (e.g. the Kabylie fires of Aug 2021, *_SP sources) to tune the parameters.
"""
import sys

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from findfire.config import STUDY_BBOX
from findfire.detection.filters import mark_redetections
from findfire.zones.clustering import cluster_hotspots

KM_LAT = 111.195
KM_LON = KM_LAT * np.cos(np.radians(36.0))
T0 = pd.Timestamp("2026-10-17 01:00", tz="UTC")


def frame(xy, size, sat="N20", minutes=0.0):
    xy = np.atleast_2d(xy)
    return pd.DataFrame(dict(latitude=36.0 + xy[:, 1] / KM_LAT, longitude=4.0 + xy[:, 0] / KM_LON,
                             acq_dt=T0 + pd.Timedelta(minutes=minutes), scan=size, track=size, satellite=sat, frp=1.0))


def old_labels(df, eps_m=1500):
    lab = DBSCAN(eps=eps_m / 6371008.8, min_samples=1, metric="haversine", algorithm="ball_tree").fit_predict(
        np.radians(df[["latitude", "longitude"]].to_numpy()))
    sizes = pd.Series(lab).map(pd.Series(lab).value_counts())
    return np.where(sizes >= 2, lab, -1)                       # the notebook: a lone hotspot is not a zone


def new_labels(df, **kw):
    return cluster_hotspots(mark_redetections(df), **kw)


def scenario(rng):
    parts, truth, fid = [], [], 0

    def add(df, t):
        parts.append(df); truth.extend(t)

    for _ in range(4):                                            # 4 compact nadir fires, 60+ km apart
        c = rng.uniform(-90, 90, 2); n = int(rng.integers(15, 40))
        add(frame(c + rng.normal(0, 0.6, (n, 2)), 0.4), [fid] * n); fid += 1
    c = np.array([100.0, 0.0]); n = 25                            # swath-edge fire, 0.8 km pixels, 30% of them missed
    xy = c + np.c_[np.arange(2 * n) * 0.8, rng.normal(0, 0.3, 2 * n)]
    xy = xy[rng.random(2 * n) < 0.7]
    add(frame(xy, 0.8), [fid] * len(xy)); fid += 1
    A = np.array([-60.0, 60.0]); B = A + [4.8, 0]                 # two fires bridged by 4 stray detections
    for blob in (A, B):
        pts = blob + rng.normal(0, 0.35, (20, 2)); add(frame(pts, 0.4), [fid] * 20); fid += 1
    add(frame(A + np.array([[1.7, 0], [2.4, 0], [3.1, 0], [3.8, 0]]), 0.4), [-1] * 4)
    fl = rng.uniform(-100, 100, (15, 2))                          # 15 industrial flares, each seen by 2 satellites
    add(frame(fl, 0.4, "N20"), [-1] * 15)
    add(frame(fl + 0.05, 0.4, "SNPP", 50), [-1] * 15)
    return pd.concat(parts, ignore_index=True), np.array(truth)


def score(labels, truth):
    fires = sorted(set(truth) - {-1})
    split = sum(len(set(labels[truth == f]) - {-1}) > 1 or (labels[truth == f] == -1).any() for f in fires)
    zones = sorted(set(labels) - {-1})
    merged = sum(len(set(truth[labels == z]) - {-1}) >= 2 for z in zones)
    false = sum(len(set(truth[labels == z]) - {-1}) == 0 for z in zones)
    return dict(zones=len(zones), true_fires=len(fires), fires_split_or_missed=split, zones_merging_fires=merged,
                false_zones=false)


def main():
    rows = {"old (eps 1500 m, min_samples=1)": [], "new defaults": [], "new, min_neighbors=3": []}
    for seed in range(20):
        df, truth = scenario(np.random.default_rng(seed))
        for name, lab in zip(rows, (old_labels(df), new_labels(df), new_labels(df, min_neighbors=3))):
            rows[name].append(score(lab, truth))
    print("mean over 20 random synthetic scenes (7 real fires + 4 bridge strays + 15 two-satellite flares each)")
    print(pd.DataFrame({k: pd.DataFrame(v).mean() for k, v in rows.items()}).round(2).T.to_string())
    if len(sys.argv) > 1:
        from findfire.ingestion.firms import load_csv
        w, s, e, n = STUDY_BBOX
        d = load_csv(sys.argv[1]); d = d[d.latitude.between(s, n) & d.longitude.between(w, e)].reset_index(drop=True)
        print(f"\nreal CSV, study box: {len(d)} hotspots (no ground truth)")
        for name, lab in (("old", old_labels(d)), ("new", new_labels(d)), ("new min_neighbors=3", new_labels(d, min_neighbors=3))):
            print(f"  {name:22s} zones={len(set(lab) - {-1})}  hotspots in a zone={(lab >= 0).sum()}  lone={(lab == -1).sum()}")


if __name__ == "__main__":
    main()
