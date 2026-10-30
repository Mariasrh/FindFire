# Land cover per zone

What is on the ground under each fire zone (forest, scrub, grass, crop, built-up, ...). A "zone" here is a **fire zone**: the polygon built from a group of VIIRS hotspots, as defined in [`data_contract.md`](data_contract.md). Land cover is computed from a global map over that polygon and attached to the zone as a `land_cover` object. The zone fields themselves are in the contract.

Code: `src/findfire/landcover/worldcover.py`. Scripts: `scripts/landcover_zones.py`, `scripts/validate_landcover.py`, `scripts/export_event_state.py`. Tests: `tests/test_landcover.py`.

## Data source

**ESA WorldCover 10 m**, two releases supported: **2020 (algorithm v100)** and **2021 (algorithm v200)**. Global land cover from Sentinel-1 and Sentinel-2, 11 classes, WGS84, free under CC BY 4.0. It is delivered as 3 x 3 degree Cloud-Optimized GeoTIFF tiles on the public bucket `s3://esa-worldcover` (no account needed).

- Because the tiles are COGs, only the pixels under a zone are read over HTTP. There is no large download.
- Tiles can also be put in a local folder under their original file names (`ESA_WorldCover_10m_2021_v200_N36E003_Map.tif`, `ESA_WorldCover_10m_2020_v100_N36E003_Map.tif`). A local tile is used when present. Both years can share one folder because the file names differ. This is how the tests and offline runs work.
- Tile names follow the south-west corner of the tile: `N36E003` covers latitude 36 to 39 and longitude 3 to 6. A zone across a tile boundary is read from both tiles and combined.
- Each map is a **snapshot of its year**. It cannot show changes after that year.

### Which year to use

A map built from imagery of year Y can already contain the burn scars of fires that happened in Y, and a fresh scar is mapped as `bare` / sparse vegetation. What is wanted is the land **before** the fire, so each fire uses the latest map from a year before it (`year_for(date)` in `worldcover.py`):

| Fire date                                  | Map used       | Why                                         |
| ------------------------------------------ | -------------- | ------------------------------------------- |
| Aug 2021 (Kabylie, the EMSR533 validation) | **2020, v100** | 2021 already contains the scars             |
| Live fires (2026)                          | **2021, v200** | the newest map before the fire              |
| 2020 or earlier                            | none           | `year_for` raises: no map predates the fire |

The default everywhere is 2021. Pass `--year 2020` to the scripts, or `year=2020` to the functions, to use the other map.

The 2020 and 2021 releases come from different algorithm versions, so **their differences are not a land-change result**: part of it is the algorithm, not the land. Do not present a 2020 vs 2021 comparison as change detection [5].

## From WorldCover class to label and fuel

| WorldCover code     | Class                                                                         | `label`    | `fuel` (forecast vegetation key) |
| ------------------- | ----------------------------------------------------------------------------- | ---------- | -------------------------------- |
| 10                  | tree cover                                                                    | `forest`   | `forest`                         |
| 20                  | shrubland                                                                     | `scrub`    | `shrub`                          |
| 30                  | grassland                                                                     | `grass`    | `grass`                          |
| 40                  | cropland                                                                      | `crop`     | `null`                           |
| 50                  | built-up                                                                      | `built-up` | `null`                           |
| 60                  | bare / sparse vegetation                                                      | `bare`     | `null`                           |
| 70, 80, 90, 95, 100 | snow and ice, permanent water, herbaceous wetland, mangroves, moss and lichen | `other`    | `null`                           |

Pixels with code 0 (no data) or any code not in the table are ignored. Class codes and the tile grid are the same in both years.

## The `land_cover` object

Added to a zone's properties. Real excerpt, zone 8 of a live run (`--firms-days 5`); the fields `n_pixels`, `source` and `year` are left out here but are always present:

