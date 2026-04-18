"""Level-1 composable requirement packages for :class:`~commercial_aircraft.program.cargo_jet_program.CargoJetProgram`.

Each :class:`~tg_model.model.elements.Requirement` subclass uses the package-level surface:
``model.parameter``, ``model.attribute``, ``model.constraint``, and ``model.composed_of``
for nesting sub-packages.  All executable acceptance lives in ``model.constraint`` on the
relevant leaf package.
"""

from __future__ import annotations

from typing import Any

from unitflow.catalogs.si import kg, m

from tg_model.model.elements import Requirement


# ---------------------------------------------------------------------------
# Mission closure — two atomic leaf packages
# ---------------------------------------------------------------------------


class MissionPayloadClosureRequirement(Requirement):
    """Scenario payload mass vs aircraft modeled maximum payload envelope."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("mission_payload_closure")
        model.doc(
            "The notional design mission payload mass shall be less than or equal to the aircraft "
            "modeled maximum payload mass for the declared mass envelope (verification by analysis)."
        )
        scenario_payload = model.parameter("scenario_payload", unit=kg)
        envelope_payload = model.parameter("envelope_payload", unit=kg)
        payload_margin = model.attribute(
            "payload_margin_kg",
            unit=kg,
            expr=envelope_payload - scenario_payload,
        )
        model.constraint("payload_margin_non_negative", expr=payload_margin >= 0 * kg)


class MissionRangeClosureRequirement(Requirement):
    """Scenario design range vs aircraft modeled maximum design range envelope."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("mission_range_closure")
        model.doc(
            "The notional design mission range shall be less than or equal to the aircraft modeled "
            "maximum design range for the declared range envelope (verification by analysis)."
        )
        scenario_range = model.parameter("scenario_range", unit=m)
        envelope_range = model.parameter("envelope_range", unit=m)
        range_margin = model.attribute(
            "range_margin_m",
            unit=m,
            expr=envelope_range - scenario_range,
        )
        model.constraint("range_margin_non_negative", expr=range_margin >= 0 * m)


class L1MissionRequirements(Requirement):
    """Mission / design-closure obligations (executable acceptance on the aircraft part).

    The package-level ``reserved_operational_buffer_kg`` parameter and its associated
    constraint are illustrative policy slots owned by the mission package (not wired
    through ``allocate``).
    """

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("l1_mission_requirements")
        model.doc(
            "Mission-closure Level-1 obligations: payload and range scenario shall close "
            "against the declared aircraft performance envelope."
        )
        reserved = model.parameter("reserved_operational_buffer_kg", unit=kg, required=True)
        headroom = model.attribute("reporting_headroom_kg", unit=kg, expr=reserved)
        model.constraint(
            "mission_package_reserved_buffer_non_negative",
            expr=headroom >= 0 * kg,
        )
        model.composed_of("payload_closure", MissionPayloadClosureRequirement)
        model.composed_of("range_closure", MissionRangeClosureRequirement)


# ---------------------------------------------------------------------------
# Airworthiness context — text-only leaf packages
# ---------------------------------------------------------------------------


class TransportCategoryPart25Requirement(Requirement):
    """Regulatory context: 14 CFR Part 25 applicability statement."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("transport_category_part25")
        model.doc(
            "The notional product shall be scoped to transport-category airworthiness expectations "
            "consistent with 14 CFR Part 25; modeled values and constraints are illustrative and not a "
            "substitute for certification data."
        )


class FlightTestMethodologyAlignmentRequirement(Requirement):
    """Methodological alignment with FAA AC 25-7C flight-test performance philosophy."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("flight_test_methodology_alignment")
        model.doc(
            "High-level performance demonstration intent for the notional program shall align with the "
            "flight-test performance philosophy described in FAA AC 25-7C (not a complete test program)."
        )


class L1AirworthinessRequirements(Requirement):
    """Regulatory and methodology framing (text + citations; no executable acceptance in this slice)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("l1_airworthiness_requirements")
        model.doc(
            "Airworthiness context obligations framing regulatory scope and methodology for the "
            "notional Atlas-400F program."
        )
        model.composed_of("part25", TransportCategoryPart25Requirement)
        model.composed_of("flight_test", FlightTestMethodologyAlignmentRequirement)


# ---------------------------------------------------------------------------
# Product configuration obligations — text-only leaf packages
# ---------------------------------------------------------------------------


class AirportPlanningRepresentativeRequirement(Requirement):
    """Configuration representative of wide-body cargo airport-planning categories."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("airport_planning_representative")
        model.doc(
            "The aircraft configuration shall remain representative of wide-body cargo operations for "
            "airport planning purposes (order-of-magnitude compatibility with public planning categories); "
            "the model does not reproduce OEM planning figures."
        )


class VerificationTraceabilityRequirement(Requirement):
    """Traceability of demonstrated mass and performance results to declared model inputs."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("verification_traceability")
        model.doc(
            "Demonstrated mass and performance results in the model shall be traceable to declared "
            "parameters, computed attributes, or constraints under the allocated aircraft block."
        )


class L1ProductRequirements(Requirement):
    """Configuration and traceability obligations on the vehicle block."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("l1_product_requirements")
        model.doc(
            "Product-level configuration and traceability obligations for the notional Atlas-400F."
        )
        model.composed_of("airport_planning", AirportPlanningRepresentativeRequirement)
        model.composed_of("verification_traceability", VerificationTraceabilityRequirement)


# ---------------------------------------------------------------------------
# Root package
# ---------------------------------------------------------------------------


class L1RequirementsRoot(Requirement):
    """Top-level Level-1 grouping: mission, airworthiness context, product-level requirements."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("l1_requirements_root")
        model.doc(
            "Level-1 requirement tree for the Atlas-400F notional cargo jet program: mission "
            "closure, airworthiness context, and product configuration obligations."
        )
        model.composed_of("mission", L1MissionRequirements)
        model.composed_of("airworthiness", L1AirworthinessRequirements)
        model.composed_of("product", L1ProductRequirements)
