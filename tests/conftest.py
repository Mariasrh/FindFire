import numpy as np
import pandas as pd
import pytest

KM_LAT = 111.195
KM_LON = 111.195 * np.cos(np.radians(36.0))
T0 = pd.Timestamp("2026-10-17 01:00", tz="UTC")


def hs(points, size=0.375, sat="N20", minutes=0):
    """points: (east_km, north_km[, minutes]) around 36 N, 4 E. Pixel `size` in km (scalar or per point)."""
    rows = []
    for k, p in enumerate(points):
        e, n = p[0], p[1]
        m = p[2] if len(p) > 2 else minutes
        s = size[k] if np.ndim(size) else size
        rows.append(dict(latitude=36.0 + n / KM_LAT, longitude=4.0 + e / KM_LON, acq_dt=T0 + pd.Timedelta(minutes=m),
                         scan=s, track=s, satellite=sat, frp=1.0, confidence="n"))
    return pd.DataFrame(rows)


@pytest.fixture
def make():
    return hs
