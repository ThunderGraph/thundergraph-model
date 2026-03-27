"""Smoke: commercial_aircraft example compiles and instantiates."""

from __future__ import annotations

import sys
from pathlib import Path

from unitflow import Quantity
from unitflow.catalogs.si import kg, m

# Example package is ``examples/commercial_aircraft/`` — put ``examples/`` on path.
_THUNDERGRAPH_MODEL = Path(__file__).resolve().parents[2]
_EXAMPLES_ROOT = _THUNDERGRAPH_MODEL / "examples"
if str(_EXAMPLES_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_ROOT))

from commercial_aircraft import CargoJetProgram, reset_commercial_aircraft_types  # noqa: E402
from commercial_aircraft.reporting.extract import extract_cargo_jet_evaluation_report  # noqa: E402
from commercial_aircraft.reporting.snapshot import format_cargo_jet_report  # noqa: E402

from tg_model.execution.configured_model import instantiate  # noqa: E402
from tg_model.execution.evaluator import Evaluator  # noqa: E402
from tg_model.execution.graph_compiler import compile_graph  # noqa: E402
from tg_model.execution.run_context import RunContext  # noqa: E402
from tg_model.execution.validation import validate_graph  # noqa: E402


def setup_function() -> None:
    reset_commercial_aircraft_types()


def test_cargo_jet_program_instantiate_classmethod_matches_module() -> None:
    """Phase 4: ``CargoJetProgram.instantiate()`` matches ``instantiate(CargoJetProgram)``."""
    cm_fn = instantiate(CargoJetProgram)
    cm_cls = CargoJetProgram.instantiate()
    assert cm_fn.root.stable_id == cm_cls.root.stable_id
    assert set(cm_fn.path_registry.keys()) == set(cm_cls.path_registry.keys())


def test_cargo_jet_program_compiles() -> None:
    art = CargoJetProgram.compile()
    assert "nodes" in art
    assert "scenario_payload_mass_kg" in art["nodes"]
    assert "mission_desk_baseline_max_range_m" in art["nodes"]
    assert art["nodes"]["mission_range_margin_m"]["kind"] == "attribute"
    assert "_computed_by" in art["nodes"]["mission_range_margin_m"]["metadata"]
    assert "c_far25" in art["nodes"]
    assert art["nodes"]["l1"]["kind"] == "requirement_block"
    ac_key = next(k for k in art["child_types"] if k.endswith("Aircraft"))
    ac_nodes = art["child_types"][ac_key]["nodes"]
    assert ac_nodes["fuselage"]["kind"] == "part"
    assert ac_nodes["operating_empty_mass_kg"]["kind"] == "attribute"
    assert ac_nodes["modeled_max_payload_kg"]["kind"] == "attribute"
    ac_child = art["child_types"][ac_key]["child_types"]
    wing_key = next(k for k in ac_child if k.endswith("WingAssembly"))
    wing_nodes = ac_child[wing_key]["nodes"]
    assert "_computed_by" in wing_nodes["wing_structural_intensity_kg_per_m"]["metadata"]


def test_cargo_jet_program_instantiate_and_evaluate_parameters() -> None:
    cm = instantiate(CargoJetProgram)
    ac = cm.aircraft
    # Notional weight book: OEW 140 t, MZFW 240 t → structural payload cap 100 t; MTOW 280 t with 40 t trip fuel.
    inputs = {
        cm.scenario_payload_mass_kg: Quantity(95_000, kg),
        cm.scenario_design_range_m: Quantity(8_000_000, m),
        cm.mission_desk_baseline_max_range_m: Quantity(10_000_000, m),
        ac.modeled_max_design_range_m: Quantity(9_000_000, m),
        ac.notional_mzfw_kg: Quantity(240_000, kg),
        ac.notional_mtow_kg: Quantity(280_000, kg),
        ac.notional_trip_fuel_kg: Quantity(40_000, kg),
        ac.fuselage.dry_mass_kg: Quantity(45_000, kg),
        ac.wing.dry_mass_kg: Quantity(32_000, kg),
        ac.wing.notional_wing_span_m: Quantity(64, m),
        ac.empennage.dry_mass_kg: Quantity(8_000, kg),
        ac.landing_gear.dry_mass_kg: Quantity(12_000, kg),
        ac.propulsion_installation.dry_mass_kg: Quantity(28_000, kg),
        ac.aircraft_systems.dry_mass_kg: Quantity(15_000, kg),
    }
    result = cm.evaluate(inputs=inputs)
    assert not result.failures, result.failures
    assert cm.root is not None
    out = result.outputs
    margin = out[cm.mission_range_margin_m.stable_id]
    assert margin > Quantity(2_000_000, m)
    assert margin < Quantity(2_100_000, m)
    wing_i = out[ac.wing.wing_structural_intensity_kg_per_m.stable_id]
    assert wing_i.is_close(Quantity(975, kg / m))


