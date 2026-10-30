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
- Satellite hotspots miss part of the real growth (VIIRS passes a few times a day (two satellites in 2021), and a zone only grows when new hotspots are seen). The Copernicus EMSR533 burned areas, mapped from optical satellites (Sentinel-2, SPOT 6/7), are the better reference; see the next section. Compared by date, the footprint of the largest hotspot zone (about 27,000 ha on 13 August) is roughly half of the mapped burned area (53,094 ha), assuming they are the same fire (not checked on a map).

- The model grows the **whole edge** of a zone. For a zone of about 26,000 ha, a circle of that area has a perimeter of about 57 km; probably only a few km of it are really burning at a given time. So large zones are overestimated more than small ones.
- The placeholder head rates are not absurd as head-fire speeds (observed rates in Mediterranean shrub and pine experiments reach about 14 to 20 m/min); the gap comes from holding that speed for 12 hours.

## Fuel dryness: tried, not used
Humidity and temperature were tried in the spread rate, on branch `feat/forecast-fuel-moisture` (`forecast/fuel.py`, option `--fuel`, off by default). Fuel moisture comes from the Canadian Fine Fuel Moisture Code (Van Wagner and Pickett 1985, equations 1 to 10, from Open-Meteo temperature, humidity, wind and rain of the last week), turned into a spread factor with equation 25; the Canadian wind function is left out because the model already has its own wind effect.

On the Kabylie hotspot hindcast (8 to 14 August 2021, 263 zone-steps that grew) it **did not help**. The two scores below do not change when every prediction is scaled by the same factor, so they test whether the weather term tells fast from slow zones, not the overall level:

| | rank correlation, predicted vs observed growth | spread of log10(predicted/observed) |
|---|---|---|
| without fuel | 0.38 | 0.95 |
| with fuel | 0.14 | 1.22 |

The fuel factor was between 0.36 and 8.0 (median 6.8): in that very dry week most zones got a similar, large factor, so it added noise. This is one event and a rough reference (hotspots), so it does not prove that fuel moisture never matters, and FFMC was built for Canadian pine forest. The code stays behind `--fuel`, off by default, and should only be used after it has been checked on a second event.

## Check against the real burned area (Copernicus EMSR533, Kabylie)
Anes's table of burned areas mapped on 12, 13, 14, 15 and 16 August 2021 (`docs/emsr533_burned_area.md`) gives the real growth: about 283 ha/h from 12 to 13 August (peak), then 94, 20 and 15 ha/h. `python scripts/compare_emsr533.py` starts from the area mapped on each date, grows it with the model until the next mapping, and solves for the rate factor that would match:

| period | real growth (ha/h) | model x0.2 | model x0.1 | factor needed |
|---|---|---|---|---|
| 12 to 13 Aug | 283 | 141 | 70 | 0.39 |
| 13 to 14 Aug | 94 | 151 | 75 | 0.12 |
| 14 to 15 Aug | 20 | 154 | 77 | 0.03 |
| 15 to 16 Aug | 15 | 155 | 77 | 0.02 |

(Fixed wind of 4 m/s; with 2 or 7 m/s the model rates change by less than 5% and the factors do not change, because for a zone this large the wind changes the shape much more than the area. Run it without `--wind` to use the real wind of each date.)

- **One fixed speed cannot fit the whole fire.** The factor needed falls by a factor of about 20 from the peak to the end. Tuned for the peak (x0.4) the model is about 20 times too fast at the end; tuned for the end (x0.02) it is about 20 times too slow at the peak. The placeholder rates (x1) are about 2.7x too fast at the peak and about 55x at the end.
- This agrees with the hotspot hindcast, from the other side: the factor that matched the hotspot growth (0.1 to 0.2) lies between the peak value and the end values, and is lower than the peak value because hotspots undercount.
- The cause is that the model holds one spread rate for the whole forecast and has no notion of a fire slowing down (ridges, agricultural breaks, containment, weather change). A rate that follows the fire's recent observed growth is the natural fix. First look (`compare_emsr533.py`, forecasting each period with the factor the previous period needed, fixed 4 m/s wind): predictions 302, 96 and 20 ha/h against 94, 20 and 15 observed, a typical error of 2.8x. The fixed factors on the same three periods give 27x (x1), 5.1x (x0.2) and 2.9x (x0.1). So the adaptive rate, with no tuning, does about as well as the best fixed factor, which was itself chosen by looking at this fire. It tracks a slow decline well (20 against 15 ha/h) but lags a sharp one (302 against 94 ha/h). Three periods of one fire is a first look, not a validation. For the demo, show a range and say it comes from one fire.
- One fire, one zone: the whole mapped area (46,000 to 56,000 ha) is treated as a single circle although it may be several fires that merged.

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
- Not a physical model: no slope, no fuel moisture (tried, see above: it did not help), no spotting, no firefighting, wind held constant for the whole forecast.
- The starting shape is a circle, so the real shape of the zone is ignored.
- One vegetation type per run: the land cover module (`docs/landcover.md`) is not yet connected to the forecast.
- Wind is a weather-model value, not measured at the fire.
- The whole edge of the zone grows at the same rate (see above): large zones are overestimated.
- Estimates only: use them to compare scenarios, not to plan an evacuation.

## How it is checked
- `python -m pytest -q`: formula, geometry and direction tests (published LB formula in m/s, cap at 8, head-to-back ratio).
- `python -m pytest tests/test_forecast.py tests/test_forecast_wind.py`: model, geometry and wind selection (network calls are mocked: archive vs forecast URL, caching, fallback).
- `python scripts/check_forecast.py`: on a real `forecast.json`, polygon area equals reported area, areas never shrink, the fire moves the way the wind pushes it, flags inactive zones and extreme growth. Proves the arithmetic, not the realism.
- `python scripts/compare_emsr533.py`: model growth against the burned areas mapped by Copernicus EMSR533, with the rate factor needed per period (offline with `--wind SPEED FROM_DEG`).
- `python scripts/hindcast_forecast.py --event 2021-08-08 2021-08-14 --archive-wind`: compares predicted and observed area one 12 h step later on a past event, with the wind of that date. VIIRS passes a few times a day (two satellites in 2021), so 30/60/120 min forecasts cannot be scored. The result is shown separately for **growing** zones (new hotspots in the last step, known when the forecast is made) and **fading** zones (none), then by zone size. `--rate-scale 1 0.5 0.2 0.1` tries other speeds without new wind requests. See the next section for how far to trust it.