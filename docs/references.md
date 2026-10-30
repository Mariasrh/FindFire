# References

## Satellite data

**NASA FIRMS (VIIRS active fires)**
- Sources: VIIRS near-real-time from Suomi-NPP, NOAA-20 and NOAA-21 (live), standard-processing archive for past events. 375 m pixels.
- Access: FIRMS area API with the study box, `FIRMS_MAP_KEY` in `.env`.
- Latency: near-real-time data within 3 hours of the satellite pass:
  https://www.earthdata.nasa.gov/learn/find-data/near-real-time/firms
- `type` field (archive and saved CSVs only): 0 vegetation fire, 1 active volcano, 2 other static land source
  (gas flares, refineries, industry), 3 offshore. Near-real-time data has no `type`, so live runs use the
  static-source mask instead (`scripts/build_static_mask.py` writes `data/static_sources.csv`).

**EUMETSAT MTG FCI Active Fire Monitoring**
- Collection `EO:EUM:DAT:0682` (netCDF), 2 km at the sub-satellite point, one product every 10 minutes, pre-operational.
- First MTG imager satellite (MTG-I1) launched in December 2022, so no MTG data exists for 2021.
- Access: `eumdac`, `EUMETSAT_KEY` and `EUMETSAT_SECRET` in `.env`; reading needs `satpy`. https://data.eumetsat.int

**Copernicus Emergency Management Service, activation EMSR533** (validation reference)
- August 2021 Kabylie fires, AOI01 Tizi Ouzou; products Delineation and Monit01 to Monit04, from Sentinel-2 and SPOT 6/7.
- Vector packages unzipped under `data/emsr533/` (not in git). https://mapping.emergency.copernicus.eu/activations/EMSR533/

## Weather

**Open-Meteo**: forecast API (now and the last 60 days) and historical archive API (older dates), 10 m wind.
No key for non-commercial use. https://open-meteo.com/en/docs and https://open-meteo.com/en/docs/historical-weather-api

## Land cover

**ESA WorldCover 10 m**, 2020 (v100) and 2021 (v200), CC BY 4.0. https://esa-worldcover.org
Accuracy and limits: `docs/landcover.md`.

## Maps and stations

- Fire station positions: OpenStreetMap contributors (ODbL), tag `amenity=fire_station`, `scripts/fetch_fire_stations.py`.
  Coverage is incomplete. Number of trucks and tank size are assumptions (below).
- Online basemap: OpenStreetMap tiles (ODbL), darkened in the browser.
  Tile usage policy: https://operations.osmfoundation.org/policies/tiles/
- Offline map: coastline and borders from Natural Earth (public domain). https://www.naturalearthdata.com
- Map library: Leaflet. https://leafletjs.com

## Fire spread

Ellipse model and length-to-breadth ratio (Anderson 1983; Finney 1998, FARSITE). Sources and calibration: `docs/forecast.md`.

## Values without a source (ASSUMPTIONS)

These numbers are placeholders chosen to make the system run. They must be confirmed with the Civil Protection before any real use.

| Value | Used in | Now |
|---|---|---|
| Water per metre of attacked front | `water/water_demand.py` | forest 10, scrub 8, crop 5, urban 20 L/min per m |
| Longest front attacked at once | `water/water_demand.py` | forest 2000, scrub 2000, crop 1500, urban 500 m |
| Safety margin; extra margin when wind is 30 km/h or more | `water/water_demand.py` | x1.2; x1.2 |
| Severity thresholds | `water/water_demand.py` | low under 10 ha, medium under 200 ha, critical above |
| Pump flow per truck | `stations/nearest_station.py` | 2000 L/min |
| Trucks per station, tank size | `data/fire_stations.csv` | 3 trucks, 4000 L |
| Road speed and road factor (arrival time) | `stations/nearest_station.py` | 50 km/h, straight-line distance x 1.3 |
| Longest arrival time for a reinforcement | `stations/nearest_station.py` | 60 min |
| Spread rates and wind gain | `forecast/spread.py` | see `docs/forecast.md` |
| Wind used when none is found for a date | `dashboard/server.py` | 3 m/s from the west, shown as a warning on the page |