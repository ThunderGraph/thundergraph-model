"""Integration test: allocate(..., inputs={...}) wires scenario values into
package-level model.parameter slots on a Requirement and constraints evaluate end-to-end.

Scenario
--------
A ``ThrusterPart`` declares thrust and specific-impulse parameters.
A ``ThrustReq`` declares matching parameters and checks thrust >= a floor value.
The root ``PropulsionSystem`` composes both, then allocates ``thrust_req`` to
``thruster`` with ``inputs`` mapping the requirement's parameters to the part's slots.

The inputs dict passed to evaluate() need only contain the part-side parameters;
the requirement parameters are auto-wired from the part via the allocation.
"""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kN, s

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.requirements import (
    all_requirements_satisfied,
    iter_requirement_satisfaction,
    summarize_requirement_satisfaction,
)
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.model.elements import Part, Requirement, System


class ThrusterPart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("thruster")
        model.parameter("vacuum_thrust", unit=kN)
        model.parameter("specific_impulse", unit=s)


class ThrustFloorReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("thrust_floor")
        model.doc("Thruster shall deliver at least the declared minimum vacuum thrust.")
        required = model.parameter("required_thrust", unit=kN)
        declared = model.parameter("declared_thrust", unit=kN)
        margin = model.attribute("thrust_margin", unit=kN, expr=declared - required)
        model.constraint("thrust_margin_non_negative", expr=margin >= Quantity(0, kN))


class PropulsionSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("propulsion_system")
        floor = model.parameter("mission_thrust_floor", unit=kN)
        thruster = model.composed_of("thruster", ThrusterPart)
        req = model.composed_of("thrust_req", ThrustFloorReq)
        model.allocate(
            req,
            thruster,
            inputs={
                "required_thrust": floor,
                "declared_thrust": thruster.vacuum_thrust,
            },
        )


def setup_function() -> None:
    ThrusterPart._reset_compilation()
    ThrustFloorReq._reset_compilation()
    PropulsionSystem._reset_compilation()


def test_graph_validates() -> None:
    cm = instantiate(PropulsionSystem)
    graph, handlers = compile_graph(cm)
    result = validate_graph(graph)
    assert result.passed, result.failures


def test_constraint_passes_when_declared_exceeds_floor() -> None:
    cm = instantiate(PropulsionSystem)
    graph, handlers = compile_graph(cm)
    evaluator = Evaluator(graph, compute_handlers=handlers)
    ctx = RunContext()

    result = evaluator.evaluate(
        ctx,
        inputs={
            cm.mission_thrust_floor.stable_id: Quantity(50, kN),
            cm.thruster.vacuum_thrust.stable_id: Quantity(80, kN),
            cm.thruster.specific_impulse.stable_id: Quantity(450, s),
        },
    )

    assert result.passed, result.failures
    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert sat[0].passed
    assert "thrust_req" in sat[0].requirement_path
    assert "thruster" in sat[0].allocation_target_path


def test_constraint_fails_when_declared_below_floor() -> None:
    cm = instantiate(PropulsionSystem)
    graph, handlers = compile_graph(cm)
    evaluator = Evaluator(graph, compute_handlers=handlers)
    ctx = RunContext()

    result = evaluator.evaluate(
        ctx,
        inputs={
            cm.mission_thrust_floor.stable_id: Quantity(100, kN),
            cm.thruster.vacuum_thrust.stable_id: Quantity(60, kN),
            cm.thruster.specific_impulse.stable_id: Quantity(450, s),
        },
    )

    assert not result.passed
    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert not sat[0].passed


def test_summary_counts_one_check() -> None:
    cm = instantiate(PropulsionSystem)
    graph, handlers = compile_graph(cm)
    evaluator = Evaluator(graph, compute_handlers=handlers)
    ctx = RunContext()

    result = evaluator.evaluate(
        ctx,
        inputs={
            cm.mission_thrust_floor.stable_id: Quantity(50, kN),
            cm.thruster.vacuum_thrust.stable_id: Quantity(80, kN),
            cm.thruster.specific_impulse.stable_id: Quantity(450, s),
        },
    )

    summary = summarize_requirement_satisfaction(result)
    assert summary.check_count == 1
    assert summary.all_passed
    assert all_requirements_satisfied(result)


def test_requirement_parameters_not_free_inputs() -> None:
    """The requirement package parameters are wired, not free INPUT_PARAMETER nodes."""
    cm = instantiate(PropulsionSystem)
    graph, _ = compile_graph(cm)

    req_param_node_ids = {
        f"val:{cm.thrust_req.required_thrust.path_string}",
        f"val:{cm.thrust_req.declared_thrust.path_string}",
    }
    from tg_model.execution.graph_compiler import NodeKind
    for node_id in req_param_node_ids:
        node = graph.nodes.get(node_id)
        assert node is not None, f"Missing graph node {node_id!r}"
        assert node.kind != NodeKind.INPUT_PARAMETER, (
            f"Requirement parameter {node_id!r} should be wired (not a free input)"
        )
