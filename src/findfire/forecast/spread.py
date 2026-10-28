"""Simplified fire growth: an ellipse stretched along the wind (issue F6).

What it does, in plain words
  1. The zone's current area is replaced by a circle of the same area (radius r0).
  2. Wind and vegetation give a head rate of spread R (metres per minute).
  3. Wind also sets how stretched the fire is: the length-to-breadth ratio LB (Anderson 1983, as used by FARSITE, U in m/s).
  4. LB gives the back rate Rb = R (1 - e) / (1 + e), with e = sqrt(LB^2 - 1) / LB.
  5. After t minutes the fire reaches r0 + R t downwind and r0 + Rb t upwind. The sideways reach follows from LB.

LIMITS (say them in the report)
  * Not a physical model: no slope, no spotting, no firefighting, no change of wind in time.
  * Fuel dryness is optional (forecast.fuel, Canadian FFMC): without it every zone has the reference dryness.
  * The zone is a circle at the start, so its real shape is ignored.
  * Rates marked ASSUMPTION below are placeholders. Replace them with sourced values (docs/references.md).
  * Wind comes from a weather model at 10 m height, not measured at the fire.
"""
from __future__ import annotations

import inspect
import math
from typing import Callable

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import Point, shape

from findfire.forecast.fuel import Fuel
from findfire.forecast.wind import Wind
from findfire.zones.geometry import _transformers, utm_epsg

HORIZONS_MIN = (30, 60, 120)
LB_MAX = 8.0             # Finney (1998) truncates the ratio at 8

# ASSUMPTION: 10 m wind -> wind at flame height. Typical factors are below 1 because vegetation slows the wind.
WIND_ADJUSTMENT = 0.4
# ASSUMPTION: rate of spread with no wind, metres per minute. PLACEHOLDERS: source them before the demo.
BASE_ROS_M_MIN = {"grass": 5.0, "shrub": 2.0, "forest": 1.0}
# ASSUMPTION: how much each m/s of flame-height wind speeds the head fire up (1 + gain x wind).
WIND_GAIN = 0.3


def length_breadth(midflame_ms: float) -> float:
    """Length-to-breadth ratio of the fire ellipse from the wind at flame height (1 = circle).

    LB = 0.936 exp(0.2566 U) + 0.461 exp(-0.1548 U) - 0.397, U in metres per second (Anderson 1983 as used in
    FARSITE; unit and the cap at 8 confirmed in Finney 1998, RMRS-RP-4). The 0.397 makes LB = 1 with no wind."""
    u = max(midflame_ms, 0.0)
    return min(LB_MAX, max(1.0, 0.936 * math.exp(0.2566 * u) + 0.461 * math.exp(-0.1548 * u) - 0.397))


def rates(wind: Wind, vegetation: str = "shrub", fuel_factor: float = 1.0) -> dict:
    """Head and back rate of spread (m/min) and the length-to-breadth ratio.
    `fuel_factor` scales the rate for fuel dryness (forecast.fuel.Fuel.factor, 1.0 = reference dryness)."""
    if vegetation not in BASE_ROS_M_MIN:
        raise ValueError(f"vegetation must be one of {sorted(BASE_ROS_M_MIN)}")
    u = wind.speed_ms * WIND_ADJUSTMENT
    lb = length_breadth(u)
    head = BASE_ROS_M_MIN[vegetation] * fuel_factor * (1.0 + WIND_GAIN * u)
    ecc = math.sqrt(lb * lb - 1.0) / lb
    back = head * (1.0 - ecc) / (1.0 + ecc)
    return dict(head_m_min=head, back_m_min=back, length_breadth=lb)


def grow(area_ha: float, wind: Wind, vegetation: str, minutes: float, fuel_factor: float = 1.0) -> dict:
    """Ellipse after `minutes`: semi-axes a (along the wind) and b (across), centre shift (m), area (ha)."""
    r = rates(wind, vegetation, fuel_factor)
    r0 = math.sqrt(max(area_ha, 0.0) * 1e4 / math.pi)
    total = (r["head_m_min"] + r["back_m_min"]) * minutes / 2.0       # growth of the long semi-axis
    a = r0 + total
    b = r0 + total / r["length_breadth"]
    shift = (r["head_m_min"] - r["back_m_min"]) * minutes / 2.0       # centre moves downwind
    return dict(a_m=a, b_m=b, shift_m=shift, area_ha=math.pi * a * b / 1e4, perimeter_km=_ellipse_perimeter_m(a, b) / 1e3, **r)


