"""Phase 7: requirement package constraint results carry requirement_path."""

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
from tg_model.model.elements import Part, Requirement, System


class Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("motor")
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


class ShaftPowerPositiveRequirement(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("shaft_power_positive")
        model.doc("Motor shall deliver positive shaft power.")
        shaft_power = model.parameter("shaft_power", unit=N * m / s)
        model.constraint(
            "shaft_power_positive_check",
            expr=shaft_power > Quantity(0, N * m / s),
        )


class SysWithReq(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("sys_with_req")
        motor = model.composed_of("motor", Motor)
        req = model.composed_of("shaft_power_req", ShaftPowerPositiveRequirement)
        model.allocate(
            req,
            motor,
            inputs={"shaft_power": motor.shaft_power},
        )


class SysAllocTraceOnly(System):
    """Requirement with no constraints — no reqcheck nodes."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("sys_alloc_trace_only")
        motor = model.composed_of("motor", Motor)
        req = model.composed_of("trace_only", _TraceOnlyRequirement)
        model.allocate(req, motor)


class _TraceOnlyRequirement(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("trace_only")
        model.doc("Text only, no constraints.")


def setup_function() -> None:
    Motor._reset_compilation()
    MotorWithPort._reset_compilation()
    SysWithReq._reset_compilation()
    SysAllocTraceOnly._reset_compilation()
    ShaftPowerPositiveRequirement._reset_compilation()
    _TraceOnlyRequirement._reset_compilation()


def test_requirement_acceptance_passes_with_positive_power() -> None:
    cm = instantiate(SysWithReq)
    graph, handlers = compile_graph(cm)
    validation = validate_graph(graph)
    assert validation.passed, validation.failures

    evaluator = Evaluator(graph, compute_handlers=handlers)
    ctx = RunContext()
    result = evaluator.evaluate(
        ctx,
        inputs={
            cm.motor.torque.stable_id: Quantity(50, N * m),
            cm.motor.shaft_speed.stable_id: Quantity(100, m / (m * s)),
        },
    )

    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert sat[0].passed
    assert "shaft_power" in sat[0].requirement_path
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
    result = evaluator.evaluate(
        ctx,
        inputs={
            cm.motor.torque.stable_id: Quantity(1, N * m),
            cm.motor.shaft_speed.stable_id: Quantity(1, m / (m * s)),
        },
    )
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
    result = evaluator.evaluate(
        ctx,
        inputs={
            cm.motor.torque.stable_id: Quantity(0, N * m),
            cm.motor.shaft_speed.stable_id: Quantity(100, m / (m * s)),
        },
    )

    sat = iter_requirement_satisfaction(result)
    assert len(sat) == 1
    assert not sat[0].passed
    assert not all_requirements_satisfied(result)


def test_allocate_non_part_target_rejected_at_graph_compile() -> None:
    class SysBadAlloc(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sys_bad_alloc")
            motor = model.composed_of("motor", MotorWithPort)
            req = model.composed_of("req", ShaftPowerPositiveRequirement)
            model.allocate(req, motor.power_out)

    SysBadAlloc._reset_compilation()
    MotorWithPort._reset_compilation()
    ShaftPowerPositiveRequirement._reset_compilation()
    cm = instantiate(SysBadAlloc)
    with pytest.raises(GraphCompilationError, match="PartInstance"):
        compile_graph(cm)
    SysBadAlloc._reset_compilation()


class TestCompileTimeRules:
    def test_constraint_without_expr_rejected(self) -> None:
        class BadReq(Requirement):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("bad_req")
                model.doc("stub.")
                model.constraint("empty", expr=None)  # type: ignore[arg-type]

        class OrphanSys(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("orphan")
                model.composed_of("r", BadReq)

        OrphanSys._reset_compilation()
        BadReq._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="must set expr"):
            OrphanSys.compile()
        OrphanSys._reset_compilation()
        BadReq._reset_compilation()
