"""Dispatch: share the trucks of the stations between ALL active zones, so no truck is counted twice.

Each zone alert goes to the stations that are actually engaged, not to every station:
  * the LEAD station is the nearest one. It receives the alert and coordinates the zone, even if it has no free truck;
  * the other engaged stations are REINFORCEMENTS, asked only when the lead station cannot supply all the trucks.
A zone with no new hotspot in the last step (spreading is False) is WATCH ONLY: no alert and no truck, until new
hotspots appear. Priority among the others: the most severe first, then the largest.
A station never sends more trucks than it has, over all zones together.

ASSUMPTIONS (placeholders): trucks per station come from the stations file (3 by default in the OSM file),
max_eta_min is the longest arrival time accepted for a reinforcement.
"""
from __future__ import annotations

import re

from findfire.stations.nearest_station import MAX_ETA_MIN, nearest_stations

SEARCH_STATIONS = 15
SEVERITY_ORDER = {"critical": 0, "medium": 1, "low": 2}


def display_name(name: str) -> str:
    """OSM stations without a name are called OSM-<id> by scripts/fetch_fire_stations.py."""
    return f"Unnamed station ({name})" if re.fullmatch(r"OSM-\d+", name) else name


def priority(card: dict):
    return (SEVERITY_ORDER.get(card.get("severity"), 9), -float(card.get("area_ha", 0.0)))


def dispatch(cards: list[dict], stations, n_search: int = SEARCH_STATIONS, max_eta_min: float = MAX_ETA_MIN) -> dict:
    """Update each card in place (assignments, trucks_sent, unmet_trucks, needs_reinforcement, lead station).

    Returns {"summary": {...}, "stations": [...]} where "stations" lists the engaged stations with their load."""
    free = {int(i): int(t) for i, t in stations["trucks"].items()}
    total_trucks = sum(free.values())
    load = {}                                              # station id -> {"name", "zones": set, "trucks": int}

    def engage(station_id, name, zone_id, trucks):
        entry = load.setdefault(station_id, dict(name=name, zones=set(), trucks=0))
        entry["zones"].add(zone_id)
        entry["trucks"] += trucks

    full = partial = none = watch = 0
    for i in sorted(range(len(cards)), key=lambda k: (priority(cards[k]), k)):
        card = cards[i]
        if "nearest_station" in card:
            card["nearest_station"] = display_name(str(card["nearest_station"]))
        if card.get("spreading") is False:                 # no new hotspot: watch only, no alert, no truck
            card.update(assignments=[], trucks_sent=0, unmet_trucks=0, needs_reinforcement=False,
                        eta_last_truck_min=0.0, monitoring=True, involved_station_ids=[])
            watch += 1
            continue
        card["monitoring"] = False
        near = nearest_stations(card["latitude"], card["longitude"], stations, n=n_search)
        lead_id = int(near.index[0])
        lead = near.iloc[0]
        needed = int(card["trucks_needed_now"])
        remaining, assignments = needed, []
        for idx, st in near.iterrows():
            if remaining <= 0:
                break
            idx = int(idx)
            if float(st["eta_min"]) > max_eta_min:
                continue
            take = min(free.get(idx, 0), remaining)
            if take <= 0:
                continue
            free[idx] -= take
            remaining -= take
            name = display_name(str(st["name"]))
            assignments.append(dict(station_id=idx, station=name, trucks=take,
                                    eta_min=float(st["eta_min"]), distance_km=float(st["distance_km"]),
                                    role="lead" if idx == lead_id else "reinforcement"))
            engage(idx, name, card["zone_id"], take)
        lead_name = display_name(str(lead["name"]))
        engage(lead_id, lead_name, card["zone_id"], 0)                # the lead station always gets the alert
        sent = needed - remaining
        card.update(assignments=assignments, trucks_sent=sent, unmet_trucks=remaining,
                    needs_reinforcement=remaining > 0,
                    eta_last_truck_min=max((a["eta_min"] for a in assignments), default=0.0),
                    lead_station=dict(id=lead_id, name=lead_name, eta_min=float(lead["eta_min"]),
                                      distance_km=float(lead["distance_km"]),
                                      free_trucks_left=free.get(lead_id, 0)),
                    involved_station_ids=sorted({lead_id} | {a["station_id"] for a in assignments}))
        if remaining <= 0:
            full += 1
        elif sent > 0:
            partial += 1
        else:
            none += 1
    used = total_trucks - sum(free.values())
    summary = dict(zones=len(cards) - watch, monitoring=watch, fully_served=full, partly_served=partial,
                   not_served=none, trucks_engaged=used, trucks_total=total_trucks)
    engaged = sorted(({"id": sid, "name": e["name"], "zones": len(e["zones"]), "trucks": e["trucks"],
                       "latitude": float(stations.at[sid, "latitude"]), "longitude": float(stations.at[sid, "longitude"])}
                      for sid, e in load.items()), key=lambda s: (-s["zones"], s["name"], s["id"]))
    return dict(summary=summary, stations=engaged)