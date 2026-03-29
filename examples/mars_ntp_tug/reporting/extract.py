"""Build plain dicts from :class:`~tg_model.execution.configured_model.ConfiguredModel` and
:class:`~tg_model.execution.evaluator.RunResult` for the Mars NTP tug notebook."""

from __future__ import annotations

from typing import Any

from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.evaluator import RunResult
from tg_model.execution.requirements import summarize_requirement_satisfaction

# Keep statements aligned with ``tug_model`` leaf ``requirement`` text.
_FORMAL_REQUIREMENT_ROWS: tuple[dict[str, Any], ...] = (
    {
        "node_name": "req_heu_fuel_specification",
        "package": "reactor_fuel",
        "allocate_to": "reactor_core",
        "verification_kind": "package_constraints",
        "mission_closure_acceptance": False,
        "statement": (
            "The loaded fuel shall meet the program HEU mass-fraction floor for this notional tug "
            "(verification by analysis / assay records)."
        ),
    },
    {
        "node_name": "req_triso_barrier_function",
        "package": "reactor_fuel",
        "allocate_to": "reactor_core",
        "verification_kind": "package_constraints",
        "mission_closure_acceptance": False,
        "statement": (
            "TRISO particle coatings shall preserve a bounded fraction of intact particles under "
            "declared thermal cycling for this concept (verification by qualification test data)."
        ),
    },
    {
        "node_name": "req_channel_cooling_envelope",
        "package": "thermal_hydraulic",
        "allocate_to": "reactor_core",
        "verification_kind": "package_constraints",
        "mission_closure_acceptance": False,
        "statement": (
            "Core thermal-hydraulic operation shall remain within the declared hot-side temperature ratio "
            "and positive-flow envelope for the operating scenario (verification by analysis)."
        ),
    },
    {
        "node_name": "req_ntp_vacuum_thrust_capability",
        "package": "propulsion",
        "allocate_to": "nozzle",
        "verification_kind": "package_constraints",
        "mission_closure_acceptance": False,
        "statement": (
            "The propulsion subsystem shall deliver vacuum thrust no less than the declared mission floor "
            "for Earth-Mars cargo transfer burns (verification by test / analysis)."
        ),
    },
    {
        "node_name": "req_payload_dose_bound",
        "package": "shielding",
        "allocate_to": "shadow_shield",
        "verification_kind": "package_constraints",
        "mission_closure_acceptance": False,
        "statement": (
            "Ionizing dose at the cargo interface shall not exceed the declared limit proxy "
            "(verification by analysis)."
        ),
    },
    {
        "node_name": "req_delta_v_closure",
        "package": "mission",
        "allocate_to": "design_envelope",
        "verification_kind": "executable_acceptance",
        "mission_closure_acceptance": True,
        "statement": (
            "The design shall close the scenario Earth-Mars transfer delta-v within the declared "
            "capability envelope (verification by mission analysis)."
        ),
    },
    {
        "node_name": "req_propellant_mass_closure",
        "package": "mission",
        "allocate_to": "design_envelope",
        "verification_kind": "executable_acceptance",
        "mission_closure_acceptance": True,
        "statement": (
            "Loaded propellant mass shall meet or exceed the scenario-required hydrogen mass for the reference "
            "transfer (verification by mass accounting)."
        ),
    },
    {
        "node_name": "req_subcritical_assembly_rules",
        "package": "safety_policy",
        "allocate_to": "reactor_core",
        "verification_kind": "context_citations_only",
        "mission_closure_acceptance": False,
        "statement": (
            "Ground and launch-site handling shall maintain subcritical configurations per the program safety "
            "basis (verification by procedure / criticality safety analysis)."
        ),
    },
)


def _qty_str(value: Any) -> str:
    if value is None:
        return ""
    # Avoid Quantity.__str__ display resolver edge cases for ad-hoc dimensionless units.
    if hasattr(value, "magnitude"):
        mag = value.magnitude
        unit = getattr(value, "unit", None)
        sym = getattr(unit, "symbol", None) if unit is not None else None
        if sym:
            return f"{mag} {sym}"
        return f"{mag}"
    return str(value)


