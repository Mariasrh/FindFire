"""Find the nearest fire stations and plan the trucks to send."""
import math

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0
ROAD_FACTOR = 1.3      # road distance is longer than straight distance
AVG_SPEED_KMH = 50.0   # placeholder average truck speed
PUMP_L_MIN = 2000.0    # placeholder: water a truck can deliver per minute (TO BE CONFIRMED)
MAX_ETA_MIN = 60.0       # placeholder: ignore stations further than this (TO BE CONFIRMED)
SEARCH_STATIONS = 8      # how many nearest stations are considered
PARAMETERS_STATUS = "placeholder, to be confirmed"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_stations(lat: float, lon: float, stations: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Return the n closest stations with distance and estimated arrival time (vectorised haversine)."""
    p1 = np.radians(lat)
    p2 = np.radians(stations["latitude"].to_numpy(dtype=float))
    dphi = p2 - p1
    dlmb = np.radians(stations["longitude"].to_numpy(dtype=float) - lon)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    dist = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))
    order = np.argsort(dist, kind="stable")[:n]
    out = stations.iloc[order].copy()
    out["distance_km"] = dist[order]
    out["eta_min"] = out["distance_km"] * ROAD_FACTOR / AVG_SPEED_KMH * 60
    return out.round({"distance_km": 1, "eta_min": 0})


def plan_response(lat: float, lon: float, volume_l: float, stations: pd.DataFrame, n: int = 3) -> dict:
    """Tank loads needed to deliver a total volume (no refilling considered).

    Kept for reference: the number of trucks to send at once is given by plan_trucks.
    """
    close = nearest_stations(lat, lon, stations, n)
    loads_needed = math.ceil(volume_l / close.iloc[0]["truck_capacity_l"])
    remaining = loads_needed
    assignments = []
    for _, st in close.iterrows():
        if remaining <= 0:
            break
        sent = min(int(st["trucks"]), remaining)
        assignments.append({
            "station": st["name"],
            "wilaya": st["wilaya"],
            "distance_km": st["distance_km"],
            "eta_min": st["eta_min"],
            "trucks": sent,
        })
        remaining -= sent
    return {
        "loads_needed": loads_needed,
        "assignments": assignments,
        "unmet_loads": max(remaining, 0),
        "needs_reinforcement": remaining > 0,
    }


def plan_trucks(lat: float, lon: float, flow_l_min: float, stations: pd.DataFrame,
                n: int = SEARCH_STATIONS, pump_l_min: float = PUMP_L_MIN,
                max_eta_min: float = MAX_ETA_MIN) -> dict:
    """Trucks to engage AT THE SAME TIME to deliver the required flow.

    Trucks are taken from the n nearest stations. If they cannot cover the
    flow, unmet_trucks > 0 and reinforcements are needed.
    autonomy_min is how long a full tank lasts at the pump flow, before a
    truck has to refill.
    """
    close = nearest_stations(lat, lon, stations, n)
    reachable = close[close["eta_min"] <= max_eta_min]
    needed = math.ceil(flow_l_min / pump_l_min) if flow_l_min > 0 else 0
    remaining = needed
    assignments = []
    for _, st in reachable.iterrows():
        if remaining <= 0:
            break
        sent = min(int(st["trucks"]), remaining)
        if sent <= 0:
            continue
        assignments.append({
            "station": st["name"],
            "wilaya": st["wilaya"],
            "distance_km": st["distance_km"],
            "eta_min": st["eta_min"],
            "trucks": sent,
        })
        remaining -= sent
    capacity = float(close.iloc[0]["truck_capacity_l"])
    return {
        "trucks_needed": needed,
        "trucks_sent": needed - remaining,
        "unmet_trucks": remaining,
        "needs_reinforcement": remaining > 0,
        "autonomy_min": round(capacity / pump_l_min, 1),
        "assignments": assignments,
        "parameters_status": PARAMETERS_STATUS,
    }