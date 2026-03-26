"""Build plain dicts from :class:`~tg_model.execution.configured_model.ConfiguredModel` + evaluation results.

**Demo coupling:** :func:`_external_provenance_by_slot` and ``slot_states_summary`` read
private ``_slot_records`` on :class:`~tg_model.execution.run_context.RunContext` That is
acceptable for this example’s reporting only — not a stable framework API.
"""

from __future__ import annotations

from typing import Any

from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.evaluator import RunResult
from tg_model.execution.run_context import RunContext, SlotState

# Rows for the printed "Level-1 requirements" table only. Requirement text lives in
# ``commercial_aircraft.program.l1_requirement_blocks`` — keep ``node_name`` and ``statement`` aligned.
_L1_REPORT_ROWS: tuple[dict[str, Any], ...] = (
    {
        "node_name": "req_cargo_design_mission_payload_closure",
        "block": "mission",
        "allocate_to": "aircraft",
        "verification_kind": "executable_acceptance",
        "mission_closure_acceptance": True,
        "statement": (
            "The notional design mission payload mass shall be less than or equal to the aircraft modeled "
            "maximum payload mass for the declared mass envelope (verification by analysis)."
        ),
    },
    {
        "node_name": "req_cargo_design_mission_range_closure",
        "block": "mission",
        "allocate_to": "aircraft",
        "verification_kind": "executable_acceptance",
        "mission_closure_acceptance": True,
        "statement": (
            "The notional design mission range shall be less than or equal to the aircraft modeled maximum "
            "design range for the declared range envelope (verification by analysis)."
        ),
    },
    {
        "node_name": "req_transport_category_part25",
        "block": "airworthiness",
        "allocate_to": "program_root",
        "verification_kind": "context_citations_only",
        "mission_closure_acceptance": False,
        "statement": (
            "The notional product shall be scoped to transport-category airworthiness expectations "
            "consistent with 14 CFR Part 25; modeled values and constraints are illustrative and not a "
            "substitute for certification data."
        ),
    },
    {
        "node_name": "req_airport_planning_representative",
        "block": "product",
        "allocate_to": "aircraft",
        "verification_kind": "context_citations_only",
        "mission_closure_acceptance": False,
        "statement": (
            "The aircraft configuration shall remain representative of wide-body cargo operations for "
            "airport planning purposes (order-of-magnitude compatibility with public planning categories); "
            "the model does not reproduce OEM planning figures."
        ),
    },
    {
        "node_name": "req_verification_traceability",
        "block": "product",
        "allocate_to": "aircraft",
        "verification_kind": "evidenced_by_constraints",
        "mission_closure_acceptance": False,
        "statement": (
            "Demonstrated mass and performance results in the model shall be traceable to declared "
            "parameters, computed attributes, or constraints under the allocated aircraft block."
        ),
    },
    {
        "node_name": "req_flight_test_methodology_alignment",
        "block": "airworthiness",
        "allocate_to": "program_root",
        "verification_kind": "context_citations_only",
        "mission_closure_acceptance": False,
        "statement": (
            "High-level performance demonstration intent for the notional program shall align with the "
            "flight-test performance philosophy described in FAA AC 25-7C (not a complete test program)."
        ),
    },
)


_ENVELOPE_CONSTRAINT_NAMES = frozenset(
    {
        "notional_takeoff_mass_closure",
        "design_mission_payload_within_structural_envelope",
        "design_mission_range_within_modeled_envelope",
    },
)


def _qty_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _length_m_human(value: Any) -> str:
    """Format a length quantity stored in metres for humans (km primary, m in parentheses)."""
    if value is None or not hasattr(value, "magnitude"):
        return ""
    m_val = float(value.magnitude)
    km = m_val / 1000.0
    return f"{km:,.1f} km ({m_val:,.0f} m)"


def _external_provenance_by_slot(ctx: RunContext) -> dict[str, Any]:
    """Collect non-trivial provenance from the run (external compute attaches dict provenance)."""
    out: dict[str, Any] = {}
    for sid, rec in ctx._slot_records.items():
        if not rec.is_ready:
            continue
        prov = rec.provenance
        if prov in (None, "computed", "input"):
            continue
        out[sid] = prov
    return out


