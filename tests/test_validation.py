import numpy as np
import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import box

from findfire.ingestion.emsr import load_product
from findfire.validation import compare, step_for, zones_at

CRS = 32631


def square(x, y, side=10_000):
    return box(x, y, x + side, y + side)


def gdf(geom, crs=CRS):
    return gpd.GeoDataFrame(geometry=[geom], crs=crs)


def test_compare_recall_precision_iou_on_half_overlap():
    ref = gdf(square(0, 0))                                  # 10 km square = 10 000 ha
    aoi = gdf(square(-5_000, -5_000, 20_000))
    zones = gdf(square(5_000, 0))                            # shifted half a side to the east
    m = compare(ref, aoi, zones)
    assert m["ref_ha"] == pytest.approx(10_000, rel=0.01)
    assert m["zones_ha"] == pytest.approx(10_000, rel=0.01)
    assert m["recall"] == pytest.approx(0.5, abs=0.01)
    assert m["precision"] == pytest.approx(0.5, abs=0.01)
    assert m["iou"] == pytest.approx(1 / 3, abs=0.01)


def test_compare_clips_both_to_the_area_of_interest():
    ref = gdf(square(0, 0))
    aoi = gdf(square(0, 0, 5_000))                           # only the south-west quarter of the reference
    zones = gdf(square(0, 0, 5_000))
    m = compare(ref, aoi, zones)
    assert m["ref_ha"] == pytest.approx(2_500, rel=0.01)
    assert m["recall"] == m["precision"] == m["iou"] == pytest.approx(1.0, abs=0.01)


def test_compare_without_zones_has_no_precision():
    m = compare(gdf(square(0, 0)), gdf(square(-5_000, -5_000, 20_000)),
                gpd.GeoDataFrame(geometry=[], crs=CRS))
    assert m["recall"] == 0.0 and m["iou"] == 0.0
    assert np.isnan(m["precision"])


def test_step_for_takes_the_first_step_at_or_after_the_observation():
    steps = list(pd.to_datetime(["2021-08-12 00:00", "2021-08-12 12:00", "2021-08-13 00:00"], utc=True))
    assert step_for(pd.Timestamp("2021-08-12 10:40", tz="UTC"), steps) == steps[1]
    assert step_for(pd.Timestamp("2021-08-13 06:00", tz="UTC"), steps) == steps[2]
    assert step_for(pd.Timestamp("2021-08-20 00:00", tz="UTC"), steps) == steps[2]   # later than all -> last step


def test_zones_at_builds_a_lonlat_geodataframe_for_the_step():
    t = pd.Timestamp("2021-08-12 12:00", tz="UTC")
    snaps = [dict(time=t - pd.Timedelta(hours=12), zones=[]),
             dict(time=t, zones=[dict(zone_id=1, status="active", area_ha=12.5, geometry=box(4.0, 36.0, 4.1, 36.1))])]
    z = zones_at(snaps, t)
    assert z.crs.to_epsg() == 4326 and len(z) == 1
    assert z.zone_id.iloc[0] == 1 and z.area_ha.iloc[0] == 12.5


def test_zones_at_drops_zones_below_the_minimum_area():
    t = pd.Timestamp("2021-08-12 12:00", tz="UTC")
    snaps = [dict(time=t, zones=[
        dict(zone_id=1, status="active", area_ha=5.0, geometry=box(4.0, 36.0, 4.01, 36.01)),
        dict(zone_id=2, status="active", area_ha=50.0, geometry=box(4.0, 36.0, 4.1, 36.1)),
    ])]
    assert len(zones_at(snaps, t, min_zone_ha=10)) == 1
    assert zones_at(snaps, t, min_zone_ha=10).zone_id.iloc[0] == 2
    assert len(zones_at(snaps, t, min_zone_ha=50)) == 1          # >= keeps the zone on the threshold
    assert zones_at(snaps, t).zone_id.tolist() == [1, 2]


def test_load_product_reports_a_missing_product_folder():
    with pytest.raises(FileNotFoundError):
        load_product("no_such_product")
