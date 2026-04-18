"""Runtime: decision, fork_join, emit_item, validate scenario final state, trace export."""

from __future__ import annotations

from typing import ClassVar

from tg_model.execution.behavior import (
    BehaviorStep,
    BehaviorTrace,
    DecisionDispatchOutcome,
    ItemFlowStep,
    behavior_authoring_projection,
    behavior_trace_to_records,
    dispatch_decision,
    dispatch_event,
    dispatch_fork_join,
    dispatch_sequence,
    emit_item,
    validate_scenario_trace,
)
from tg_model.execution.configured_model import instantiate
from tg_model.execution.instances import PartInstance
from tg_model.execution.run_context import RunContext
from tg_model.model.elements import Part, System


class Decider(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("decider")
        hot = model.guard("hot", predicate=lambda c, p: c.get_value(p.temp.stable_id) > 0)
        model.parameter("temp", unit="1")
        model.action("cool", effect=lambda c, p: c.bind_input(p.temp.stable_id, 0.0))
        model.action("heat", effect=lambda c, p: c.bind_input(p.temp.stable_id, 100.0))
        model.decision("route", branches=[(hot, "cool")], default_action="heat")


class Strict(Part):
    """Decision with no default: cold temp does not match ``hot`` guard."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("strict")
        hot = model.guard("hot", predicate=lambda c, p: c.get_value(p.temp.stable_id) > 0)
        model.parameter("temp", unit="1")
        model.action("cool", effect=lambda c, p: None)
        model.decision("route", branches=[(hot, "cool")])


class Forky(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("forky")
        model.action("a", effect=lambda c, p: None)
        model.action("b", effect=lambda c, p: None)
        model.action("c", effect=lambda c, p: None)
        model.fork_join("fj", branches=[["a"], ["b"]], then_action="c")


class DecisionMerge(Part):
    _after_hits: ClassVar[list[str]] = []

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("decision_merge")
        g = model.guard("take_a", predicate=lambda c, p: True)
        model.action("branch_a", effect=lambda c, p: None)
        model.action("branch_b", effect=lambda c, p: None)

        def after(_c, _p) -> None:
            cls._after_hits.append("after")

        model.action("after", effect=after)
        m = model.merge("m", then_action="after")
        model.decision("d", branches=[(g, "branch_a")], default_action="branch_b", merge_point=m)


class Seqgy(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("seqgy")
        model.action("s1", effect=lambda c, p: None)
        model.action("s2", effect=lambda c, p: None)
        model.sequence("main", steps=["s1", "s2"])


class Sender(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("sender")
        model.port("out", direction="out")
        model.item_kind("Msg")

        def send(ctx, p):
            pass  # emit_item called from test with port instance

        model.action("send", effect=send)


class Receiver(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("receiver")
        model.port("inp", direction="in")
        model.parameter("last", unit="1")

        def apply_msg(ctx: RunContext, p: PartInstance) -> None:
            pl = ctx.peek_item_payload(p.path_string, "Msg")
            if pl is not None:
                ctx.bind_input(p.last.stable_id, pl)

        model.action("apply_msg", effect=apply_msg)
        msg = model.event("Msg")
        off = model.state("off", initial=True)
        on = model.state("on")
        model.transition(off, on, on=msg, effect="apply_msg")


class Bus(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("bus")
        snd = model.composed_of("snd", Sender)
        rcv = model.composed_of("rcv", Receiver)
        model.connect(source=snd.out, target=rcv.inp, carrying="Msg")
        model.scenario(
            "flow",
            expected_event_order=[],
            expected_interaction_order=[("rcv", "Msg")],
            expected_item_kind_order=["Msg"],
        )


def setup_function() -> None:
    Decider._reset_compilation()
    Forky._reset_compilation()
    Strict._reset_compilation()
    DecisionMerge._after_hits.clear()
    DecisionMerge._reset_compilation()
    Seqgy._reset_compilation()
    Sender._reset_compilation()
    Receiver._reset_compilation()
    Bus._reset_compilation()


def test_dispatch_decision_default_branch() -> None:
    cm = instantiate(Decider)
    ctx = RunContext()
    ctx.bind_input(cm.temp.stable_id, -1.0)
    tr = BehaviorTrace()
    r = dispatch_decision(ctx, cm.root, "route", trace=tr)
    assert r.chosen_action == "heat"
    assert r.outcome is DecisionDispatchOutcome.ACTION_RAN
    assert r
    assert len(tr.decision_steps) == 1


def test_dispatch_decision_guard_branch() -> None:
    cm = instantiate(Decider)
    ctx = RunContext()
    ctx.bind_input(cm.temp.stable_id, 50.0)
    r = dispatch_decision(ctx, cm.root, "route")
    assert r.chosen_action == "cool"
    assert r.outcome is DecisionDispatchOutcome.ACTION_RAN


def test_dispatch_decision_no_action() -> None:
    cm = instantiate(Strict)
    ctx = RunContext()
    ctx.bind_input(cm.temp.stable_id, -1.0)
    r = dispatch_decision(ctx, cm.root, "route")
    assert not r
    assert r.outcome is DecisionDispatchOutcome.NO_ACTION
    assert r.chosen_action is None


def test_dispatch_fork_join() -> None:
    cm = instantiate(Forky)
    ctx = RunContext()
    tr = BehaviorTrace()
    dispatch_fork_join(ctx, cm.root, "fj", trace=tr)
    assert len(tr.fork_join_steps) == 1


def test_dispatch_decision_then_merge_runs_shared_continuation() -> None:
    cm = instantiate(DecisionMerge)
    ctx = RunContext()
    tr = BehaviorTrace()
    r = dispatch_decision(ctx, cm.root, "d", trace=tr)
    assert r.merge_ran
    assert DecisionMerge._after_hits == ["after"]
    assert len(tr.merge_steps) == 1
    kinds = [r["kind"] for r in behavior_trace_to_records(tr)]
    assert kinds == ["decision", "merge"]


def test_dispatch_sequence() -> None:
    cm = instantiate(Seqgy)
    ctx = RunContext()
    tr = BehaviorTrace()
    dispatch_sequence(ctx, cm.root, "main", trace=tr)
    assert len(tr.sequence_steps) == 1


def test_behavior_authoring_projection() -> None:
    proj = behavior_authoring_projection(Seqgy)
    assert "sequences" in proj and "main" in proj["sequences"]
    assert proj["transitions"] == []


def test_emit_item_dispatches_receiver_event_and_payload() -> None:
    cm = instantiate(Bus)
    ctx = RunContext()
    tr = BehaviorTrace()
    out = emit_item(ctx, cm, cm.snd.out, "Msg", 42, trace=tr)
    assert len(out) == 1
    assert out[0]
    assert ctx.get_active_behavior_state(cm.rcv.path_string) == "on"
    assert ctx.get_value(cm.rcv.last.stable_id) == 42
    assert len(tr.item_flows) == 1
    assert tr.item_flows[0].payload == 42
    ok, err = validate_scenario_trace(
        definition_type=Bus,
        scenario_name="flow",
        part_path=cm.path_string,
        trace=tr,
        root=cm.root,
    )
    assert ok and err == []


def test_validate_scenario_initial_from_state() -> None:
    class S(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            a = model.state("a", initial=True)
            b = model.state("b")
            e = model.event("e")
            model.transition(a, b, on=e)
            model.scenario(
                "bad_init",
                expected_event_order=[e],
                initial_behavior_state="b",
            )

    S._reset_compilation()
    cm = instantiate(S)
    ctx = RunContext()
    tr = BehaviorTrace()
    dispatch_event(ctx, cm.root, "e", trace=tr)
    ok, err = validate_scenario_trace(
        definition_type=S,
        scenario_name="bad_init",
        part_path=cm.path_string,
        trace=tr,
    )
    assert not ok
    assert any("initial" in m for m in err)


def test_validate_scenario_final_state() -> None:
    class S(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            a = model.state("a", initial=True)
            b = model.state("b")
            e = model.event("e")
            model.transition(a, b, on=e)
            model.scenario(
                "sc",
                expected_event_order=[e],
                expected_final_behavior_state="b",
            )

    S._reset_compilation()
    cm = instantiate(S)
    ctx = RunContext()
    tr = BehaviorTrace()
    dispatch_event(ctx, cm.root, "e", trace=tr)
    ok, err = validate_scenario_trace(
        definition_type=S,
        scenario_name="sc",
        part_path=cm.path_string,
        trace=tr,
        ctx=ctx,
    )
    assert ok and err == []


def test_behavior_trace_to_records_sorted() -> None:
    tr = BehaviorTrace()
    tr.steps.append(
        BehaviorStep(
            step_index=1,
            part_path="p",
            event_name="e",
            from_state="a",
            to_state="b",
            effect_name=None,
        )
    )
    tr.item_flows.append(
        ItemFlowStep(
            step_index=0,
            source_port_path="s",
            target_port_path="t",
            item_kind="k",
        )
    )
    recs = behavior_trace_to_records(tr)
    assert [r["step_index"] for r in recs] == [0, 1]
