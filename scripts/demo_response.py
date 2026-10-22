"""Print the response plan for two hand-made zones near Tizi Ouzou."""
import pandas as pd
from shapely.geometry import box

from findfire.response import response_table

stations = pd.read_csv("data/fire_stations.csv")
zones = [
    dict(zone_id=1, status="new", area_ha=15.0, geometry=box(4.00, 36.70, 4.004, 36.704)),
    dict(zone_id=2, status="active", area_ha=120.0, geometry=box(4.10, 36.60, 4.11, 36.61)),
]
table = response_table(zones, stations)
cols = ["zone_id", "severity", "area_ha", "flow_l_min", "volume_l", "nearest_station",
        "nearest_distance_km", "nearest_eta_min", "loads_needed", "trucks_sent", "needs_reinforcement"]
pd.set_option("display.width", 220)
print(table[cols].to_string(index=False))