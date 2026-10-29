"""Tiny web server for the firefighter dashboard (standard library only).

GET /           the page (index.html)
GET /api/cards  JSON with one card per active zone, rebuilt only when the state file changes
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

from findfire.dashboard.cards import dashboard_payload, load_state, zones_from_state

PAGE = Path(__file__).with_name("index.html")
DEFAULT_WIND = (3.0, 270.0)      # ASSUMPTION: m/s and FROM degrees, used only when no real wind is available


_NO_WIND = {}      # replay only: (lat, lon, hour) -> reason, so a missing wind is looked up once, not per zone


def _json_default(obj):
    if hasattr(obj, "item"):                       # numpy numbers
        return obj.item()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


WIND_GRID_DEG = 0.5      # winds are looked up on a 0.5 degree grid (about 55 km): far fewer requests
WIND_WORKERS = 8         # and the requests of one step run in parallel
WIND_CACHE_PATH = None   # set by scripts/serve_dashboard.py: winds of past dates are kept there, so a replay works offline
_cache_lock = threading.Lock()


def _snap(value):
    return round(value / WIND_GRID_DEG) * WIND_GRID_DEG


def _cache_key(lat, lon, when):
    return f"{lat:.2f},{lon:.2f},{str(when)[:13]}"


def _read_cache():
    try:
        return json.loads(Path(WIND_CACHE_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(cache):
    try:
        path = Path(WIND_CACHE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass                                              # the cache is a convenience, never a reason to fail


def compute_forecast(zones, vegetation, fixed_wind=None, when=None, problems=None):
    """Growth forecast of the active zones (needs the forecast package and, unless fixed_wind, internet).

    `when` is the time of the state (a replayed fire has the date of the fire, not today).
    If no wind can be found for that time and place, DEFAULT_WIND is used and the reason is added to `problems`."""
    from shapely.geometry import shape

    from findfire.forecast import wind as wind_mod
    from findfire.forecast.spread import forecast_zones
    active = [z for z in zones if z.get("status") != "inactive"
              and (z.get("new_hotspots") is None or z.get("new_hotspots") > 0)]      # still spreading
    if not active:
        return []
    if fixed_wind:
        wind_fn = lambda lat, lon: wind_mod.Wind(*fixed_wind)           # noqa: E731
    else:
        history = when is not None
        use_disk = history and WIND_CACHE_PATH is not None
        disk = _read_cache() if use_disk else {}
        found, failed, new_winds = {}, {}, {}                           # per forecast: cell -> Wind / reason

        def lookup(cell):
            if cell in found or cell in failed:
                return
            lat, lon = cell
            key = _cache_key(lat, lon, when)
            if use_disk and key in disk:
                found[cell] = wind_mod.Wind(disk[key]["speed_ms"], disk[key]["from_deg"])
            elif history and key in _NO_WIND:
                failed[cell] = _NO_WIND[key]
            else:
                try:
                    wind = wind_mod.cached_wind(lat, lon, when)
                except Exception as err:                                # noqa: BLE001
                    failed[cell] = (f"no wind for {when or 'now'} ({str(err)[:90]}): default wind "
                                    f"{DEFAULT_WIND[0]} m/s from {DEFAULT_WIND[1]:.0f} deg used")
                    if history:
                        _NO_WIND[key] = failed[cell]
                else:
                    found[cell] = wind
                    if use_disk:
                        new_winds[key] = dict(speed_ms=float(wind.speed_ms), from_deg=float(wind.from_deg))

        cells = set()
        for z in active:
            geom = z["geometry"] if hasattr(z["geometry"], "centroid") else shape(z["geometry"])
            cells.add((_snap(geom.centroid.y), _snap(geom.centroid.x)))
        with ThreadPoolExecutor(max_workers=WIND_WORKERS) as pool:
            list(pool.map(lookup, sorted(cells)))
        if new_winds:
            with _cache_lock:
                disk.update(new_winds)
                _write_cache(disk)

        def wind_fn(lat, lon):
            cell = (_snap(lat), _snap(lon))
            lookup(cell)                                                # normally already done above
            if cell in found:
                return found[cell]
            if problems is not None:
                problems.append(failed[cell])
            return wind_mod.Wind(*DEFAULT_WIND)
    return forecast_zones(active, wind_fn, vegetation)


class Dashboard:
    def __init__(self, state_path, stations_path, vegetation="shrub", fixed_wind=None, forecast=True):
        self.state_path, self.vegetation = Path(state_path), vegetation
        self.fixed_wind, self.forecast_on = fixed_wind, forecast
        self.stations = pd.read_csv(stations_path)
        self._mtime, self._payload, self._lock = None, None, threading.Lock()
        self._prev_area, self._prev_step = {}, None

    def payload(self) -> dict:
        with self._lock:
            if not self.state_path.exists():
                return dict(sample=False, replay=None, n_zones=0, inactive=0, cards=[], errors=[],
                            warnings=[f"state file not found: {self.state_path}. Waiting for data: start scripts/replay_to_state.py (replay) or scripts/run_live.py (live)."])
            mtime = self.state_path.stat().st_mtime
            if mtime == self._mtime and self._payload is not None:
                return self._payload
            try:
                state = load_state(self.state_path)
            except ValueError as err:                      # file being written: keep the last good payload
                old = self._payload or dict(sample=False, replay=None, n_zones=0, inactive=0, cards=[], errors=[],
                                            warnings=[])
                return dict(old, warnings=old.get("warnings", []) + [f"state file unreadable for now: {err}"])
            when = state.get("replay_time")
            warnings, forecast, problems = [], None, []
            if self.forecast_on:
                try:
                    forecast = compute_forecast(zones_from_state(state), self.vegetation, self.fixed_wind,
                                                when=when, problems=problems)
                except Exception as err:                   # noqa: BLE001 - the dashboard works without a forecast
                    warnings.append(f"forecast unavailable: {err}")
                warnings.extend(dict.fromkeys(problems))   # each message once
            payload = dashboard_payload(state, self.stations, forecast, warnings)
            payload["replay"] = (dict(time=when, step=state.get("step"), steps=state.get("steps"),
                                      event=state.get("event")) if state.get("replay") else None)
            step = state.get("step")
            if self._prev_step is not None and step is not None and step < self._prev_step:
                self._prev_area = {}                               # replay restarted
            areas = {}
            for c in payload["cards"]:
                areas[c["zone_id"]] = c["area_ha"]
                before = self._prev_area.get(c["zone_id"])
                c["area_change_ha"] = None if before is None else round(c["area_ha"] - before, 1)
            self._prev_area, self._prev_step = areas, step
            self._payload, self._mtime = payload, mtime
            return payload


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