"""Unit tests for pre-execution static validation."""

from __future__ import annotations

from tg_model.execution.dependency_graph import DependencyGraph, DependencyNode, NodeKind
from tg_model.execution.validation import validate_graph


class TestCycleDetection:
    def test_valid_graph_passes(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.INPUT_PARAMETER))
        g.add_node(DependencyNode("b", NodeKind.LOCAL_EXPRESSION))
        g.add_edge("a", "b")
        result = validate_graph(g)
        assert result.passed

    def test_cycle_detected(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.ATTRIBUTE_VALUE))
        g.add_node(DependencyNode("b", NodeKind.LOCAL_EXPRESSION))
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        result = validate_graph(g)
        assert not result.passed
        assert any("cycle" in f.message.lower() for f in result.failures)


class TestOrphanedCompute:
    def test_fully_disconnected_compute_flagged(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("orphan_expr", NodeKind.LOCAL_EXPRESSION))
        result = validate_graph(g)
        assert not result.passed
        assert any("no dependencies" in f.message.lower() for f in result.failures)

    def test_compute_with_deps_passes(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("input", NodeKind.INPUT_PARAMETER))
        g.add_node(DependencyNode("expr", NodeKind.LOCAL_EXPRESSION))
        g.add_edge("input", "expr")
        result = validate_graph(g)
        assert result.passed

    def test_constant_compute_with_dependents_passes(self) -> None:
        """A constant expression (no deps) that feeds a value node is valid."""
        g = DependencyGraph()
        g.add_node(DependencyNode("const_expr", NodeKind.LOCAL_EXPRESSION))
        g.add_node(DependencyNode("output", NodeKind.ATTRIBUTE_VALUE))
        g.add_edge("const_expr", "output")
        result = validate_graph(g)
        assert result.passed


class TestEmptyRollup:
    def test_empty_rollup_flagged(self) -> None:
        """A roll-up with no child dependencies is invalid."""
        g = DependencyGraph()
        g.add_node(DependencyNode("rollup_node", NodeKind.ROLLUP_COMPUTATION))
        g.add_node(DependencyNode("output", NodeKind.ATTRIBUTE_VALUE))
        g.add_edge("rollup_node", "output")
        result = validate_graph(g)
        assert not result.passed
        assert any("roll-up" in f.message.lower() for f in result.failures)

    def test_rollup_with_children_passes(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("child_val", NodeKind.INPUT_PARAMETER))
        g.add_node(DependencyNode("rollup_node", NodeKind.ROLLUP_COMPUTATION))
        g.add_node(DependencyNode("output", NodeKind.ATTRIBUTE_VALUE))
        g.add_edge("child_val", "rollup_node")
        g.add_edge("rollup_node", "output")
        result = validate_graph(g)
        assert result.passed
