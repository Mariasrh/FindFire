import numpy as np
import pandas as pd

from findfire.live.pipeline import build_state, latency_minutes
from findfire.live.store import Store
from conftest import T0, hs

NOW = T0 + pd.Timedelta(hours=20)


def mtg(points, minutes):
    if not points:
        return pd.DataFrame(columns=["latitude", "longitude", "acq_dt", "scan", "track", "confidence", "satellite", "source"])
    d = pd.concat([hs([p], size=2.0, sat="MTG-I1", minutes=m) for p, m in zip(points, minutes)], ignore_index=True)
    d["confidence"], d["source"] = "n", "MTG_FIR"
    return d


def fire(minutes=0):
    return hs([(x * 0.4, y * 0.4) for x in range(3) for y in range(3)], minutes=minutes)


def test_viirs_cluster_becomes_zone_with_area():
    zones, hot, alerts, through = build_state(fire(180), mtg([], []), NOW)
    assert len(zones) == 1 and zones[0]["area_ha"] > 5 and zones[0]["status"] in {"new", "active"}


def test_build_zones_ignores_non_vegetation_hotspots():
    zones, _, _, _ = build_state(fire(180).assign(type=2), mtg([], []), NOW)
    assert zones == []


def test_mtg_alert_confirmed_by_viirs_with_lead_time():
    m = mtg([(0.5, 0.5)] * 3, [0, 10, 20])
    _, _, alerts, _ = build_state(fire(180), m, NOW)
    a = alerts.iloc[0]
    assert len(alerts) == 1 and a.status == "confirmed" and abs(a.lead_time_min - 180) < 1 and a.zone_id == 0


def test_single_scan_is_not_an_alert():
    _, _, alerts, _ = build_state(fire(180), mtg([(0.5, 0.5)], [0]), NOW)
    assert alerts.empty


def test_pending_then_not_confirmed_depends_on_viirs_coverage():
    m = mtg([(40, 40)] * 3, [0, 10, 20])
    far = hs([(0, 0, 60)])
    _, _, a1, _ = build_state(far, m, NOW)                      # VIIRS data stops 1 h after the alert: window still open
    assert a1.iloc[0].status == "pending"
    far2 = pd.concat([far, hs([(0, 0, 14 * 60)])], ignore_index=True)
    _, _, a2, _ = build_state(far2, m, NOW)                     # VIIRS has data 14 h later and saw nothing there
    assert a2.iloc[0].status == "not_confirmed"


def test_no_viirs_at_all_leaves_alert_pending():
    _, _, a, _ = build_state(hs([]).reindex(columns=["latitude", "longitude", "acq_dt", "scan", "track", "satellite", "frp"]),
                             mtg([(1, 1)] * 2, [0, 10]), NOW)
    assert a.iloc[0].status == "pending"


def test_store_keeps_first_ingested_time_and_measures_latency(tmp_path):
    s = Store(tmp_path)
    d = hs([(0, 0)]); d["source"] = "X"
    assert s.add("viirs", d, now=T0 + pd.Timedelta(minutes=90)) == 1
    assert s.add("viirs", d, now=T0 + pd.Timedelta(minutes=200)) == 0          # duplicate: not new, time unchanged
    med, p90 = latency_minutes(s.load("viirs"))
    assert abs(med - 90) < 1e-6
