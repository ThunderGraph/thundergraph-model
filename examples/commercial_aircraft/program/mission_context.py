"""Scenario and citation identifiers for the cargo jet example (strings only — no tg_model import)."""

from __future__ import annotations

# Scenario parameters declared on :class:`CargoJetProgram` (names must match ``model.parameter``).
SCENARIO_PAYLOAD_MASS_KG = "scenario_payload_mass_kg"
SCENARIO_DESIGN_RANGE_M = "scenario_design_range_m"

# Mission desk (external compute binding on program root).
MISSION_DESK_BASELINE_MAX_RANGE_M = "mission_desk_baseline_max_range_m"
MISSION_RANGE_MARGIN_M = "mission_range_margin_m"

# Aircraft envelope / weight book (names match ``model.parameter`` / ``model.attribute`` on ``Aircraft``).
AIRCRAFT_MODELED_MAX_DESIGN_RANGE_M = "modeled_max_design_range_m"
AIRCRAFT_NOTIONAL_MZFW_KG = "notional_mzfw_kg"
AIRCRAFT_NOTIONAL_MTOW_KG = "notional_mtow_kg"
AIRCRAFT_NOTIONAL_TRIP_FUEL_KG = "notional_trip_fuel_kg"
# Derived on ``Aircraft`` but bound via ``allocate`` inputs for L1 acceptance.
AIRCRAFT_MODELED_MAX_PAYLOAD_KG = "modeled_max_payload_kg"
AIRCRAFT_OPERATING_EMPTY_MASS_KG = "operating_empty_mass_kg"

# Citation node names in ``CargoJetProgram.define()`` (for cross-references in docs/tests).
CITATION_ACAPS = "c_acaps"
CITATION_FAR25 = "c_far25"
CITATION_AC25_7C = "c_ac25_7c"

# Retrieved date for citation metadata (ISO 8601 date) — update when URIs are re-validated.
CITATION_RETRIEVED_ISO = "2025-03-25"
