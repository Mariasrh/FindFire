"""Tiny web server for the firefighter dashboard (standard library only).

GET /           the page (index.html)
GET /api/cards  JSON with one card per active zone, rebuilt only when the state file changes
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

from findfire.dashboard.cards import dashboard_payload, load_state, zones_from_state

PAGE = Path(__file__).with_name("index.html")


def _json_default(obj):
    if hasattr(obj, "item"):                       # numpy numbers
        return obj.item()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def compute_forecast(zones, vegetation, fixed_wind=None):
    """Growth forecast of the active zones (needs the forecast package and, unless fixed_wind, internet)."""
    from findfire.forecast import wind as wind_mod
    from findfire.forecast.spread import forecast_zones
    active = [z for z in zones if z.get("status") != "inactive"]
    if not active:
        return []
    if fixed_wind:
        wind_fn = lambda lat, lon: wind_mod.Wind(*fixed_wind)           # noqa: E731
    else:
        wind_fn = getattr(wind_mod, "cached_wind_or_default", wind_mod.cached_wind)
    return forecast_zones(active, wind_fn, vegetation)


class Dashboard:
    def __init__(self, state_path, stations_path, vegetation="shrub", fixed_wind=None, forecast=True):
        self.state_path, self.vegetation = Path(state_path), vegetation
        self.fixed_wind, self.forecast_on = fixed_wind, forecast
        self.stations = pd.read_csv(stations_path)
        self._mtime, self._payload, self._lock = None, None, threading.Lock()

    def payload(self) -> dict:
        with self._lock:
            if not self.state_path.exists():
                return dict(sample=False, n_zones=0, inactive=0, cards=[], errors=[],
                            warnings=[f"state file not found: {self.state_path}. Run scripts/run_live.py first."])
            mtime = self.state_path.stat().st_mtime
            if mtime == self._mtime and self._payload is not None:
                return self._payload
            try:
                state = load_state(self.state_path)
            except ValueError as err:                      # file being written: keep the last good payload
                old = self._payload or dict(sample=False, n_zones=0, inactive=0, cards=[], errors=[], warnings=[])
                return dict(old, warnings=old.get("warnings", []) + [f"state file unreadable for now: {err}"])
            warnings, forecast = [], None
            if self.forecast_on:
                try:
                    forecast = compute_forecast(zones_from_state(state), self.vegetation, self.fixed_wind)
                except Exception as err:                   # noqa: BLE001 - the dashboard works without a forecast
                    warnings.append(f"forecast unavailable: {err}")
            self._payload = dashboard_payload(state, self.stations, forecast, warnings)
            self._mtime = mtime
            return self._payload


def make_server(dashboard: Dashboard, host="127.0.0.1", port=8000) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body: bytes, kind):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):                                  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/cards":
                body = json.dumps(dashboard.payload(), default=_json_default).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def log_message(self, *args):                      # keep the terminal quiet
            pass

    return ThreadingHTTPServer((host, port), Handler)