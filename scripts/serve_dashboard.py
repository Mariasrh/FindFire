"""Serve the firefighter dashboard.

    python scripts/serve_dashboard.py                                   # reads data/live/state.json
    python scripts/serve_dashboard.py --state data/live/sample_state.json
    python scripts/serve_dashboard.py --no-forecast                     # no Open-Meteo call
    python scripts/serve_dashboard.py --wind 6 270                      # fixed wind (m/s, FROM degrees), works offline

Then open http://127.0.0.1:8000 and click "Enable sound" once (browsers block sound until a click).
"""
import argparse

from findfire.config import DATA_DIR
from findfire.dashboard.server import Dashboard, make_server

a = argparse.ArgumentParser()
a.add_argument("--state", default=str(DATA_DIR / "live" / "state.json"))
a.add_argument("--stations", default=str(DATA_DIR / "fire_stations.csv"))
a.add_argument("--port", type=int, default=8000)
a.add_argument("--vegetation", default="shrub", choices=["grass", "shrub", "forest"])
a.add_argument("--no-forecast", action="store_true")
a.add_argument("--wind", nargs=2, type=float, metavar=("SPEED_MS", "FROM_DEG"))
a = a.parse_args()

from findfire.dashboard import server as server_module
server_module.WIND_CACHE_PATH = DATA_DIR / "archive" / "wind_cache.json"   # past winds are kept: a replay then works offline
dashboard = Dashboard(a.state, a.stations, a.vegetation, tuple(a.wind) if a.wind else None, not a.no_forecast)
server = make_server(dashboard, port=a.port)
print(f"Dashboard on http://127.0.0.1:{a.port}  (state: {a.state})  Ctrl+C to stop")
try:
    server.serve_forever()
except KeyboardInterrupt:
    print("stopped")