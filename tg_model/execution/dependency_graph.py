"""Bipartite dependency graph for configured models.

Value nodes represent slots (parameters, attributes, constraint results).
Compute nodes represent operations (expressions, roll-ups, constraints).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Any


class NodeKind(Enum):
    INPUT_PARAMETER = "input_parameter"
    ATTRIBUTE_VALUE = "attribute_value"
    CONSTRAINT_RESULT = "constraint_result"
    LOCAL_EXPRESSION = "local_expression"
    ROLLUP_COMPUTATION = "rollup_computation"
    SOLVE_GROUP = "solve_group"
    CONSTRAINT_CHECK = "constraint_check"
    EXTERNAL_COMPUTATION = "external_computation"


class DependencyNode:
    """One node in the configuration-scoped dependency graph."""

    __slots__ = ("kind", "metadata", "node_id", "slot_id")

    def __init__(
        self,
        node_id: str,
        kind: NodeKind,
        slot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.node_id = node_id
        self.kind = kind
        self.slot_id = slot_id
        self.metadata = metadata or {}

    @property
    def is_value_node(self) -> bool:
        return self.kind in (
            NodeKind.INPUT_PARAMETER,
            NodeKind.ATTRIBUTE_VALUE,
            NodeKind.CONSTRAINT_RESULT,
        )

    @property
    def is_compute_node(self) -> bool:
        return self.kind in (
            NodeKind.LOCAL_EXPRESSION,
            NodeKind.ROLLUP_COMPUTATION,
            NodeKind.SOLVE_GROUP,
            NodeKind.CONSTRAINT_CHECK,
            NodeKind.EXTERNAL_COMPUTATION,
        )

    def __repr__(self) -> str:
        return f"<DependencyNode: {self.node_id} ({self.kind.value})>"


class DependencyGraph:
    """Configuration-scoped bipartite dependency graph.

    Edges go from dependency -> dependent (A must resolve before B).
    """

    def __init__(self) -> None:
        self._nodes: dict[str, DependencyNode] = {}
        self._edges: list[tuple[str, str]] = []
        self._dependents: dict[str, list[str]] = {}
        self._dependencies: dict[str, list[str]] = {}

    def add_node(self, node: DependencyNode) -> None:
        self._nodes[node.node_id] = node
        if node.node_id not in self._dependents:
            self._dependents[node.node_id] = []
        if node.node_id not in self._dependencies:
            self._dependencies[node.node_id] = []

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add edge: from_id must resolve before to_id."""
        self._edges.append((from_id, to_id))
        self._dependents.setdefault(from_id, []).append(to_id)
        self._dependencies.setdefault(to_id, []).append(from_id)

    def get_node(self, node_id: str) -> DependencyNode:
        return self._nodes[node_id]

    @property
    def nodes(self) -> dict[str, DependencyNode]:
        return dict(self._nodes)

    @property
    def edges(self) -> list[tuple[str, str]]:
        return list(self._edges)

    def dependencies_of(self, node_id: str) -> list[str]:
        return list(self._dependencies.get(node_id, []))

    def dependents_of(self, node_id: str) -> list[str]:
        return list(self._dependents.get(node_id, []))

    def topological_order(self) -> list[str]:
        """Return nodes in evaluation order. Raises if cycles exist."""
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        for _, to_id in self._edges:
            in_degree[to_id] = in_degree.get(to_id, 0) + 1

        ready = [nid for nid, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while ready:
            ready.sort()
            current = ready.pop(0)
            order.append(current)
            for dep in self._dependents.get(current, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    ready.append(dep)

        if len(order) != len(self._nodes):
            remaining = set(self._nodes) - set(order)
            raise ValueError(f"Dependency cycle detected involving: {remaining}")

        return order

    def dependency_closure(self, seeds: Iterable[str]) -> set[str]:
        """All nodes reachable by walking ``dependencies_of`` from ``seeds`` (including seeds)."""
        seen: set[str] = set()
        stack = list(seeds)
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            if nid not in self._nodes:
                raise KeyError(f"Unknown node id in dependency_closure seeds: {nid!r}")
            seen.add(nid)
            stack.extend(self.dependencies_of(nid))
        return seen

    def dependent_closure(self, seeds: Iterable[str]) -> set[str]:
        """All nodes reachable by walking ``dependents_of`` from ``seeds`` (including seeds)."""
        seen: set[str] = set()
        stack = list(seeds)
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            if nid not in self._nodes:
                raise KeyError(f"Unknown node id in dependent_closure seeds: {nid!r}")
            seen.add(nid)
            stack.extend(self.dependents_of(nid))
        return seen

    def induced_subgraph(self, node_ids: set[str]) -> DependencyGraph:
        """Copy of this graph restricted to ``node_ids`` and edges with both ends inside."""
        unknown = node_ids - set(self._nodes)
        if unknown:
            raise KeyError(f"induced_subgraph: unknown nodes {unknown!r}")
        sub = DependencyGraph()
        for nid in node_ids:
            node = self._nodes[nid]
            sub.add_node(
                DependencyNode(
                    node.node_id,
                    node.kind,
                    slot_id=node.slot_id,
                    metadata=dict(node.metadata),
                )
            )
        for fr, to in self._edges:
            if fr in node_ids and to in node_ids:
                sub.add_edge(fr, to)
        return sub
