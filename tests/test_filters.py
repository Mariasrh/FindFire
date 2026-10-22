import pandas as pd

from findfire.detection.filters import (apply_exclusions, assign_pass, build_static_mask, mark_redetections,
                                        persistence, vegetation_only)
from conftest import hs


def test_same_satellite_twelve_hours_later_is_not_a_duplicate():
    d = pd.concat([hs([(0, 0)], minutes=0), hs([(0, 0)], minutes=720)], ignore_index=True)
    assert list(mark_redetections(d)["dup_of"]) == [-1, -1]


def test_other_satellite_far_away_is_not_a_duplicate():
    d = pd.concat([hs([(0, 0)], sat="N20"), hs([(5, 0)], sat="SNPP", minutes=50)], ignore_index=True)
    assert list(mark_redetections(d)["dup_of"]) == [-1, -1]


def test_exclusion_circle_removes_hotspots_inside_only():
    d = hs([(0, 0), (30, 0)])
    z = pd.DataFrame([dict(name="refinery", latitude=d.latitude[0], longitude=d.longitude[0], radius_km=2.0)])
    assert list(apply_exclusions(d, z).index) == [1]


def test_static_mask_needs_many_distinct_days():
    rows = []
    for day in range(25):
        rows.append(hs([(0, 0)], minutes=day * 1440))
    rows.append(hs([(40, 0)], minutes=0))
    h = pd.concat(rows, ignore_index=True)
    m = build_static_mask(h, min_days=20)
    assert len(m) == 1 and m.days_seen[0] == 25


def test_persistence_counts_other_passes_only():
    d = pd.concat([hs([(0, 0)], sat="N20", minutes=0), hs([(0.2, 0)], sat="SNPP", minutes=50),
                   hs([(0, 0)], sat="N20", minutes=720), hs([(25, 25)], sat="N20", minutes=0)], ignore_index=True)
    p = persistence(d)
    assert list(p) == [2, 2, 2, 0]


def test_assign_pass_splits_on_gaps():
    d = pd.concat([hs([(0, 0, 0), (1, 0, 5)]), hs([(0, 0, 600)])], ignore_index=True)
    p = assign_pass(d)
    assert p[0] == p[1] != p[2]


def test_other_satellite_hours_later_is_not_a_duplicate():
    d = pd.concat([hs([(0, 0)], sat="N20", minutes=0), hs([(0, 0)], sat="SNPP", minutes=300)], ignore_index=True)
    assert list(mark_redetections(d)["dup_of"]) == [-1, -1]          # 5 h apart > 3 h window


def test_persistence_ignores_detections_outside_the_window():
    d = pd.concat([hs([(0, 0)], sat="N20", minutes=0), hs([(0, 0)], sat="SNPP", minutes=60 * 72)], ignore_index=True)
    assert list(persistence(d, window_h=48)) == [0, 0]


def test_vegetation_only_keeps_vegetation_and_drops_static_and_offshore():
    d = pd.DataFrame(dict(type=[0, 2, 1, 3, 0]))
    out = vegetation_only(d)
    assert list(out.index) == [0, 4]
    assert out.attrs["non_vegetation_dropped"] == 3


def test_vegetation_only_keeps_rows_with_unknown_type():
    d = pd.DataFrame(dict(type=[0, None, 2]))
    assert list(vegetation_only(d).index) == [0, 1]


def test_vegetation_only_is_a_noop_without_the_type_column():
    d = hs([(0, 0), (1, 0)])
    assert len(vegetation_only(d)) == 2
