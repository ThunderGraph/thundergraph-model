"""Phase 7: requirement acceptance expressions evaluated via the same graph as constraints."""

from __future__ import annotations

import pytest

from unitflow import Quantity
from unitflow.catalogs.si import N, m, rad, s

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import GraphCompilationError, compile_graph
from tg_model.execution.requirements import (
    all_requirements_satisfied,
    iter_requirement_satisfaction,
    summarize_requirement_satisfaction,
)
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part, System


class Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        torque = model.parameter("torque", unit=N * m)
        speed = model.parameter("shaft_speed", unit=rad / s)
        model.attribute(
            "shaft_power",
            unit=N * m / s,
            expr=torque * speed,
        )


class MotorWithPort(Motor):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        super().define(model)
        model.port("power_out", direction="out")


class SysWithReq(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        motor = model.part("motor", Motor)
        req = model.requirement(
            "shaft_power_positive",
            "Motor shall deliver positive shaft power.",
            expr=motor.shaft_power > Quantity(0, N * m / s),
        )
        model.allocate(req, motor)


class SysAllocTraceOnly(System):
    """Requirement with allocate but no acceptance expr — no reqcheck nodes."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        motor = model.part("motor", Motor)
        r = model.requirement("trace_only", "Text only, no expr.")
        model.allocate(r, motor)


def setup_function() -> None:
    Motor._reset_compilation()
    MotorWithPort._reset_compilation()
    SysWithReq._reset_compilation()
    SysAllocTraceOnly._reset_compilation()


def test_requirement_acceptance_passes_with_positive_power() -> None:
    cm = instantiate(SysWithReq)
    graph, handlers = compile_graph(cm)
    validation = validate_graph(graph)
    assert validation.passed, validation.failures

    evaluator = Evaluator(graph, compute_handlers=handlers)
    ctx = RunContext()
    result = evaluator.evaluate(ctx, inputs={
        cm.motor.torque.stable_id: Quantity(50, N * m),
        cm.motor.shaft_speed.stable_id: Quantity(100, m / (m * s)),
    })

    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert sat[0].passed
    assert sat[0].requirement_path.endswith("shaft_power_positive")
    assert "motor" in sat[0].allocation_target_path
    summary = summarize_requirement_satisfaction(result)
    assert summary.check_count == 1
    assert summary.all_passed
    assert all_requirements_satisfied(result)


def test_no_acceptance_checks_summary_not_vacuously_passed() -> None:
    cm = instantiate(SysAllocTraceOnly)
    graph, handlers = compile_graph(cm)
    evaluator = Evaluator(graph, compute_handlers=handlers)
    ctx = RunContext()
    result = evaluator.evaluate(ctx, inputs={
        cm.motor.torque.stable_id: Quantity(1, N * m),
        cm.motor.shaft_speed.stable_id: Quantity(1, m / (m * s)),
    })
    summary = summarize_requirement_satisfaction(result)
    assert summary.check_count == 0
    assert not summary.all_passed
    assert not all_requirements_satisfied(result)
    assert iter_requirement_satisfaction(result) == []


def test_requirement_acceptance_fails_when_power_not_positive() -> None:
    cm = instantiate(SysWithReq)
    graph, handlers = compile_graph(cm)
    evaluator = Evaluator(graph, compute_handlers=handlers)
    ctx = RunContext()
    result = evaluator.evaluate(ctx, inputs={
        cm.motor.torque.stable_id: Quantity(0, N * m),
        cm.motor.shaft_speed.stable_id: Quantity(100, m / (m * s)),
    })

    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert not sat[0].passed
    assert not all_requirements_satisfied(result)


def test_allocate_non_part_target_rejected_at_graph_compile() -> None:
    class SysBadAlloc(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            motor = model.part("motor", MotorWithPort)
            req = model.requirement(
                "r",
                "text",
                expr=motor.shaft_power > Quantity(0, N * m / s),
            )
            model.allocate(req, motor.power_out)

    SysBadAlloc._reset_compilation()
    MotorWithPort._reset_compilation()
    cm = instantiate(SysBadAlloc)
    with pytest.raises(GraphCompilationError, match="PartInstance"):
        compile_graph(cm)
    SysBadAlloc._reset_compilation()


class TestCompileTimeRules:
    def test_expr_without_allocate_rejected(self) -> None:
        class OrphanReq(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                motor = model.part("motor", Motor)
                model.requirement(
                    "orphan",
                    "has expr",
                    expr=motor.shaft_power > Quantity(0, N * m / s),
                )

        OrphanReq._reset_compilation()
        Motor._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="allocate"):
            OrphanReq.compile()
        OrphanReq._reset_compilation()
