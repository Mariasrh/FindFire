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

## How far to trust the sizes (hindcast, one fire)
Measured on one event only: Kabylie, 8 to 14 August 2021, real wind of those days, one 12 h step ahead, 1048 zone-steps.
- With the placeholder rates the forecast grows fires about 16x too fast against the hotspot footprint (median predicted/observed growth 16.3x for the 263 zone-steps that grew; 15x, 17x and 13x for zones under 100 ha, 100 to 1000 ha and over 1000 ha). 75% of the 1048 zone-steps did not grow at all in the observed data.
- **Growing vs fading** (new hotspots in the last step or not, known when the forecast is made):

  | | zone-steps | really grew | predicted/observed growth, median (middle half) |
  |---|---|---|---|
  | growing | 422 | 204 | 12.2x (4.6x to 35x) |
  | fading | 626 | 59 | 33.6x (9.7x to 94x) |

  As expected the model is about three times worse on fading fires, because it has no notion of a fire slowing down. But the growing fires are **not** only 1x to 3x too fast: they are about 12x too fast, so the rates have to come down for them too. The spread within each group is wide (a factor of 7 between the middle-half limits), so single zone forecasts are only good to a factor of a few even after tuning.
- Scanning the base rate (growing steps, median and middle half): x1 gives 12.2x (4.6 to 35), x0.5 gives 5.2x (1.9 to 15), x0.2 gives 1.7x (0.6 to 5.6), x0.1 gives 0.8x (0.3 to 2.7). So a factor of **about 0.1 to 0.2** matches the hotspot growth. Report it as a range, not one number, and remember it comes from **one fire only** and was fitted and scored on the same week. Because hotspots undercount real growth (next point), the true factor is probably at the upper end of the range or above it.
- Satellite hotspots miss part of the real growth (VIIRS passes about twice a day, and a zone only grows when new hotspots are seen), so the footprint undercounts. The burned areas of the Copernicus EMSR533 activation are a better reference; they are being requested from the validation work (Anes). Until then the numbers above are rough.
- The model grows the **whole edge** of a zone. For a zone of about 26,000 ha, a circle of that area has a perimeter of about 57 km; probably only a few km of it are really burning at a given time. So large zones are overestimated more than small ones.
- The placeholder head rates are not absurd as head-fire speeds (observed rates in Mediterranean shrub and pine experiments reach about 14 to 20 m/min); the gap comes from holding that speed for 12 hours.

## Sources
- Open-Meteo forecast API (no key for non-commercial use): https://open-meteo.com/en/docs
- Ellipse and length-to-breadth ratio (Anderson 1983, used by FARSITE): https://owfflammaphelp62.firenet.gov/LegacyFARSITE/Tech_Elliptical_Dimensions.htm
- Length-to-breadth ratio LB = 0.936 e^(0.2566 U) + 0.461 e^(-0.1548 U) - 0.397, U = midflame wind in **m/s**, LB capped at 8, and the head-to-back ratio HB = (LB + sqrt(LB^2-1)) / (LB - sqrt(LB^2-1)): Finney 1998, FARSITE, RMRS-RP-4: https://www.frames.gov/documents/behaveplus/publications/Finney_1998_RMRS-RP-4.pdf
- Same formula and the directional rate of spread: https://arxiv.org/pdf/2009.00695
- Observed rates of spread in Mediterranean shrub and pine experiments (Fernandes 2001, Fernandes et al. 2002, Baeza et al. 2002, Bilgili and Saglam 2003), as summarised in Sullivan 2009, "A review of wildland fire spread modelling, 1990-present, 2: empirical and quasi-empirical models": https://arxiv.org/pdf/0706.4128 (secondary source: read the original papers before quoting values)

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
- The whole edge of the zone grows at the same rate (see above): large zones are overestimated.
- Estimates only: use them to compare scenarios, not to plan an evacuation.

## How it is checked
- `python -m pytest -q`: formula, geometry and direction tests (published LB formula in m/s, cap at 8, head-to-back ratio).
- `python -m pytest tests/test_forecast.py tests/test_forecast_wind.py`: model, geometry and wind selection (network calls are mocked: archive vs forecast URL, caching, fallback).
- `python scripts/check_forecast.py`: on a real `forecast.json`, polygon area equals reported area, areas never shrink, the fire moves the way the wind pushes it, flags inactive zones and extreme growth. Proves the arithmetic, not the realism.
- `python scripts/hindcast_forecast.py --event 2021-08-08 2021-08-14 --archive-wind`: compares predicted and observed area one 12 h step later on a past event, with the wind of that date. VIIRS passes about twice a day, so 30/60/120 min forecasts cannot be scored. The result is shown separately for **growing** zones (new hotspots in the last step, known when the forecast is made) and **fading** zones (none), then by zone size. `--rate-scale 1 0.5 0.2 0.1` tries other speeds without new wind requests. See the next section for how far to trust it.