def test_cargo_jet_configured_model_evaluate_facade() -> None:
    """Facade evaluate() matches explicit pipeline: externals, requirements, constraint outcomes."""
    cm = instantiate(CargoJetProgram)
    ac = cm.aircraft
    inputs = {
        cm.scenario_payload_mass_kg: Quantity(95_000, kg),
        cm.scenario_design_range_m: Quantity(8_000_000, m),
        cm.mission_desk_baseline_max_range_m: Quantity(10_000_000, m),
        ac.modeled_max_design_range_m: Quantity(9_000_000, m),
        ac.notional_mzfw_kg: Quantity(240_000, kg),
        ac.notional_mtow_kg: Quantity(280_000, kg),
        ac.notional_trip_fuel_kg: Quantity(40_000, kg),
        ac.fuselage.dry_mass_kg: Quantity(45_000, kg),
        ac.wing.dry_mass_kg: Quantity(32_000, kg),
        ac.wing.notional_wing_span_m: Quantity(64, m),
        ac.empennage.dry_mass_kg: Quantity(8_000, kg),
        ac.landing_gear.dry_mass_kg: Quantity(12_000, kg),
        ac.propulsion_installation.dry_mass_kg: Quantity(28_000, kg),
        ac.aircraft_systems.dry_mass_kg: Quantity(15_000, kg),
    }
    result_facade = cm.evaluate(inputs=inputs)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph, configured_model=cm).passed
    inputs_by_id = {slot.stable_id: val for slot, val in inputs.items()}
    result_explicit = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs=inputs_by_id,
    )
    assert result_facade.passed == result_explicit.passed
    assert result_facade.failures == result_explicit.failures
    assert len(result_facade.constraint_results) == len(result_explicit.constraint_results)
    assert [c.passed for c in result_facade.constraint_results] == [
        c.passed for c in result_explicit.constraint_results
    ]


def test_requirement_allocate_edges_exist() -> None:
    compiled = CargoJetProgram.compile()
    edges = compiled.get("edges", [])
    allocates = [e for e in edges if e.get("kind") == "allocate"]
    # One allocate edge per Level-1 requirement wired in CargoJetProgram.define
    assert len(allocates) == 6


def test_references_edges_exist() -> None:
    compiled = CargoJetProgram.compile()
    edges = compiled.get("edges", [])
    refs = [e for e in edges if e.get("kind") == "references"]
    # Multiple citations per requirement → more reference edges than allocates.
    assert len(refs) >= 5


def test_cargo_jet_extract_and_snapshot_report() -> None:
    cm = instantiate(CargoJetProgram)
    ac = cm.aircraft
    inputs = {
        cm.scenario_payload_mass_kg: Quantity(95_000, kg),
        cm.scenario_design_range_m: Quantity(8_000_000, m),
        cm.mission_desk_baseline_max_range_m: Quantity(10_000_000, m),
        ac.modeled_max_design_range_m: Quantity(9_000_000, m),
        ac.notional_mzfw_kg: Quantity(240_000, kg),
        ac.notional_mtow_kg: Quantity(280_000, kg),
        ac.notional_trip_fuel_kg: Quantity(40_000, kg),
        ac.fuselage.dry_mass_kg: Quantity(45_000, kg),
        ac.wing.dry_mass_kg: Quantity(32_000, kg),
        ac.wing.notional_wing_span_m: Quantity(64, m),
        ac.empennage.dry_mass_kg: Quantity(8_000, kg),
        ac.landing_gear.dry_mass_kg: Quantity(12_000, kg),
        ac.propulsion_installation.dry_mass_kg: Quantity(28_000, kg),
        ac.aircraft_systems.dry_mass_kg: Quantity(15_000, kg),
    }
    result = cm.evaluate(inputs=inputs)
    assert result.passed, result.failures
    data = extract_cargo_jet_evaluation_report(cm, result)
    assert data["evaluation_passed"]
    assert data["thesis"]["margin_non_negative"]
    assert data["thesis"]["declared_envelope_constraints_passed"]
    assert data["external_provenance"] == {}
    assert data["slot_states_summary"] is None
    assert " m" in data["thesis"]["mission_range_margin_m"]
    assert "km" in data["thesis"]["mission_range_margin_km"].lower()
    text = format_cargo_jet_report(data)
    assert "Verdict" in text
    assert "Mission desk" in text
    assert "Declared envelope" in text
    assert "req_cargo_design_mission_payload_closure" in text
    assert "req_cargo_design_mission_range_closure" in text
    assert "executable_acceptance" in text


