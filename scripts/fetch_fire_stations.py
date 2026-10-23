"""Download fire stations in Algeria from OpenStreetMap (Overpass API).

Output: data/fire_stations.csv. Trucks and tank capacity are NOT in OSM:
they are filled with clearly marked default assumptions.
Data (c) OpenStreetMap contributors, ODbL license.
"""
import pandas as pd
import requests

URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "FindFire-student-project/0.1 (wildfire detection prototype)"}
QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="DZ"][admin_level=2]->.dz;
(
  node["amenity"="fire_station"](area.dz);
  way["amenity"="fire_station"](area.dz);
  relation["amenity"="fire_station"](area.dz);
);
out center tags;
"""

DEFAULT_TRUCKS = 3          # ASSUMPTION, replace with real data
DEFAULT_CAPACITY_L = 4000   # ASSUMPTION, replace with real data


def download() -> dict:
    last_error = None
    for url in URLS:
        try:
            response = requests.post(url, data={"data": QUERY}, headers=HEADERS, timeout=240)
            response.raise_for_status()
            print(f"OK from {url}")
            return response.json()
        except requests.RequestException as err:
            print(f"Failed on {url}: {err}")
            last_error = err
    raise RuntimeError(f"All Overpass servers failed: {last_error}")


def fetch() -> pd.DataFrame:
    rows = []
    for el in download()["elements"]:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        rows.append({
            "name": tags.get("name") or tags.get("name:fr") or tags.get("name:ar") or f"OSM-{el['id']}",
            "wilaya": tags.get("addr:state") or tags.get("addr:city") or "unknown",
            "latitude": lat,
            "longitude": lon,
            "trucks": DEFAULT_TRUCKS,
            "truck_capacity_l": DEFAULT_CAPACITY_L,
            "trucks_source": "assumed",
        })
    return pd.DataFrame(rows).drop_duplicates(subset=["latitude", "longitude"])


if __name__ == "__main__":
    stations = fetch()
    stations.to_csv("data/fire_stations.csv", index=False)
    print(f"{len(stations)} stations saved to data/fire_stations.csv")
    print(stations.head(10).to_string(index=False))