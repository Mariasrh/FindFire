"""Water demand estimation for a fire zone.

WARNING: every rate below is a PLACEHOLDER. Replace them with sourced
values (see docs/references.md) before the final report.
"""
import math
from dataclasses import dataclass

HA_TO_M2 = 10_000

# rate_l_min_m2: water applied per minute on the active fire front
# band_m: width of the active front we try to extinguish
TERRAIN_PARAMS = {
    "forest": {"rate_l_min_m2": 0.5, "band_m": 50},
    "scrub": {"rate_l_min_m2": 0.4, "band_m": 30},
    "crop": {"rate_l_min_m2": 0.2, "band_m": 20},
    "urban": {"rate_l_min_m2": 2.0, "band_m": 20},
}

SAFETY_FACTOR = 1.2
STRONG_WIND_KMH = 30
STRONG_WIND_FACTOR = 1.2
DEFAULT_DURATION_MIN = 60


@dataclass
class WaterDemand:
    flow_l_min: float
    volume_l: float
    severity: str


def severity_from_area(area_ha: float) -> str:
    """Simple severity levels based on fire area (placeholder thresholds)."""
    if area_ha < 10:
        return "low"
    if area_ha < 200:
        return "medium"
    return "critical"


def front_area_m2(area_m2: float, band_m: float) -> float:
    """Area of the active fire front: a band of width band_m around the
    perimeter, estimated from the area assuming a roughly circular zone."""
    perimeter_m = 2 * math.sqrt(math.pi * area_m2)
    return min(area_m2, perimeter_m * band_m)


def compute_water_demand(
    area_ha: float,
    terrain: str = "forest",
    duration_min: int = DEFAULT_DURATION_MIN,
    wind_kmh: float = 0.0,
) -> WaterDemand:
    """Return flow (L/min), total volume (L) and severity for a fire zone."""
    if terrain not in TERRAIN_PARAMS:
        raise ValueError(f"Unknown terrain '{terrain}'. Use one of {list(TERRAIN_PARAMS)}")
    if area_ha < 0:
        raise ValueError("area_ha must be positive")

    params = TERRAIN_PARAMS[terrain]
    area_m2 = area_ha * HA_TO_M2
    factor = SAFETY_FACTOR * (STRONG_WIND_FACTOR if wind_kmh >= STRONG_WIND_KMH else 1.0)

    flow = front_area_m2(area_m2, params["band_m"]) * params["rate_l_min_m2"] * factor
    return WaterDemand(
        flow_l_min=round(flow, 1),
        volume_l=round(flow * duration_min, 1),
        severity=severity_from_area(area_ha),
    )