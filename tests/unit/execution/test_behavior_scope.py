"""Phase 6: behavior effects may only touch value slots on the active part subtree."""

from __future__ import annotations

import pytest

from tg_model.execution.behavior import dispatch_decision, dispatch_event, dispatch_sequence
from tg_model.execution.configured_model import instantiate
from tg_model.execution.run_context import RunContext
from tg_model.model.elements import Part, System


class PeerB(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("peer_b")
        model.parameter("t", unit="1")


class PeerA(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("peer_a")
        model.parameter("t", unit="1")


class PeerSys(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("peer_sys")
        model.composed_of("a", PeerA)
        model.composed_of("b", PeerB)


def setup_function() -> None:
    PeerSys._reset_compilation()


def test_behavior_effect_cannot_bind_peer_slot() -> None:
    steal_id: list[str | None] = [None]

    class PeerASteal(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("peer_a_steal")
            model.parameter("t", unit="1")

            def steal(ctx, p) -> None:
                ctx.bind_input(steal_id[0], 1.0)  # type: ignore[arg-type]

            model.action("steal", effect=steal)
            model.sequence("s", steps=["steal"])

    class SysSteal(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sys_steal")
            model.composed_of("a", PeerASteal)
            model.composed_of("b", PeerB)

    SysSteal._reset_compilation()
    cm = instantiate(SysSteal)
    steal_id[0] = cm.b.t.stable_id

    ctx = RunContext()
    with pytest.raises(RuntimeError, match="structural boundary"):
        dispatch_sequence(ctx, cm.a, "s")


def test_get_or_create_record_respects_behavior_scope() -> None:
    steal_id: list[str | None] = [None]

    class PeerASteal(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("peer_a_steal")
            model.parameter("t", unit="1")

            def steal(ctx, p) -> None:
                ctx.get_or_create_record(steal_id[0])  # type: ignore[arg-type]

            model.action("steal", effect=steal)
            model.sequence("s", steps=["steal"])

    class SysSteal(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sys_steal")
            model.composed_of("a", PeerASteal)
            model.composed_of("b", PeerB)

    SysSteal._reset_compilation()
    cm = instantiate(SysSteal)
    steal_id[0] = cm.b.t.stable_id

    ctx = RunContext()
    with pytest.raises(RuntimeError, match="structural boundary"):
        dispatch_sequence(ctx, cm.a, "s")


def test_pop_behavior_effect_scope_without_push_raises() -> None:
    ctx = RunContext()
    with pytest.raises(RuntimeError, match="matching push_behavior_effect_scope"):
        ctx.pop_behavior_effect_scope()


def test_transition_guard_cannot_read_peer_slot() -> None:
    steal_id: list[str | None] = [None]

    class PeerAState(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("peer_a_state")
            model.parameter("t", unit="1")
            a = model.state("a", initial=True)
            b = model.state("b")
            e = model.event("e")

            def bad(c: RunContext, p) -> bool:
                return c.get_value(steal_id[0]) is not None  # type: ignore[arg-type]

            model.transition(a, b, on=e, when=bad)

    class SysGuard(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sys_guard")
            model.composed_of("a", PeerAState)
            model.composed_of("b", PeerB)

    SysGuard._reset_compilation()
    cm = instantiate(SysGuard)
    steal_id[0] = cm.b.t.stable_id
    ctx = RunContext()
    ctx.bind_input(cm.b.t.stable_id, 1.0)
    with pytest.raises(RuntimeError, match="structural boundary"):
        dispatch_event(ctx, cm.a, "e")


def test_decision_predicate_cannot_read_peer_slot() -> None:
    steal_id: list[str | None] = [None]

    class PeerADec(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("peer_a_dec")
            model.parameter("t", unit="1")

            def bad_pred(c: RunContext, p) -> bool:
                return c.get_value(steal_id[0]) == 1.0  # type: ignore[arg-type]

            g = model.guard("peer_bad", predicate=bad_pred)
            model.action("act", effect=lambda c, p: None)
            model.decision("d", branches=[(g, "act")])

    class SysDec(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sys_dec")
            model.composed_of("a", PeerADec)
            model.composed_of("b", PeerB)

    SysDec._reset_compilation()
    cm = instantiate(SysDec)
    steal_id[0] = cm.b.t.stable_id
    ctx = RunContext()
    ctx.bind_input(cm.b.t.stable_id, 1.0)
    with pytest.raises(RuntimeError, match="structural boundary"):
        dispatch_decision(ctx, cm.a, "d")


def test_behavior_effect_can_bind_own_slot() -> None:
    class PeerAOk(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("peer_a_ok")
            model.parameter("t", unit="1")

            def ok(ctx, p) -> None:
                ctx.bind_input(p.t.stable_id, 3.0)

            model.action("ok", effect=ok)
            model.sequence("s", steps=["ok"])

    class SysOk(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sys_ok")
            model.composed_of("a", PeerAOk)

    SysOk._reset_compilation()
    cm = instantiate(SysOk)
    ctx = RunContext()
    dispatch_sequence(ctx, cm.a, "s")
    assert ctx.get_value(cm.a.t.stable_id) == 3.0
