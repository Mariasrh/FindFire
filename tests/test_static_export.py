import json

import numpy as np
import pandas as pd
from shapely.geometry import box

from findfire.dashboard.static_export import _clean, payloads_for, static_page, write_static_demo

STATIONS = "tests/data/sample_stations.csv"


def zone(zone_id, status, area_ha, bbox, new_hotspots=2):
    return dict(zone_id=zone_id, status=status, area_ha=np.float64(area_ha), perimeter_km=1.5, n_hotspots=3,
                frp_total_mw=7.5, first_detected=pd.Timestamp("2021-08-08T10:00:00Z"),
                last_detected=pd.Timestamp("2021-08-09T10:00:00Z"), new_hotspots=new_hotspots, geometry=box(*bbox))


def snaps():
    t0 = pd.Timestamp("2021-08-09T12:00:00Z")
    return [dict(time=t0, zones=[zone(1, "new", 15, (4.0, 36.7, 4.004, 36.704))]),
            dict(time=t0 + pd.Timedelta(hours=12), zones=[zone(1, "active", 30, (4.0, 36.7, 4.006, 36.706)),
                                                          zone(2, "new", 120, (4.1, 36.6, 4.11, 36.61))])]


def test_one_answer_per_step_after_an_empty_one(tmp_path):
    answers = payloads_for(snaps(), STATIONS, tmp_path, "test")
    assert [a["replay"]["step"] for a in answers] == [0, 1, 2]
    assert answers[0]["cards"] == [] and [c["zone_id"] for c in answers[2]["cards"]][0] in (1, 2)
    assert answers[2]["cards"][0]["area_change_ha"] is not None or answers[2]["cards"][1]["area_change_ha"] is not None
    json.dumps(answers, allow_nan=False)                     # valid JSON for a browser


def test_nan_becomes_null():
    assert _clean({"a": [float("nan"), 1.0, float("inf")]}) == {"a": [None, 1.0, None]}


def test_static_page_is_wired_to_steps_json():
    page = ('<head><link rel="icon" href="/logo.png"></head><body><img src="/logo.png">'
            '<section id="kpis"></section>\n<main></main><script>\nconst POLL_MS = 5000;\n</script></body>')
    out = static_page(page)
    assert 'fetch("steps.json")' in out and 'src="logo.png"' in out and 'href="logo.png"' in out
    assert out.index("steps.json") < out.index("const POLL_MS") and "Online demo" in out


def test_write_static_demo(tmp_path):
    out = write_static_demo(tmp_path / "docs" / "demo", [{"cards": []}], "<html></html>")
    assert (out / "index.html").exists() and json.loads((out / "steps.json").read_text()) == [{"cards": []}]
    assert (tmp_path / "docs" / ".nojekyll").exists()