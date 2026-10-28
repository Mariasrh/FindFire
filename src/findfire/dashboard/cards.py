"""Dashboard cards: one card per active fire zone (area, water, stations, trucks, forecast).

Input: the state written by scripts/run_live.py (data/live/state.json), whose "zones" are GeoJSON features
with the zone fields in "properties" (zone_id, status, area_ha, ...) and a lon/lat polygon.

Everything here is a pure function, so it can be tested without a server.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from pyproj import Geod
from shapely.geometry import shape

from findfire.response import response_for_zone
from findfire.dashboard.dispatch import dispatch
from findfire.water.water_demand import compute_water_demand

SEVERITY_ORDER = {"critical": 0, "medium": 1, "low": 2}
FORECAST_DURATION_MIN = 60
_GEOD = Geod(ellps="WGS84")


def load_state(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def zones_from_state(state: dict) -> list[dict]:
    """GeoJSON features -> zone dicts with a shapely geometry in lon/lat."""
    zones = []
    for feature in state.get("zones", []):
        zone = dict(feature.get("properties") or {})
        zone["geometry"] = shape(feature["geometry"])
        zones.append(zone)
    return zones


def perimeter_m(geometry) -> float:
    """Geodesic perimeter in metres of a lon/lat polygon (or multipolygon)."""
    geometry = geometry if hasattr(geometry, "centroid") else shape(geometry)
    parts = getattr(geometry, "geoms", [geometry])
    return float(sum(abs(_GEOD.geometry_area_perimeter(p)[1]) for p in parts))


def forecast_steps(entry: dict, terrain: str) -> list[dict]:
    """Growth steps of one zone (from forecast_zones) with the water demand at each horizon.

    The perimeter of the forecast ellipse is used, so a fire stretched by the wind needs a longer front."""
    wind_kmh = float(entry.get("wind_speed_ms", 0.0)) * 3.6          # the water model wants km/h
    steps = []
    for s in entry.get("steps", []):
        per = perimeter_m(s["geometry"]) if s.get("geometry") is not None else None
        demand = compute_water_demand(float(s["area_ha"]), terrain, FORECAST_DURATION_MIN, wind_kmh, perimeter_m=per)
        steps.append(dict(minutes=int(s["minutes"]), area_ha=round(float(s["area_ha"]), 1),
                          severity=demand.severity, flow_l_min=demand.flow_l_min,
                          front_attacked_m=demand.front_attacked_m))
    return steps


def build_cards(zones: list[dict], stations: pd.DataFrame, forecast: list[dict] | None = None):
    """-> (cards, errors, n_inactive). One bad zone never hides the others."""
    by_zone = {f.get("zone_id"): f for f in (forecast or [])}
    cards, errors, inactive = [], [], 0
    for zone in zones:
        try:
            entry = by_zone.get(zone.get("zone_id"))
            wind_kmh = float(entry["wind_speed_ms"]) * 3.6 if entry else 0.0
            plan = response_for_zone(zone, stations, wind_kmh=wind_kmh)
            if plan is None:
                inactive += 1
                continue
            card = dict(plan)
            card["terrain_assumed"] = not zone.get("terrain")
            new_hotspots = zone.get("new_hotspots")                  # replay only: observations in the last step
            card["new_hotspots"] = None if new_hotspots is None else int(new_hotspots)
            card["spreading"] = new_hotspots is None or int(new_hotspots) > 0
            card["forecast"] = forecast_steps(entry, card["terrain"]) if entry else []
            card["wind"] = (dict(speed_ms=entry["wind_speed_ms"], from_deg=entry["wind_from_deg"],
                                 spread_to_deg=entry["spread_to_deg"]) if entry else None)
            cards.append(card)
        except Exception as err:          # noqa: BLE001 - report it on the page instead of crashing
            errors.append(f"zone {zone.get('zone_id')}: {err}")
    cards.sort(key=lambda c: (SEVERITY_ORDER.get(c["severity"], 9), -c["area_ha"]))
    return cards, errors, inactive


def dashboard_payload(state: dict, stations: pd.DataFrame, forecast=None, warnings=None) -> dict:
    zones = zones_from_state(state)
    cards, errors, inactive = build_cards(zones, stations, forecast)
    try:
        plan = dispatch(cards, stations)
    except Exception as err:          # noqa: BLE001 - the dashboard still works with the per-zone plans
        plan = dict(summary={}, stations=[])
        errors.append(f"dispatch: {err}")
    return dict(sample=bool(state.get("sample")), n_zones=len(zones), inactive=inactive,
                cards=cards, errors=errors, warnings=list(warnings or []),
                dispatch=plan["summary"], stations=plan["stations"])
