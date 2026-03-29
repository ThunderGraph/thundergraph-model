"""Static validation for compiled :class:`~tg_model.execution.dependency_graph.DependencyGraph` objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.dependency_graph import DependencyGraph, NodeKind
from tg_model.execution.external_ops import ExternalOpsError, navigate_to_part, resolve_attribute_ref_to_slot
from tg_model.execution.value_slots import ValueSlot


@dataclass
class ValidationFailure:
    """Single validation problem (category + message + optional graph path)."""

    category: str
    message: str
    path: str | None = None


@dataclass
class ValidationResult:
    """Aggregate result of :func:`validate_graph`."""

    failures: list[ValidationFailure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when ``failures`` is empty."""
        return len(self.failures) == 0

    def add(self, category: str, message: str, path: str | None = None) -> None:
        """Append a :class:`ValidationFailure`."""
        self.failures.append(ValidationFailure(category=category, message=message, path=path))


class GraphValidationError(Exception):
    """Raised when :func:`validate_graph` fails before evaluation.

    Typical source: :meth:`tg_model.execution.configured_model.ConfiguredModel.evaluate`
    when ``validate=True`` and static checks do not pass.

    Subclasses :class:`Exception` (not :class:`BaseException`) so typical ``except Exception``
    handlers catch it; use this type or inspect :attr:`result` when you need to distinguish
    validation from other failures.

    Attributes
    ----------
    result : ValidationResult
        Structured failures from :func:`validate_graph`.
    """

    def __init__(self, message: str, *, result: ValidationResult) -> None:
        self.result = result
        super().__init__(message)


def validate_graph(
    graph: DependencyGraph,
    *,
    configured_model: ConfiguredModel | None = None,
) -> ValidationResult:
    """Run static checks before evaluation (cycles, orphans, roll-ups, externals).

    Parameters
    ----------
    graph : DependencyGraph
        Output of :func:`~tg_model.execution.graph_compiler.compile_graph`.
    configured_model : ConfiguredModel, optional
        When provided, runs :class:`~tg_model.integrations.external_compute.ValidatableExternalCompute`
        ``validate_binding`` hooks where implemented.

    Returns
    -------
    ValidationResult
        Non-passing result lists structured :class:`ValidationFailure` rows (never raises for soft checks).
    """
    result = ValidationResult()

    _check_cycles(graph, result)
    _check_orphaned_compute_nodes(graph, result)
    _check_empty_rollups(graph, result)
    _check_solve_group_integrity(graph, result)
    _check_duplicate_slot_assignments(graph, result)
    if configured_model is not None:
        _check_validatable_external_bindings(graph, configured_model, result)

    return result


def _check_cycles(graph: DependencyGraph, result: ValidationResult) -> None:
    try:
        graph.topological_order()
    except ValueError as e:
        result.add("dependency", str(e))


def _check_orphaned_compute_nodes(graph: DependencyGraph, result: ValidationResult) -> None:
    for node_id, node in graph.nodes.items():
        if not node.is_compute_node:
            continue
        deps = graph.dependencies_of(node_id)
        dependents = graph.dependents_of(node_id)
        if len(deps) == 0 and len(dependents) == 0:
            result.add(
                "dependency",
                f"Compute node '{node_id}' has no dependencies and no dependents",
                path=node_id,
            )


def _check_empty_rollups(graph: DependencyGraph, result: ValidationResult) -> None:
    for node_id, node in graph.nodes.items():
        if node.kind != NodeKind.ROLLUP_COMPUTATION:
            continue
        deps = graph.dependencies_of(node_id)
        if len(deps) == 0:
            result.add(
                "rollup",
                f"Roll-up '{node_id}' has no child dependencies — the selector resolved to nothing",
                path=node_id,
            )


def _check_solve_group_integrity(graph: DependencyGraph, result: ValidationResult) -> None:
    for node_id, node in graph.nodes.items():
        if node.kind != NodeKind.SOLVE_GROUP:
            continue

        target_slots = node.metadata.get("target_slots", {})
        if not target_slots:
            result.add(
                "solve_group",
                f"Solve group '{node_id}' has no target slots for unknowns",
                path=node_id,
            )

        slot_ids = list(target_slots.values())
        if len(slot_ids) != len(set(slot_ids)):
            result.add(
                "solve_group",
                f"Solve group '{node_id}' has duplicate target slot IDs",
                path=node_id,
            )


def _check_validatable_external_bindings(
    graph: DependencyGraph,
    cm: ConfiguredModel,
    result: ValidationResult,
) -> None:
    for node_id, node in graph.nodes.items():
        if node.kind != NodeKind.EXTERNAL_COMPUTATION:
            continue
        binding = node.metadata.get("binding")
        if binding is None:
            continue
        ext = binding.external
        validate_fn = getattr(ext, "validate_binding", None)
        if validate_fn is None or not callable(validate_fn):
            continue
        owner_path = node.metadata.get("owner_path")
        if not owner_path:
            result.add("external_binding", f"Node '{node_id}' missing owner_path", path=node_id)
            continue
        try:
            owner = navigate_to_part(cm.root, tuple(owner_path))
            input_specs: dict[str, Any] = {}
            for iname, ref in binding.inputs.items():
                slot = resolve_attribute_ref_to_slot(ref, owner, cm)
                input_specs[iname] = slot.metadata.get("unit")
            output_specs: dict[str, Any] = {}
            if binding.output_routes:
                for key, ref in binding.output_routes.items():
                    out_slot = resolve_attribute_ref_to_slot(ref, owner, cm)
                    output_specs[key] = out_slot.metadata.get("unit")
            else:
                for sid in node.metadata.get("output_slot_ids", ()):
                    vs = cm.id_registry.get(sid)
                    if isinstance(vs, ValueSlot):
                        output_specs[sid] = vs.metadata.get("unit")
            validate_fn(input_specs=input_specs, output_specs=output_specs)
        except ExternalOpsError as e:
            result.add("external_binding", str(e), path=node_id)
        except Exception as e:
            result.add(
                "external_binding",
                f"validate_binding failed for {getattr(ext, 'name', ext)!r}: {e}",
                path=node_id,
            )


def _check_duplicate_slot_assignments(graph: DependencyGraph, result: ValidationResult) -> None:
    """Check that no slot_id is written to by more than one compute node."""
    slot_writers: dict[str, list[str]] = {}
    for node_id, node in graph.nodes.items():
        if node.kind == NodeKind.EXTERNAL_COMPUTATION:
            for sid in node.metadata.get("output_slot_ids", ()):
                slot_writers.setdefault(sid, []).append(node_id)
            continue
        if node.is_compute_node and node.slot_id:
            slot_writers.setdefault(node.slot_id, []).append(node_id)

    for slot_id, writers in slot_writers.items():
        if len(writers) > 1:
            result.add(
                "dependency",
                f"Slot '{slot_id}' is written to by multiple compute nodes: {writers}",
            )
