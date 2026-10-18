"""Footprint methods on SIMULATED fires with known extent. It compares methods, it does not replace CEMS validation.

Simulation: an irregular 'burned area' (union of ellipses, 200-4000 ha) that grows over 6-10 passes. At each pass the
active front is a band of 400-700 m along the current perimeter (plus a few interior pixels); each pixel inside it is
detected with probability 0.8, with 80 m geolocation jitter and pixel sizes of 375-700 m. Truth = final burned area.
Metrics: IoU, commission (predicted area outside truth / predicted area), omission (truth not covered / truth).
Change the parameters at the top to mimic your region, or feed real CEMS polygons through zone_footprint instead.
"""
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely import affinity
from shapely.geometry import Point
from shapely.ops import unary_union

from findfire.zones.footprint import zone_footprint

TO_LL = Transformer.from_crs(32631, 4326, always_xy=True).transform
FWD = Transformer.from_crs(4326, 32631, always_xy=True).transform


def simulate(rng, p_detect=0.8, jitter=80.0):
    n = rng.integers(2, 6)
    ell = [affinity.rotate(affinity.scale(Point(*rng.normal(0, 900, 2)).buffer(1), rng.uniform(900, 2800), rng.uniform(700, 2200)),
                           rng.uniform(0, 180)) for _ in range(n)]
    truth = unary_union(ell)
    c = truth.centroid; K = int(rng.integers(6, 11)); pts, sizes = [], []
    gx = rng.uniform(0, 375); gy = rng.uniform(0, 375)
    minx, miny, maxx, maxy = truth.bounds
    xs = np.arange(minx - 1000, maxx + 1000, 375.0) + gx; ys = np.arange(miny - 1000, maxy + 1000, 375.0) + gy
    X, Y = np.meshgrid(xs, ys); cells = np.c_[X.ravel(), Y.ravel()]
    for k in range(1, K + 1):
        cur = affinity.scale(truth, 0.35 + 0.65 * k / K, 0.35 + 0.65 * k / K, origin=c)
        w = rng.uniform(400, 700)
        band = cur.buffer(w / 2).difference(cur.buffer(-w / 2))
        inside = shapely.contains_xy(band, cells[:, 0], cells[:, 1])
        interior = shapely.contains_xy(cur, cells[:, 0], cells[:, 1]) & (rng.random(len(cells)) < 0.05)
        pick = (inside | interior) & (rng.random(len(cells)) < p_detect)
        for q in cells[pick]:
            pts.append(q + rng.normal(0, jitter, 2)); sizes.append(rng.uniform(0.375, 0.7))
    return truth, np.array(pts), np.array(sizes)


def score(pred, truth):
    inter = pred.intersection(truth).area
    return dict(iou=inter / pred.union(truth).area, commission=1 - inter / pred.area, omission=1 - inter / truth.area,
                area_ratio=pred.area / truth.area)


def main(n=60):
    rng = np.random.default_rng(1)
    sims = [simulate(rng) for _ in range(n)]
    methods = [("close 750 m (current)", dict(method="close", close_m=750)), ("close 375 m", dict(method="close", close_m=375)),
               ("boxes only", dict(method="boxes"))] + [(f"alpha x{a}, edge {e}", dict(method="alpha", alpha_scale=a, edge_fraction=e))
                                                           for a in (1.5, 3.0) for e in (1.0, 0.5, 0.25, 0.0)]
    rows = {}
    for name, kw in methods:
        r = []
        for truth, pts, sz in sims:
            if len(pts) < 4:
                continue
            lon, lat = TO_LL(pts[:, 0], pts[:, 1])
            geo, *_ = zone_footprint(lon, lat, sz, sz, epsg=32631, **kw)
            polys = [shapely.Polygon(np.c_[FWD(*np.array(g.exterior.coords).T)]) for g in getattr(geo, "geoms", [geo])]
            r.append(score(unary_union(polys), truth))
        rows[name] = pd.DataFrame(r).mean()
    print(f"mean over {n} simulated fires")
    print(pd.DataFrame(rows).T.round(2).to_string())


if __name__ == "__main__":
    main()
