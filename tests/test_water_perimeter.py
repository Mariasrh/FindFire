import pytest

from findfire.water.water_demand import compute_water_demand, water_for_forecast


def test_longer_perimeter_than_a_circle_gives_a_longer_front():
    circle = compute_water_demand(10, "forest")
    long_shape = compute_water_demand(10, "forest", perimeter_m=circle.perimeter_m * 1.5)
    assert long_shape.front_attacked_m > circle.front_attacked_m


def test_impossibly_short_perimeter_is_raised_to_the_circle():
    circle = compute_water_demand(10, "forest")
    short = compute_water_demand(10, "forest", perimeter_m=10)
    assert short.perimeter_m == circle.perimeter_m


def test_without_perimeter_nothing_changes():
    a = compute_water_demand(10, "forest")
    b = compute_water_demand(10, "forest", perimeter_m=None)
    assert a.flow_l_min == b.flow_l_min


def test_forecast_hook_returns_a_dict_with_the_keys():
    d = water_for_forecast(25.0, 2.1, wind_kmh=12.0)
    for key in ("flow_l_min", "volume_l", "severity", "front_attacked_m", "parameters_status"):
        assert key in d
    assert isinstance(d["flow_l_min"], float)


def test_forecast_hook_uses_kilometres():
    a = water_for_forecast(1.0, 0.5)
    b = compute_water_demand(1.0, "forest", perimeter_m=500.0)
    assert a["perimeter_m"] == b.perimeter_m


def test_negative_perimeter_rejected():
    with pytest.raises(ValueError):
        compute_water_demand(10, "forest", perimeter_m=-1)