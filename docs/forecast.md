# Fire growth forecast (F6)

Code: `src/findfire/forecast/` (`wind.py`, `spread.py`), script `scripts/forecast_zones.py`, tests `tests/test_forecast.py`.

## What it does
For each zone it predicts the burning area at T+30, T+60 and T+120 minutes and the shape of the grown fire.

1. The zone's area is turned into a circle of the same area (radius r0).
2. Wind (Open-Meteo, 10 m height) and vegetation give the head rate of spread R (m/min).
3. Wind at flame height gives the length-to-breadth ratio LB of the fire ellipse.
4. Back rate Rb = R (1 - e) / (1 + e), with e = sqrt(LB^2 - 1) / LB.
5. After t minutes the fire reaches r0 + R t downwind and r0 + Rb t upwind. Area = pi x a x b.

Wind direction is the direction the wind comes FROM (270 = west wind). The fire is pushed the way the wind blows, so it moves toward the opposite compass direction (270 gives east, 90).

## Which wind, and when (`forecast/wind.py`)
| Asked for | Service | Notes |
|---|---|---|
| now, the future, or the last 60 days | Open-Meteo forecast API (`past_days` for the recent past) | |
| older than 60 days (a past fire, e.g. Kabylie 2021) | Open-Meteo archive API, one day per request | `archive-api.open-meteo.com/v1/archive` with `start_date` = `end_date` |
| no internet / no data | `DEFAULT_WIND`: calm (0 m/s), marked `source="default"` | A calm wind gives round fires with no invented direction. The output and the script print a warning. |

Zones close together (0.1 degree) share one request per day, so a replay does not call the service once per zone.
`scripts/forecast_zones.py --wind-time last_detected` takes each zone's wind at its own last detection; `--as-of 2021-08-10T12:00Z` uses one moment for all zones. In code: `forecast_zones(zones, wind_or_default, when=...)` with a timestamp or a function `zone -> timestamp`.

## Inactive zones
Zones with status `inactive` (no detection for days: an old burn) are skipped by default (`skip_inactive=True`; `--include-inactive` to override).

## Water hook
`water_fn` is called with the forecast area, and also with `perimeter_km` and `wind_kmh` when the function accepts them. `findfire.water.water_demand.water_for_forecast` takes all of them; `scripts/forecast_zones.py --water` plugs it in. Every forecast step then carries `perimeter_km` (ellipse) and a `water` entry.

## Sources
- Open-Meteo forecast API (no key for non-commercial use): https://open-meteo.com/en/docs
- Ellipse and length-to-breadth ratio (Anderson 1983, used by FARSITE): https://owfflammaphelp62.firenet.gov/LegacyFARSITE/Tech_Elliptical_Dimensions.htm
- Length-to-breadth ratio LB = 0.936 e^(0.2566 U) + 0.461 e^(-0.1548 U) - 0.397, U = midflame wind in **m/s**, LB capped at 8, and the head-to-back ratio HB = (LB + sqrt(LB^2-1)) / (LB - sqrt(LB^2-1)): Finney 1998, FARSITE, RMRS-RP-4: https://www.frames.gov/documents/behaveplus/publications/Finney_1998_RMRS-RP-4.pdf
- Same formula and the directional rate of spread: https://arxiv.org/pdf/2009.00695

## Assumptions to replace with sourced values (marked ASSUMPTION in `spread.py`)
| Value | Now | Meaning |
|---|---|---|
| `BASE_ROS_M_MIN` | grass 5, shrub 2, forest 1 | rate of spread with no wind, m/min (placeholders) |
| `WIND_GAIN` | 0.3 | speed-up of the head fire per m/s of flame-height wind |
| `WIND_ADJUSTMENT` | 0.4 | 10 m wind to flame-height wind |

## Limits (for the report)
- Not a physical model: no slope, no fuel moisture, no spotting, no firefighting, wind held constant for the whole forecast.
- The starting shape is a circle, so the real shape of the zone is ignored.
- One vegetation type per run: the repo has no land-cover layer yet.
- Wind is a weather-model value, not measured at the fire.
- Estimates only: use them to compare scenarios, not to plan an evacuation.

## How it is checked
- `python -m pytest -q`: formula, geometry and direction tests (published LB formula in m/s, cap at 8, head-to-back ratio).
- `python -m pytest tests/test_forecast.py tests/test_forecast_wind.py`: model, geometry and wind selection (network calls are mocked: archive vs forecast URL, caching, fallback).
- `python scripts/check_forecast.py`: on a real `forecast.json`, polygon area equals reported area, areas never shrink, the fire moves the way the wind pushes it, flags inactive zones and extreme growth. Proves the arithmetic, not the realism.
- `python scripts/hindcast_forecast.py --event 2021-08-08 2021-08-14 --archive-wind`: compares predicted and observed area one 12 h step later on a past event, with the wind of that date. VIIRS passes about twice a day, so 30/60/120 min forecasts cannot be scored; use the ratio only to calibrate `BASE_ROS_M_MIN`, and look at the zones that really grew, because in a quiet period most zones stop growing.
