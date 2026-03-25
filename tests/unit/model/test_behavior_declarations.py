"""Unit tests: behavioral declarations compile-time rules."""

from __future__ import annotations

import pytest

from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part


class GoodMachine(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        off = model.state("off", initial=True)
        on = model.state("on")
        ev = model.event("go")
        model.action("noop")
        model.transition(off, on, on=ev)


class DupTransition(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        a = model.state("a", initial=True)
        b = model.state("b")
        e = model.event("x")
        model.transition(a, b, on=e)
        model.transition(a, b, on=e)


class TwoInitial(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.state("s1", initial=True)
        model.state("s2", initial=True)


class StatesNoInitial(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.state("only", initial=False)


class BadEffect(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
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
