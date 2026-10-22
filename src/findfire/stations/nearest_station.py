"""Find the nearest fire stations and plan the trucks to send."""
import math

import pandas as pd

EARTH_RADIUS_KM = 6371.0
ROAD_FACTOR = 1.3      # road distance is longer than straight distance
AVG_SPEED_KMH = 50.0   # placeholder average truck speed


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_stations(lat: float, lon: float, stations: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Return the n closest stations with distance and estimated arrival time."""
    df = stations.copy()
    df["distance_km"] = df.apply(
        lambda r: haversine_km(lat, lon, r["latitude"], r["longitude"]), axis=1
    )
    df["eta_min"] = df["distance_km"] * ROAD_FACTOR / AVG_SPEED_KMH * 60
    return df.nsmallest(n, "distance_km").round({"distance_km": 1, "eta_min": 0})


def plan_response(lat: float, lon: float, volume_l: float, stations: pd.DataFrame, n: int = 3) -> dict:
    """Assign trucks from the nearest stations until the water volume is covered.

    A truck-load is one full tank. If the nearby stations cannot cover the
    demand, unmet_loads > 0 and reinforcements are needed.
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