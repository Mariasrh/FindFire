# System Validation & Performance Metrics

Code: `src/findfire/validation.py`, `src/findfire/live/pipeline.py`, `src/findfire/detection/filters.py`  
Scripts: `scripts/Run_Comparison.py`, `scripts/validate_emsr.py`, `scripts/build_static_mask.py`, `scripts/build_replay.py`  
Tests: `tests/test_validation.py`, `tests/test_pipeline.py`, `tests/test_filters.py`

---

## 1. Operational Context & Evaluation Strategy

### Wildfire Seasonality & Inactivity Logic
Wildfires in Algeria are heavily concentrated in the Mediterranean summer (July–August). In late autumn (late October), weather conditions naturally suppress wildfire outbreaks, resulting in minimal to zero active wildfires across the country.

Under FindFire's state machine (`INACTIVE = pd.Timedelta(days=3)` in `src/findfire/live/pipeline.py`), any tracked fire zone that receives no new satellite hotspot detections within **72 hours** is classified as `inactive`. The operational dashboard intentionally filters out inactive zones to keep responders focused exclusively on immediate threats. Consequently, running live ingestion today (`python scripts/run_live.py --once --no-mtg --firms-days 5` yielding 660 raw FIRMS detections and 9 localized zones, most inactive) correctly shows few or no active zones on the map. This reflects accurate seasonal behavior, not a defect.

### One Unified Story: Replay & Validation Alignment
Because an operational demonstration cannot rely on a live wildfire occurring on demo day, the system architecture feeds real archived satellite detections through the exact same production pipeline:

1. **Demonstration Replay**: Replays real, archived detections from the **Kabylie wildfire complex of August 8–14, 2021** step by step through the pipeline. The dashboard behaves dynamically as if the event were occurring live: VIIRS passes cluster into expanding fire zones, the F6 elliptical spread model projects growth, and nearest fire stations calculate water and truck requirements.
2. **Quantitative Validation**: The performance metrics table (precision, recall, IoU and false-alarm suppression) is evaluated on this exact same August 2021 Kabylie event against independent ground-truth mapping from the Copernicus Emergency Management Service (**EMSR533**).

By using the August 2021 Kabylie event for both the interactive demonstration and the empirical validation, the demo and the reported numbers tell **one coherent, rigorous, and verifiable story**.

---

## 2. Summary Metrics Table

All values below are benchmarked on the August 2021 Kabylie wildfire complex (EMSR533 reference), matching the replay demonstration dataset.