def _ellipse_perimeter_m(a: float, b: float) -> float:
    """Ramanujan's approximation, accurate to a few parts per million for fire-like ellipses."""
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def ellipse_polygon(lon: float, lat: float, a_m: float, b_m: float, shift_m: float, to_deg: float):
    """Ellipse as a shapely polygon in lon/lat. Built in the UTM zone of the centre (never in degrees)."""
    epsg = utm_epsg(lon, lat)
    fwd, inv = _transformers(epsg)
    x0, y0 = fwd(lon, lat)
    theta = math.radians(to_deg)                                       # bearing: clockwise from north
    unit = Point(0, 0).buffer(1.0, quad_segs=32)
    e = affinity.scale(unit, xfact=b_m, yfact=a_m, origin=(0, 0))      # long axis points north
    e = affinity.rotate(e, -to_deg, origin=(0, 0))                     # shapely rotates counter-clockwise
    e = affinity.translate(e, x0 + shift_m * math.sin(theta), y0 + shift_m * math.cos(theta))
    return shapely.transform(e, lambda c: np.column_stack(inv(c[:, 0], c[:, 1])))


def _call_water(water_fn: Callable, area_ha: float, perimeter_km: float, wind_ms: float) -> dict:
    """Call the water function with as much as it accepts: (area), or (area, perimeter_km, wind_kmh).
    findfire.water.water_demand.water_for_forecast takes the full set; a plain `lambda ha: ...` still works."""
    try:
        params = inspect.signature(water_fn).parameters
    except (TypeError, ValueError):
        return water_fn(area_ha)
    var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    kw = {}
    if "perimeter_km" in params or var_kw:
        kw["perimeter_km"] = perimeter_km
    if "wind_kmh" in params or var_kw:
        kw["wind_kmh"] = wind_ms * 3.6
    return water_fn(area_ha, **kw)


def forecast_zone(zone: dict, wind: Wind, vegetation: str = "shrub", horizons=HORIZONS_MIN,
                  water_fn: Callable[..., dict] | None = None, fuel: Fuel | None = None) -> dict:
    """Forecast one zone. `zone` needs `area_ha` and `geometry` (shapely or GeoJSON); `zone_id` is kept if present.

    `water_fn` is optional. It is called with the forecast area, and also with `perimeter_km` and `wind_kmh` if it
    accepts them (see findfire.water.water_demand.water_for_forecast). Every step then gets a `water` entry.
    `fuel` is optional (forecast.fuel.Fuel): its factor scales the spread rate. None = reference dryness (factor 1)."""
    factor = 1.0 if fuel is None else fuel.factor
    geom = zone["geometry"]
    geom = geom if hasattr(geom, "centroid") else shape(geom)
    c = geom.centroid
    steps = []
    for t in horizons:
        g = grow(zone["area_ha"], wind, vegetation, t, factor)
        step = dict(minutes=t, area_ha=g["area_ha"], growth_ha=g["area_ha"] - zone["area_ha"],
                    perimeter_km=g["perimeter_km"],
                    geometry=ellipse_polygon(c.x, c.y, g["a_m"], g["b_m"], g["shift_m"], wind.to_deg))
        if water_fn is not None:
            step["water"] = _call_water(water_fn, g["area_ha"], g["perimeter_km"], wind.speed_ms)
        steps.append(step)
    r = rates(wind, vegetation, factor)
    return dict(zone_id=zone.get("zone_id"), area_now_ha=zone["area_ha"], vegetation=vegetation,
                wind_speed_ms=wind.speed_ms, wind_from_deg=wind.from_deg, spread_to_deg=wind.to_deg,
                wind_source=wind.source, length_breadth=r["length_breadth"], head_ros_m_min=r["head_m_min"],
                fuel_factor=factor, ffmc=None if fuel is None else fuel.ffmc, fuel_source=None if fuel is None else fuel.source,
                steps=steps)


def forecast_zones(zones: list[dict], wind_fn: Callable[..., Wind], vegetation: str = "shrub",
                   horizons=HORIZONS_MIN, water_fn=None, when=None, skip_inactive: bool = True,
                   fuel_fn: Callable[..., Fuel] | None = None) -> list[dict]:
    """Forecast every zone.

    `wind_fn(lat, lon) -> Wind`, or `wind_fn(lat, lon, when) -> Wind` when `when` is given
    (e.g. forecast.wind.wind_or_default, or a fixed wind for tests).
    `when`: the moment the wind is taken at. None = the wind function's own default (now). A timestamp = one moment for
    every zone (a replay step). A function `zone -> timestamp` = per zone, e.g. `lambda z: z["last_detected"]`.
    `skip_inactive`: zones with status "inactive" (no detection for days, an old burn) get no forecast.
    `fuel_fn`: optional, called like `wind_fn` (lat, lon) or (lat, lon, when) and returns a Fuel
    (e.g. forecast.fuel.fuel_or_default). None = no fuel dryness, factor 1."""
    out = []
    for z in zones:
        if skip_inactive and z.get("status") == "inactive":
            continue
        geom = z["geometry"] if hasattr(z["geometry"], "centroid") else shape(z["geometry"])
        c = geom.centroid
        if when is None:
            wind = wind_fn(c.y, c.x)
        else:
            wind = wind_fn(c.y, c.x, when(z) if callable(when) else when)
        fuel = None
        if fuel_fn is not None:
            fuel = fuel_fn(c.y, c.x) if when is None else fuel_fn(c.y, c.x, when(z) if callable(when) else when)
        out.append(forecast_zone(z, wind, vegetation, horizons, water_fn, fuel))
    return out
