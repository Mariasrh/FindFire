"""Water demand estimation for a fire zone.

Model (to be stated as assumptions in the report):
- Crews cannot attack a whole fire perimeter at once. They treat a limited
  length of the fire front, capped by `max_front_attacked_m`.
- Water is applied per metre of front attacked (`water_l_min_per_m_front`).
- The fire perimeter is estimated from the area, assuming a roughly circular
  zone. Real fires are elongated, so this is a lower bound.

WARNING: ALL numeric parameters below are PLACEHOLDERS, to be confirmed with
sourced values (Protection Civile guidelines, firefighting literature) and
written with their source in docs/references.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

HA_TO_M2 = 10_000

# Placeholder parameters per terrain (TO BE CONFIRMED).
TERRAIN_PARAMS = {
    "forest": {"water_l_min_per_m_front": 10.0, "max_front_attacked_m": 2000},
    "scrub": {"water_l_min_per_m_front": 8.0, "max_front_attacked_m": 2000},
    "crop": {"water_l_min_per_m_front": 5.0, "max_front_attacked_m": 1500},
    "urban": {"water_l_min_per_m_front": 20.0, "max_front_attacked_m": 500},
}

SAFETY_FACTOR = 1.2
STRONG_WIND_KMH = 30
STRONG_WIND_FACTOR = 1.2
DEFAULT_DURATION_MIN = 60
PARAMETERS_STATUS = "placeholder, to be confirmed"


@dataclass
class WaterDemand:
    flow_l_min: float
    volume_l: float
    severity: str
    perimeter_m: float
    front_attacked_m: float
    front_share: float          # share of the perimeter that can be attacked (0 to 1)
    parameters_status: str = PARAMETERS_STATUS


def severity_from_area(area_ha: float) -> str:
    """Simple severity levels based on fire area (placeholder thresholds)."""
    if area_ha < 10:
        return "low"
    if area_ha < 200:
        return "medium"
    return "critical"


def perimeter_m_from_area(area_m2: float) -> float:
    """Perimeter of a circle with this area."""
    return 2 * math.sqrt(math.pi * area_m2)


def compute_water_demand(
    area_ha: float,
    terrain: str = "forest",
    duration_min: int = DEFAULT_DURATION_MIN,
    wind_kmh: float = 0.0,
) -> WaterDemand:
    """Return flow (L/min), total volume (L), severity and front details."""
    if terrain not in TERRAIN_PARAMS:
        raise ValueError(f"Unknown terrain '{terrain}'. Use one of {list(TERRAIN_PARAMS)}")
    if area_ha < 0:
        raise ValueError("area_ha must be positive")

    params = TERRAIN_PARAMS[terrain]
    perimeter = perimeter_m_from_area(area_ha * HA_TO_M2)
    attacked = min(perimeter, params["max_front_attacked_m"])
    factor = SAFETY_FACTOR * (STRONG_WIND_FACTOR if wind_kmh >= STRONG_WIND_KMH else 1.0)

    flow = attacked * params["water_l_min_per_m_front"] * factor
    return WaterDemand(
        flow_l_min=round(flow, 1),
        volume_l=round(flow * duration_min, 1),
        severity=severity_from_area(area_ha),
        perimeter_m=round(perimeter, 1),
        front_attacked_m=round(attacked, 1),
        front_share=round(attacked / perimeter, 3) if perimeter > 0 else 0.0,
    )