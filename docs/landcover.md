# Land cover per zone

What is on the ground under each fire zone (forest, scrub, grass, crop, built-up, ...). A "zone" here is a **fire zone**: the polygon built from a group of VIIRS hotspots, as defined in [`data_contract.md`](data_contract.md). Land cover is computed from a global map over that polygon and attached to the zone as a `land_cover` object. The zone fields themselves are in the contract.

Code: `src/findfire/landcover/worldcover.py`. Scripts: `scripts/landcover_zones.py`, `scripts/validate_landcover.py`. Tests: `tests/test_landcover.py`.

## Data source

**ESA WorldCover 10 m, 2021, algorithm v200.** Global land cover from Sentinel-1 and Sentinel-2, 11 classes, WGS84, free under CC BY 4.0. It is delivered as 3 x 3 degree Cloud-Optimized GeoTIFF tiles on the public bucket `s3://esa-worldcover` (no account needed).

- Because the tiles are COGs, only the pixels under a zone are read over HTTP. There is no large download.
- Tiles can also be put in a local folder under their original file names (`ESA_WorldCover_10m_2021_v200_N36E003_Map.tif`). A local tile is used when present. This is how the tests and offline runs work.
- Tile names follow the south-west corner of the tile: `N36E003` covers latitude 36 to 39 and longitude 3 to 6. A zone across a tile boundary is read from both tiles and combined.
- The map is a **2021 snapshot**. It shows the land before a recent fire, which is what is wanted, but it cannot show changes after 2021.

## From WorldCover class to label and fuel

| WorldCover code | Class | `label` | `fuel` (forecast vegetation key) |
|---|---|---|---|
| 10 | tree cover | `forest` | `forest` |
| 20 | shrubland | `scrub` | `shrub` |
| 30 | grassland | `grass` | `grass` |
| 40 | cropland | `crop` | `null` |
| 50 | built-up | `built-up` | `null` |
| 60 | bare / sparse vegetation | `bare` | `null` |
| 70, 80, 90, 95, 100 | snow and ice, permanent water, herbaceous wetland, mangroves, moss and lichen | `other` | `null` |

Pixels with code 0 (no data) or any code not in the table are ignored.

## The `land_cover` object

Added to a zone's properties. Real excerpt, zone 8 of a live run (`--firms-days 5`); the fields `n_pixels` and `source` are left out here but are always present:

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

(`fuel`, `dominant_class`, `classes`, `n_pixels` and `source` are also present in the real object.)

| Field | Meaning |
|---|---|
| `label` | The group of the **single largest WorldCover class** under the footprint, from the table above. |
| `fuel` | The vegetation key the fire-growth forecast understands for that largest class (`forest`, `shrub`, `grass`), or `null` for crop, built-up, bare and other. |
| `dominant_class` | Name of the largest WorldCover class (for example `tree cover`). |
| `dominant_share` | Share of the footprint covered by the whole `label` group, 0 to 1. For `other` this adds several classes together. |
| `majority` | `true` when `dominant_share` is above 0.5. When `false` the zone is **mixed**: show it as mixed and do not present `label` as certain. |
| `shares` | Share of the footprint per label group. Only groups present are listed. |
| `classes` | Share of the footprint per WorldCover class. Only classes present are listed. |
| `n_pixels` | Number of 10 m pixels read under the footprint. |
| `source` | Data set name and version (`ESA WorldCover 2021 v200 (10 m)`). |

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

## Running it

```
python scripts/landcover_zones.py                 # reads data/live/state.json, writes data/live/landcover.json
python scripts/landcover_zones.py --write-state   # also writes land_cover into each zone of state.json
python scripts/landcover_zones.py --tiles D:/worldcover   # local tiles first
python scripts/landcover_zones.py --no-remote     # never use the internet (a missing tile gives null)
```

