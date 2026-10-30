# Copernicus EMS EMSR533 Burned Area & Fire Growth

**Event**: August 2021 Wildfires, Kabylie, Algeria  
**Copernicus EMS Activation**: [EMSR533 (AOI01 Tizi Ouzou)](https://mapping.emergency.copernicus.eu/activations/EMSR533/)  
**Data Sources**: Vector packages under `data/emsr533/`, validated in `data/results/emsr_validation.csv`

---

## 1. Burned Area Progression Table

| Product | Satellite Sensor | Acquisition Date & Time (UTC) | Burned Area (ha) | Burned Area ($\text{km}^2$) | Daily Growth ($\Delta$ ha) | Daily Growth (%) | Hourly Growth Rate |
|---|---|---|---|---|---|---|---|
| **Delineation** | Sentinel-2B (v2) | **2021-08-12 10:40** | **46,361.5 ha** | 463.6 $\text{km}^2$ | — | — | Baseline mapping |
| **Monit01** | SPOT 7 | **2021-08-13 10:27** | **53,094.0 ha** | 530.9 $\text{km}^2$ | **+6,732.5 ha** | +14.5% | **~283 ha/h** |
| **Monit02** | SPOT 6 | **2021-08-14 10:21** | **55,337.1 ha** | 553.4 $\text{km}^2$ | **+2,243.1 ha** | +4.2% | **~94 ha/h** |
| **Monit03** | SPOT 7 | **2021-08-15 10:12** | **55,805.4 ha** | 558.1 $\text{km}^2$ | **+468.3 ha** | +0.8% | **~20 ha/h** |
| **Monit04** | SPOT 6/7 | **2021-08-16 10:06** | **56,158.0 ha** | 561.6 $\text{km}^2$ | **+352.6 ha** | +0.6% | **~15 ha/h** |

*Note on Sensor Transition*: Delineation was produced using Sentinel-2B imagery (10 m resolution), whereas Monit01 through Monit04 were produced using high-resolution SPOT 6/7 optical imagery (1.5 m resolution). Part of the apparent growth and boundary difference between Delineation and Monit01 comes from the change of satellite sensor and spatial resolution.

---

## 2. Growth Phases & Fire Dynamics

1. **Initial Observed Expansion (12 Aug 10:40 \(\to\) 13 Aug 10:27 UTC)**:
   * **Observed Growth**: **+6,732.5 ha** in 23h 47m (**~283 ha/hour**).
   * **Note**: Reflects both active fire progression and finer perimeter delineation from the higher-resolution SPOT 7 sensor.

2. **Deceleration Phase (13 Aug 10:27 \(\to\) 14 Aug 10:21 UTC)**:
   * **Observed Growth**: **+2,243.1 ha** in 23h 54m (**~94 ha/hour**).
   * **Note**: Growth slowed down significantly compared to the initial 24 hours.

3. **Stabilization & Containment (14 Aug 10:21 \(\to\) 16 Aug 10:06 UTC)**:
   * **Observed Growth**: **+468.3 ha** on Aug 15 (~20 ha/h) and **+352.6 ha** on Aug 16 (~15 ha/h).
   * **Note**: Perimeter expansion largely leveled off as the active fire front ceased major forward progression.

---

## 3. Comparison with Tracked Zones

- In all validation evaluations, the Copernicus reference area is compared with the **sum (union) of all our tracked zones clipped inside the AOI01 boundary**, not a single isolated zone.
- Our local FIRMS archive dataset (`viirs_2021-08-08_2021-08-14.csv`) ends on August 14 at 13:15 UTC. Consequently, our tracked zones reach **52,900 ha** at Monit02 (Aug 14) and remain frozen at **53,155 ha** for Monit03 and Monit04.
- Total areas are close (53,155 ha tracked vs. 56,158 ha reference at Monit04), with about two-thirds spatial overlap (recall ~0.66).

---

## 4. Optical Ground Truth vs. Thermal Hotspots

- **Optical Sensors (Sentinel-2, SPOT 6/7)**: Map the persistent charcoal and ash scar on the ground at high spatial resolution (1.5 m to 10 m). Even after active flaming subsides, the mapped scar remains visible.
- **Thermal Hotspots (VIIRS 375 m)**: Detect instantaneous radiant heat emissions during satellite overpasses (a few per day, two VIIRS satellites in 2021). Areas that burn rapidly between overpasses or smolder with lower radiative energy can be missed initially, making optical ground-truth perimeters a more reliable benchmark for measuring total cumulative growth.
