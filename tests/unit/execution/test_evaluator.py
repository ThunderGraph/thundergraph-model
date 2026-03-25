"""Unit tests for the synchronous evaluator."""

from __future__ import annotations

from tg_model.execution.dependency_graph import DependencyGraph, DependencyNode, NodeKind
from tg_model.execution.evaluator import Evaluator, RunResult
from tg_model.execution.run_context import RunContext, SlotState


def _build_power_graph() -> tuple[DependencyGraph, dict]:
    """Build: speed, torque -> power_expr -> power_val, then constraint."""
    g = DependencyGraph()
    g.add_node(DependencyNode("speed", NodeKind.INPUT_PARAMETER, slot_id="s_speed"))
    g.add_node(DependencyNode("torque", NodeKind.INPUT_PARAMETER, slot_id="s_torque"))
    g.add_node(DependencyNode("power_expr", NodeKind.LOCAL_EXPRESSION, slot_id="s_power"))
    g.add_node(DependencyNode("power_val", NodeKind.ATTRIBUTE_VALUE, slot_id="s_power"))
    g.add_node(DependencyNode("power_check", NodeKind.CONSTRAINT_CHECK, metadata={"name": "power_positive"}))
    g.add_edge("speed", "power_expr")
    g.add_edge("torque", "power_expr")
    g.add_edge("power_expr", "power_val")
    g.add_edge("power_val", "power_check")

    handlers = {
        "power_expr": lambda deps: deps["speed"] * deps["torque"],
        "power_check": lambda deps: deps["power_val"] > 0,
    }
    return g, handlers


class TestBasicEvaluation:
    def test_evaluates_power(self) -> None:
        g, handlers = _build_power_graph()
        evaluator = Evaluator(g, compute_handlers=handlers)
        ctx = RunContext()
        result = evaluator.evaluate(ctx, inputs={"s_speed": 100.0, "s_torque": 50.0})
        assert result.passed
        assert ctx.get_value("s_power") == 5000.0

    def test_constraint_passes(self) -> None:
        g, handlers = _build_power_graph()
        evaluator = Evaluator(g, compute_handlers=handlers)
        ctx = RunContext()
        result = evaluator.evaluate(ctx, inputs={"s_speed": 100.0, "s_torque": 50.0})
        assert len(result.constraint_results) == 1
        assert result.constraint_results[0].passed is True
        assert result.constraint_results[0].name == "power_positive"


class TestFailurePropagation:
    def test_missing_required_input_fails(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("speed", NodeKind.INPUT_PARAMETER, slot_id="s_speed", metadata={"required": True}))
        evaluator = Evaluator(g)
        ctx = RunContext()
        result = evaluator.evaluate(ctx)
        assert not result.passed
        assert any("Missing required input" in f for f in result.failures)

    def test_missing_handler_fails(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.INPUT_PARAMETER, slot_id="s_a"))
        g.add_node(DependencyNode("expr", NodeKind.LOCAL_EXPRESSION, slot_id="s_out"))
        g.add_edge("a", "expr")
        evaluator = Evaluator(g, compute_handlers={})
        ctx = RunContext()
        result = evaluator.evaluate(ctx, inputs={"s_a": 1.0})
        assert not result.passed
        assert any("No compute handler" in f for f in result.failures)

    def test_blocked_propagation(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.INPUT_PARAMETER, slot_id="s_a", metadata={"required": True}))
        g.add_node(DependencyNode("expr", NodeKind.LOCAL_EXPRESSION, slot_id="s_out"))
        g.add_edge("a", "expr")
        evaluator = Evaluator(g, compute_handlers={"expr": lambda deps: deps["a"] * 2})
        ctx = RunContext()
        result = evaluator.evaluate(ctx)
        assert ctx.get_state("s_out") == SlotState.BLOCKED


class TestRunContextIsolation:
    def test_repeated_runs_are_isolated(self) -> None:
        g, handlers = _build_power_graph()
        evaluator = Evaluator(g, compute_handlers=handlers)

        ctx1 = RunContext()
        r1 = evaluator.evaluate(ctx1, inputs={"s_speed": 100.0, "s_torque": 50.0})

        ctx2 = RunContext()
        r2 = evaluator.evaluate(ctx2, inputs={"s_speed": 200.0, "s_torque": 25.0})

        assert ctx1.get_value("s_power") == 5000.0
        assert ctx2.get_value("s_power") == 5000.0
        assert r1.passed and r2.passed
