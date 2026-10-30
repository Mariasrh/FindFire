<p align=center><img src=docs/logo.png width=220 alt=FindFire></p>

# FindFire

Near-real-time wildfire alerts for northern Algeria from two satellites.
Each new fire zone alerts the nearest fire station, with the water and trucks needed
and a growth forecast. Student prototype.

## What it does

1. **Detect**: VIIRS active fires from NASA FIRMS (375 m, a few passes a day) and
   MTG FCI Active Fire Monitoring from EUMETSAT (2 km, every 10 minutes, pre-operational).
2. **Filter**: study area of northern Algeria (Sahara gas flares are outside),
   FIRMS `type` = vegetation (archive data), and a mask of 85 permanent industrial
   heat sources (live data has no `type`).
3. **Group and track**: hotspots become fire zones (polygon, area, status
   new / active / inactive) followed over time.
4. **Alert**: each new zone alerts its nearest fire station (469 stations from
   OpenStreetMap). If it lacks trucks, neighbouring stations are asked as reinforcements.
   A truck is never counted for two zones.
5. **Estimate**: water flow for the attackable fire front, computed for the time the
   first truck arrives, trucks needed, tank autonomy.
6. **Forecast**: growth at +30, +60 and +120 min with the wind of the fire's date
   (Open-Meteo), only for zones that are still spreading.
7. **Dashboard**: alert banner and sound, map (red = spreading, dim = watch only,
   grey = no longer active), details on click, one view per station. The replay works offline.

## Results (August 2021 Kabylie fires, Copernicus EMS EMSR533, AOI01)

| Metric | Value |
|---|---|
| Recall (mapped burned area inside our zones) | 0.65 to 0.66 |
| Precision (our zones inside the mapped burned area) | 0.63 to 0.70 |
| IoU | 0.47 to 0.51 |
| Non-vegetation detections removed (archive) | 536 of 11,614, 26 false zones |
| Industrial points removed by the static mask (live) | 519 of 536, 29 false zones, no loss of recall or precision |

One event only, details in `docs/validation.md`.
Real growth of the fire (EMSR533): 283 ha/h on 12-13 Aug, then 94, 20 and 15 ha/h.
FIRMS near-real-time data arrive within 3 hours of the satellite pass (NASA).
The MTG early alert is implemented and tested on real EUMETSAT data, but its lead time
is not measured yet: no MTG data exists for 2021 and no fire occurred during our live test.
194 automated tests, plus 11 that run only when the optional `rasterio` is installed: `python -m pytest tests -q`.

## Run the demo (replay of the August 2021 Kabylie fires)

1. Install with Python 3.13: `python -m venv venv`, `venv\Scripts\activate`,
   `pip install -r requirements.txt`, `pip install -e .`
2. Put the two cache files in `data/archive/`: `viirs_2021-08-08_2021-08-14.csv`
   (FIRMS detections) and `wind_cache.json` (Open-Meteo archive winds).
   With them the replay runs offline and needs no key. Without them the first run
   downloads the data (needs `FIRMS_MAP_KEY` in `.env` and internet).
3. Terminal 1: `python scripts/serve_dashboard.py --state data/live/replay_state.json --port 8010`,
   then open http://127.0.0.1:8010 and click "Enable sound".
4. Terminal 2: `python scripts/replay_to_state.py --seconds 8`

## Run live

Needs `.env` with `FIRMS_MAP_KEY`, `EUMETSAT_KEY`, `EUMETSAT_SECRET`:
`python scripts/run_live.py --once`, then `python scripts/serve_dashboard.py --port 8010`.

## Limits

- Water per metre of front, pump flow, growth rates and 3 trucks of 4,000 L per station
  are assumptions, to be confirmed with the Civil Protection.
- Arrival times use straight-line distance x 1.3 at 50 km/h, not road routing.
- Severity uses the cumulative zone area, so large zones are all "critical".
- The growth forecast uses one fixed spread rate. Compared with EMSR533, the rate the fire really
  needed fell about 20 times between its peak and its end (one fire only), so the forecast
  overestimates when a fire slows down. It is shown only for zones that are still spreading.
- Zones are estimates from 375 m pixels, not measured burned areas.
  "Inactive" means no recent detection, not extinguished.
- Very small fires can be missed. A single isolated detection does not create a zone,
  to limit false alarms.
- OpenStreetMap coverage of fire stations is incomplete.
- Terrain shows "forest (assumed)": the land cover module (ESA WorldCover, `docs/landcover.md`)
  is not yet connected to the dashboard.
- Without internet the map is a simplified one (coastline and borders from Natural Earth)
  instead of the OpenStreetMap basemap.

## Layout

`src/findfire/` (ingestion, detection, zones, live, forecast, water, stations, dashboard, landcover),
`scripts/` (entry points), `tests/`, `docs/`, `data/fire_stations.csv`.

## Data and credits

NASA FIRMS (VIIRS), EUMETSAT (MTG FCI), Copernicus Emergency Management Service (EMSR533),
Open-Meteo, OpenStreetMap contributors (ODbL), Natural Earth (public domain),
ESA WorldCover 2020 and 2021 (CC BY 4.0).

## Team

- Maria: water and trucks model, station data, dispatch, dashboard, replay player
- Houria: zones and tracking, MTG ingestion, live pipeline, replay, data contract, land cover
- Anes: Copernicus EMS validation, vegetation filter and static mask, one-command runner
- Hadjer: growth forecast, wind (archive and forecast), hindcast