```json
"land_cover": {
  "label": "forest",
  "fuel": "forest",
  "dominant_class": "tree cover",
  "dominant_share": 0.7139,
  "majority": true,
  "shares": { "crop": 0.1784, "forest": 0.7139, "grass": 0.0103, "scrub": 0.0974 },
  "classes": { "tree cover": 0.7139, "shrubland": 0.0974, "grassland": 0.0103, "cropland": 0.1784 }
}
```

A mixed zone (zone 13 of the same run): the top class covers less than half, so `majority` is `false`.

```json
"land_cover": {
  "label": "forest",
  "dominant_share": 0.4272,
  "majority": false,
  "shares": { "crop": 0.1391, "forest": 0.4272, "grass": 0.1217, "scrub": 0.312 }
}
```

(`fuel`, `dominant_class`, `classes`, `n_pixels`, `source` and `year` are also present in the real object.)

| Field            | Meaning                                                                                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `label`          | The group of the **single largest WorldCover class** under the footprint, from the table above.                                                            |
| `fuel`           | The vegetation key the fire-growth forecast understands for that largest class (`forest`, `shrub`, `grass`), or `null` for crop, built-up, bare and other. |
| `dominant_class` | Name of the largest WorldCover class (for example `tree cover`).                                                                                           |
| `dominant_share` | Share of the footprint covered by the whole `label` group, 0 to 1. For `other` this adds several classes together.                                         |
| `majority`       | `true` when `dominant_share` is above 0.5. When `false` the zone is **mixed**: show it as mixed and do not present `label` as certain.                     |
| `shares`         | Share of the footprint per label group. Only groups present are listed.                                                                                    |
| `classes`        | Share of the footprint per WorldCover class. Only classes present are listed.                                                                              |
| `n_pixels`       | Number of 10 m pixels read under the footprint.                                                                                                            |
| `source`         | Data set name and version (for example `ESA WorldCover 2020 v100 (10 m)`).                                                                                 |
| `year`           | Year of the WorldCover map the label comes from (2020 or 2021). Show it next to the label so a reader knows which map was used.                            |

All shares are rounded to 4 decimals, so they add up to 1 only approximately.

### When land cover is unavailable

`land_cover` is `null` and `land_cover_error` holds the reason. Nothing is guessed. Reasons raised by the code:

- the tile is not in the local folder and remote reading is off (`tile ... not found in ...`);
- the tile cannot be read (`cannot read ...`: no internet, bucket unreachable);
- no land-cover pixels under the footprint (`no land-cover pixels under this zone (sea, or outside the tile data)`).

Example:

```json
"land_cover": null,
"land_cover_error": "no land-cover pixels under this zone (sea, or outside the tile data)"
```

`land_cover_error` is present **only** when `land_cover` is `null`. A consumer must show "land cover unavailable" in that case, never "forest". If the dashboard keeps "forest (assumed)" it must be labelled as an assumption and used only when `land_cover` is `null`.

An unknown year (anything other than 2020 or 2021) raises `ValueError`; it is a usage error, not an unavailable tile.

## Running it

Land cover needs rasterio, which is not in `requirements.txt`: `pip install -r requirements-landcover.txt`

Live zones (2021 map, the default):

```
python scripts/landcover_zones.py                 # reads data/live/state.json, writes data/live/landcover.json
python scripts/landcover_zones.py --write-state   # also writes land_cover into each zone of state.json
python scripts/landcover_zones.py --tiles D:/worldcover   # local tiles first
python scripts/landcover_zones.py --no-remote     # never use the internet (a missing tile gives null)
```

A past event (for example Kabylie, Aug 2021, labelled with the 2020 map). The land-cover scripts read `data/live/state.json` by default, which holds today's zones, so first build a state file for the event:

```
python scripts/export_event_state.py --csv data/archive/viirs_2021-08-08_2021-08-14.csv --out data/events/kabylie2021/state.json
python scripts/landcover_zones.py --state data/events/kabylie2021/state.json --year 2020 --geojson --out data/events/kabylie2021/landcover_2020.geojson
```

