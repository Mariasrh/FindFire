import pandas as pd
import pytest
import requests

from findfire.forecast import wind as W


def payload(day="2021-08-10", speed=7.5, deg=250.0):
    times = [f"{day}T{h:02d}:00" for h in range(24)]
    return {"hourly": {"time": times, "wind_speed_10m": [speed] * 24, "wind_direction_10m": [deg] * 24}}


class Fake:
    """Stands in for requests.get: records every call, answers with a fixed payload (or one per asked day)."""
    def __init__(self, data=None, error=None, by_day=False):
        self.calls, self.data, self.error, self.by_day = [], data, error, by_day

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params)))
        if self.error:
            raise self.error
        fake = self
        data = payload(params["start_date"]) if self.by_day else self.data

        class R:
            def raise_for_status(self): pass
            def json(self): return data
        return R()


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    monkeypatch.setattr(W.time, "sleep", lambda s: None)          # no real waiting in the retry tests
    W._payload.cache_clear()
    yield
    W._payload.cache_clear()


def test_old_fire_uses_the_archive_for_that_day(monkeypatch):
    fake = Fake(payload("2021-08-10"))
    monkeypatch.setattr(W.requests, "get", fake)
    w = W.fetch_wind(36.7, 4.5, pd.Timestamp("2021-08-10 14:20", tz="UTC"))
    url, params = fake.calls[0]
    assert url == W.ARCHIVE_URL
    assert params["start_date"] == params["end_date"] == "2021-08-10"
    assert "past_days" not in params
    assert params["wind_speed_unit"] == "ms" and params["hourly"] == "wind_speed_10m,wind_direction_10m"
    assert (w.speed_ms, w.from_deg, w.source) == (7.5, 250.0, "open-meteo")


def test_a_few_days_ago_uses_the_forecast_api_with_past_days(monkeypatch):
    when = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=3)
    day = when.strftime("%Y-%m-%d")
    fake = Fake(payload(day))
    monkeypatch.setattr(W.requests, "get", fake)
    W.fetch_wind(36.7, 4.5, when)
    url, params = fake.calls[0]
    assert url == W.URL
    assert params["past_days"] == 3                      # calendar days back; the answer also holds today
    assert "start_date" not in params


def test_now_uses_the_forecast_api_without_past_days(monkeypatch):
    now = pd.Timestamp.now(tz="UTC")
    fake = Fake(payload(now.strftime("%Y-%m-%d")))
    monkeypatch.setattr(W.requests, "get", fake)
    W.fetch_wind(36.7, 4.5)
    assert fake.calls[0][0] == W.URL and "past_days" not in fake.calls[0][1]


def test_past_days_never_exceeds_the_open_meteo_limit(monkeypatch):
    when = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=W.RECENT_DAYS - 1)
    fake = Fake(payload(when.strftime("%Y-%m-%d")))
    monkeypatch.setattr(W.requests, "get", fake)
    W.fetch_wind(36.7, 4.5, when)
    assert fake.calls[0][1]["past_days"] <= W.MAX_PAST_DAYS


def test_zones_in_the_same_cell_and_day_share_one_request(monkeypatch):
    fake = Fake(by_day=True)
    monkeypatch.setattr(W.requests, "get", fake)
    a = W.cached_wind(36.71, 4.52, pd.Timestamp("2021-08-10 06:00", tz="UTC"))
    b = W.cached_wind(36.74, 4.48, pd.Timestamp("2021-08-10 18:00", tz="UTC"))     # same 0.1 degree cell, same day
    assert len(fake.calls) == 1 and a == b
    W.cached_wind(36.71, 4.52, pd.Timestamp("2021-08-11 06:00", tz="UTC"))         # another day -> a new request
    assert len(fake.calls) == 2


def test_wind_or_default_is_calm_and_marked_when_offline(monkeypatch):
    monkeypatch.setattr(W.requests, "get", Fake(error=requests.ConnectionError("offline")))
    w = W.wind_or_default(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    assert w.source == "default" and w.speed_ms == 0.0


def test_wind_or_default_also_covers_a_bad_answer(monkeypatch):
    monkeypatch.setattr(W.requests, "get", Fake({"hourly": {"time": [], "wind_speed_10m": [], "wind_direction_10m": []}}))
    assert W.wind_or_default(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC")).source == "default"


def test_wind_or_default_passes_real_data_through(monkeypatch):
    monkeypatch.setattr(W.requests, "get", Fake(payload("2021-08-10", 5.0, 90.0)))
    w = W.wind_or_default(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    assert (w.speed_ms, w.from_deg, w.source) == (5.0, 90.0, "open-meteo")


def test_a_wind_for_the_wrong_day_is_refused_not_used(monkeypatch):
    monkeypatch.setattr(W.requests, "get", Fake(payload("2021-08-11")))             # answer is for another day
    with pytest.raises(ValueError):
        W.fetch_wind(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))


class Flaky:
    """First `fails` calls raise `error`, then answers with `data`."""
    def __init__(self, error, fails, data):
        self.error, self.fails, self.data, self.n = error, fails, data, 0

    def __call__(self, url, params=None, timeout=None):
        self.n += 1
        if self.n <= self.fails:
            raise self.error
        data = self.data

        class R:
            def raise_for_status(self): pass
            def json(self): return data
        return R()


def test_a_slow_answer_is_retried_then_used(monkeypatch):
    flaky = Flaky(requests.ReadTimeout("slow"), 2, payload("2021-08-10", 4.0, 100.0))
    monkeypatch.setattr(W.requests, "get", flaky)
    w = W.fetch_wind(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    assert flaky.n == 3 and (w.speed_ms, w.from_deg) == (4.0, 100.0)


def test_it_gives_up_after_the_retries_and_raises(monkeypatch):
    flaky = Flaky(requests.ReadTimeout("slow"), 99, None)
    monkeypatch.setattr(W.requests, "get", flaky)
    with pytest.raises(requests.ReadTimeout):
        W.fetch_wind(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    assert flaky.n == W.RETRIES


def test_a_client_error_is_not_retried(monkeypatch):
    class Resp: status_code = 400
    bad = Flaky(requests.HTTPError("bad request", response=Resp()), 99, None)
    monkeypatch.setattr(W.requests, "get", bad)
    with pytest.raises(requests.HTTPError):
        W.fetch_wind(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC"))
    assert bad.n == 1


def test_rate_limit_is_retried(monkeypatch):
    class Resp: status_code = 429
    flaky = Flaky(requests.HTTPError("too many", response=Resp()), 1, payload("2021-08-10"))
    monkeypatch.setattr(W.requests, "get", flaky)
    assert W.fetch_wind(36.7, 4.5, pd.Timestamp("2021-08-10 12:00", tz="UTC")).source == "open-meteo"
    assert flaky.n == 2