def test_extract_cargo_jet_includes_provenance_when_ctx_passed() -> None:
    """Optional ``ctx=`` on extract fills demo-only provenance / slot summaries from the run context."""
    cm = instantiate(CargoJetProgram)
    ac = cm.aircraft
    inputs = {
        cm.scenario_payload_mass_kg: Quantity(95_000, kg),
        cm.scenario_design_range_m: Quantity(8_000_000, m),
        cm.mission_desk_baseline_max_range_m: Quantity(10_000_000, m),
        ac.modeled_max_design_range_m: Quantity(9_000_000, m),
        ac.notional_mzfw_kg: Quantity(240_000, kg),
        ac.notional_mtow_kg: Quantity(280_000, kg),
        ac.notional_trip_fuel_kg: Quantity(40_000, kg),
        ac.fuselage.dry_mass_kg: Quantity(45_000, kg),
        ac.wing.dry_mass_kg: Quantity(32_000, kg),
        ac.wing.notional_wing_span_m: Quantity(64, m),
        ac.empennage.dry_mass_kg: Quantity(8_000, kg),
        ac.landing_gear.dry_mass_kg: Quantity(12_000, kg),
        ac.propulsion_installation.dry_mass_kg: Quantity(28_000, kg),
        ac.aircraft_systems.dry_mass_kg: Quantity(15_000, kg),
    }
    ctx = RunContext()
    result = cm.evaluate(inputs=inputs, run_context=ctx)
    data = extract_cargo_jet_evaluation_report(cm, result, ctx=ctx)
    assert data["external_provenance"]
    assert data["slot_states_summary"] is not None
    assert data["slot_states_summary"]["realized"] >= 1


def test_stress_scenario_negative_mission_margin() -> None:
    """Low mission-desk baseline vs requested range → negative margin; evaluator should still complete."""
    cm = instantiate(CargoJetProgram)
    ac = cm.aircraft
    inputs = {
        cm.scenario_payload_mass_kg: Quantity(95_000, kg),
        cm.scenario_design_range_m: Quantity(8_000_000, m),
        cm.mission_desk_baseline_max_range_m: Quantity(6_000_000, m),
        ac.modeled_max_design_range_m: Quantity(9_000_000, m),
        ac.notional_mzfw_kg: Quantity(240_000, kg),
        ac.notional_mtow_kg: Quantity(280_000, kg),
        ac.notional_trip_fuel_kg: Quantity(40_000, kg),
        ac.fuselage.dry_mass_kg: Quantity(45_000, kg),
        ac.wing.dry_mass_kg: Quantity(32_000, kg),
        ac.wing.notional_wing_span_m: Quantity(64, m),
        ac.empennage.dry_mass_kg: Quantity(8_000, kg),
        ac.landing_gear.dry_mass_kg: Quantity(12_000, kg),
        ac.propulsion_installation.dry_mass_kg: Quantity(28_000, kg),
        ac.aircraft_systems.dry_mass_kg: Quantity(15_000, kg),
    }
    result = cm.evaluate(inputs=inputs)
    assert not result.passed
    margin = result.outputs[cm.mission_range_margin_m.stable_id]
    assert margin < Quantity(0, m)
    data = extract_cargo_jet_evaluation_report(cm, result)
    assert not data["thesis"]["margin_non_negative"]
    text = format_cargo_jet_report(data)
    assert "FAIL" in text
