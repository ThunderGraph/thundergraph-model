"""Unit tests for RunContext."""

from __future__ import annotations

import pytest

from tg_model.execution.run_context import ConstraintResult, RunContext, SlotState


class TestSlotRecordLifecycle:
    def test_initial_state_is_unbound(self) -> None:
        ctx = RunContext()
        assert ctx.get_state("slot1") == SlotState.UNBOUND

    def test_bind_input(self) -> None:
        ctx = RunContext()
        ctx.bind_input("slot1", 42.0)
        assert ctx.get_state("slot1") == SlotState.BOUND_INPUT
        assert ctx.get_value("slot1") == 42.0

    def test_realize(self) -> None:
        ctx = RunContext()
        ctx.realize("slot1", 99.0, provenance="computed")
        assert ctx.get_state("slot1") == SlotState.REALIZED
        assert ctx.get_value("slot1") == 99.0

    def test_fail(self) -> None:
        ctx = RunContext()
        record = ctx.get_or_create_record("slot1")
        record.fail("upstream failed")
        assert ctx.get_state("slot1") == SlotState.FAILED

    def test_get_value_raises_on_unbound(self) -> None:
        ctx = RunContext()
        with pytest.raises(ValueError, match="no ready value"):
            ctx.get_value("slot1")


class TestRunContextIsolation:
    def test_two_contexts_are_independent(self) -> None:
        ctx1 = RunContext()
        ctx2 = RunContext()
        ctx1.bind_input("slot1", 100.0)
        ctx2.bind_input("slot1", 200.0)
        assert ctx1.get_value("slot1") == 100.0
        assert ctx2.get_value("slot1") == 200.0


class TestConstraintResults:
    def test_add_and_query(self) -> None:
        ctx = RunContext()
        ctx.add_constraint_result(ConstraintResult("c1", True))
        ctx.add_constraint_result(ConstraintResult("c2", False))
        assert len(ctx.constraint_results) == 2
        assert ctx.all_passed is False

    def test_all_passed_when_all_true(self) -> None:
        ctx = RunContext()
        ctx.add_constraint_result(ConstraintResult("c1", True))
        ctx.add_constraint_result(ConstraintResult("c2", True))
        assert ctx.all_passed is True