- Results are **cached by footprint** in `data/landcover/cache.json` (the key includes the year, the version and the footprint geometry), so a zone whose footprint did not change is not read again. Only successful reads are cached.
- `state.json` is rewritten by `scripts/run_live.py` at every cycle, and that rewrite does not call the land-cover code. `land_cover` written with `--write-state` therefore lasts only until the next cycle. Until the live rebuild calls `annotate_zones`, run the script again after each cycle.
- The script prints the data attribution; show it wherever the data is displayed (see the end of this file).

## Reading a result

The zone `label` alone hides how sure the map is. Use the `majority` flag and `dominant_share`, grouped into tiers (the same rule `scripts/validate_landcover.py` uses):

| Tier | Rule | Suggested use |
|---|---|---|
| confident | `majority`, `dominant_share` at least 0.7, label `crop` or `forest` | use directly |
| likely | `majority`, any other case (grass, scrub, or a share between 0.5 and 0.7) | use, show the share |
| mixed | `majority` is `false` | show as mixed; do not force one fuel |
| review | label is `built-up`, `bare` or `other` | check the zone on imagery: it can be a heat source the mask missed, or a footprint that overshoots into a town |
| unknown | `land_cover` is `null` | show "unavailable" |

## Accuracy and limits

- ESA reports an overall accuracy of **76.7 %** for v200 (independent validation by Wageningen University for statistical accuracy and IIASA for spatial accuracy). The figure is a global average, not a confidence for a zone. Details are in the Product Validation Report (`WorldCover_PVR_V2.0.pdf`, hosted at `pure.iiasa.ac.at`).
- A third-party study reports, citing the same validation, an overall accuracy of 73.6 % in Africa and, for cropland in Africa, a user's accuracy of 71.4 % and a producer's accuracy of 50.8 % (arXiv 2307.02575). So a `crop` label is right roughly 7 times in 10 in Africa, and about half of real cropland is mapped as something else. Treat these as indicative for Algeria, not exact.
- Shrubland, grassland and bare are the classes most often confused with each other. A local assessment in Turkey found the same (Osgouei, Sertel and Kabadayi, 2023). Treat `scrub`, `grass` and `bare` as soft labels.
- ESA's shrubland definition may include uncultivated cropland without a harvest or bare-soil period, so some `scrub` zones may be fallow fields.
- `dominant_share` says how the pixels under the footprint were labelled. It is not the probability that the label is right.
- The footprint is built from 375 m pixels, so it includes land around the real fire. Land cover is computed over the footprint, not over the burned area.
- Recent burn scars can appear as `bare` if the 2021 imagery includes a burn.
- Two vocabularies are in use: `label` says `scrub` and `built-up`, `fuel` says `shrub`. The water-demand module uses its own terrain keys (`forest`, `scrub`, `crop`, `urban`). The labels `grass`, `bare` and `other` have no terrain key there yet.

## Not connected yet

- The fire-growth forecast takes one `vegetation` value for all zones (`--vegetation`, default `shrub`). It does not read `fuel` from the zones.
- Water demand does not read `land_cover`.
- The live rebuild, the replay and the map pages do not call or display land cover.

## Checking the labels

`scripts/validate_landcover.py` builds a page with each zone outlined on satellite imagery. You pick what you see (the prediction is hidden until you answer), export a CSV, and the script prints the agreement overall, by tier and by predicted label:

```
python scripts/validate_landcover.py --n 20                                   # builds data/results/landcover_validation.html
python scripts/validate_landcover.py --csv-in data/results/landcover_checks.csv   # prints the agreement table
```

Every mixed and review zone is always included; the rest are sampled at random up to `--n`. Zones without land cover cannot be checked and are skipped. The check measures agreement between the label and what a person sees in imagery of unknown date, on a small number of zones that are not independent (neighbouring zones can share a field). Report the count with the percentage.

## Tests

`tests/test_landcover.py` covers tile naming, shares, majority and mixed zones, the label-to-fuel mapping, zones across a tile boundary, missing tiles and zones outside the data (they raise instead of guessing), `annotate_zones` writing `null` plus an error, the cache, and `summarise` ignoring no-data and unknown codes.

## Attribution

(c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. Licence CC BY 4.0.
