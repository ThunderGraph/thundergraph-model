"""Unit tests: discrete behavior dispatch and scenario validation."""

from __future__ import annotations

import pytest

from tg_model.execution.behavior import (
    BehaviorTrace,
    DispatchOutcome,
    dispatch_event,
    validate_scenario_trace,
)
from tg_model.execution.configured_model import instantiate
from tg_model.execution.run_context import RunContext
from tg_model.model.elements import Part


class Tiny(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        off = model.state("off", initial=True)
        on = model.state("on")
        ev = model.event("go")
        model.transition(off, on, on=ev)


def setup_function() -> None:
    Tiny._reset_compilation()


class TestDispatch:
    def test_dispatch_transitions_and_trace(self) -> None:
        cm = instantiate(Tiny)
        ctx = RunContext()
        tr = BehaviorTrace()
        r0 = dispatch_event(ctx, cm, "nope")
        assert r0.outcome is DispatchOutcome.NO_MATCH
        assert not r0
        r1 = dispatch_event(ctx, cm, "go", trace=tr)
        assert r1.outcome is DispatchOutcome.FIRED
        assert r1
        assert ctx.get_active_behavior_state(cm.path_string) == "on"
        assert len(tr.steps) == 1
        assert tr.steps[0].from_state == "off" and tr.steps[0].to_state == "on"

    def test_guard_blocks_distinct_from_no_match(self) -> None:
        class Guarded(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                a = model.state("a", initial=True)
                b = model.state("b")
                e = model.event("e")
                model.transition(a, b, on=e, when=lambda _c, _p: False)

        Guarded._reset_compilation()
        cm = instantiate(Guarded)
        ctx = RunContext()
        rg = dispatch_event(ctx, cm, "e")
        assert rg.outcome is DispatchOutcome.GUARD_FAILED
        assert ctx.get_active_behavior_state(cm.path_string) == "a"

    def test_effect_sees_post_transition_state(self) -> None:
        seen: list[str | None] = []

        class Order(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                a = model.state("a", initial=True)
                b = model.state("b")
                ev = model.event("ev")

                def mark(ctx: RunContext, part) -> None:
                    seen.append(ctx.get_active_behavior_state(part.path_string))

                model.action("mark", effect=mark)
                model.transition(a, b, on=ev, effect="mark")

        Order._reset_compilation()
        cm = instantiate(Order)
        ctx = RunContext()
        assert dispatch_event(ctx, cm, "ev").outcome is DispatchOutcome.FIRED
        assert seen == ["b"]

    def test_effect_exception_reverts_state(self) -> None:
        class Boom(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                a = model.state("a", initial=True)
                b = model.state("b")
                ev = model.event("ev")

                def bad(_ctx, _part) -> None:
                    raise RuntimeError("effect failed")

                model.action("bad", effect=bad)
                model.transition(a, b, on=ev, effect="bad")

        Boom._reset_compilation()
        cm = instantiate(Boom)
        ctx = RunContext()
        tr = BehaviorTrace()
        with pytest.raises(RuntimeError, match="effect failed"):
            dispatch_event(ctx, cm, "ev", trace=tr)
        assert ctx.get_active_behavior_state(cm.path_string) == "a"
        assert tr.steps == []


class TestScenario:
    def test_scenario_match(self) -> None:
        class S(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                a = model.state("a", initial=True)
                b = model.state("b")
                c = model.state("c")
                e1 = model.event("e1")
                e2 = model.event("e2")
                model.transition(a, b, on=e1)
                model.transition(b, c, on=e2)
                model.scenario("seq", expected_event_order=[e1, e2])

        S._reset_compilation()
        cm = instantiate(S)
        ctx = RunContext()
        trace = BehaviorTrace()
        assert dispatch_event(ctx, cm, "e1", trace=trace).outcome is DispatchOutcome.FIRED
        assert dispatch_event(ctx, cm, "e2", trace=trace).outcome is DispatchOutcome.FIRED
        ok, errs = validate_scenario_trace(
            definition_type=S,
            scenario_name="seq",
            part_path=cm.path_string,
            trace=trace,
        )
        assert ok and errs == []
