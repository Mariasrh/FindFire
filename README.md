
## Run the demo (replay of the August 2021 Kabylie fires)

1. Install with Python 3.13: `python -m venv venv`, `venv\Scripts\activate`, `pip install -r requirements.txt`, `pip install -e .`
2. Put the two cache files in `data/archive/`: `viirs_2021-08-08_2021-08-14.csv` (FIRMS detections) and `wind_cache.json` (Open-Meteo archive winds). With them the replay runs offline and needs no key. Without them the first run downloads the data (needs `FIRMS_MAP_KEY` in `.env` and internet).
3. Terminal 1: `python scripts/serve_dashboard.py --state data/live/replay_state.json --port 8010`, then open http://127.0.0.1:8010 and click "Enable sound".
4. Terminal 2: `python scripts/replay_to_state.py --seconds 8`
5. Live mode (needs `.env` with `FIRMS_MAP_KEY`, `EUMETSAT_KEY`, `EUMETSAT_SECRET`): `python scripts/run_live.py --once`, then `python scripts/serve_dashboard.py --port 8010`.

Without internet the map shows a fixed frame of the study area instead of the basemap. Water, pump and growth parameters and the 3 trucks per station are assumptions (see docs). Station positions: OpenStreetMap contributors.
