"""Integration test: end-to-end evaluation using unitflow expressions.

Proves the full contract: define with expr= -> compile -> instantiate ->
graph compiler -> validate -> evaluate using real unitflow expression trees.
No hand-built graphs. All symbols derived from canonical AttributeRefs.
"""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import N, kg, m, rad, s

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import GraphCompilationError, compile_graph
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.model.declarations.values import rollup
from tg_model.model.elements import Part, System


class Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        torque = model.parameter("torque", unit=N * m)
        speed = model.parameter("shaft_speed", unit=rad / s)
        power = model.attribute(
            "shaft_power",
            unit=N * m / s,
            expr=torque * speed,
        )
        model.constraint(
            "power_positive",
            expr=power > Quantity(0, N * m / s),
        )


class SimpleSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.part("motor", Motor)


def setup_function() -> None:
    Motor._reset_compilation()
    SimpleSystem._reset_compilation()


class TestUnitflowExpressionEvaluation:
    def test_full_pipeline_with_unitflow_expressions(self) -> None:
        cm = instantiate(SimpleSystem)

        graph, handlers = compile_graph(cm)

        validation = validate_graph(graph)
        assert validation.passed, f"Validation failed: {[f.message for f in validation.failures]}"

        torque_slot = cm.motor.torque
        speed_slot = cm.motor.shaft_speed
        power_slot = cm.motor.shaft_power

        evaluator = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()

        result = evaluator.evaluate(
            ctx,
            inputs={
                torque_slot.stable_id: Quantity(50, N * m),
                speed_slot.stable_id: Quantity(100, m / (m * s)),
            },
        )

        power_value = ctx.get_value(power_slot.stable_id)
        assert isinstance(power_value, Quantity)
        assert power_value.is_close(Quantity(5000, N * m / s))
        assert len(result.constraint_results) == 1
        assert result.constraint_results[0].passed is True

    def test_constraint_fails_when_power_is_zero(self) -> None:
        cm = instantiate(SimpleSystem)
        graph, handlers = compile_graph(cm)

        torque_slot = cm.motor.torque
        speed_slot = cm.motor.shaft_speed

        evaluator = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        result = evaluator.evaluate(
            ctx,
            inputs={
                torque_slot.stable_id: Quantity(0, N * m),
                speed_slot.stable_id: Quantity(100, m / (m * s)),
            },
        )

        assert len(result.constraint_results) == 1
        assert result.constraint_results[0].passed is False

    def test_repeated_runs_are_isolated(self) -> None:
        cm = instantiate(SimpleSystem)
        graph, handlers = compile_graph(cm)

        torque_slot = cm.motor.torque
        speed_slot = cm.motor.shaft_speed
        power_slot = cm.motor.shaft_power

        evaluator = Evaluator(graph, compute_handlers=handlers)

        ctx1 = RunContext()
        evaluator.evaluate(
            ctx1,
            inputs={
                torque_slot.stable_id: Quantity(50, N * m),
                speed_slot.stable_id: Quantity(100, m / (m * s)),
            },
        )

        ctx2 = RunContext()
        evaluator.evaluate(
            ctx2,
            inputs={
                torque_slot.stable_id: Quantity(25, N * m),
                speed_slot.stable_id: Quantity(200, m / (m * s)),
            },
        )

        p1 = ctx1.get_value(power_slot.stable_id)
        p2 = ctx2.get_value(power_slot.stable_id)

        assert p1.is_close(Quantity(5000, N * m / s))
        assert p2.is_close(Quantity(5000, N * m / s))


class SolvedMotor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        torque = model.attribute("shaft_torque", unit=N * m)
        speed = model.parameter("shaft_speed", unit=rad / s)
        power_unit = N * m / s
        power = model.parameter("shaft_power", unit=power_unit)
        model.solve_group(
            "power_balance",
            equations=[power == torque * speed],
            unknowns=[torque],
            givens=[power, speed],
        )


class TestSolveGroupEvaluation:
    def test_solve_group_computes_unknown(self) -> None:
        cm = instantiate(SolvedMotor)
        graph, handlers = compile_graph(cm)

        evaluator = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        evaluator.evaluate(
            ctx,
            inputs={
                cm.shaft_power.stable_id: Quantity(5000, N * m / s),
                cm.shaft_speed.stable_id: Quantity(100, rad / s),
            },
        )

        torque_value = ctx.get_value(cm.shaft_torque.stable_id)
        assert isinstance(torque_value, Quantity)
        assert torque_value.is_close(Quantity(50, N * m))


class AggregatedSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        class Box(Part):
            @classmethod
            def define(cls, m2):  # type: ignore[override]
                m2.parameter("mass", unit=kg)

        model.part("box1", Box)
        model.part("box2", Box)

        model.attribute("total_mass", unit=kg, expr=rollup.sum(model.parts(), value=lambda c: c.mass))


class TestRollupEvaluation:
    def test_rollup_computes_sum(self) -> None:
        cm = instantiate(AggregatedSystem)
        graph, handlers = compile_graph(cm)

        evaluator = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        evaluator.evaluate(
            ctx,
            inputs={
                cm.box1.mass.stable_id: Quantity(10, kg),
                cm.box2.mass.stable_id: Quantity(25, kg),
            },
        )

        total = ctx.get_value(cm.total_mass.stable_id)
        assert total.is_close(Quantity(35, kg))


class TestConstantExpression:
    """Constant expressions (no free symbols) must compile, validate, and evaluate."""

    def test_constant_quantity_evaluates(self) -> None:
        class ConstPart(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.attribute("mass", unit=kg, expr=Quantity(5, kg))

        ConstPart._reset_compilation()
        cm = instantiate(ConstPart)
        graph, handlers = compile_graph(cm)

        validation = validate_graph(graph)
        assert validation.passed, f"Validation failed: {[f.message for f in validation.failures]}"

        evaluator = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        result = evaluator.evaluate(ctx)

        mass_value = ctx.get_value(cm.mass.stable_id)
        assert isinstance(mass_value, Quantity)
        assert mass_value.is_close(Quantity(5, kg))
        assert result.passed


class TestSolveGroupContractEnforcement:
    """The compiler must reject solve groups where declarations don't match equations."""

    def test_rejects_declared_unknown_not_in_equations(self) -> None:
        class BadSolve(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                torque = model.attribute("torque", unit=N * m)
                drag = model.attribute("drag", unit=N * m)
                speed = model.parameter("speed", unit=rad / s)
                power = model.parameter("power", unit=N * m / s)
                model.solve_group(
                    "sg",
                    equations=[power == torque * speed],
                    unknowns=[torque, drag],
                    givens=[power, speed],
                )

        BadSolve._reset_compilation()
        cm = instantiate(BadSolve)
        with pytest.raises(GraphCompilationError, match="declared unknowns not found"):
            compile_graph(cm)

    def test_rejects_undeclared_symbol_in_equations(self) -> None:
        class BadSolve(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                torque = model.attribute("torque", unit=N * m)
                speed = model.parameter("speed", unit=rad / s)
                power = model.parameter("power", unit=N * m / s)
                fudge = model.parameter("fudge", unit=N * m / s)
                model.solve_group(
                    "sg",
                    equations=[power + fudge == torque * speed],
                    unknowns=[torque],
                    givens=[power, speed],
                )

        BadSolve._reset_compilation()
        cm = instantiate(BadSolve)
        with pytest.raises(GraphCompilationError, match="not declared as unknown or given"):
            compile_graph(cm)

    def test_rejects_declared_given_not_in_equations(self) -> None:
        class BadSolve(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                torque = model.attribute("torque", unit=N * m)
                speed = model.parameter("speed", unit=rad / s)
                power = model.parameter("power", unit=N * m / s)
                unused = model.parameter("unused", unit=kg)
                model.solve_group(
                    "sg",
                    equations=[power == torque * speed],
                    unknowns=[torque],
                    givens=[power, speed, unused],
                )

        BadSolve._reset_compilation()
        cm = instantiate(BadSolve)
        with pytest.raises(GraphCompilationError, match="declared givens not found"):
            compile_graph(cm)

    def test_rejects_same_slot_as_unknown_and_given(self) -> None:
        class BadSolve(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                torque = model.attribute("torque", unit=N * m)
                speed = model.parameter("speed", unit=rad / s)
                power = model.parameter("power", unit=N * m / s)
                model.solve_group(
                    "sg",
                    equations=[power == torque * speed],
                    unknowns=[torque],
                    givens=[power, speed, torque],
                )

        BadSolve._reset_compilation()
        cm = instantiate(BadSolve)
        with pytest.raises(GraphCompilationError, match="declared as both unknown and given"):
            compile_graph(cm)
