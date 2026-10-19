import datetime as dt

import pandas as pd
import pytest

from findfire.live.events import fetch_period, replay_json
from findfire.live.replay import page
from conftest import T0, hs


def local_fire():
    d = pd.concat([hs([(x * 0.4, y * 0.4) for x in range(3) for y in range(3)], minutes=m) for m in (0, 720, 1440, 2160)],
                  ignore_index=True)
    d["frp"] = 5.0
    return d


def test_local_data_is_used_for_the_selected_days():
    d, notes = fetch_period(dt.date(2026, 10, 17), dt.date(2026, 10, 18), local_fire())
    assert len(d) == 36 and "local" in notes[0].lower()


def test_period_limits():
    with pytest.raises(ValueError):
        fetch_period(dt.date(2026, 1, 1), dt.date(2026, 3, 1), None)
    with pytest.raises(ValueError):
        fetch_period(dt.date(2026, 10, 19), dt.date(2026, 10, 17), None)


def test_replay_json_is_valid_json_with_steps_and_zones():
    import json
    out = replay_json(dt.date(2026, 10, 17), dt.date(2026, 10, 18), local_fire())
    json.dumps(out, allow_nan=False)
    assert len(out["steps"]) >= 3 and out["steps"][-1]["zones"] and out["notes"]


def test_page_embeds_events_and_works_without_data():
    html = page(None, [dict(name="x", start="2021-08-08", end="2021-08-14")])
    assert "2021-08-08" in html and "null ||" in html
