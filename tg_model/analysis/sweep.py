"""Parameter sweeps over a fixed dependency graph (Phase 5).

Reuses :class:`tg_model.execution.evaluator.Evaluator` for each sample; every
sample gets a fresh :class:`tg_model.execution.run_context.RunContext`.

**Coherence:** Pass ``configured_model`` whenever you have it; the library then
verifies sweep :class:`ValueSlot` handles match ``compile_graph(configured_model)``.

**Throughput:** Samples run sequentially. This is not a parallel study runner.

**Pruning:** ``prune_to_slots`` evaluates an *upstream-closed* subgraph only.
Constraint (and other) nodes outside that closure are *not* executed —
``RunResult.constraint_results`` may be empty. Do not treat a pruned sweep as a
compliance run unless you know what you excluded.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tg_model.analysis._coherence import assert_slots_align_with_graph, plan_sweep_axes
from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.dependency_graph import DependencyGraph
from tg_model.execution.evaluator import Evaluator, RunResult
from tg_model.execution.run_context import RunContext
from tg_model.execution.value_slots import ValueSlot


@dataclass(frozen=True)
class SweepRecord:
    """One row from :func:`sweep` / :func:`sweep_async`.

    Attributes
    ----------
    index : int
        Zero-based Cartesian index (deterministic axis ordering).
    inputs : dict
        ``ValueSlot.stable_id`` → bound value for that sample.
    result : RunResult
        Evaluation outcome for the sample.
    """

    index: int
    inputs: dict[str, Any]
    result: RunResult


def _value_node_id(slot: ValueSlot) -> str:
    return f"val:{slot.path_string}"


def _prepare_pruned(
    graph: DependencyGraph,
    handlers: dict[str, Any],
    prune_to_slots: Sequence[ValueSlot] | None,
) -> tuple[DependencyGraph, dict[str, Any]]:
    if not prune_to_slots:
        return graph, handlers
    seeds = [_value_node_id(s) for s in prune_to_slots]
    for vid in seeds:
        if vid not in graph.nodes:
            raise ValueError(
                f"Prune target {vid!r} is not a graph node (expected val:<instance.path> for a compiled value slot)."
            )
    needed = graph.dependency_closure(seeds)
    sub = graph.induced_subgraph(needed)
    sub_handlers = {k: handlers[k] for k in sub.nodes if k in handlers}
    return sub, sub_handlers


def _maybe_assert_coherence(
    configured_model: ConfiguredModel | None,
    graph: DependencyGraph,
    parameter_slots: Sequence[ValueSlot],
    prune_slots: Sequence[ValueSlot] | None,
) -> None:
    if configured_model is None:
        return
    to_check = list(parameter_slots)
    if prune_slots:
        to_check.extend(prune_slots)
    assert_slots_align_with_graph(
        configured_model,
        graph,
        to_check,
        context="sweep",
    )


def sweep(
    *,
    graph: DependencyGraph,
    handlers: dict[str, Any],
    parameter_values: Mapping[ValueSlot, Sequence[Any]],
    configured_model: ConfiguredModel | None = None,
    prune_to_slots: Sequence[ValueSlot] | None = None,
    collect: bool = True,
    sink: Callable[[SweepRecord], None] | None = None,
) -> list[SweepRecord]:
    """Cartesian product over ``parameter_values``; one synchronous evaluation per tuple.

    Parameters
    ----------
    graph, handlers
        From :func:`~tg_model.execution.graph_compiler.compile_graph`.
    parameter_values
        Maps each parameter :class:`~tg_model.execution.value_slots.ValueSlot` to a sequence
        of values (axes). Dimension order is sorted by ``stable_id``.
    configured_model : ConfiguredModel, optional
        When passed, asserts sweep slots match the graph (coherence check).
    prune_to_slots : sequence of ValueSlot, optional
        Restricts to upstream closure of these slots (see module warnings).
    collect : bool, default True
        When False, return an empty list and stream via ``sink``.
    sink : callable, optional
        Receives each :class:`SweepRecord` when provided.

    Returns
    -------
    list of SweepRecord
        All samples when ``collect`` is True.

    Raises
    ------
    ValueError
        If ``collect=False`` without ``sink``, or prune targets are not graph nodes.
    """
    if not collect and sink is None:
        raise ValueError("sweep(..., collect=False) requires a sink callable")

    slots_sorted, combo_lists = plan_sweep_axes(parameter_values)
    _maybe_assert_coherence(configured_model, graph, slots_sorted, prune_to_slots)

    eval_graph, eval_handlers = _prepare_pruned(graph, handlers, prune_to_slots)
    evaluator = Evaluator(eval_graph, compute_handlers=eval_handlers)

    records: list[SweepRecord] = []
    for idx, combo in enumerate(itertools.product(*combo_lists)):
        inputs: dict[str, Any] = {}
        for slot, val in zip(slots_sorted, combo, strict=True):
            inputs[slot.stable_id] = val
        ctx = RunContext()
        result = evaluator.evaluate(ctx, inputs=inputs)
        rec = SweepRecord(index=idx, inputs=dict(inputs), result=result)
        if sink is not None:
            sink(rec)
        if collect:
            records.append(rec)
    return records


async def sweep_async(
    *,
    configured_model: ConfiguredModel,
    graph: DependencyGraph,
    handlers: dict[str, Any],
    parameter_values: Mapping[ValueSlot, Sequence[Any]],
    prune_to_slots: Sequence[ValueSlot] | None = None,
    collect: bool = True,
    sink: Callable[[SweepRecord], None] | None = None,
) -> list[SweepRecord]:
    """Like :func:`sweep` but awaits :meth:`~tg_model.execution.evaluator.Evaluator.evaluate_async`.

    Parameters
    ----------
    configured_model : ConfiguredModel
        Required for async externals and always used for coherence checks.
    graph, handlers, parameter_values, prune_to_slots, collect, sink
        Same semantics as :func:`sweep`.

    Returns
    -------
    list of SweepRecord
        Same as :func:`sweep`.

    Raises
    ------
    ValueError
        Same as :func:`sweep`.
    """
    if not collect and sink is None:
        raise ValueError("sweep_async(..., collect=False) requires a sink callable")

    slots_sorted, combo_lists = plan_sweep_axes(parameter_values)
    _maybe_assert_coherence(configured_model, graph, slots_sorted, prune_to_slots)

    eval_graph, eval_handlers = _prepare_pruned(graph, handlers, prune_to_slots)
    evaluator = Evaluator(eval_graph, compute_handlers=eval_handlers)

    records: list[SweepRecord] = []
    for idx, combo in enumerate(itertools.product(*combo_lists)):
        inputs: dict[str, Any] = {}
        for slot, val in zip(slots_sorted, combo, strict=True):
            inputs[slot.stable_id] = val
        ctx = RunContext()
        result = await evaluator.evaluate_async(
            ctx,
            configured_model=configured_model,
            inputs=inputs,
        )
        rec = SweepRecord(index=idx, inputs=dict(inputs), result=result)
        if sink is not None:
            sink(rec)
        if collect:
            records.append(rec)
    return records
