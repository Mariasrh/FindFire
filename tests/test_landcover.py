from datetime import date

import numpy as np
import pytest
from shapely.geometry import box

from findfire.landcover.worldcover import (DEFAULT_YEAR, LandCoverUnavailable, annotate_zones, base_url, summarise,
                                           tile_filename, tile_id, year_for, zone_land_cover)

PX = 0.0001                                                   # ~11 m, close to the real 10 m grid


def write_tile(folder, tile, west, north, array, year=DEFAULT_YEAR):
    """A tiny stand-in GeoTIFF (EPSG:4326) saved under the real WorldCover file name of `year`.
    Skips the calling test when rasterio is not installed (pip install -r requirements-landcover.txt)."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    h, w = array.shape
    with rasterio.open(folder / tile_filename(tile, year), "w", driver="GTiff", height=h, width=w, count=1, dtype="uint8",
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
    pytest.importorskip("rasterio")                           # the tile read itself needs rasterio
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


# ---------------------------------------------------------------- years
G = box(4.0, 36.0, 4.01, 36.01)


def test_2020_uses_v100_names_and_urls():
    assert tile_filename("N36E003", 2020) == "ESA_WorldCover_10m_2020_v100_N36E003_Map.tif"
    assert base_url(2020).endswith("/v100/2020/map")
    assert base_url(2021).endswith("/v200/2021/map")


def test_unknown_year_raises():
    with pytest.raises(ValueError):
        tile_filename("N36E003", 2019)
    with pytest.raises(ValueError):
        zone_land_cover(G, remote=False, year=2019)


def test_year_for_picks_the_map_before_the_fire():
    assert year_for(date(2021, 8, 8)) == 2020             # Kabylie validation
    assert year_for(date(2021, 1, 15)) == 2020
    assert year_for(date(2026, 10, 17)) == 2021           # live fires
    with pytest.raises(ValueError):
        year_for(date(2020, 7, 1))                        # no earlier map exists


def test_year_selects_the_matching_local_tile(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 10, "uint8"), year=2020)   # forest before the fire
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 60, "uint8"), year=2021)   # burn scar: bare
    r20 = zone_land_cover(G, tmp_path, remote=False, year=2020)
    r21 = zone_land_cover(G, tmp_path, remote=False, year=2021)
    assert (r20["label"], r20["fuel"], r20["year"]) == ("forest", "forest", 2020)
    assert (r21["label"], r21["year"]) == ("bare", 2021)
    assert "2020 v100" in r20["source"]


def test_missing_tile_of_the_other_year_raises(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 10, "uint8"), year=2021)
    with pytest.raises(LandCoverUnavailable):
        zone_land_cover(G, tmp_path, remote=False, year=2020)


def test_cache_does_not_mix_years(tmp_path):
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 10, "uint8"), year=2020)
    write_tile(tmp_path, "N36E003", 4.0, 36.01, np.full((100, 100), 60, "uint8"), year=2021)
    cache = tmp_path / "c.json"
    z20, z21 = [dict(zone_id=1, geometry=G)], [dict(zone_id=1, geometry=G)]
    annotate_zones(z20, tmp_path, remote=False, cache_file=cache, year=2020)
    annotate_zones(z21, tmp_path, remote=False, cache_file=cache, year=2021)
    assert z20[0]["land_cover"]["label"] == "forest" and z21[0]["land_cover"]["label"] == "bare"
    import json
    assert len(json.loads(cache.read_text())) == 2


def test_old_cache_entries_without_year_get_it_on_read(tmp_path):
    import json
    from findfire.landcover.worldcover import _key
    old = {k: v for k, v in summarise({10: 10}).items() if k != "year"}
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({_key(G, 2021): old}))
    z = [dict(zone_id=1, geometry=G)]
    annotate_zones(z, tmp_path, remote=False, cache_file=cache, year=2021)
    assert z[0]["land_cover"]["year"] == 2021