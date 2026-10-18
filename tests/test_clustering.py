import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from findfire.detection.filters import mark_redetections
from findfire.zones.clustering import cluster_hotspots
from conftest import hs


def old_dbscan(df, eps_m=1500):
    """The notebook's clustering, for comparison."""
    return DBSCAN(eps=eps_m / 6371008.8, min_samples=1, metric="haversine", algorithm="ball_tree").fit_predict(
        np.radians(df[["latitude", "longitude"]].to_numpy()))


def test_compact_fire_is_one_cluster_and_far_fire_is_another():
    a = [(x * 0.4, y * 0.4) for x in range(4) for y in range(4)]
    b = [(30 + x * 0.4, y * 0.4) for x in range(3) for y in range(3)]
    lab = cluster_hotspots(hs(a + b))
    assert len(set(lab[:16])) == 1 and len(set(lab[16:])) == 1 and lab[0] != lab[16] and (lab >= 0).all()


def test_lone_hotspot_is_noise():
    assert list(cluster_hotspots(hs([(0, 0)]))) == [-1]


def test_swath_edge_fire_with_gaps_stays_one_zone_but_old_dbscan_splits_it():
    pts = [(i * 1.6, 0) for i in range(5)]                 # every second 0.8 km pixel detected
    d = hs(pts, size=0.8)
    assert len(set(cluster_hotspots(d))) == 1
    assert len(set(old_dbscan(d))) == 5                    # 1.6 km centre spacing > eps 1.5 km


def test_pixel_size_scales_the_link_distance():
    near = hs([(0, 0), (1.0, 0)], size=0.375)              # gap 0.625 km
    assert (cluster_hotspots(near) == 0).all()
    far = hs([(0, 0), (2.0, 0)], size=0.375)               # gap 1.625 km
    assert (cluster_hotspots(far) == -1).all()
    big = hs([(0, 0), (2.0, 0)], size=2.0)                 # MTG-size pixels touching: always linked
    assert (cluster_hotspots(big) == 0).all()


def test_stray_chain_merges_fires_by_default_but_core_rule_cuts_it():
    A = [(x * 0.4, y * 0.4) for x in range(3) for y in range(3)]            # 0 .. 0.8 km
    B = [(4.8 + x * 0.4, y * 0.4) for x in range(3) for y in range(3)]      # 4.8 .. 5.6 km
    chain = [(1.7, 0.4), (2.4, 0.4), (3.1, 0.4), (3.8, 0.4)]               # spacing 0.7 km
    d = hs(A + B + chain)
    assert len(set(cluster_hotspots(d, min_neighbors=1))) == 1
    lab = cluster_hotspots(d, min_neighbors=3)
    assert len(set(lab[lab >= 0])) == 2 and lab[0] != lab[9]


def test_two_satellites_seeing_one_flare_do_not_make_a_zone():
    d = pd.concat([hs([(0, 0)], sat="N20", minutes=0), hs([(0.05, 0.02)], sat="SNPP", minutes=50)], ignore_index=True)
    d = mark_redetections(d)
    assert list(d["dup_of"]) == [-1, 0]
    assert (cluster_hotspots(d) == -1).all()
    assert len(set(old_dbscan(d))) == 1                    # the notebook would have called this a 2-hotspot zone


def test_redetections_inherit_the_label_of_their_pixel():
    pts = [(x * 0.4, 0) for x in range(4)]
    d = pd.concat([hs(pts, sat="N20"), hs([(0.02, 0.01)], sat="SNPP", minutes=50)], ignore_index=True)
    lab = cluster_hotspots(mark_redetections(d))
    assert lab[4] == lab[0] >= 0


def test_time_window_separates_old_and_new_detections():
    d = hs([(0, 0, 0), (0.4, 0, 5), (0.8, 0, 600), (1.2, 0, 605)])
    assert len(set(cluster_hotspots(d))) == 1
    lab = cluster_hotspots(d, max_dt=pd.Timedelta(hours=1))
    assert lab[0] == lab[1] != lab[2] == lab[3]


def test_empty_input():
    assert len(cluster_hotspots(hs([]).reindex(columns=["latitude", "longitude", "acq_dt", "scan", "track"]))) == 0
