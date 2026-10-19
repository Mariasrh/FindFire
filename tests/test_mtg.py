import numpy as np
import pandas as pd
import pytest
import xarray as xr
from pyproj import Transformer
from pyresample.geometry import AreaDefinition

from findfire.ingestion.mtg import fire_classes, fire_pixels

GEOS = {"proj": "geos", "h": 35786400, "lon_0": 0, "a": 6378137, "rf": 298.257223563, "sweep": "y"}


def _raster(lonlats, values, size=1000):
    ext = 5.56e6
    area = AreaDefinition("t", "t", "t", GEOS, size, size, (-ext, -ext, ext, ext))
    xs, ys = area.get_proj_vectors()
    to_xy = Transformer.from_crs(4326, area.crs, always_xy=True).transform
    arr = np.zeros((size, size))
    for (lon, lat), v in zip(lonlats, values):
        x, y = to_xy(lon, lat)
        arr[np.argmin(abs(ys - y)), np.argmin(abs(xs - x))] = v
    return xr.DataArray(arr, dims=("y", "x"), attrs=dict(
        area=area, flag_values=[0, 1, 2], flag_meanings=["no_fire", "potential_fire", "fire"],
        start_time=pd.Timestamp("2026-10-17 12:00")))


def test_fire_classes_from_enum_names():
    assert fire_classes([0, 1, 2], ["no_fire", "potential_fire", "fire"]) == {1: "potential", 2: "fire"}
    with pytest.raises(ValueError):
        fire_classes([0], ["no_fire"])


def test_pixels_are_georeferenced_and_filtered_to_bbox():
    r = _raster([(4.0, 36.0), (6.5, 35.0), (-5.0, 20.0)], [2, 1, 2])      # last one is far outside the study box
    df = fire_pixels(r)
    assert len(df) == 2
    first = df.iloc[0]
    assert abs(first.longitude - 4.0) < 0.1 and abs(first.latitude - 36.0) < 0.1
    assert set(df.confidence) == {"fire", "potential"}
    assert df.acq_dt.iloc[0] == pd.Timestamp("2026-10-17 12:00", tz="UTC")
    assert (df.scan > 5).all()                                             # 11 km synthetic grid: footprint is measured, not assumed


def test_no_fire_gives_empty_table_with_columns():
    df = fire_pixels(_raster([], []))
    assert df.empty and "acq_dt" in df
