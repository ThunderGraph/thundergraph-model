"""Bipartite dependency graph for one configured model (:class:`DependencyGraph`).

Edges point **from dependency → dependent** (inputs must resolve before consumers).
:class:`~tg_model.execution.evaluator.Evaluator` consumes :meth:`DependencyGraph.topological_order`.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Any


class NodeKind(Enum):
    """Compute vs value classification for dependency nodes."""

    INPUT_PARAMETER = "input_parameter"
    ATTRIBUTE_VALUE = "attribute_value"
    CONSTRAINT_RESULT = "constraint_result"
    LOCAL_EXPRESSION = "local_expression"
    ROLLUP_COMPUTATION = "rollup_computation"
    SOLVE_GROUP = "solve_group"
    CONSTRAINT_CHECK = "constraint_check"
    EXTERNAL_COMPUTATION = "external_computation"


class DependencyNode:
    """Single node in a :class:`DependencyGraph` (value or compute kind)."""

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
    """Directed graph of value and compute nodes for one compile of a configured model.

    Notes
    -----
    ``add_edge(from_id, to_id)`` means ``from_id`` must be satisfied before ``to_id``.
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
        """Add dependency edge (``from_id`` before ``to_id``)."""
        self._edges.append((from_id, to_id))
        self._dependents.setdefault(from_id, []).append(to_id)
        self._dependencies.setdefault(to_id, []).append(from_id)

    def get_node(self, node_id: str) -> DependencyNode:
        """Return node by id.

        Raises
        ------
        KeyError
            If unknown.
        """
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
        """Deterministic topological sort (stable tie-break by sorted ready queue).

        Returns
        -------
        list[str]
            Node ids in evaluation order.

        Raises
        ------
        ValueError
            If a cycle remains (not all nodes scheduled).
        """
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
        """Walk upstream dependencies from ``seeds``.

        Raises
        ------
        KeyError
            If a seed is not a known node id.
        """
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
        """Walk downstream dependents from ``seeds``.

        Raises
        ------
        KeyError
            If a seed is not a known node id.
        """
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
        """Copy restricted to ``node_ids`` (internal edges only).

        Raises
        ------
        KeyError
            If any requested id is unknown.
        """
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
