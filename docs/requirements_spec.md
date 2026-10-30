# Requirements and status

FindFire turns satellite fire detections into alerts for fire stations in northern Algeria.
This page lists what the system must do, where it is done, and how far it was checked.
Status: **done**, **partial** (works, with a stated limit) or **not measured**.

## Functional requirements

| # | Requirement | Where | Status and evidence |
|---|---|---|---|
| FR1 | Ingest VIIRS active fires from NASA FIRMS (near-real-time for live, archive for past events) | `ingestion/firms.py`, `scripts/run_live.py` | Done. Live run: 660 detections in 5 days |
| FR2 | Ingest MTG FCI Active Fire Monitoring from EUMETSAT every 10 minutes | `ingestion/mtg.py` | Done. Real granules read live; no fire pixel during the test (October) |
| FR3 | Keep vegetation fires, drop industry and gas flares | `detection/filters.py`, `data/static_sources.csv` | Done. Archive: 536 of 11,614 detections removed (26 false zones). Live mask: 519 of 536 industrial points (29 false zones), no loss of recall or precision |
| FR4 | Group hotspots into fire zones and follow them in time (new / active / inactive) | `zones/`, `docs/data_contract.md` | Done |
| FR5 | Early alert from MTG, confirmed by VIIRS, with the lead time measured | `live/pipeline.py` | Partial: implemented and tested; lead time not measured (no MTG data in 2021, no fire during the live test) |
| FR6 | Alert the nearest fire station; ask neighbouring stations when it lacks trucks; never count a truck twice | `dashboard/dispatch.py` | Done (trucks per station assumed) |
| FR7 | Water flow and trucks needed when the first truck arrives | `water/`, `stations/`, `dashboard/cards.py` | Done, with placeholder parameters (see `references.md`) |
| FR8 | Growth forecast at +30, +60 and +120 min with the wind of the fire's date | `forecast/`, `docs/forecast.md` | Partial: works; one fixed spread rate, checked on one fire against EMSR533 |
| FR9 | Dashboard: alert banner and sound, map, details on click, one view per station | `dashboard/` | Done |
| FR10 | Replay a real past fire through the same pipeline | `scripts/replay_to_state.py` | Done (Kabylie, 8 to 14 Aug 2021) |
| FR11 | Validate zones against an independent reference | `validation.py`, `docs/validation.md` | Done on one event (EMSR533): recall 0.65 to 0.66, precision 0.63 to 0.70, IoU 0.47 to 0.51 |
| FR12 | Land cover under each zone | `landcover/`, `docs/landcover.md` | Partial: module done (ESA WorldCover); not shown on the dashboard yet |

## Non-functional requirements

| # | Requirement | Status |
|---|---|---|
| NFR1 | Near real time | FIRMS near-real-time data within 3 hours of the pass (NASA); MTG every 10 min; dashboard refresh every 5 s; one replay step computed in about 2 s with the wind cache (6.5 s the first time, measured on our PC) |
| NFR2 | The demo works without internet | Done: cached detections and winds, built-in offline map |
| NFR3 | Open data and free services only; no key in git | Done: keys only in `.env`, ignored by git |
| NFR4 | Automated tests | 194 tests, plus 11 that need the optional `rasterio` |
| NFR5 | Every assumption is written down | Values without a source are listed in `references.md` and marked ASSUMPTION in the code |

## Known limits

- Very small fires can be missed (375 m and 2 km pixels); a single isolated detection does not create a zone.
- Live zone ids are rebuilt at every cycle, so in live mode a zone can be alerted again after a rebuild (the replay has stable ids).
- One failed FIRMS source makes the whole FIRMS poll of that cycle retry later.
- Severity uses the cumulative zone area; the forecast uses one fixed spread rate; arrival times are straight-line based, not road routing.

## Next steps

Land cover on the dashboard cards; stable live zone ids; road routing for arrival times; MTG lead time measured during a fire season;
a spread rate that follows the recent observed growth; water and truck parameters confirmed with the Civil Protection.