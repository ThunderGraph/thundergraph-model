"""Integration: behavior effects use RunContext; coexist with value evaluation."""

from __future__ import annotations

from tg_model.execution.behavior import (
    BehaviorTrace,
    DispatchOutcome,
    dispatch_event,
    validate_scenario_trace,
)
from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.instances import PartInstance
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.model.elements import Part, System


class Controller(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("controller")
        model.parameter("marker", unit="%")
        off = model.state("off", initial=True)
        running = model.state("running")
        start = model.event("start")
        stop = model.event("stop")

        def arm(ctx: RunContext, part: PartInstance) -> None:
            ctx.bind_input(part.marker.stable_id, 1.0)

        def disarm(ctx: RunContext, part: PartInstance) -> None:
            ctx.bind_input(part.marker.stable_id, 0.0)

        model.action("arm", effect=arm)
        model.action("disarm", effect=disarm)
        model.transition(off, running, on=start, effect="arm")
        model.transition(running, off, on=stop, effect="disarm")
        model.scenario("start_stop", expected_event_order=[start, stop])


class Host(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("host")
        model.composed_of("ctrl", Controller)


class EvalThenBehavior(Part):
    """Start transition has no effect so evaluate can bind marker before behavior runs."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("eval_then_behavior")
        model.parameter("marker", unit="%")
        off = model.state("off", initial=True)
        running = model.state("running")
        start = model.event("start")
        stop = model.event("stop")
        model.transition(off, running, on=start)

        def disarm(ctx: RunContext, part: PartInstance) -> None:
            ctx.bind_input(part.marker.stable_id, 0.0)

        model.action("disarm", effect=disarm)
        model.transition(running, off, on=stop, effect="disarm")


def setup_function() -> None:
    Controller._reset_compilation()
    Host._reset_compilation()
    EvalThenBehavior._reset_compilation()


def test_root_controller_effect_writes_slot() -> None:
    cm = instantiate(Controller)
    ctx = RunContext()
    trace = BehaviorTrace()
    mid = cm.marker.stable_id
    assert dispatch_event(ctx, cm.root, "start", trace=trace).outcome is DispatchOutcome.FIRED
    assert ctx.get_value(mid) == 1.0
    assert dispatch_event(ctx, cm.root, "stop", trace=trace).outcome is DispatchOutcome.FIRED
    assert ctx.get_value(mid) == 0.0


def test_nested_part_path_and_scenario() -> None:
    cm = instantiate(Host)
    ctrl = cm.ctrl
    ctx = RunContext()
    trace = BehaviorTrace()
    assert dispatch_event(ctx, ctrl, "start", trace=trace).outcome is DispatchOutcome.FIRED
    assert dispatch_event(ctx, ctrl, "stop", trace=trace).outcome is DispatchOutcome.FIRED
    ok, errs = validate_scenario_trace(
        definition_type=Controller,
        scenario_name="start_stop",
        part_path=ctrl.path_string,
        trace=trace,
    )
    assert ok and not errs


def test_behavior_then_graph_evaluate_same_context() -> None:
    cm = instantiate(Controller)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    ctx = RunContext()
    assert dispatch_event(ctx, cm.root, "start").outcome is DispatchOutcome.FIRED
    ev = Evaluator(graph, compute_handlers=handlers)
    result = ev.evaluate(ctx, inputs={})
    assert result.passed
    assert ctx.get_value(cm.marker.stable_id) == 1.0


def test_evaluate_then_behavior_same_context() -> None:
    """Value spine first, then behavior mutates a slot — same RunContext end-to-end."""
    cm = instantiate(EvalThenBehavior)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    ctx = RunContext()
    ev = Evaluator(graph, compute_handlers=handlers)
    result = ev.evaluate(ctx, inputs={cm.marker.stable_id: 5.0})
    assert result.passed
    assert ctx.get_value(cm.marker.stable_id) == 5.0
    assert dispatch_event(ctx, cm.root, "start").outcome is DispatchOutcome.FIRED
    assert ctx.get_value(cm.marker.stable_id) == 5.0
    assert dispatch_event(ctx, cm.root, "stop").outcome is DispatchOutcome.FIRED
    assert ctx.get_value(cm.marker.stable_id) == 0.0
