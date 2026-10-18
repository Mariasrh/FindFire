"""Local replay server: pick a start and end date in the page, it loads that event and replays it.

    python scripts/serve_replay.py                       # then open http://127.0.0.1:8765
    python scripts/serve_replay.py --csv data/raw/firms_algeria.csv   # offline demo from a saved CSV
Needs FIRMS_MAP_KEY for periods that are not in a local file. Downloads are cached in data/archive/.
Add your own events (e.g. the CEMS activations) to data/events.json.
"""
import argparse
import datetime as dt
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from findfire.ingestion import firms
from findfire.live.events import load_events, replay_json
from findfire.live.replay import page

LOCAL = None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        b = body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, page(None, load_events(), "FindFire replay"), "text/html; charset=utf-8")
        if u.path == "/api/replay":
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                out = replay_json(dt.date.fromisoformat(q["start"]), dt.date.fromisoformat(q["end"]), LOCAL,
                                  int(q.get("min_neighbors", 1)), q.get("footprint", "alpha"), float(q.get("edge", 0.5)))
                return self._send(200, json.dumps(out, allow_nan=False), "application/json")
            except Exception as exc:
                return self._send(200, json.dumps({"error": f"{type(exc).__name__}: {exc}"}), "application/json")
        self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--csv"); ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    if a.csv:
        LOCAL = firms.load_csv(a.csv)
    print(f"Replay on http://127.0.0.1:{a.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
