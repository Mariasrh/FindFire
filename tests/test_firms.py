import pandas as pd

from findfire.ingestion.firms import prepare


def raw(types):
    n = len(types)
    return pd.DataFrame(dict(latitude=[35.0 + i / 10 for i in range(n)], longitude=[4.0] * n,
                             acq_date=["2021-08-08"] * n, acq_time=[1200] * n, confidence=["n"] * n, type=types))


def test_prepare_drops_non_vegetation_rows_and_reports_the_count():
    out = prepare(raw([0, 2, 3]), vegetation=True)
    assert len(out) == 1 and out.attrs["non_vegetation_dropped"] == 2


def test_prepare_can_keep_non_vegetation_rows():
    assert len(prepare(raw([0, 2, 3]), vegetation=False)) == 3


def test_prepare_without_the_type_column_is_unaffected():
    assert len(prepare(raw([0, 2]).drop(columns=["type"]), vegetation=True)) == 2
