import pandas as pd

from findfire.zones.tracking import run_tracking
from conftest import hs


def blob(x0, minutes, y0=0.0):
    return hs([(x0 + i * 0.4, y0 + j * 0.4) for i in range(3) for j in range(2)], minutes=minutes)


def ids(snap):
    return sorted(z["zone_id"] for z in snap["zones"])


def test_zone_keeps_its_id_and_only_grows():
    v = pd.concat([blob(0, 0), blob(1.0, 800), blob(2.0, 1600)], ignore_index=True)
    r = run_tracking(v)
    assert all(ids(s) == [1] for s in r["snaps"][1:] if s["zones"])
    areas = [s["zones"][0]["area_ha"] for s in r["snaps"] if s["zones"]]
    assert areas == sorted(areas) and areas[-1] > areas[0]


def test_two_fires_that_grow_together_merge_and_older_id_wins():
    v = pd.concat([blob(0, 0), blob(3.2, 400), blob(1.6, 800)], ignore_index=True)   # the third blob bridges the first two
    r = run_tracking(v)
    final = r["snaps"][-1]
    assert ids(final) == [1] and len(r["merges"]) == 1 and r["merges"][0][1:] == (2, 1)


def test_old_burn_scar_does_not_glue_to_a_new_fire():
    v = pd.concat([blob(0, 0), blob(1.8, 60 * 24 * 5)], ignore_index=True)          # 5 days later, 1.2 km away
    r = run_tracking(v, window=pd.Timedelta(days=7), link_dt=pd.Timedelta(hours=72))
    assert len(r["snaps"][-1]["zones"]) == 2


def test_lone_hotspot_creates_no_zone_and_hotspot_is_in_the_step():
    r = run_tracking(hs([(0, 0)]))
    assert all(not s["zones"] for s in r["snaps"]) and (r["snaps"][0]["hotspots"].zone_id == -1).all()


def test_two_satellites_one_flare_is_no_zone():
    v = pd.concat([hs([(0, 0)], sat="N20"), hs([(0.03, 0)], sat="SNPP", minutes=50)], ignore_index=True)
    assert all(not s["zones"] for s in run_tracking(v)["snaps"])
