"""External compute adapters and binding factories (Phase 3)."""

from commercial_aircraft.integrations.adapters import AtlasMissionDesk, WingStructuralCaeSnapshot
from commercial_aircraft.integrations.bindings import (
    make_mission_range_margin_binding,
    make_wing_structural_intensity_binding,
)

__all__ = [
    "AtlasMissionDesk",
    "WingStructuralCaeSnapshot",
    "make_mission_range_margin_binding",
    "make_wing_structural_intensity_binding",
]
