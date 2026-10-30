"""Compare the forecast model with the real growth of the Kabylie fire (Copernicus EMSR533, optical burned areas).

    python scripts/compare_emsr533.py --table docs/emsr533_burned_area.md            # wind of each date from Open-Meteo (archive)
    python scripts/compare_emsr533.py --table docs/emsr533_burned_area.md --wind 6 90 # fixed wind (6 m/s from the east), no internet

For every period between two mappings it starts from the area mapped at the start, grows it with the model for the time to the
next mapping, and prints the real and the modelled growth in ha per hour. The last column is the single rate factor that would
make the model match that period: if it changes a lot between the peak and the end of the fire, one fixed speed cannot fit.
"""
import argparse
from pathlib import Path

import pandas as pd

from findfire.forecast.emsr_compare import compare, parse_table, typical_error
from findfire.forecast.spread import BASE_ROS_M_MIN
from findfire.forecast.wind import Wind, cached_wind

ap = argparse.ArgumentParser()
ap.add_argument("--table", default="docs/emsr533_burned_area.md", help="markdown table of burned areas by date (Anes, EMSR533)")
ap.add_argument("--lat", type=float, default=36.65, help="where to take the wind (APPROXIMATE point in the fire area: replace with the centroid of the EMSR533 area)")
ap.add_argument("--lon", type=float, default=4.2)
ap.add_argument("--wind", nargs=2, type=float, metavar=("SPEED_MS", "FROM_DEG"), help="fixed wind instead of Open-Meteo")
ap.add_argument("--vegetation", default="shrub", choices=sorted(BASE_ROS_M_MIN))
ap.add_argument("--factors", nargs="+", type=float, default=[1.0, 0.2, 0.1])
a = ap.parse_args()

table = parse_table(Path(a.table).read_text(encoding="utf-8"))
wind_fn = (lambda t: Wind(*a.wind, source="fixed")) if a.wind else (lambda t: cached_wind(a.lat, a.lon, t))
res = compare(table, wind_fn, a.vegetation, tuple(a.factors))

cols = [f"model_x{f:g}_ha_per_h" for f in a.factors]
show = res[["start", "end", "area_start_ha", "observed_ha_per_h", *cols, "implied_factor", "wind_ms", "wind_source"]].copy()
show["start"] = show["start"].dt.strftime("%d %b %H:%M")
show["end"] = show["end"].dt.strftime("%d %b %H:%M")
print(show.round(2).to_string(index=False))
grew = res[res.implied_factor > 0]
if len(grew) > 1:
    lo, hi = grew.implied_factor.min(), grew.implied_factor.max()
    print(f"\nRate factor needed to match each period: {lo:.3f} to {hi:.3f} (a factor of {hi / lo:.1f} between the largest and the smallest).")
    print("If that range is wide, one fixed speed cannot fit both the peak and the end of the fire: the model has no fading in time.")

# ADAPTIVE rate: each period is forecast with the factor the previous period needed. Compared on the same periods as fixed factors.
ad = res.dropna(subset=["model_adaptive_ha_per_h"])
if len(ad):
    print("\nADAPTIVE rate (factor of the previous period) against fixed factors, periods where it can be used:")
    print(f"{'period':>24} {'real ha/h':>10} {'adaptive':>10} " + " ".join(f"{'x' + format(f, 'g'):>10}" for f in a.factors))
    for r in ad.itertuples():
        fixed = " ".join(f"{getattr(r, f'model_x{f:g}_ha_per_h'.replace('.', '_')) if False else res.loc[r.Index, f'model_x{f:g}_ha_per_h']:>10.1f}" for f in a.factors)
        print(f"{r.start:%d %b} -> {r.end:%d %b}".rjust(24) + f" {r.observed_ha_per_h:>10.1f} {r.model_adaptive_ha_per_h:>10.1f} {fixed}")
    obs = ad.observed_ha_per_h
    print("typical error (1.0 = perfect, 2.0 = on average a factor of 2 off): adaptive "
          f"{typical_error(ad.model_adaptive_ha_per_h, obs):.1f}x | " +
          " | ".join(f"x{f:g} {typical_error(ad[f'model_x{f:g}_ha_per_h'], obs):.1f}x" for f in a.factors))
    print(f"Only {len(ad)} periods from ONE fire: a first look, not a validation. The factor of the previous period lags a sharp change.")
print("Reminder: the whole mapped area is treated as one circle growing from its whole edge; the wind is one value per period at one point.")