`export_event_state.py` runs the same tracking as `validate_emsr.py` and keeps the zones of the last step. It also accepts `--event START END` (FIRMS archive, needs `FIRMS_MAP_KEY`) instead of `--csv`. Zone ids come from tracking that one data set, so match them to live zones by location, not by id.

### Output formats

- Default: `--out` is a JSON object `{zone_id: land_cover record}`.
- With `--geojson`: `--out` is a GeoJSON **FeatureCollection** for the dashboard. Each feature has the zone polygon (lon/lat) and the properties `zone_id`, `area_ha`, `status` and `land_cover` (plus `land_cover_error` when it is `null`). The top level has `land_cover_year`, `source` and `attribution`. A reader needs no rasterio: it only reads the file and can match zones by polygon location.

### Cache

- Results are **cached by year and footprint** in `data/landcover/cache.json` (the key includes the year, the version and the footprint geometry), so a zone whose footprint did not change is not read again, and 2020 and 2021 results never mix. Only successful reads are cached. Entries cached before the `year` field existed are valid and get `year` added when read.
- `state.json` is rewritten by `scripts/run_live.py` at every cycle, and that rewrite does not call the land-cover code. `land_cover` written with `--write-state` therefore lasts only until the next cycle. Until the live rebuild calls `annotate_zones`, run the script again after each cycle.
- The script prints the data attribution for the selected year; show it wherever the data is displayed (see the end of this file).

## Reading a result

The zone `label` alone hides how sure the map is. Use the `majority` flag and `dominant_share`, grouped into tiers (the same rule `scripts/validate_landcover.py` uses):

| Tier      | Rule                                                                      | Suggested use                                                                                                  |
| --------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| confident | `majority`, `dominant_share` at least 0.7, label `crop` or `forest`       | use directly                                                                                                   |
| likely    | `majority`, any other case (grass, scrub, or a share between 0.5 and 0.7) | use, show the share                                                                                            |
| mixed     | `majority` is `false`                                                     | show as mixed; do not force one fuel                                                                           |
| review    | label is `built-up`, `bare` or `other`                                    | check the zone on imagery: it can be a heat source the mask missed, or a footprint that overshoots into a town |
| unknown   | `land_cover` is `null`                                                    | show "unavailable"                                                                                             |

The tiers are checked in the order unknown, review, mixed, confident, likely. A zone whose label is `built-up`, `bare` or `other` is therefore `review` even when it is also mixed (`majority` is `false`).

## Accuracy and limits

### Reported accuracy

- **2021 map (v200):** overall accuracy **76.7 % (±0.5)** globally over 11 classes, validated independently by Wageningen University (statistical accuracy) and IIASA (spatial accuracy) [1][2]. For Africa: **76.5 % (±1.3)**, as reported by Digital Earth Africa [4].
- **2020 map (v100):** produced with an earlier algorithm, **74.4 % (±0.1)** globally [1][6] and **73.6 % (±0.2)** for Africa, as reported by Digital Earth Africa [4].
- These are global and continental averages. They are not a confidence level for a specific zone, and no Algeria-specific validation is cited here. The local check described under _Checking the labels_ is how a project-specific agreement figure is produced.
- As summarised by Digital Earth Africa, tree cover, cropland, water and bare / sparse vegetation are among the well-mapped classes and shrubland is among the less accurate ones [4]. Grassland is not on the list of well-mapped classes. This is why only `crop` and `forest` can reach the _confident_ tier, and why `scrub` and `grass` labels are shown with their share. The class-level statement is global, not local, so the local check described under _Checking the labels_ remains the project's own evidence.
- ESA's grassland class may include uncultivated cropland without a harvest or bare-soil period in the reference year [3]. Some `grass` zones may therefore be fallow fields.

### What the label does and does not say

