"""Integration tests: Requirement with derived attributes inside a child System evaluates
correctly end-to-end.

Scenario
--------
An ``AutonomousPlatform`` (root) composes an ``EnergySubsystem`` (child System).
The child System composes a ``BatteryModule`` (Part) and an ``EnergyCapacityReq``
(Requirement) with a derived attribute and a constraint.

The requirement parameters are free inputs (not auto-wired here, as allocation
wiring from child Systems is a separate concern). This file tests only that the
graph compiler correctly resolves the `attribute(expr=...)` symbols relative to
the child System's PartInstance — the bug that triggered:

    GraphCompilationError: Symbol '...' has registered path (...)
    but could not be resolved under 'AutonomousPlatform'
"""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kJ

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.requirements import (
    all_requirements_satisfied,
    iter_requirement_satisfaction,
)
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.model.elements import Part, Requirement, System


class BatteryModule(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("battery_module")
        model.parameter("usable_energy_kj", unit=kJ)


class EnergyCapacityReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("energy_capacity")
        model.doc("Usable battery energy must cover mission demand.")
        mission = model.parameter("mission_energy_kj", unit=kJ)
        usable = model.parameter("usable_energy_kj", unit=kJ)
        margin = model.attribute("energy_margin_kj", unit=kJ, expr=usable - mission)
        model.constraint("margin_non_negative", expr=margin >= Quantity(0, kJ))


class EnergySubsystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("energy_subsystem")
        model.parameter("mission_energy_kj", unit=kJ)
        model.composed_of("battery", BatteryModule)
        model.composed_of("energy_req", EnergyCapacityReq)


class AutonomousPlatform(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("autonomous_platform")
        model.composed_of("energy", EnergySubsystem)


def setup_function() -> None:
    BatteryModule._reset_compilation()
    EnergyCapacityReq._reset_compilation()
    EnergySubsystem._reset_compilation()
    AutonomousPlatform._reset_compilation()


def _make_evaluator(cm):
    graph, handlers = compile_graph(cm)
    return graph, handlers, Evaluator(graph, compute_handlers=handlers)


def _inputs(cm, *, mission_kj: float, usable_kj: float) -> dict:
    """Build a complete inputs dict for one evaluation run.

    The requirement parameters are free INPUT_PARAMETER nodes (no auto-wiring
    from child System allocations), so we supply them alongside the part-side
    parameters with the same numerical values.
    """
    return {
        cm.energy.mission_energy_kj.stable_id: Quantity(mission_kj, kJ),
        cm.energy.battery.usable_energy_kj.stable_id: Quantity(usable_kj, kJ),
        cm.energy.energy_req.mission_energy_kj.stable_id: Quantity(mission_kj, kJ),
        cm.energy.energy_req.usable_energy_kj.stable_id: Quantity(usable_kj, kJ),
    }


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------

def test_graph_validates() -> None:
    """Static validation must pass before evaluation begins."""
    cm = instantiate(AutonomousPlatform)
    graph, _, _ = _make_evaluator(cm)
    result = validate_graph(graph)
    assert result.passed, result.failures


# ---------------------------------------------------------------------------
# Derived attribute value correctness
# ---------------------------------------------------------------------------

def test_derived_margin_value_is_correct_when_satisfied() -> None:
    """energy_margin_kj must equal usable - mission after evaluation (positive case)."""
    cm = instantiate(AutonomousPlatform)
    _, _, evaluator = _make_evaluator(cm)
    ctx = RunContext()
    evaluator.evaluate(ctx, inputs=_inputs(cm, mission_kj=300.0, usable_kj=500.0))

    margin_id = cm.energy.energy_req.energy_margin_kj.stable_id
    margin_value = ctx.get_value(margin_id)
    assert margin_value is not None, "energy_margin_kj was not realized"
    assert abs(margin_value.magnitude - 200.0) < 1e-9


def test_derived_margin_value_is_correct_when_violated() -> None:
    """Margin is still computed (as negative) when the constraint fails."""
    cm = instantiate(AutonomousPlatform)
    _, _, evaluator = _make_evaluator(cm)
    ctx = RunContext()
    evaluator.evaluate(ctx, inputs=_inputs(cm, mission_kj=600.0, usable_kj=400.0))

    margin_id = cm.energy.energy_req.energy_margin_kj.stable_id
    margin_value = ctx.get_value(margin_id)
    assert margin_value is not None, "energy_margin_kj was not realized"
    assert margin_value.magnitude == pytest.approx(-200.0)


# ---------------------------------------------------------------------------
# Constraint pass / fail / boundary
# ---------------------------------------------------------------------------

def test_constraint_passes_when_battery_exceeds_demand() -> None:
    """Requirement is satisfied when usable > mission demand."""
    cm = instantiate(AutonomousPlatform)
    _, _, evaluator = _make_evaluator(cm)
    result = evaluator.evaluate(RunContext(), inputs=_inputs(cm, mission_kj=300.0, usable_kj=500.0))

    assert result.passed, result.failures
    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert sat[0].passed
    assert "energy_req" in sat[0].requirement_path


def test_constraint_fails_when_battery_below_demand() -> None:
    """Requirement is violated when usable < mission demand."""
    cm = instantiate(AutonomousPlatform)
    _, _, evaluator = _make_evaluator(cm)
    result = evaluator.evaluate(RunContext(), inputs=_inputs(cm, mission_kj=600.0, usable_kj=400.0))

    assert not result.passed
    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert not sat[0].passed


def test_constraint_passes_at_exact_boundary() -> None:
    """Zero margin (usable == demand) is the >= 0 boundary — must pass."""
    cm = instantiate(AutonomousPlatform)
    _, _, evaluator = _make_evaluator(cm)
    result = evaluator.evaluate(RunContext(), inputs=_inputs(cm, mission_kj=400.0, usable_kj=400.0))

    assert result.passed, result.failures
    assert all_requirements_satisfied(result)


def test_all_requirements_satisfied_reflects_result() -> None:
    """Helper agrees with individual constraint results for both pass and fail cases."""
    cm = instantiate(AutonomousPlatform)
    _, _, evaluator = _make_evaluator(cm)

    passing = evaluator.evaluate(RunContext(), inputs=_inputs(cm, mission_kj=200.0, usable_kj=350.0))
    failing = evaluator.evaluate(RunContext(), inputs=_inputs(cm, mission_kj=500.0, usable_kj=300.0))

    assert all_requirements_satisfied(passing)
    assert not all_requirements_satisfied(failing)


# ---------------------------------------------------------------------------
# Graph reuse: independent runs over the same compiled graph
# ---------------------------------------------------------------------------

def test_repeated_evaluations_are_independent() -> None:
    """Two evaluate() calls with different inputs produce independent, correct results.
    Confirms the compiled graph is safely reusable (RunContexts are isolated)."""
    cm = instantiate(AutonomousPlatform)
    _, _, evaluator = _make_evaluator(cm)
    margin_id = cm.energy.energy_req.energy_margin_kj.stable_id

    ctx1 = RunContext()
    evaluator.evaluate(ctx1, inputs=_inputs(cm, mission_kj=300.0, usable_kj=500.0))

    ctx2 = RunContext()
    evaluator.evaluate(ctx2, inputs=_inputs(cm, mission_kj=600.0, usable_kj=400.0))

    assert ctx1.get_value(margin_id).magnitude == pytest.approx(200.0)
    assert ctx2.get_value(margin_id).magnitude == pytest.approx(-200.0)
