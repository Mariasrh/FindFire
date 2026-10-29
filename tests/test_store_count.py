import pandas as pd

from findfire.live.store import KEY, Store


def rows(times, start=0):
    data = []
    for i, t in enumerate(times):
        r = {k: float(start + i) for k in KEY if k != "acq_dt"}
        r["acq_dt"] = t
        data.append(r)
    return pd.DataFrame(data)


def test_add_counts_only_new_rows_even_when_old_rows_expire(tmp_path):
    st = Store(tmp_path)
    now = pd.Timestamp("2026-10-29T12:00:00Z")
    old_t = now - st.keep + pd.Timedelta(hours=1)               # inside the window at first
    assert st.add("viirs", rows([old_t] * 5), now=now) == 5
    later = now + pd.Timedelta(hours=2)                         # those 5 rows are now too old and are dropped
    assert st.add("viirs", rows([later] * 2, start=100), now=later) == 2
    assert st.add("viirs", rows([later] * 2, start=100), now=later) == 0    # duplicates are not new
    assert len(st.load("viirs")) == 2 and "_new" not in st.load("viirs").columns