def extract_mars_ntp_evaluation_report(
    cm: ConfiguredModel,
    run_result: RunResult,
) -> dict[str, Any]:
    """Flatten scenario, thesis, operating point, constraints, and formal requirement metadata."""
    outputs = dict(run_result.outputs)
    rc = cm.reactor_core
    pf = cm.propellant_feed
    nz = cm.nozzle
    sh = cm.shadow_shield
    env = cm.design_envelope

    def _g(slot: Any) -> Any:
        return outputs.get(slot.stable_id)

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

    summary = summarize_requirement_satisfaction(run_result)
    reqcheck_ok = summary.all_passed

    return {
        "evaluation_passed": run_result.passed,
        "failures": list(run_result.failures),
        "reqcheck_all_passed": reqcheck_ok,
        "reqcheck_count": summary.check_count,
        "thesis": {
            "narrative": (
                "Program-root **napkin parameters** feed :class:`~examples.mars_ntp_tug.integrations.adapters."
                "MarsTransferNapkinDesk` via ``computed_by=`` (same integration pattern as the cargo jet mission "
                "desk). The desk produces **sim_*** attributes (propellant, wet mass, thrust floor, mass flow, "
                "thermal power). **Mission** closure still uses ``requirement_accept_expr`` on ``requirements."
                "mission``; **package** parameters for thermal-hydraulic and propulsion are mirrored from the "
                "desk in ``merge_mars_ntp_eval_inputs`` so notebooks do not hand-copy five derived numbers. "
                "**Coherence** constraints check reactor/nozzle operating points against the desk snapshot."
            ),
        },
        "napkin_assumptions": {
            "napkin_dry_mass_incl_payload_kg": _qty_str(_g(cm.napkin_dry_mass_incl_payload_kg)),
            "napkin_transfer_delta_v": _qty_str(_g(cm.napkin_transfer_delta_v)),
            "napkin_specific_impulse_vacuum_s": _qty_str(_g(cm.napkin_specific_impulse_vacuum_s)),
            "napkin_reference_gravity": _qty_str(_g(cm.napkin_reference_gravity)),
            "napkin_thrust_to_weight_start": _qty_str(_g(cm.napkin_thrust_to_weight_start)),
            "napkin_thermal_to_jet_efficiency": _qty_str(_g(cm.napkin_thermal_to_jet_efficiency)),
            "napkin_propellant_loadout_margin": _qty_str(_g(cm.napkin_propellant_loadout_margin)),
            "napkin_jet_kinetic_fraction": _qty_str(_g(cm.napkin_jet_kinetic_fraction)),
        },
        "mission_desk_outputs": {
            "sim_propellant_required_kg": _qty_str(_g(cm.sim_propellant_required_kg)),
            "sim_wet_mass_start_kg": _qty_str(_g(cm.sim_wet_mass_start_kg)),
            "sim_min_vacuum_thrust_kn": _qty_str(_g(cm.sim_min_vacuum_thrust_kn)),
            "sim_hydrogen_mass_flow_kg_s": _qty_str(_g(cm.sim_hydrogen_mass_flow_kg_s)),
            "sim_rated_thermal_power_mw": _qty_str(_g(cm.sim_rated_thermal_power_mw)),
        },
        "scenario_mission": {
            "mission_delta_v_required": _qty_str(_g(cm.mission_delta_v_required)),
            "mission_propellant_required": _qty_str(_g(cm.mission_propellant_required)),
            "mission_min_vacuum_thrust": _qty_str(_g(cm.mission_min_vacuum_thrust)),
        },
        "reactor_operating_point": {
            "rated_thermal_power": _qty_str(_g(rc.rated_thermal_power)),
            "hydrogen_mass_flow": _qty_str(_g(rc.hydrogen_mass_flow)),
            "u235_mass_fraction": _qty_str(_g(rc.u235_mass_fraction)),
            "triso_intact_fraction": _qty_str(_g(rc.triso_intact_fraction)),
            "peak_fuel_matrix_temp_ratio": _qty_str(_g(rc.peak_fuel_matrix_temp_ratio)),
        },
        "propulsion_and_tank": {
            "tank_propellant_mass": _qty_str(_g(pf.tank_propellant_mass)),
            "vacuum_thrust": _qty_str(_g(nz.vacuum_thrust)),
            "dose_proxy_at_cargo": _qty_str(_g(sh.dose_proxy_at_cargo)),
            "dose_limit_proxy": _qty_str(_g(sh.dose_limit_proxy)),
        },
        "design_envelope": {
            "design_delta_v_capability": _qty_str(_g(env.design_delta_v_capability)),
            "design_propellant_capacity": _qty_str(_g(env.design_propellant_capacity)),
        },
        "constraints": constraints,
        "formal_requirements": list(_FORMAL_REQUIREMENT_ROWS),
    }
