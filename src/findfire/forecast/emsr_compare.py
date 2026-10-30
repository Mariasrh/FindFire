"""Compare the forecast model with the real growth of a fire mapped from optical satellites (Copernicus EMSR533, Kabylie 2021).

Idea: start from the burned area mapped on one date, grow it with the model for the time until the next mapping, and
compare with the area really mapped then. For each period we also solve for the single "rate factor" (multiplier of the
base spread rate) that would make the model match. If that factor changes a lot from the peak of the fire to its end,
one fixed speed cannot fit the whole fire: the model has no fading in time.

LIMITS: the whole mapped area is treated as ONE zone (a circle of the same area) although it may be several fires that
merged; the wind is one value per period at one point; the circle grows from its whole edge (see docs/forecast.md).
"""
from __future__ import annotations

import re

import pandas as pd

from findfire.forecast import spread
from findfire.forecast.wind import Wind

# a table row like:  | **Monit01** | SPOT 7 | **2021-08-13 10:27** | **53,094.0 ha** | ...
ROW = re.compile(r"\*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\*\*\s*\|\s*\*\*([\d,]+(?:\.\d+)?) ha\*\*")


def parse_table(text: str) -> pd.DataFrame:
    """Dates (UTC) and burned areas (ha) from the markdown table of docs/emsr533_burned_area.md (sorted by date)."""
    rows = [(pd.Timestamp(t, tz="UTC"), float(a.replace(",", ""))) for t, a in ROW.findall(text)]
    if len(rows) < 2:
        raise ValueError("fewer than 2 dated burned areas found in the table")
    return pd.DataFrame(rows, columns=["time", "area_ha"]).sort_values("time").reset_index(drop=True)


def predicted_area(area_ha: float, wind: Wind, hours: float, vegetation: str = "shrub", factor: float = 1.0) -> float:
    """Model area after `hours`. `factor` multiplies the base spread rate (1 = the placeholder rates).
    The rates are scaled in place and restored, so this works with or without the optional fuel factor of spread.grow."""
    original = dict(spread.BASE_ROS_M_MIN)
    try:
        for k in original:
            spread.BASE_ROS_M_MIN[k] = original[k] * factor
        return spread.grow(area_ha, wind, vegetation, hours * 60.0)["area_ha"]
    finally:
        spread.BASE_ROS_M_MIN.update(original)


def implied_factor(area_ha: float, observed_ha: float, wind: Wind, hours: float, vegetation: str = "shrub") -> float:
    """The rate factor for which the model reproduces `observed_ha`. 0 if the area did not grow; inf if even x1000 is too slow.
    Bisection: the predicted area increases with the factor."""
    if observed_ha <= area_ha:
        return 0.0
    lo, hi = 0.0, 1000.0
    if predicted_area(area_ha, wind, hours, vegetation, hi) < observed_ha:
        return float("inf")
    for _ in range(80):
        mid = (lo + hi) / 2
        if predicted_area(area_ha, wind, hours, vegetation, mid) < observed_ha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def compare(table: pd.DataFrame, wind_fn, vegetation: str = "shrub", factors=(1.0, 0.2, 0.1)) -> pd.DataFrame:
    """One row per period between two mappings. `wind_fn(time) -> Wind` is asked for the start of the period."""
    out = []
    for (t0, a0), (t1, a1) in zip(table.itertuples(index=False), table.iloc[1:].itertuples(index=False)):
        hours = (t1 - t0) / pd.Timedelta(hours=1)
        wind = wind_fn(t0)
        row = dict(start=t0, end=t1, hours=hours, area_start_ha=a0, area_end_ha=a1, observed_ha_per_h=(a1 - a0) / hours,
                   wind_ms=wind.speed_ms, wind_from_deg=wind.from_deg, wind_source=wind.source)
        for f in factors:
            row[f"model_x{f:g}_ha_per_h"] = (predicted_area(a0, wind, hours, vegetation, f) - a0) / hours
        row["implied_factor"] = implied_factor(a0, a1, wind, hours, vegetation)
        out.append(row)
    df = pd.DataFrame(out)
    # ADAPTIVE rate: forecast each period with the factor the PREVIOUS period needed (what is known when the forecast is made).
    # The first period has no previous one, so it gets no adaptive forecast.
    prev = df["implied_factor"].shift(1)
    df["adaptive_factor"] = prev.where((prev > 0) & (prev < float("inf")))
    df["model_adaptive_ha_per_h"] = [
        (predicted_area(r.area_start_ha, Wind(r.wind_ms, r.wind_from_deg), r.hours, vegetation, r.adaptive_factor) - r.area_start_ha) / r.hours
        if pd.notna(r.adaptive_factor) else float("nan") for r in df.itertuples()]
    return df


def typical_error(predicted, observed) -> float:
    """Geometric mean of how far off the predictions are, as a factor (1.0 = perfect, 2.0 = on average twice too high or too low)."""
    import numpy as np
    p, o = np.asarray(predicted, float), np.asarray(observed, float)
    m = (p > 0) & (o > 0)
    if not m.any():
        return float("nan")
    r = p[m] / o[m]
    return float(np.exp(np.mean(np.abs(np.log(r)))))
