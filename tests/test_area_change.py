import numpy as np
import pandas as pd
from shapely.geometry import box

from findfire.dashboard.replay_player import snapshot_to_state, write_state
from findfire.dashboard.server import Dashboard

STATIONS = "tests/data/sample_stations.csv"


def zone(zone_id, area_ha):
    return dict(zone_id=zone_id, status="active", area_ha=np.float64(area_ha), perimeter_km=1.5, n_hotspots=3,
                frp_total_mw=7.5, first_detected=pd.Timestamp("2021-08-08T10:00:00Z"),
                last_detected=pd.Timestamp("2021-08-09T10:00:00Z"), new_hotspots=2, geometry=box(4.0, 36.7, 4.004, 36.704))


def step(hours, area_ha):
    return dict(time=pd.Timestamp("2021-08-09T12:00:00Z") + pd.Timedelta(hours=hours), zones=[zone(1, area_ha)])


def test_the_area_change_since_the_last_update_is_reported(tmp_path):
    out = tmp_path / "s.json"
    dash = Dashboard(out, STATIONS, forecast=False)
    changes = []
    for i, (hours, area) in enumerate([(0, 100.0), (12, 160.5), (24, 160.5)]):
        write_state(out, snapshot_to_state(step(hours, area), i, 3))
        changes.append(dash.payload()["cards"][0]["area_change_ha"])
    assert changes == [None, 60.5, 0.0]


def test_a_restarted_replay_does_not_report_a_fake_change(tmp_path):
    out = tmp_path / "s.json"
    dash = Dashboard(out, STATIONS, forecast=False)
    write_state(out, snapshot_to_state(step(0, 100.0), 4, 14))
    dash.payload()
    write_state(out, snapshot_to_state(step(12, 5000.0), 0, 14))        # the replay starts again at step 1
    assert dash.payload()["cards"][0]["area_change_ha"] is None