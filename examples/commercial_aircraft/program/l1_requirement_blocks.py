"""Level-1 requirement subtree for :class:`~commercial_aircraft.program.cargo_jet_program.CargoJetProgram`.

Each nested :class:`~tg_model.model.elements.RequirementBlock` calls the ThunderGraph authoring API
directly: ``model.requirement(...)``, ``model.requirement_input``,
``model.requirement_attribute`` (derived quantities on the requirement), ``model.requirement_accept_expr``
where executable acceptance is needed, and (from :meth:`CargoJetProgram.define`) ``model.references``
plus ``model.allocate`` / ``model.allocate(..., inputs=...)``.
"""

from __future__ import annotations

from typing import Any

from unitflow.catalogs.si import kg, m

from tg_model.model.elements import RequirementBlock


class L1MissionRequirements(RequirementBlock):
    """Mission / design-closure obligations (executable acceptance on the aircraft part).

    Split into **two** atomic requirements so each has a single verifiable ``shall`` (INCOSE-style
    decomposition): payload mass vs envelope, then design range vs envelope.
    """

    @classmethod
    def define(cls, model: Any) -> None:
        r_payload = model.requirement(
            "req_cargo_design_mission_payload_closure",
            (
                "The notional design mission payload mass shall be less than or equal to the aircraft "
                "modeled maximum payload mass for the declared mass envelope (verification by analysis)."
            ),
            rationale=(
                "Atomic mass-side mission obligation; executable acceptance compares scenario payload to "
                "rolled-up envelope on the allocated aircraft block."
            ),
        )
        scenario_payload = model.requirement_input(r_payload, "scenario_payload", unit=kg)
        envelope_payload = model.requirement_input(r_payload, "envelope_payload", unit=kg)
        payload_margin_kg = model.requirement_attribute(
            r_payload,
            "payload_margin_kg",
            expr=envelope_payload - scenario_payload,
            unit=kg,
        )
        model.requirement_accept_expr(
            r_payload,
            expr=payload_margin_kg >= 0 * kg,
        )

        r_range = model.requirement(
            "req_cargo_design_mission_range_closure",
            (
                "The notional design mission range shall be less than or equal to the aircraft modeled "
                "maximum design range for the declared range envelope (verification by analysis)."
            ),
            rationale=(
                "Atomic range-side mission obligation; executable acceptance compares scenario range to "
                "the modeled design-range envelope on the allocated aircraft block."
            ),
        )
        scenario_range = model.requirement_input(r_range, "scenario_range", unit=m)
        envelope_range = model.requirement_input(r_range, "envelope_range", unit=m)
        range_margin_m = model.requirement_attribute(
            r_range,
            "range_margin_m",
            expr=envelope_range - scenario_range,
            unit=m,
        )
        model.requirement_accept_expr(
            r_range,
            expr=range_margin_m >= 0 * m,
        )


class L1AirworthinessRequirements(RequirementBlock):
    """Regulatory and methodology framing (text + citations; no executable acceptance in this slice)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.requirement(
            "req_transport_category_part25",
            (
                "The notional product shall be scoped to transport-category airworthiness expectations "
                "consistent with 14 CFR Part 25; modeled values and constraints are illustrative and not a "
                "substitute for certification data."
            ),
            rationale=(
                "Frames regulatory context for the example; allocation to the program root emphasizes "
                "program-wide applicability before subsystem decomposition."
            ),
        )
        model.requirement(
            "req_flight_test_methodology_alignment",
            (
                "High-level performance demonstration intent for the notional program shall align with the "
                "flight-test performance philosophy described in FAA AC 25-7C (not a complete test program)."
            ),
            rationale=(
                "Methodological citation only; allocated to program root as cross-cutting program context."
            ),
        )


class L1ProductRequirements(RequirementBlock):
    """Configuration and traceability obligations on the vehicle block."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.requirement(
            "req_airport_planning_representative",
            (
                "The aircraft configuration shall remain representative of wide-body cargo operations for "
                "airport planning purposes (order-of-magnitude compatibility with public planning categories); "
                "the model does not reproduce OEM planning figures."
            ),
            rationale=(
                "Links high-level configuration to ACAPS-style public references without claiming OEM data "
                "for Atlas-400F."
            ),
        )
        model.requirement(
            "req_verification_traceability",
            (
                "Demonstrated mass and performance results in the model shall be traceable to declared "
                "parameters, computed attributes, or constraints under the allocated aircraft block."
            ),
            rationale=(
                "Verifiability / traceability obligation for MBSE credibility; supports audit-style reading "
                "of the evaluation report."
            ),
        )


class L1RequirementsRoot(RequirementBlock):
    """Top-level Level-1 grouping: mission, airworthiness context, product-level requirements."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.requirement_block("mission", L1MissionRequirements)
        model.requirement_block("airworthiness", L1AirworthinessRequirements)
        model.requirement_block("product", L1ProductRequirements)