- `dominant_share` says how the pixels under the footprint were labelled. It is not the probability that the label is right.
- The footprint is built from 375 m VIIRS pixels, so it includes land around the real fire. Land cover is computed over the footprint, not over the burned area.
- **Burn scars:** a map of year Y can show a fire of year Y as `bare`. This is why the Aug 2021 Kabylie replay and validation use the **2020** map. The 2020 map can still show `bare` where something burned in 2020, so zones in the _review_ tier should be checked on imagery.
- The 2020 and 2021 maps are not a change-detection pair (different algorithm versions) [5].
- Two vocabularies are in use: `label` says `scrub` and `built-up`, `fuel` says `shrub`. The water-demand module uses its own terrain keys (`forest`, `scrub`, `crop`, `urban`). The labels `grass`, `bare` and `other` have no terrain key there yet.

## Not connected yet

- The fire-growth forecast takes one `vegetation` value for all zones (`--vegetation`, default `shrub`). It does not read `fuel` from the zones.
- Water demand does not read `land_cover`.
- The live rebuild, the replay and the map pages do not call or display land cover. The dashboard is meant to read the GeoJSON file above.
- `year_for` is not wired into the replay or validation path: the year is passed by hand with `--year`.

## Checking the labels

`scripts/validate_landcover.py` builds a page with each zone outlined on satellite imagery. You pick what you see (the prediction is hidden until you answer), export a CSV, and the script prints the agreement overall, by tier and by predicted label:

```
python scripts/validate_landcover.py --state data/events/kabylie2021/state.json --year 2020 --n 20 --out data/results/landcover_validation_2020.html
python scripts/validate_landcover.py --csv-in data/results/landcover_checks_2020.csv   # prints the agreement table
```

Every mixed and review zone is always included; the rest are sampled at random up to `--n`. Zones without land cover cannot be checked and are skipped. The check measures agreement between the label and what a person sees in imagery of unknown date, on a small number of zones that are not independent (neighbouring zones can share a field). Report the count with the percentage.

## Tests

`tests/test_landcover.py` covers tile naming, shares, majority and mixed zones, the label-to-fuel mapping, zones across a tile boundary, missing tiles and zones outside the data (they raise instead of guessing), `annotate_zones` writing `null` plus an error, the cache, and `summarise` ignoring no-data and unknown codes. For the year option it covers the v100 and v200 file names and URLs, an unknown year raising, `year_for`, each year reading its own local tile, a missing tile of the other year, the cache not mixing years, and old cache entries getting `year`.

rasterio is optional for the test run: the tests that build or read tiles skip themselves when it is not installed (`pytest.importorskip`), and the others (names, URLs, `year_for`, `summarise`, the cache read) still run.

## Sources

1. ESA WorldCover, data access and validation statements (76.7 % for 2021, 74.4 % for 2020): https://esa-worldcover.org/en/data-access
2. Product Validation Report v2.0 (2021 / v200): https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PVR_V2.0.pdf
3. Product User Manual v2.0 (class definitions, including grassland): https://pure.iiasa.ac.at/18983/1/WorldCover_PUM_V2.0.pdf
4. Digital Earth Africa, ESA WorldCover (Africa accuracy for 2020 and 2021, class-level summary): https://docs.digitalearthafrica.org/en/latest/data_specs/ESA_WorldCover_specs.html
5. Zenodo record, ESA WorldCover 10 m 2021 v200 (2020 vs 2021 algorithm caveat): https://zenodo.org/records/7254221
6. Product Validation Report v1.1 (2020 / v100): https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/docs/WorldCover_PVR_V1.1.pdf

## Attribution

(c) ESA WorldCover project <year> / Contains modified Copernicus Sentinel data (<year>) processed by ESA WorldCover consortium, with <year> the year of the map used (2020 or 2021). Licence CC BY 4.0. The GeoJSON output carries this line in its `attribution` field.
