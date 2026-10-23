"""Response plan for fire zones: water demand, nearest stations and trucks.

Takes the zone dicts produced by findfire.live.pipeline.build_zones and
findfire.zones.tracking.run_tracking.

Simplifications (to state in the report):
- area_ha is the cumulative footprint of the zone.
- trucks_needed_now = flow / pump flow of one truck (placeholder, to be confirmed).
- trucks come from the 3 nearest stations; the last wave arrives later than the first.
- inactive zones (no detection for 3 days) get no plan.
"""
from __future__ import annotations

import pandas as pd

from findfire.stations.nearest_station import nearest_stations, plan_response, plan_trucks
from findfire.water.water_demand import compute_water_demand

DEFAULT_TERRAIN = "forest"   # until the land cover filter provides a value
LAT_RANGE = (15.0, 40.0)     # catches a geometry that is not in lon/lat
LON_RANGE = (-10.0, 15.0)

COLUMNS = [
    "zone_id", "status", "latitude", "longitude", "area_ha", "terrain", "severity",
    "flow_l_min", "volume_l", "nearest_station", "nearest_distance_km", "nearest_eta_min",
    "loads_needed", "trucks_needed_now", "trucks_sent", "unmet_trucks", "autonomy_min",
    "eta_last_truck_min", "needs_reinforcement", "assignments",
]

SEVERITY_ORDER = {"critical": 0, "medium": 1, "low": 2}


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
    """Water demand + truck plan for one zone. None for an inactive zone."""
    if stations is None or stations.empty:
        raise ValueError("No fire stations loaded")
    if zone.get("status") == "inactive":
        return None
    lat, lon = zone_centre(zone)
    terrain = terrain or zone.get("terrain") or DEFAULT_TERRAIN
    water = compute_water_demand(float(zone["area_ha"]), terrain, duration_min, wind_kmh)
    loads = plan_response(lat, lon, water.volume_l, stations)
    trucks = plan_trucks(lat, lon, water.flow_l_min, stations)
    nearest = nearest_stations(lat, lon, stations, n=1).iloc[0]
    etas = [a["eta_min"] for a in trucks["assignments"]]
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
        loads_needed=loads["loads_needed"],
        trucks_needed_now=trucks["trucks_needed"],
        trucks_sent=trucks["trucks_sent"],
        unmet_trucks=trucks["unmet_trucks"],
        autonomy_min=trucks["autonomy_min"],
        eta_last_truck_min=float(max(etas)) if etas else 0.0,
        needs_reinforcement=trucks["needs_reinforcement"],
        assignments=trucks["assignments"],
    )


def response_table(zones: list[dict], stations: pd.DataFrame, **kw) -> pd.DataFrame:
    """One row per non-inactive zone, most severe first, then largest area."""
    rows = [r for z in zones if (r := response_for_zone(z, stations, **kw)) is not None]
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    table = pd.DataFrame(rows)[COLUMNS]
    table["_rank"] = table["severity"].map(SEVERITY_ORDER)
    table = table.sort_values(["_rank", "area_ha"], ascending=[True, False], kind="mergesort")
    return table.drop(columns="_rank").reset_index(drop=True)