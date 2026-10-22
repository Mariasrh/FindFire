"""Response plan for fire zones: water demand, nearest stations and trucks.

Takes the zone dicts produced by findfire.live.pipeline.build_zones and
findfire.zones.tracking.run_tracking.

Simplifications (to state in the report):
- area_ha is the cumulative footprint of the zone, so the demand is an
  upper bound for an old fire.
- one truck delivers one tank load, no refilling.
- inactive zones (no detection for 3 days) get no plan.
"""
from __future__ import annotations

import pandas as pd

from findfire.stations.nearest_station import nearest_stations, plan_response
from findfire.water.water_demand import compute_water_demand

DEFAULT_TERRAIN = "forest"   # until the land cover filter provides a value
LAT_RANGE = (15.0, 40.0)     # catches a geometry that is not in lon/lat
LON_RANGE = (-10.0, 15.0)

COLUMNS = [
    "zone_id", "status", "latitude", "longitude", "area_ha", "terrain", "severity",
    "flow_l_min", "volume_l", "nearest_station", "nearest_distance_km", "nearest_eta_min",
    "loads_needed", "trucks_sent", "unmet_loads", "needs_reinforcement", "assignments",
]


def zone_centre(zone: dict) -> tuple[float, float]:
    """(latitude, longitude) of the zone centre. The geometry must be in lon/lat."""
    c = zone["geometry"].centroid
    lat, lon = float(c.y), float(c.x)
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        raise ValueError(
            f"Zone {zone.get('zone_id')}: centre ({lat}, {lon}) is not a lon/lat position "
            "in Algeria. Check the coordinate system of the zone geometry."
        )
    return lat, lon


def response_for_zone(zone: dict, stations: pd.DataFrame, wind_kmh: float = 0.0,
                      terrain: str | None = None, duration_min: int = 60) -> dict | None:
    """Water demand + station plan for one zone. None for an inactive zone."""
    if stations is None or stations.empty:
        raise ValueError("No fire stations loaded")
    if zone.get("status") == "inactive":
        return None
    lat, lon = zone_centre(zone)
    terrain = terrain or zone.get("terrain") or DEFAULT_TERRAIN
    water = compute_water_demand(float(zone["area_ha"]), terrain, duration_min, wind_kmh)
    plan = plan_response(lat, lon, water.volume_l, stations)
    nearest = nearest_stations(lat, lon, stations, n=1).iloc[0]
    return dict(
        zone_id=zone["zone_id"],
        status=zone.get("status"),
        latitude=lat,
        longitude=lon,
        area_ha=float(zone["area_ha"]),
        terrain=terrain,
        severity=water.severity,
        flow_l_min=water.flow_l_min,
        volume_l=water.volume_l,
        nearest_station=nearest["name"],
        nearest_distance_km=float(nearest["distance_km"]),
        nearest_eta_min=float(nearest["eta_min"]),
        loads_needed=plan["loads_needed"],
        trucks_sent=sum(a["trucks"] for a in plan["assignments"]),
        unmet_loads=plan["unmet_loads"],
        needs_reinforcement=plan["needs_reinforcement"],
        assignments=plan["assignments"],
    )


def response_table(zones: list[dict], stations: pd.DataFrame, **kw) -> pd.DataFrame:
    """One row per non-inactive zone, largest water volume first."""
    rows = [r for z in zones if (r := response_for_zone(z, stations, **kw)) is not None]
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(rows)[COLUMNS].sort_values("volume_l", ascending=False).reset_index(drop=True)