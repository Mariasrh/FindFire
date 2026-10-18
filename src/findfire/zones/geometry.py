"""Zone polygons, area and perimeter, measured in the right Algerian UTM zone.

Areas and distances must never be computed in degrees. Algeria spans UTM zones 29N to 32N
(EPSG:32629 to 32632), so each zone is measured in the UTM zone of its own centre.
"""
from functools import lru_cache

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import unary_union

from findfire.config import CLOSE_M


def utm_epsg(lon, lat):
    """EPSG code of the WGS84 UTM zone that contains (lon, lat). Algeria is entirely north of the equator."""
    return 32600 + int((lon + 180) // 6) + 1


@lru_cache(maxsize=8)
def _transformers(epsg):
    return (Transformer.from_crs(4326, epsg, always_xy=True).transform,
            Transformer.from_crs(epsg, 4326, always_xy=True).transform)


def zone_geometry(lons, lats, scan_km, track_km, epsg=None, close_m=CLOSE_M):
    """Polygon (lon/lat), area (ha) and perimeter (km) of a group of VIIRS hotspots.

    Each hotspot is a rectangle of its own pixel size (`scan` x `track`, in km, columns of the FIRMS file).
    The rectangles are merged, and small gaps are closed with a buffer of `close_m` metres."""
    lons, lats = np.asarray(lons, float), np.asarray(lats, float)
    epsg = epsg or utm_epsg(lons.mean(), lats.mean())
    forward, inverse = _transformers(epsg)
    squares = []
    for lon, lat, scan, track in zip(lons, lats, scan_km, track_km):
        x, y = forward(lon, lat)
        squares.append(box(x - scan * 500, y - track * 500, x + scan * 500, y + track * 500))
    polygon = unary_union(squares).buffer(close_m).buffer(-close_m)
    geometry = shapely.transform(polygon, lambda c: np.column_stack(inverse(c[:, 0], c[:, 1])))
    return geometry, polygon.area / 1e4, polygon.length / 1e3