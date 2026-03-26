"""Shared checks: configured model, compiled graph, and ValueSlot handles must align."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.dependency_graph import DependencyGraph
from tg_model.execution.value_slots import ValueSlot


def assert_slots_align_with_graph(
    configured_model: ConfiguredModel,
    graph: DependencyGraph,
    slots: Iterable[ValueSlot],
    *,
    context: str,
) -> None:
    """Verify slots belong to ``configured_model`` and appear as ``val:<path>`` nodes in ``graph``.

    Parameters
    ----------
    configured_model : ConfiguredModel
        Topology built from the same root as ``graph``.
    graph : DependencyGraph
        Output of :func:`~tg_model.execution.graph_compiler.compile_graph` for that model.
    slots : iterable of ValueSlot
        Handles to verify (parameters, prune targets, …).
    context : str
        Label for error messages (e.g. ``\"sweep\"``).

    Raises
    ------
    ValueError
        On registry mismatch, path mismatch, or missing graph node.
    """
    for s in slots:
        if s.stable_id not in configured_model.id_registry:
            raise ValueError(
                f"{context}: slot {s.path_string!r} (stable_id={s.stable_id!r}) "
                f"is not registered on the given configured_model."
            )
        reg = configured_model.id_registry[s.stable_id]
        if not isinstance(reg, ValueSlot):
            raise ValueError(
                f"{context}: id_registry[{s.stable_id!r}] is not a ValueSlot "
                f"(got {type(reg).__name__})."
            )
        if reg.path_string != s.path_string:
            raise ValueError(
                f"{context}: slot path mismatch for stable_id {s.stable_id!r}: "
                f"handle has {s.path_string!r}, model has {reg.path_string!r}."
            )
        vid = f"val:{s.path_string}"
        if vid not in graph.nodes:
            raise ValueError(
                f"{context}: no graph node {vid!r} for slot {s.path_string!r}. "
                "Pass the DependencyGraph from compile_graph(same configured_model)."
            )


def plan_sweep_axes(
    parameter_values: Mapping[ValueSlot, Sequence[Any]],
) -> tuple[list[ValueSlot], list[Sequence[Any]]]:
    """Sort sweep axes by ``stable_id`` and validate each axis is non-empty.

    Parameters
    ----------
    parameter_values
        Map each parameter slot to its value sequence.

    Returns
    -------
    slots_sorted : list[ValueSlot]
        Keys sorted by ``stable_id``.
    combo_lists : list[Sequence[Any]]
        Parallel list of value sequences (same order as ``slots_sorted``).

    Raises
    ------
    ValueError
        If any slot maps to an empty sequence.
    """
    if not parameter_values:
        return [], []
    slots_sorted = sorted(parameter_values.keys(), key=lambda s: s.stable_id)
    combo_lists: list[Sequence[Any]] = []
    for slot in slots_sorted:
        seq = parameter_values[slot]
        if not seq:
            raise ValueError(f"Empty value sequence for slot '{slot.path_string}'")
        combo_lists.append(seq)
    return slots_sorted, combo_lists
