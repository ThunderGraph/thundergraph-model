"""L1 requirement subtree authoring (RequirementBlock types) for :class:`CargoJetProgram`.

Requirement **text** and allocation metadata live in :mod:`commercial_aircraft.program.l1_specs`
(stdlib only). This module registers nested ``RequirementBlock`` types and attaches acceptance for the
mission-closure slice via ``requirement_input`` + ``requirement_accept_expr`` and
``allocate(..., inputs=...)`` on the program root.
"""

from __future__ import annotations

from typing import Any

from commercial_aircraft.program.l1_specs import L1_REQUIREMENTS
from unitflow.catalogs.si import kg, m

from tg_model.model.elements import RequirementBlock

_SPECS = {s.node_name: s for s in L1_REQUIREMENTS}


class L1MissionRequirements(RequirementBlock):
    """Mission / showcase-thesis obligations."""

    @classmethod
    def define(cls, model: Any) -> None:
        spec = _SPECS["req_cargo_design_mission_closure"]
        r = model.requirement(spec.node_name, spec.statement, rationale=spec.rationale)
        scenario_payload = model.requirement_input(r, "scenario_payload", unit=kg)
        scenario_range = model.requirement_input(r, "scenario_range", unit=m)
        envelope_payload = model.requirement_input(r, "envelope_payload", unit=kg)
        envelope_range = model.requirement_input(r, "envelope_range", unit=m)
        model.requirement_accept_expr(
            r,
            expr=(scenario_payload <= envelope_payload)
            & (scenario_range <= envelope_range),
        )


class L1AirworthinessRequirements(RequirementBlock):
    """Regulatory and methodology framing (text + allocate; no executable acceptance in Phase 1)."""

    @classmethod
    def define(cls, model: Any) -> None:
        for key in ("req_transport_category_part25", "req_flight_test_methodology_alignment"):
            spec = _SPECS[key]
            model.requirement(spec.node_name, spec.statement, rationale=spec.rationale)


class L1ProductRequirements(RequirementBlock):
    """Configuration and traceability obligations on the vehicle block."""

    @classmethod
    def define(cls, model: Any) -> None:
        for key in ("req_airport_planning_representative", "req_verification_traceability"):
            spec = _SPECS[key]
            model.requirement(spec.node_name, spec.statement, rationale=spec.rationale)


class L1RequirementsRoot(RequirementBlock):
    """Top-level L1 grouping: mission, airworthiness context, product-level requirements."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.requirement_block("mission", L1MissionRequirements)
        model.requirement_block("airworthiness", L1AirworthinessRequirements)
        model.requirement_block("product", L1ProductRequirements)