| Metric | Measured Value / Range | Baseline / Reference | Method / Evaluation Source | Notes |
|---|---|---|---|---|
| **Precision** | **63.0% – 70.0%** (mean: 67.6%) | Copernicus EMS EMSR533 ground truth | Overlap of cumulative sum of VIIRS zones with CEMS optical burn scar | Precision increases as fire perimeter consolidates. |
| **Recall** | **65.0% – 66.0%** (mean: 65.8%) | Copernicus EMS EMSR533 ground truth | Share of reference CEMS burned scar covered by sum of tracked zones | Uniform across all 5 Copernicus monitoring products. |
| **IoU (Jaccard Index)** | **0.47 – 0.51** (mean: 0.50) | Copernicus EMS EMSR533 ground truth | Intersection over Union (\(\frac{Z \cap R}{Z \cup R}\)) | Geometric agreement between zone footprints and optical scar. |
| **Alert Lead Time** | **Not measured: no MTG data in 2021.** | Polar VIIRS pass (~12 h cycle) | Evaluated on 2021 historical event | MTG-I1 launched in December 2022; no operational MTG data exists for August 2021. |
| **Data Latency (VIIRS)** | **Within 3 hours** (NASA FIRMS) | Acquisition to NRT distribution | NASA FIRMS documented NRT latency | Documented turnaround for FIRMS NRT active fire data ([NASA FIRMS](https://www.earthdata.nasa.gov/learn/find-data/near-real-time/firms)). |
| **Data Latency (MTG)** | **Not measured.** | EUMETSAT Data Store stream | Pre-operational stream | Not available for the August 2021 benchmark event. |
| **False Alerts Removed (Archive)** | **536 / 11,614 hotspots** (4.6%), **26 false zones** | Raw FIRMS archive data | `vegetation_only` filter using FIRMS standard `type` column | Eliminates active volcanoes, offshore points, and static industrial emitters. |
| **False Alerts Removed (Live NRT)** | **519 / 536 industrial points** (96.8%), **29 false zones** | Raw type-less NRT stream | Spatial exclusion via `static_sources.csv` (85 multi-day flare clusters) | Cuts zone count from 180 to 151 with **zero reduction** in EMSR533 recall (0.658) or precision (0.676). |

---

## 3. Copernicus EMS (EMSR533) Ground-Truth Validation

The quantitative reference for burned-area extent is Copernicus Emergency Management Service activation **[EMSR533](https://mapping.emergency.copernicus.eu/activations/EMSR533/)** (August 2021 Kabylie wildfires, AOI01 Tizi Ouzou).

Copernicus mapped the burned scar using optical satellite imagery (Sentinel-2B, SPOT 6/7) across five published vector products. Tracked VIIRS zones are evaluated at the first 12-hour tracking step at or after each satellite observation time:

| Product | Imagery Source | Observation (UTC) | Tracking Step (UTC) | CEMS Reference (ha) | Our Zones (ha) | Recall | Precision | IoU |
|---|---|---|---|---|---|---|---|---|
| **Delineation** | Sentinel-2B (v2) | 2021-08-12 10:40 | 2021-08-12 12:00 | 46,361.5 ha | 48,013.0 ha | **0.65** | **0.63** | **0.47** |
| **Monit01** | SPOT 7 | 2021-08-13 10:27 | 2021-08-13 12:00 | 53,094.0 ha | 51,896.6 ha | **0.66** | **0.67** | **0.50** |
| **Monit02** | SPOT 6 | 2021-08-14 10:21 | 2021-08-14 12:00 | 55,337.1 ha | 52,900.2 ha | **0.66** | **0.69** | **0.51** |
| **Monit03** | SPOT 7 | 2021-08-15 10:12 | 2021-08-15 00:00* | 55,805.4 ha | 53,155.0 ha | **0.66** | **0.69** | **0.51** |
| **Monit04** | SPOT 6/7 | 2021-08-16 10:06 | 2021-08-15 00:00* | 56,158.0 ha | 53,155.0 ha | **0.66** | **0.70** | **0.51** |

*\*Note on Monit03 and Monit04*: Our local FIRMS archive file (`viirs_2021-08-08_2021-08-14.csv`) ends on 14 August at 13:15 UTC. Consequently, our tracked zones remain frozen at 53,155 ha for Monit03 (15 Aug) and Monit04 (16 Aug), evaluated at the last available tracking step.

### Performance Insights
1. **Recall Stability (~66%)**: Using 375 m thermal anomalies alone, the tracking pipeline detects about two-thirds of the total ground scar mapped by sub-10 m optical sensors.
2. **Precision Improvement**: Precision rises from 0.63 to 0.69 between 12 and 14 Aug as our zones and the mapped scar converge. Our data stops on 14 Aug, so Monit03 and Monit04 compare our final zones (53,155 ha) with a reference that is still growing.
3. **Burned Extent Comparison**: At final observation (Monit04), total areas are close (53,155 vs 56,158 ha) but about two thirds overlap (recall 0.66).

---

## 4. Mathematical Formulation

All spatial metrics are calculated in local metric projection (UTM Zone 31N, EPSG:32631) clipped strictly within the Copernicus AOI01 polygon \(A\):

$$R = \text{CEMS Reference Burned Area} \cap A$$
$$Z = \text{Union of Tracked Fire Zones} \cap A$$

*Note: \(Z\) is the spatial union (sum) of all our tracked zones inside AOI01, not a single individual zone.*

- **Recall**: Completeness of burned-area detection:
  $$\text{Recall} = \frac{\text{Area}(Z \cap R)}{\text{Area}(R)}$$

- **Precision**: Spatial purity of tracked zones:
  $$\text{Precision} = \frac{\text{Area}(Z \cap R)}{\text{Area}(Z)}$$

- **Intersection-over-Union (IoU)**: Overall geometric congruence:
  $$\text{IoU} = \frac{\text{Area}(Z \cap R)}{\text{Area}(Z \cup R)}$$

---

## 5. Alert Lead Time & Ingestion Latency

### Alert Lead Time (MTG FCI \(\to\) VIIRS)
- **Status on Benchmark Event**: **Not measured: no MTG data in 2021.**
- **Context**: Meteosat Third Generation (MTG-I1) was launched on December 13, 2022. No MTG active fire observations exist for the August 2021 Kabylie fire event.
- **Pipeline Implementation**: In the live operational pipeline (`src/findfire/live/pipeline.py`), MTG alert lead time is measured dynamically whenever an MTG alert cluster (\(\ge 2\) consecutive scans) is confirmed by a subsequent VIIRS hotspot:
  $$\Delta t_{\text{lead}} = t_{\text{VIIRS confirmation}} - t_{\text{MTG first detected}}$$

### Ingestion Latency
- **VIIRS NRT**: **Within 3 hours** ([NASA FIRMS Documentation](https://www.earthdata.nasa.gov/learn/find-data/near-real-time/firms)). NASA FIRMS specifies that standard Near-Real-Time (NRT) active fire detections from Suomi-NPP and NOAA-20 are processed and distributed within 3 hours of satellite overpass.
- **MTG Live Stream**: **Not measured** on this historical event.

---

## 6. False Alarm Suppression on the Replay Event

Raw satellite detections frequently detect industrial heat sources (oil & gas flaring, refineries, power plants) and duplicate satellite overpasses. FindFire applies three complementary filtering stages:

### 1. Vegetation-Only Filter (`vegetation_only`)
- Standard FIRMS archives carry a ground classification `type`: `0 = vegetation`, `1 = volcano`, `2 = static land source/industry`, `3 = offshore`.
- On the August 2021 Kabylie dataset, dropping non-vegetation records eliminates **536 of 11,614 detections (4.6%)** and suppresses **26 false alarm zones** (180 \(\to\) 154 zones) outside the wildfire perimeter.

### 2. Static Heat Source Mask (`static_sources.csv`)
- **Challenge**: Live NRT feeds do not provide the `type` column.
- **Solution**: `scripts/build_static_mask.py` mines multi-month history to find grid cells active on \(\ge 20\) distinct calendar days, generating a catalog of **85 permanent industrial emitters** across Algeria.
- **Verification on Replay Data**: Evaluated on type-less Kabylie data, the static mask filters out **519 out of 536 industrial hotspots (96.8%)** and reduces zone count from **180 to 151** (29 false zones removed), with **zero impact** on EMSR533 recall (0.658) or precision (0.676).

### 3. Overpass Redetection Deduplication (`mark_redetections`)
- In August 2021, two VIIRS instruments were operational: Suomi-NPP and NOAA-20 (NOAA-21 was launched later, in November 2022).
- Suomi-NPP and NOAA-20 pass over the same area within ~50 minutes of each other.
- The `mark_redetections` filter links subsequent observations of the same pixel by a partner satellite within **3.0 hours** (`REDETECTION_H = 3.0` in `src/findfire/config.py`) to the earlier primary detection, preventing redundant detections of the same fire front from creating separate, duplicated clusters.

---

## 7. How to Reproduce the Validation Results

To run the validation suite against the August 2021 Kabylie ground truth:

```bash
# 1. Run the EMSR533 comparison script
python scripts/Run_Comparison.py --csv data/archive/viirs_2021-08-08_2021-08-14.csv

# 2. Alternatively, run via the unified pipeline runner
python scripts/run_all.py --validate-csv data/archive/viirs_2021-08-08_2021-08-14.csv

# 3. Execute the automated regression tests
pytest -q tests/test_validation.py
```

Validation artifacts are generated in `data/results/`:
- `emsr_validation.csv`: Table of product-by-product numerical results.
- `emsr_metrics.png`: Chart showing precision, recall, and IoU progression.
- `emsr_overlay_Monit04.png`: High-resolution cartographic overlay of tracked zones against the Copernicus EMSR533 burn scar.
