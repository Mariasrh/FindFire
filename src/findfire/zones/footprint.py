"""Zone footprints (polygon, area, perimeter) from the hotspot pixels of one zone.

Methods
  "close"  union of the pixel rectangles, gaps up to 2*close_m filled by a morphological closing (the first version)
  "boxes"  union of the pixel rectangles only (tightest possible, under-covers fire interiors)
  "alpha"  alpha shape of the pixel CENTRES (FEDS-style, Chen et al. 2022), then buffered by edge_fraction x the
           half pixel size. Delaunay triangles whose circumradius is below R are kept, so sparse 'tentacles' and long
           thin bridges between hotspots are NOT filled, while dense interiors are. R = alpha_scale x mean
           nearest-neighbour distance of the zone's own hotspots, clipped to [r_min_m, r_max_m] (the adaptive rule of
           the FET tracker). Why centres: a flagged pixel contains fire, so the burned edge runs about through its
           centre; drawing the full rectangle overshoots by half a pixel all the way round (commission error).
           edge_fraction = 1 reproduces the full pixel, 0 is the bare centres hull; fit it on reference perimeters.
Everything is measured in the UTM zone of the zone centre, never in degrees."""
from __future__ import annotations

import numpy as np
import shapely
from scipy.spatial import Delaunay, QhullError, cKDTree
from shapely.geometry import MultiPoint, Polygon, box
from shapely.ops import unary_union

from findfire.config import ALPHA_SCALE, CLOSE_M, EDGE_FRACTION, FOOTPRINT_METHOD
from findfire.zones.geometry import _transformers, utm_epsg


def circumradius(a, b, c):
    """Circumradius of triangles given vertex arrays (n,3,2)... returned per triangle."""
    A, B, C = a, b, c
    la, lb, lc = (np.hypot(*(B - C).T), np.hypot(*(A - C).T), np.hypot(*(A - B).T))
    area2 = np.abs((B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (C[:, 0] - A[:, 0]) * (B[:, 1] - A[:, 1]))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(area2 > 0, la * lb * lc / (2 * area2), np.inf)


def adaptive_radius(xy, alpha_scale=ALPHA_SCALE, r_min_m=400.0, r_max_m=2500.0) -> float:
    """alpha_scale x mean nearest-neighbour distance (metres), clipped."""
    if len(xy) < 2:
        return r_min_m
    d, _ = cKDTree(xy).query(xy, k=2)
    return float(np.clip(alpha_scale * d[:, 1].mean(), r_min_m, r_max_m))


def alpha_shape(xy: np.ndarray, radius_m: float):
    """Union of Delaunay triangles with circumradius <= radius_m. Empty Polygon if there are fewer than 3 usable points."""
    xy = np.unique(np.round(xy, 1), axis=0)
    if len(xy) < 3:
        return Polygon()
    try:
        tri = Delaunay(xy)
    except QhullError:                       # all points collinear
        return Polygon()
    s = xy[tri.simplices]
    keep = circumradius(s[:, 0], s[:, 1], s[:, 2]) <= radius_m
    if not keep.any():
        return Polygon()
    return unary_union([Polygon(t) for t in s[keep]])


def zone_footprint(lons, lats, scan_km, track_km, method: str = FOOTPRINT_METHOD, epsg=None,
                   close_m: float = CLOSE_M, alpha_scale: float = ALPHA_SCALE, edge_fraction: float = EDGE_FRACTION):
    """-> (polygon in lon/lat, area in ha, perimeter in km)."""
    lons, lats = np.asarray(lons, float), np.asarray(lats, float)
    epsg = epsg or utm_epsg(lons.mean(), lats.mean())
    fwd, inv = _transformers(epsg)
    x, y = fwd(lons, lats)
    x, y = np.asarray(x), np.asarray(y)
    hx, hy = np.asarray(scan_km, float) * 500.0, np.asarray(track_km, float) * 500.0
    boxes = unary_union([box(a - w, b - h, a + w, b + h) for a, b, w, h in zip(x, y, hx, hy)])
    if method == "boxes":
        poly = boxes
    elif method == "close":
        poly = boxes.buffer(close_m).buffer(-close_m)
    elif method == "alpha":
        xy = np.c_[x, y]
        shape = alpha_shape(xy, adaptive_radius(xy, alpha_scale))
        core = unary_union([shape, MultiPoint(xy)]) if not shape.is_empty else MultiPoint(xy)
        half = float(np.median(np.maximum(hx, hy)))
        poly = core.buffer(max(edge_fraction * half, 1.0), join_style="mitre")
    else:
        raise ValueError(f"unknown footprint method {method!r}")
    poly = shapely.make_valid(poly)
    geo = shapely.transform(poly, lambda c: np.column_stack(inv(c[:, 0], c[:, 1])))
    return geo, poly.area / 1e4, poly.length / 1e3
