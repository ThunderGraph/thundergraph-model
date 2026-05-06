"""Unit tests: behavioral declarations compile-time rules."""

from __future__ import annotations

import pytest

from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part
from tg_model.execution.behavior import behavior_authoring_projection


class GoodMachine(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("good_machine")
        off = model.state("off", initial=True)
        on = model.state("on")
        ev = model.event("go")
        model.action("noop")
        model.transition(off, on, on=ev)


class DupTransition(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("dup_transition")
        a = model.state("a", initial=True)
        b = model.state("b")
        e = model.event("x")
        model.transition(a, b, on=e)
        model.transition(a, b, on=e)


class TwoInitial(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("two_initial")
        model.state("s1", initial=True)
        model.state("s2", initial=True)


class StatesNoInitial(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("states_no_initial")
        model.state("only", initial=False)


class BadEffect(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("bad_effect")
        s = model.state("s", initial=True)
        s2 = model.state("s2")
        e = model.event("e")
        model.transition(s, s2, on=e, effect="not_an_action")


def setup_function() -> None:
    GoodMachine._reset_compilation()
    DupTransition._reset_compilation()
    TwoInitial._reset_compilation()
    StatesNoInitial._reset_compilation()
    BadEffect._reset_compilation()


class TestBehaviorCompile:
    def test_valid_machine_compiles(self) -> None:
        art = GoodMachine.compile()
        assert len(art["behavior_transitions"]) == 1
        assert art["behavior_transitions"][0]["from"] == "off"

    def test_duplicate_transition_rejected(self) -> None:
        DupTransition._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="Duplicate transition"):
            DupTransition.compile()

    def test_two_initial_states_rejected(self) -> None:
        TwoInitial._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="exactly one initial"):
            TwoInitial.compile()

    def test_states_without_initial_rejected(self) -> None:
        StatesNoInitial._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="exactly one initial"):
            StatesNoInitial.compile()

    def test_unknown_effect_rejected(self) -> None:
        BadEffect._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="action"):
            BadEffect.compile()


# ---------------------------------------------------------------------------
# then= parameter on model.action()
# ---------------------------------------------------------------------------

class ThenChain(Part):
    """Linear flow declared via then=: a → b → c."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_chain")
        model.action("a", then="b")
        model.action("b", then="c")
        model.action("c")


class ThenWithEffect(Part):
    """then= and effect= can coexist on the same action."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_with_effect")
        model.action("init", then="run", effect=lambda ctx, p: None)
        model.action("run")


class ThenBadTarget(Part):
    """then= pointing at an undeclared action must be rejected at compile time."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_bad_target")
        model.action("a", then="does_not_exist")


class ThenSelfLoop(Part):
    """Circular then= (A→A) is allowed — activity diagram renders a loop."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_self_loop")
        model.action("tick", then="tick")


class ThenCycle(Part):
    """Longer cycle (A→B→A) is allowed — diagram renders the cycle."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_cycle")
        model.action("sense", then="plan")
        model.action("plan",  then="sense")


def setup_function() -> None:  # noqa: F811
    for cls in (
        GoodMachine, DupTransition, TwoInitial, StatesNoInitial, BadEffect,
        ThenChain, ThenWithEffect, ThenBadTarget, ThenSelfLoop, ThenCycle,
    ):
        cls._reset_compilation()


class TestThenParameter:
    def test_then_chain_compiles(self) -> None:
        art = ThenChain.compile()
        nodes = art["nodes"]
        assert nodes["a"]["metadata"]["_then"] == "b"
        assert nodes["b"]["metadata"]["_then"] == "c"
        assert nodes["c"]["metadata"].get("_then") is None

    def test_then_chain_projection_returns_actions(self) -> None:
        ThenChain._reset_compilation()
        proj = behavior_authoring_projection(ThenChain)
        assert "a" in proj["actions"]
        assert "b" in proj["actions"]
        assert "c" in proj["actions"]

    def test_then_with_effect_compiles(self) -> None:
        art = ThenWithEffect.compile()
        meta_init = art["nodes"]["init"]["metadata"]
        assert meta_init["_then"] == "run"
        assert callable(meta_init["_effect"])

    def test_then_bad_target_rejected(self) -> None:
        ThenBadTarget._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="does_not_exist"):
            ThenBadTarget.compile()

    def test_then_self_loop_allowed(self) -> None:
        """A→A cycle must not raise — diagram renders a self-loop."""
        ThenSelfLoop._reset_compilation()
        art = ThenSelfLoop.compile()
        assert art["nodes"]["tick"]["metadata"]["_then"] == "tick"

    def test_then_cycle_allowed(self) -> None:
        """A→B→A cycle must not raise — diagram renders the loop."""
        ThenCycle._reset_compilation()
        art = ThenCycle.compile()
        assert art["nodes"]["sense"]["metadata"]["_then"] == "plan"
        assert art["nodes"]["plan"]["metadata"]["_then"] == "sense"

    def test_ref_returned_has_correct_kind(self) -> None:
        """model.action() must still return a Ref with kind='action' when then= is set."""
        class _Inline(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("inline_ref_check")
                ref = model.action("x", then="y")
                model.action("y")
                assert ref.kind == "action"
                assert ref.path == ("x",)

        _Inline._reset_compilation()
        _Inline.compile()  # assertion runs inside define()

    def test_action_without_then_has_no_then_metadata(self) -> None:
        """Effect-only actions must not have _then in compiled metadata."""
        ThenChain._reset_compilation()
        art = ThenChain.compile()
        assert "_then" not in art["nodes"]["c"]["metadata"]
