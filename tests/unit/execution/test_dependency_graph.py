"""Unit tests for the bipartite dependency graph."""

from __future__ import annotations

import pytest

from tg_model.execution.dependency_graph import DependencyGraph, DependencyNode, NodeKind


class TestNodeKinds:
    def test_value_nodes(self) -> None:
        for kind in (NodeKind.INPUT_PARAMETER, NodeKind.ATTRIBUTE_VALUE, NodeKind.CONSTRAINT_RESULT):
            node = DependencyNode("n", kind)
            assert node.is_value_node
            assert not node.is_compute_node

    def test_compute_nodes(self) -> None:
        for kind in (NodeKind.LOCAL_EXPRESSION, NodeKind.ROLLUP_COMPUTATION, NodeKind.CONSTRAINT_CHECK):
            node = DependencyNode("n", kind)
            assert node.is_compute_node
            assert not node.is_value_node


class TestGraphConstruction:
    def test_add_nodes_and_edges(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("speed", NodeKind.INPUT_PARAMETER, slot_id="s1"))
        g.add_node(DependencyNode("torque", NodeKind.INPUT_PARAMETER, slot_id="s2"))
        g.add_node(DependencyNode("power_expr", NodeKind.LOCAL_EXPRESSION, slot_id="s3"))
        g.add_node(DependencyNode("power", NodeKind.ATTRIBUTE_VALUE, slot_id="s3"))
        g.add_edge("speed", "power_expr")
        g.add_edge("torque", "power_expr")
        g.add_edge("power_expr", "power")

        assert len(g.nodes) == 4
        assert len(g.edges) == 3
        assert g.dependencies_of("power_expr") == ["speed", "torque"]
        assert g.dependents_of("speed") == ["power_expr"]


class TestTopologicalOrder:
    def test_simple_chain(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.INPUT_PARAMETER))
        g.add_node(DependencyNode("b", NodeKind.LOCAL_EXPRESSION))
        g.add_node(DependencyNode("c", NodeKind.ATTRIBUTE_VALUE))
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        order = g.topological_order()
        assert order.index("a") < order.index("b") < order.index("c")

    def test_cycle_raises(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.ATTRIBUTE_VALUE))
        g.add_node(DependencyNode("b", NodeKind.LOCAL_EXPRESSION))
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        with pytest.raises(ValueError, match="cycle"):
            g.topological_order()

    def test_deterministic_for_identical_graph(self) -> None:
        def build() -> list[str]:
            g = DependencyGraph()
            g.add_node(DependencyNode("x", NodeKind.INPUT_PARAMETER))
            g.add_node(DependencyNode("y", NodeKind.INPUT_PARAMETER))
            g.add_node(DependencyNode("z", NodeKind.LOCAL_EXPRESSION))
            g.add_edge("x", "z")
            g.add_edge("y", "z")
            return g.topological_order()

        assert build() == build()


class TestClosuresAndSubgraph:
    def test_dependency_closure_includes_seeds_and_ancestors(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.INPUT_PARAMETER, slot_id="sa"))
        g.add_node(DependencyNode("b", NodeKind.INPUT_PARAMETER, slot_id="sb"))
        g.add_node(DependencyNode("expr", NodeKind.LOCAL_EXPRESSION))
        g.add_node(DependencyNode("out", NodeKind.ATTRIBUTE_VALUE, slot_id="sout"))
        g.add_edge("a", "expr")
        g.add_edge("b", "expr")
        g.add_edge("expr", "out")
        c = g.dependency_closure(["out"])
        assert c == {"out", "expr", "a", "b"}

    def test_dependent_closure_includes_seeds_and_descendants(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.INPUT_PARAMETER, slot_id="sa"))
        g.add_node(DependencyNode("expr", NodeKind.LOCAL_EXPRESSION))
        g.add_node(DependencyNode("out", NodeKind.ATTRIBUTE_VALUE, slot_id="sout"))
        g.add_node(DependencyNode("check", NodeKind.CONSTRAINT_CHECK))
        g.add_edge("a", "expr")
        g.add_edge("expr", "out")
        g.add_edge("out", "check")
        c = g.dependent_closure(["a"])
        assert c == {"a", "expr", "out", "check"}

    def test_induced_subgraph_preserves_edges_inside(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("a", NodeKind.INPUT_PARAMETER))
        g.add_node(DependencyNode("b", NodeKind.LOCAL_EXPRESSION))
        g.add_node(DependencyNode("c", NodeKind.ATTRIBUTE_VALUE))
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        sub = g.induced_subgraph({"a", "b"})
        assert set(sub.nodes) == {"a", "b"}
        assert sub.edges == [("a", "b")]

    def test_unknown_seed_raises(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("x", NodeKind.INPUT_PARAMETER))
        with pytest.raises(KeyError):
            g.dependency_closure(["missing"])
