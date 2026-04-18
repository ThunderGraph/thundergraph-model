"""Compile-time rules for Phase 6 ontology: guard, decision, fork_join, scenario extras."""

from __future__ import annotations

import pytest

from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part


class GuardTransition(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("guard_transition")
        g = model.guard("ok", predicate=lambda c, p: True)
        off = model.state("off", initial=True)
        on = model.state("on")
        ev = model.event("go")
        model.transition(off, on, on=ev, guard=g)


class BadDecisionAction(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("bad_decision_action")
        g = model.guard("g", predicate=lambda c, p: True)
        model.decision("d", branches=[(g, "missing_action")])


class BadMergeAction(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("bad_merge_action")
        model.merge("m", then_action="nope")


def setup_function() -> None:
    GuardTransition._reset_compilation()
    BadDecisionAction._reset_compilation()
    BadMergeAction._reset_compilation()


def test_guard_on_transition_compiles() -> None:
    art = GuardTransition.compile()
    assert art["behavior_transitions"][0]["has_guard"] is True


def test_decision_unknown_action_rejected() -> None:
    BadDecisionAction._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="unknown action"):
        BadDecisionAction.compile()


def test_merge_unknown_then_action_rejected() -> None:
    BadMergeAction._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="unknown action"):
        BadMergeAction.compile()


def test_decision_merge_point_must_be_merge() -> None:
    class Bad(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("bad")
            g = model.guard("g", predicate=lambda c, p: True)
            model.action("a")
            model.decision("d", branches=[(None, "a")], merge_point=g)

    Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="merge ref"):
        Bad.compile()


def test_transition_guard_and_when_mutually_exclusive() -> None:
    class Both(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("both")
            g = model.guard("g", predicate=lambda c, p: True)
            off = model.state("off", initial=True)
            on = model.state("on")
            ev = model.event("e")
            model.transition(off, on, on=ev, guard=g, when=lambda c, p: True)

    Both._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="when= or guard="):
        Both.compile()


def test_scenario_final_state_metadata_preserved() -> None:
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
    art = S.compile()
    meta = art["nodes"]["sc"]["metadata"]
    assert meta["_expected_final_behavior_state"] == "b"
