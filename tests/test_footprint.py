import numpy as np
import pytest

from findfire.zones.footprint import alpha_shape, zone_footprint


def grid(n=3, step=0.4, lat0=36.0, lon0=4.0):
    ys, xs = np.meshgrid(np.arange(n) * step / 111.195, np.arange(n) * step / (111.195 * np.cos(np.radians(36))))
    return (lon0 + xs.ravel()), (lat0 + ys.ravel())


def test_edge_fraction_one_is_the_full_pixel_footprint():
    lon, lat = grid(); s = np.full(9, 0.4)
    _, a_alpha, _ = zone_footprint(lon, lat, s, s, "alpha", edge_fraction=1.0)
    _, a_boxes, _ = zone_footprint(lon, lat, s, s, "boxes")
    assert a_alpha == pytest.approx(a_boxes, rel=0.03) and a_boxes == pytest.approx(144, rel=0.03)


def test_smaller_edge_fraction_gives_a_tighter_footprint():
    lon, lat = grid(); s = np.full(9, 0.4)
    areas = [zone_footprint(lon, lat, s, s, "alpha", edge_fraction=e)[1] for e in (1.0, 0.5, 0.0)]
    assert areas[0] > areas[1] > areas[2] > 0


def test_sparse_tentacle_is_not_filled_by_alpha_but_is_by_closing():
    lon, lat = grid(4, 0.4)
    tl = [4.0 + (0.4 * 3 + 1.1 * k) / (111.195 * np.cos(np.radians(36))) for k in (1, 2, 3)]   # chain 1.1 km apart
    lon = np.r_[lon, tl]; lat = np.r_[lat, [36.0] * 3]; s = np.full(len(lon), 0.4)
    a_alpha = zone_footprint(lon, lat, s, s, "alpha", edge_fraction=1.0)[1]
    a_close = zone_footprint(lon, lat, s, s, "close", close_m=750)[1]
    assert a_alpha < a_close


def test_degenerate_inputs_do_not_crash():
    for n in (1, 2, 3):
        lon, lat = np.array([4.0, 4.005, 4.01])[:n], np.array([36.0] * 3)[:n]            # collinear / tiny
        geo, area, per = zone_footprint(lon, lat, np.full(n, 0.4), np.full(n, 0.4), "alpha")
        assert area > 0 and not geo.is_empty
    assert alpha_shape(np.zeros((2, 2)), 500).is_empty


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        zone_footprint([4.0], [36.0], [0.4], [0.4], "nope")
