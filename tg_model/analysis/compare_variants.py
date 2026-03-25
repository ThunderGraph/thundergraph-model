"""Cross-variant evaluation: same workflow, isolated runs, aligned outputs (Phase 5).

Each scenario compiles its own graph from its :class:`ConfiguredModel` — structure
may differ per variant. There is no shared :class:`tg_model.execution.run_context.RunContext`.

By default, :func:`validate_graph` runs (with ``configured_model``) before each
evaluation so ill-posed variants fail with :class:`CompareVariantsValidationError`
instead of obscure runtime errors.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias

from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.dependency_graph import DependencyGraph
from tg_model.execution.evaluator import Evaluator, RunResult
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.execution.value_slots import ValueSlot

VariantScenario: TypeAlias = tuple[str, ConfiguredModel, Mapping[str, Any]]  # noqa: UP040


class CompareVariantsValidationError(Exception):
    """Static validation failed for one variant before evaluation."""

    def __init__(self, label: str, failures: list[str]) -> None:
        self.label = label
        self.failures = list(failures)
        detail = "; ".join(failures)
        super().__init__(f"validate_graph failed for variant {label!r}: {detail}")


@dataclass(frozen=True)
class CapturedSlotOutput:
    """Resolved output for one ``output_paths`` entry."""

    value: Any | None
    present_in_run_outputs: bool
    """True iff the slot's ``stable_id`` was present in ``RunResult.outputs``."""

    @property
    def realized(self) -> bool:
        return self.present_in_run_outputs


@dataclass(frozen=True)
class VariantComparisonRow:
    label: str
    outputs: dict[str, CapturedSlotOutput]
    result: RunResult


def _assert_same_root_if_requested(
    scenarios: Sequence[VariantScenario],
    *,
    require_same_root_definition_type: bool,
) -> None:
    if not require_same_root_definition_type or len(scenarios) <= 1:
        return
    t0 = scenarios[0][1].root.definition_type
    for label, cm, _ in scenarios[1:]:
        if cm.root.definition_type is not t0:
            raise ValueError(
                f"compare_variants: scenario {label!r} root type "
                f"{cm.root.definition_type!r} differs from the first scenario ({t0!r}). "
                "Set require_same_root_definition_type=False to compare structurally "
                "different roots, or align your configured models."
            )


def _compile_and_maybe_validate(
    label: str,
    cm: ConfiguredModel,
    *,
    validate_before_run: bool,
) -> tuple[DependencyGraph, dict[str, Any]]:
    graph, handlers = compile_graph(cm)
    if validate_before_run:
        v = validate_graph(graph, configured_model=cm)
        if not v.passed:
            raise CompareVariantsValidationError(label, [f.message for f in v.failures])
    return graph, handlers


def _collect_outputs(cm: ConfiguredModel, result: RunResult, paths: Sequence[str]) -> dict[str, CapturedSlotOutput]:
    out: dict[str, CapturedSlotOutput] = {}
    for path in paths:
        handle = cm.handle(path)
        if not isinstance(handle, ValueSlot):
            raise TypeError(
                f"output_paths entry {path!r} must resolve to a ValueSlot, got {type(handle).__name__}"
            )
        sid = handle.stable_id
        present = sid in result.outputs
        out[path] = CapturedSlotOutput(
            value=result.outputs[sid] if present else None,
            present_in_run_outputs=present,
        )
    return out


def compare_variants(
    *,
    scenarios: Sequence[VariantScenario],
    output_paths: Sequence[str],
    validate_before_run: bool = True,
    require_same_root_definition_type: bool = False,
) -> list[VariantComparisonRow]:
    """Evaluate each ``(label, configured_model, inputs)`` with a fresh graph and context.

    ``inputs`` maps ``ValueSlot.stable_id`` strings to bound values, same as
    :meth:`Evaluator.evaluate`.

    **outputs** maps each path string to :class:`CapturedSlotOutput` so ``None`` values
    are not confused with “missing from the run” (check ``present_in_run_outputs``).
    """
    _assert_same_root_if_requested(scenarios, require_same_root_definition_type=require_same_root_definition_type)

    rows: list[VariantComparisonRow] = []
    for label, cm, inputs in scenarios:
        graph, handlers = _compile_and_maybe_validate(
            label, cm, validate_before_run=validate_before_run,
        )
        evaluator = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        result = evaluator.evaluate(ctx, inputs=dict(inputs))
        outputs = _collect_outputs(cm, result, output_paths)
        rows.append(VariantComparisonRow(label=label, outputs=outputs, result=result))
    return rows


async def compare_variants_async(
    *,
    scenarios: Sequence[VariantScenario],
    output_paths: Sequence[str],
    validate_before_run: bool = True,
    require_same_root_definition_type: bool = False,
) -> list[VariantComparisonRow]:
    """Like :func:`compare_variants` but uses async external evaluation per scenario."""
    _assert_same_root_if_requested(scenarios, require_same_root_definition_type=require_same_root_definition_type)

    rows: list[VariantComparisonRow] = []
    for label, cm, inputs in scenarios:
        graph, handlers = _compile_and_maybe_validate(
            label, cm, validate_before_run=validate_before_run,
        )
        evaluator = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        result = await evaluator.evaluate_async(
            ctx,
            configured_model=cm,
            inputs=dict(inputs),
        )
        outputs = _collect_outputs(cm, result, output_paths)
        rows.append(VariantComparisonRow(label=label, outputs=outputs, result=result))
    return rows