def extract_cargo_jet_evaluation_report(
    cm: ConfiguredModel,
    ctx: RunContext,
    run_result: RunResult,
) -> dict[str, Any]:
    """Flatten scenario, thesis metrics, roll-ups, constraints, and Level-1 metadata for reporting."""
    specs = _L1_REPORT_ROWS
    ac = cm.aircraft
    outputs = dict(run_result.outputs)
    margin_id = cm.mission_range_margin_m.stable_id
    margin = outputs.get(margin_id)

    constraints = [
        {
            "name": c.name,
            "passed": c.passed,
            "requirement_path": c.requirement_path,
            "allocation_target_path": c.allocation_target_path,
            "evidence": c.evidence,
        }
        for c in run_result.constraint_results
    ]

    env_constraints = [
        c for c in constraints if c["name"].rsplit(".", 1)[-1] in _ENVELOPE_CONSTRAINT_NAMES
    ]
    envelope_ok = len(env_constraints) == len(_ENVELOPE_CONSTRAINT_NAMES) and all(
        c["passed"] for c in env_constraints
    )

    margin_km = ""
    if margin is not None and hasattr(margin, "magnitude"):
        margin_km = f"{float(margin.magnitude) / 1000.0:,.1f} km"

    spec_rows = list(specs)

    scenario_range = outputs.get(cm.scenario_design_range_m.stable_id)
    modeled_range = outputs.get(ac.modeled_max_design_range_m.stable_id)
    baseline = outputs.get(cm.mission_desk_baseline_max_range_m.stable_id)

    return {
        "evaluation_passed": run_result.passed,
        "failures": list(run_result.failures),
        "thesis": {
            "narrative": (
                "The demo uses two independent ideas: (1) **Mission desk** — a toy external scaling model "
                "produces `mission_range_margin_m` and `mission_range_margin_non_negative` checks it. "
                "(2) **Declared envelope** — scenario payload/range are compared to rolled-up masses and "
                "parameters (`notional_takeoff_mass_closure`, payload/range vs envelope). "
                "Passing both is not a single physics closure; it is stitched verification for teaching."
            ),
            "mission_range_margin_m": _qty_str(margin),
            "mission_range_margin_km": margin_km,
            "margin_non_negative": bool(margin is not None and margin.magnitude >= 0)
            if hasattr(margin, "magnitude")
            else False,
            "declared_envelope_constraints_passed": envelope_ok,
        },
        "scenario": {
            "scenario_payload_mass_kg": _qty_str(outputs.get(cm.scenario_payload_mass_kg.stable_id)),
            "scenario_design_range_m": _qty_str(scenario_range),
            "scenario_design_range_human": _length_m_human(scenario_range),
            "mission_desk_baseline_max_range_m": _qty_str(baseline),
            "mission_desk_baseline_human": _length_m_human(baseline),
        },
        "aircraft": {
            "operating_empty_mass_kg": _qty_str(outputs.get(ac.operating_empty_mass_kg.stable_id)),
            "modeled_max_payload_kg": _qty_str(outputs.get(ac.modeled_max_payload_kg.stable_id)),
            "modeled_max_design_range_m": _qty_str(modeled_range),
            "modeled_max_design_range_human": _length_m_human(modeled_range),
            "notional_mtow_kg": _qty_str(outputs.get(ac.notional_mtow_kg.stable_id)),
            "notional_mzfw_kg": _qty_str(outputs.get(ac.notional_mzfw_kg.stable_id)),
            "notional_trip_fuel_kg": _qty_str(outputs.get(ac.notional_trip_fuel_kg.stable_id)),
        },
        "wing": {
            "wing_structural_intensity_kg_per_m": _qty_str(
                outputs.get(ac.wing.wing_structural_intensity_kg_per_m.stable_id),
            ),
        },
        "constraints": constraints,
        "l1_requirements": spec_rows,
        "external_provenance": _external_provenance_by_slot(ctx),
        "slot_states_summary": {
            "realized": sum(
                1 for r in ctx._slot_records.values() if r.state == SlotState.REALIZED
            ),
            "bound_input": sum(
                1 for r in ctx._slot_records.values() if r.state == SlotState.BOUND_INPUT
            ),
            "failed": sum(1 for r in ctx._slot_records.values() if r.state == SlotState.FAILED),
        },
    }
