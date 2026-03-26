"""L1 requirement records for Atlas-400F (stdlib only — safe to import without ``tg_model``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AllocateTarget = Literal["program_root", "aircraft"]
RequirementBlockSegment = Literal["mission", "airworthiness", "product"]
L1VerificationKind = Literal["executable_acceptance", "evidenced_by_constraints", "context_citations_only"]
"""How evaluation demonstrates the requirement: executable expr, supporting constraints, or citations only."""


@dataclass(frozen=True)
class L1RequirementSpec:
    """One L1 requirement: model node name, text, rationale, provenance, allocation intent."""

    node_name: str
    statement: str
    rationale: str
    citation_ids: tuple[str, ...]
    allocate_to: AllocateTarget
    """Where ``model.allocate`` should point: the configured program root or the ``aircraft`` part."""
    block: RequirementBlockSegment
    """Nested block under ``l1`` in :class:`~commercial_aircraft.program.l1_requirement_blocks.L1RequirementsRoot`."""
    verification_kind: L1VerificationKind
    """What a green run means: executable acceptance, supporting constraints/attributes, or context only (not a cert claim)."""
    mission_closure_acceptance: bool = False
    """If True, :class:`~commercial_aircraft.program.cargo_jet_program.CargoJetProgram` wires ``allocate(..., inputs=…)`` for executable acceptance."""


L1_REQUIREMENTS: tuple[L1RequirementSpec, ...] = (
    L1RequirementSpec(
        node_name="req_cargo_design_mission_closure",
        statement=(
            "The Atlas-400F program shall demonstrate, using the parameterized vehicle model, that the "
            "notional design mission defined by scenario payload mass and design range can be evaluated "
            "for feasibility against the aircraft mass and performance envelope (verification by analysis "
            "using model parameters, attributes, and constraints)."
        ),
        rationale=(
            "Singular program-level mission obligation; drives the showcase thesis (range-payload / "
            "mass closure). Allocated to the aircraft block where roll-ups and constraints will live."
        ),
        citation_ids=("c_far25", "c_ac25_7c"),
        allocate_to="aircraft",
        block="mission",
        verification_kind="executable_acceptance",
        mission_closure_acceptance=True,
    ),
    L1RequirementSpec(
        node_name="req_transport_category_part25",
        statement=(
            "The notional product shall be scoped to transport-category airworthiness expectations "
            "consistent with 14 CFR Part 25; modeled values and constraints are illustrative and not a "
            "substitute for certification data."
        ),
        rationale=(
            "Frames regulatory context for the example; allocation to the program root emphasizes "
            "program-wide applicability before subsystem decomposition."
        ),
        citation_ids=("c_far25",),
        allocate_to="program_root",
        block="airworthiness",
        verification_kind="context_citations_only",
    ),
    L1RequirementSpec(
        node_name="req_airport_planning_representative",
        statement=(
            "The aircraft configuration shall remain representative of wide-body cargo operations for "
            "airport planning purposes (order-of-magnitude compatibility with public planning categories); "
            "the model does not reproduce OEM planning figures."
        ),
        rationale=(
            "Links high-level configuration to ACAPS-style public references without claiming OEM data "
            "for Atlas-400F."
        ),
        citation_ids=("c_acaps", "c_far25"),
        allocate_to="aircraft",
        block="product",
        verification_kind="context_citations_only",
    ),
    L1RequirementSpec(
        node_name="req_verification_traceability",
        statement=(
            "Demonstrated mass and performance results in the model shall be traceable to declared "
            "parameters, computed attributes, or constraints under the allocated aircraft block."
        ),
        rationale=(
            "Verifiability / traceability obligation for MBSE credibility; supports audit-style reading "
            "of the evaluation report."
        ),
        citation_ids=("c_far25", "c_ac25_7c"),
        allocate_to="aircraft",
        block="product",
        verification_kind="evidenced_by_constraints",
    ),
    L1RequirementSpec(
        node_name="req_flight_test_methodology_alignment",
        statement=(
            "High-level performance demonstration intent for the notional program shall align with the "
            "flight-test performance philosophy described in FAA AC 25-7C (not a complete test program)."
        ),
        rationale=(
            "Methodological citation only; allocated to program root as cross-cutting program context."
        ),
        citation_ids=("c_ac25_7c",),
        allocate_to="program_root",
        block="airworthiness",
        verification_kind="context_citations_only",
    ),
)


def iter_l1_requirements() -> tuple[L1RequirementSpec, ...]:
    """Return the frozen L1 requirement tuple (iterable for define() registration)."""
    return L1_REQUIREMENTS


__all__ = [
    "AllocateTarget",
    "L1_REQUIREMENTS",
    "L1RequirementSpec",
    "L1VerificationKind",
    "RequirementBlockSegment",
    "iter_l1_requirements",
]
