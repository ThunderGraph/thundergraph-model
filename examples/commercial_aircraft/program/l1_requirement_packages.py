"""Level-1 composable requirement packages for :class:`~commercial_aircraft.program.cargo_jet_program.CargoJetProgram`.

Each nested :class:`~tg_model.model.elements.Requirement` uses the full composable surface from the
requirement-composition plan: **package-level** ``model.parameter``, ``model.attribute``, and
``model.constraint`` where the package owns shared policy values; **leaf** ``model.requirement``,
``model.requirement_input``, ``model.requirement_attribute``, ``model.requirement_accept_expr`` for
atomic acceptance; ``model.requirement_package`` for nested groupings; and (from
:meth:`CargoJetProgram.define`) ``model.references`` plus ``model.allocate`` /
``model.allocate(..., inputs=...)``.
"""

from __future__ import annotations

from typing import Any

from unitflow.catalogs.si import kg, m

from tg_model.model.elements import Requirement


class L1MissionRequirements(Requirement):
    """Mission / design-closure obligations (executable acceptance on the aircraft part).

    Split into **two** atomic requirements so each has a single verifiable ``shall`` (INCOSE-style
    decomposition): payload mass vs envelope, then design range vs envelope.

    **Package-level** ``parameter`` / ``attribute`` / ``constraint`` below are illustrative policy
    slots for the mission-closure *package* (not wired through ``allocate``): they show the same
    value/check authoring surface as a ``Part``. Unlike a root ``System``, a composable
    requirement package may own attributes and constraints directly.
    """

    @classmethod
    def define(cls, model: Any) -> None:
        # --- Package-owned value surface (plan in-scope: parameter / attribute / constraint) ---
        reserved_operational_buffer_kg = model.parameter(
            "reserved_operational_buffer_kg",
            unit=kg,
            required=True,
        )
        reporting_headroom_kg = model.attribute(
            "reporting_headroom_kg",
            unit=kg,
            expr=reserved_operational_buffer_kg,
        )
        model.constraint(
            "mission_package_reserved_buffer_non_negative",
            expr=reporting_headroom_kg >= 0 * kg,
        )

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


class L1AirworthinessRequirements(Requirement):
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


class L1ProductRequirements(Requirement):
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


class L1RequirementsRoot(Requirement):
    """Top-level Level-1 grouping: mission, airworthiness context, product-level requirements."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.requirement_package("mission", L1MissionRequirements)
        model.requirement_package("airworthiness", L1AirworthinessRequirements)
        model.requirement_package("product", L1ProductRequirements)
