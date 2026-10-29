# Data contract: zones

A **zone** is one estimated fire event: a group of VIIRS hotspots that belong together, with a polygon around them. In this project "zone" always means this **fire zone** unless qualified. It is not an *exclusion zone* (the circles around refineries and flares in `data/exclusion_zones.csv`) and not a *UTM zone* (the projection used to measure area).

- Zones are built from **VIIRS only**. MTG hotspots never create a zone; they produce separate *alerts* that can point to a zone.
- A zone is an estimate drawn from satellite pixels. It is **not a measured burned area**.

This file documents the zone format only. Land cover is documented in [`landcover.md`](landcover.md). Fields added by other modules (fire-growth forecast, water demand, response plan) are documented with those modules.

## Where zones appear

| Where | What you get | Written by |
|---|---|---|
| `data/live/state.json` → `zones` | Zones of the **live** map, rebuilt at every cycle from the stored VIIRS detections (the store keeps 7 days; with `--viirs-csv` the whole file is used) | `scripts/run_live.py` |
| Replay JSON → `steps[i].zones` | Zones **as they were at step i** (12 h steps by default) | `zones/tracking.py`; served by `scripts/serve_replay.py` (`GET /api/replay`) or embedded by `scripts/build_replay.py` |

Both use the same GeoJSON feature format. Differences:

| | Live (`state.json`) | Replay |
|---|---|---|
| `new_hotspots` | absent | present |
| Zone ids | start at 0, **not stable** between cycles | start at 1, **stable within one replay** |
| Numbers | not rounded | floats rounded to 2 decimals |

## Format

A zone is a GeoJSON `Feature`. Example: a zone from a replay run on FIRMS data of 17-18 Oct 2026 (coordinates shortened):

```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [[[6.9697, 36.8601], "..."]] },
  "properties": {
    "zone_id": 5,
    "status": "active",
    "area_ha": 41.91,
    "perimeter_km": 3.14,
    "n_hotspots": 5,
    "frp_total_mw": 17.54,
    "first_detected": "2026-10-17T00:58:00Z",
    "last_detected": "2026-10-18T00:39:00Z",
    "new_hotspots": 3
  }
}
```

| Field | Type | Unit | Meaning |
|---|---|---|---|
| `geometry` | Polygon or MultiPolygon | WGS84 lon/lat (EPSG:4326), order `[lon, lat]` | Footprint of the zone. Can have several parts or holes. |
| `zone_id` | integer | none | Identifier, see *Zone ids*. `-1` is never a zone: on a hotspot it means "in no zone". |
| `status` | string | none | `new`, `active` or `inactive`, see *Status*. |
| `area_ha` | number | hectares | Area of the footprint, measured in the UTM zone of the zone centre (never in degrees). |
| `perimeter_km` | number | kilometres | Length of the footprint outline in the same projection. Holes count. |
| `n_hotspots` | integer | count | Distinct satellite observations in the zone. The same pixel seen by a different satellite within the re-detection window counts **once**; the same satellite seeing the place again later counts again. |
| `frp_total_mw` | number | megawatts | **Sum** of the fire radiative power of every detection in the zone, including repeat detections of the same pixel. It is a cumulative sum over passes, **not** the current power of the fire. |
| `first_detected` | string | UTC, ISO 8601 `YYYY-MM-DDTHH:MM:SSZ` | Earliest detection of the zone. In a replay, when two zones merge it is the earlier of the two. |
| `last_detected` | string | UTC, ISO 8601 `YYYY-MM-DDTHH:MM:SSZ` | Latest detection in the zone. |
| `new_hotspots` | integer | count | **Replay only.** Distinct observations received during the last step (12 h by default). |
| `land_cover` | object or `null` | see `landcover.md` | **Optional.** Present only after `scripts/landcover_zones.py --write-state` has been run on the file. |
| `land_cover_error` | string | none | **Optional.** Present only when `land_cover` is `null`. |

All times are UTC. The map pages show UTC+1 (Algeria).

## Which hotspots can form a zone

Before grouping, the pipeline removes:

1. Hotspots inside a curated exclusion circle (`data/exclusion_zones.csv`).
2. In the live path only, hotspots inside a learned static-source circle (`data/static_sources.csv`). Historical and validation runs do not use it, so a present-day mask cannot change a past event.
3. Hotspots whose FIRMS `type` is not 0 (volcano, static land source, offshore) when the data has a `type` column. Near-real-time rows have no `type` and pass through.

Hotspots are then linked when the gap between their pixel rectangles is small enough, and grouped. A hotspot with no linked neighbour is not a zone. In the replay, two hotspots further apart in time than `link_dt` (72 h by default) are never linked.

## Status

Computed from the zone's detections that are still inside the time window, relative to the reference time (the build time for the live map, the step time for a replay):

| Value | Rule |
|---|---|
| `new` | earliest detection is less than 24 h before the reference time |
| `active` | not new, and the latest detection is less than 3 days before the reference time |
| `inactive` | otherwise: no recent detections. This does **not** prove the fire is out (clouds, missed passes). |

In a replay, `first_detected` is kept from earlier steps, while `status` looks only at detections still in the 7-day window. After a week, a zone can show an old `first_detected` and a `new` status. Use `last_detected` to judge recency.

## Zone ids

- **Live (`state.json`)**: ids are labels from the latest rebuild, starting at 0. They are **not stable** between cycles. Do not use them to follow a zone over time.
- **Replay**: ids start at 1 and are **stable within one replay**. A zone keeps its id across steps.
  - Two zones that join: the **older** id is kept. The event is listed in `merges` as `[step_time, merged_id, kept_id]`.
  - One zone that splits: the biggest piece keeps the id, the others get new ids.
  - Ids restart from 1 in every new replay. They are not comparable between replays.

## Related objects

Hotspots and MTG alerts refer to a zone by `zone_id` (`-1` on a hotspot means "in no zone"). Their formats are documented by their owners.

## Limits to keep in mind

- Footprints come from 375 m pixels seen only at satellite passes (a few per day). They can miss fire that burned between passes and cannot show the real burned boundary.
- `area_ha` is an estimate. It depends on the footprint method and grouping settings in `src/findfire/config.py`; the replay page lets you choose the footprint method (alpha shape, closing, pixels).
- `inactive` means "no recent detections", not "extinguished".
- Validation of zone areas against Copernicus EMS burned-area maps is documented separately.
