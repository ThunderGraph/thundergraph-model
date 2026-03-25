"""Value-graph propagation (Phase 5): upstream / downstream **value slots** only.

This is **dependency reachability** on one compiled :class:`~tg_model.execution.dependency_graph.DependencyGraph`.
It does **not** aggregate requirements, hazards, behavior, interfaces, or other program semantics —
do not treat it as a full “engineering impact” or FMEA surface without layering your own model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tg_model.execution.dependency_graph import DependencyGraph
from tg_model.execution.value_slots import ValueSlot


def _value_node_id(slot: ValueSlot) -> str:
    return f"val:{slot.path_string}"


def _slot_ids_for_nodes(graph: DependencyGraph, node_ids: set[str]) -> frozenset[str]:
    ids: set[str] = set()
    for nid in node_ids:
        sid = graph.get_node(nid).slot_id
        if sid is not None:
            ids.add(sid)
    return frozenset(ids)


@dataclass(frozen=True)
class ImpactReport:
    """Slots whose values may influence, or may be influenced by, ``changed`` slots."""

    changed_paths: tuple[str, ...]
    upstream_slot_ids: frozenset[str]
    downstream_slot_ids: frozenset[str]


def dependency_impact(
    graph: DependencyGraph,
    changed: Sequence[ValueSlot],
    *,
    upstream: bool = True,
    downstream: bool = True,
) -> ImpactReport:
    """Return value-slot stable_ids reachable upstream and/or downstream of ``changed``.

    Seeds are compiled value nodes ``val:<slot.path_string>``. Sets exclude the
    changed slots' own stable_ids so callers see *other* affected slots.
    """
    if not changed:
        return ImpactReport((), frozenset(), frozenset())

    seeds = [_value_node_id(s) for s in changed]
    for vid in seeds:
        if vid not in graph.nodes:
            raise ValueError(
                f"changed slot maps to unknown graph node {vid!r} "
                f"(is this graph compiled for the same configured model?)"
            )

    seed_ids = {s.stable_id for s in changed}

    up_ids: frozenset[str] = frozenset()
    down_ids: frozenset[str] = frozenset()

    if upstream:
        up_ids = frozenset(
            sid for sid in _slot_ids_for_nodes(graph, graph.dependency_closure(seeds)) if sid not in seed_ids
        )
    if downstream:
        down_ids = frozenset(
            sid for sid in _slot_ids_for_nodes(graph, graph.dependent_closure(seeds)) if sid not in seed_ids
        )

    paths = tuple(s.path_string for s in changed)
    return ImpactReport(paths, up_ids, down_ids)


# Explicit alias: prefer this name when “impact” would oversell scope.
value_graph_propagation = dependency_impact
