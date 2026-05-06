"""Unit tests: behavioral declarations compile-time rules."""

from __future__ import annotations

import pytest

from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part
from tg_model.execution.behavior import behavior_authoring_projection

try:
    from common.services.tg_model_projector.bundle_walker import _behavioral_records  # type: ignore[import]
    from tg_model.execution.configured_model import instantiate as _tg_instantiate
    _BUNDLE_WALKER_AVAILABLE = True
except ImportError:
    _BUNDLE_WALKER_AVAILABLE = False


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


# ---------------------------------------------------------------------------
# then= pointing at control nodes (decision / merge / fork_join)
# ---------------------------------------------------------------------------

class ThenToMerge(Part):
    """action.then= pointing at a merge control node must compile and project."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_to_merge")
        loop = model.merge("loop_back", then_action="tick")
        model.action("tick",  then="loop_back")   # → merge (control node)
        model.action("loop_back")  # should never be reached; merge owns the name


class ThenToMergeSimple(Part):
    """Simplest: an action chains into a merge which loops back."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_to_merge_simple")
        model.merge("gate", then_action="run")
        model.action("run",  then="gate")   # run → gate (merge) → run  (loop)


class ThenToForkJoin(Part):
    """action.then= pointing at a fork_join must compile and resolve to __fork."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_to_fork_join")
        model.action("prepare",    then="split")   # → fork_join entry node
        model.action("branch_a")
        model.action("branch_b")
        model.action("after_fork")
        model.fork_join(
            "split",
            branches=[["branch_a"], ["branch_b"]],
            then_action="after_fork",
        )


class ThenToDecision(Part):
    """action.then= pointing at a decision must compile and appear in successions."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_to_decision")
        model.action("evaluate", then="check")   # → decision
        ok = model.guard("ok", predicate=lambda ctx, p: True)
        model.action("pass_action")
        model.action("fail_action")
        model.decision(
            "check",
            branches=[(ok, "pass_action"), (None, "fail_action")],
        )


class ThenToForkBadBranchStep(Part):
    """fork_join branch steps must still be plain actions — not control nodes."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("then_to_fork_bad_branch_step")
        model.merge("my_merge", then_action="after")
        model.action("after")
        model.action("real_action")
        model.fork_join(
            "bad_fork",
            branches=[["my_merge"]],   # ← merge inside a branch step — should fail
            then_action="after",
        )


def setup_function() -> None:  # noqa: F811
    for cls in (
        GoodMachine, DupTransition, TwoInitial, StatesNoInitial, BadEffect,
        ThenChain, ThenWithEffect, ThenBadTarget, ThenSelfLoop, ThenCycle,
        ThenToMerge, ThenToMergeSimple, ThenToForkJoin, ThenToDecision,
        ThenToForkBadBranchStep,
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


# ---------------------------------------------------------------------------
# then= pointing at control nodes
# ---------------------------------------------------------------------------

class TestThenToControlNode:
    """then= on a plain action may target a decision, merge, or fork_join."""

    def test_then_to_merge_compiles(self) -> None:
        ThenToMergeSimple._reset_compilation()
        art = ThenToMergeSimple.compile()
        assert art["nodes"]["run"]["metadata"]["_then"] == "gate"

    def test_then_to_fork_join_compiles(self) -> None:
        ThenToForkJoin._reset_compilation()
        art = ThenToForkJoin.compile()
        assert art["nodes"]["prepare"]["metadata"]["_then"] == "split"

    def test_then_to_decision_compiles(self) -> None:
        ThenToDecision._reset_compilation()
        art = ThenToDecision.compile()
        assert art["nodes"]["evaluate"]["metadata"]["_then"] == "check"

    def test_then_to_nonexistent_still_rejected(self) -> None:
        """A then= pointing at a completely undeclared name still raises."""
        class _Bad(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("bad_ctrl_target")
                model.action("a", then="ghost_node")
        _Bad._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="ghost_node"):
            _Bad.compile()

    def test_fork_branch_step_must_be_plain_action(self) -> None:
        """Control nodes are NOT valid as fork_join branch steps."""
        ThenToForkBadBranchStep._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="my_merge"):
            ThenToForkBadBranchStep.compile()

    @pytest.mark.skipif(not _BUNDLE_WALKER_AVAILABLE, reason="bundle_walker not in path")
    def test_then_to_fork_join_generates_succession_to_fork_node(self) -> None:
        """bundle_walker must emit a succession from 'prepare' to 'split__fork'."""
        ThenToForkJoin._reset_compilation()
        cm = _tg_instantiate(ThenToForkJoin)
        part = next(iter(cm.id_registry.values()))  # only one PartInstance
        beh = _behavioral_records(part)
        src_dst_pairs = {
            (s["source_stable_id"], s["target_stable_id"])
            for s in beh["successions"]
        }
        action_map = {a["name"]: a["stable_id"] for a in beh["actions"]}
        prepare_sid = action_map.get("prepare")
        fork_sid = action_map.get("split__fork")
        assert prepare_sid is not None, "prepare action missing from bundle"
        assert fork_sid is not None, "split__fork node missing from bundle"
        assert (prepare_sid, fork_sid) in src_dst_pairs, (
            "No succession edge from 'prepare' to 'split__fork' found"
        )

    @pytest.mark.skipif(not _BUNDLE_WALKER_AVAILABLE, reason="bundle_walker not in path")
    def test_then_to_merge_generates_succession_to_merge_node(self) -> None:
        """bundle_walker must emit a succession from 'run' to the merge node."""
        ThenToMergeSimple._reset_compilation()
        cm = _tg_instantiate(ThenToMergeSimple)
        part = next(iter(cm.id_registry.values()))
        beh = _behavioral_records(part)
        src_dst_pairs = {
            (s["source_stable_id"], s["target_stable_id"])
            for s in beh["successions"]
        }
        action_map = {a["name"]: a["stable_id"] for a in beh["actions"]}
        run_sid = action_map.get("run")
        gate_sid = action_map.get("gate")
        assert run_sid is not None, "run action missing from bundle"
        assert gate_sid is not None, "gate merge node missing from bundle"
        assert (run_sid, gate_sid) in src_dst_pairs, (
            "No succession edge from 'run' to 'gate' merge found"
        )

    @pytest.mark.skipif(not _BUNDLE_WALKER_AVAILABLE, reason="bundle_walker not in path")
    def test_then_to_decision_generates_succession_to_decision_node(self) -> None:
        """bundle_walker must emit a succession from 'evaluate' to the decision node."""
        ThenToDecision._reset_compilation()
        cm = _tg_instantiate(ThenToDecision)
        part = next(iter(cm.id_registry.values()))
        beh = _behavioral_records(part)
        src_dst_pairs = {
            (s["source_stable_id"], s["target_stable_id"])
            for s in beh["successions"]
        }
        action_map = {a["name"]: a["stable_id"] for a in beh["actions"]}
        evaluate_sid = action_map.get("evaluate")
        check_sid = action_map.get("check")
        assert evaluate_sid is not None, "evaluate action missing from bundle"
        assert check_sid is not None, "check decision node missing from bundle"
        assert (evaluate_sid, check_sid) in src_dst_pairs, (
            "No succession edge from 'evaluate' to 'check' decision found"
        )
