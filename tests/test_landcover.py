import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from findfire.landcover.worldcover import (LandCoverUnavailable, annotate_zones, summarise, tile_filename, tile_id, zone_land_cover)

PX = 0.0001                                                   # ~11 m, close to the real 10 m grid


def write_tile(folder, tile, west, north, array):
    """A tiny stand-in GeoTIFF (EPSG:4326) saved under the real WorldCover file name."""
    h, w = array.shape
    with rasterio.open(folder / tile_filename(tile), "w", driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                       crs="EPSG:4326", transform=from_origin(west, north, PX, PX)) as dst:
        dst.write(array.astype("uint8"), 1)


def stripes(parts, size=100):
    """size x size raster with vertical stripes: parts = [(class, columns), ...]"""
    a = np.zeros((size, size), "uint8"); c = 0
    for code, n in parts:
        a[:, c:c + n] = code; c += n
    return a


def test_tile_ids_follow_the_worldcover_scheme():
    assert tile_id(36.5, 4.2) == "N36E003" and tile_id(36.5, 6.0) == "N36E006"
    assert tile_id(35.8, -1.2) == "N33W003" and tile_id(36.0, -0.1) == "N36W003"
    assert tile_id(-47.0, 36.5) == "S48E036"                  # the example file name in the product manual
    assert tile_filename("S48E036") == "ESA_WorldCover_10m_2021_v200_S48E036_Map.tif"


def test_shares_label_fuel_and_majority(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, stripes([(10, 60), (20, 30), (40, 10)]))
    r = zone_land_cover(box(4.0, 36.0, 4.01, 36.01), tmp_path, remote=False)
    assert r["label"] == "forest" and r["fuel"] == "forest" and r["majority"] is True
    assert r["shares"] == pytest.approx({"crop": 0.1, "forest": 0.6, "scrub": 0.3}, abs=0.02)
    assert r["classes"]["tree cover"] == pytest.approx(0.6, abs=0.02) and r["n_pixels"] > 9000


def test_a_mixed_zone_is_reported_as_mixed_not_forced_to_forest(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, stripes([(10, 40), (20, 35), (40, 25)]))
    r = zone_land_cover(box(4.0, 36.0, 4.01, 36.01), tmp_path, remote=False)
    assert r["label"] == "forest" and r["majority"] is False and r["dominant_share"] == pytest.approx(0.4, abs=0.02)


def test_scrub_and_grass_give_the_forecast_fuel_and_crops_give_none(tmp_path):
    for code, label, fuel in [(20, "scrub", "shrub"), (30, "grass", "grass"), (40, "crop", None), (80, "other", None)]:
        write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), code, "uint8"))
        r = zone_land_cover(box(4.0, 36.0, 4.01, 36.01), tmp_path, remote=False)
        assert (r["label"], r["fuel"]) == (label, fuel)


def test_a_zone_across_a_tile_boundary_combines_both_tiles(tmp_path):
    write_tile(tmp_path, "N36E000", 2.995, 36.005, np.full((50, 50), 10, "uint8"))      # west of lon 3.0: forest
    write_tile(tmp_path, "N36E003", 3.0, 36.005, np.full((50, 50), 40, "uint8"))        # east of lon 3.0: crop
    r = zone_land_cover(box(2.995, 36.0, 3.005, 36.005), tmp_path, remote=False)
    assert r["shares"] == pytest.approx({"forest": 0.5, "crop": 0.5}, abs=0.03)


def test_missing_tile_raises_instead_of_guessing(tmp_path):
    with pytest.raises(LandCoverUnavailable):
        zone_land_cover(box(4.0, 36.0, 4.01, 36.01), tmp_path, remote=False)


def test_zone_outside_the_data_raises(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 10, "uint8"))
    with pytest.raises(LandCoverUnavailable):
        zone_land_cover(box(5.0, 36.5, 5.01, 36.51), tmp_path, remote=False)


def test_annotate_zones_marks_unavailable_ones_with_null_and_never_forest(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 10, "uint8"))
    zones = [dict(zone_id=1, geometry=box(4.0, 36.0, 4.01, 36.01)), dict(zone_id=2, geometry=box(5.0, 36.5, 5.01, 36.51))]
    annotate_zones(zones, tmp_path, remote=False, cache_file=tmp_path / "c.json")
    assert zones[0]["land_cover"]["label"] == "forest"
    assert zones[1]["land_cover"] is None and "land_cover_error" in zones[1]


def test_results_are_cached_by_footprint(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 20, "uint8"))
    z = [dict(zone_id=1, geometry=box(4.0, 36.0, 4.01, 36.01))]
    cache = tmp_path / "c.json"
    annotate_zones(z, tmp_path, remote=False, cache_file=cache)
    (tmp_path / tile_filename("N36E003")).unlink()                       # the tile is gone: the cache must answer
    z2 = [dict(zone_id=9, geometry=box(4.0, 36.0, 4.01, 36.01))]
    annotate_zones(z2, tmp_path, remote=False, cache_file=cache)
    assert z2[0]["land_cover"]["label"] == "scrub"


def test_summarise_ignores_nodata_and_unknown_codes():
    r = summarise({0: 500, 10: 30, 40: 10, 7: 99})
    assert r["n_pixels"] == 40 and r["shares"]["forest"] == pytest.approx(0.75)
    with pytest.raises(LandCoverUnavailable):
        summarise({0: 10})
