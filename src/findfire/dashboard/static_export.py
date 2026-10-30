"""Online demo without a server: compute the dashboard answers of a replay in advance, so a static page
(GitHub Pages) can play them in any browser, with no Python and no key."""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from findfire.dashboard import server
from findfire.dashboard.replay_player import snapshot_to_state, write_state

STEP_MS = 8000
REPO_URL = "https://github.com/Mariasrh/FindFire"
NOTE = ('<div id="staticnote" style="margin:12px 22px 0;padding:10px 14px;border:1px solid rgba(0,229,240,.4);'
        'border-radius:10px;color:#9fb6c8;font-size:13px;line-height:1.5">Online demo: a replay of real satellite '
        'detections of the August 2021 Kabylie fires, computed by FindFire and played in your browser (one step = '
        '12 hours of the fire, shown every 8 seconds). Click "Enable sound" to hear the alerts. Live mode runs '
        'locally with free API keys: see the <a href="' + REPO_URL + '" style="color:#00e5f0">GitHub repository</a>.'
        '</div>\n')
SHIM = """<script>
// Static demo: the dashboard answers were computed in advance (steps.json). This stands in for the Python server.
(function () {
  var steps = null, i = 0;
  var ready = fetch("steps.json").then(function (r) { return r.json(); }).then(function (d) { steps = d; });
  setInterval(function () { if (steps) { i = (i + 1) % steps.length; } }, STEP_MS);
  var realFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    if (String(url).indexOf("/api/cards") === 0) {
      return ready.then(function () {
        return new Response(JSON.stringify(steps[i]), {headers: {"Content-Type": "application/json"}});
      });
    }
    return realFetch(url, opts);
  };
})();
</script>
""".replace("STEP_MS", str(STEP_MS))


def _clean(x):
    """JSON for browsers: NaN and infinity are not valid JSON, so they become null."""
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def payloads_for(snaps, stations_path, work_dir, event: str = "") -> list[dict]:
    """The dashboard answer for every replay step, after an empty first one (so the first zones raise alerts)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    state = work_dir / "static_state.json"
    total = len(snaps)
    first_time = snaps[0]["time"].isoformat() if snaps else ""
    write_state(state, {"replay": True, "replay_time": first_time, "step": 0, "steps": total,
                        "event": event, "zones": [], "alerts": []})
    dash = server.Dashboard(state, stations_path)
    answers = [dash.payload()]
    for i, snap in enumerate(snaps):
        write_state(state, snapshot_to_state(snap, i, total, event))
        dash._mtime = None                      # always rebuild, even if the file time did not change
        answers.append(dash.payload())
    state.unlink(missing_ok=True)
    return _clean(json.loads(json.dumps(answers, default=server._json_default)))


def static_page(html: str) -> str:
    """The dashboard page, wired to steps.json instead of the server."""
    html = html.replace("\r\n", "\n")
    html = html.replace('href="/logo.png"', 'href="logo.png"').replace('src="/logo.png"', 'src="logo.png"')
    anchor = "<script>\nconst POLL_MS"
    if html.count(anchor) != 1:
        raise ValueError("the dashboard page was not recognised")
    html = html.replace(anchor, SHIM + anchor)
    kpis = '<section id="kpis"></section>\n'
    html = html.replace(kpis, kpis + NOTE) if kpis in html else html.replace("<main", NOTE + "<main", 1)
    return html


def write_static_demo(out_dir, answers: list[dict], page_html: str, logo=None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page_html, encoding="utf-8")
    (out_dir / "steps.json").write_text(json.dumps(answers, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    if logo is not None and Path(logo).exists():
        shutil.copyfile(logo, out_dir / "logo.png")
    (out_dir.parent / ".nojekyll").write_text("", encoding="utf-8")     # GitHub Pages: serve files as they are
    return out_dir