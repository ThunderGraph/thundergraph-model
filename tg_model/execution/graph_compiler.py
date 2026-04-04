"""Compile a DependencyGraph from a ConfiguredModel's authored semantics.

Walks the configured topology, inspects authored expressions and constraints,
and builds the bipartite dependency graph automatically.

Edges are kept so compute nodes depend on **value** nodes (with ``slot_id``);
``Evaluator._check_dependencies_ready`` only inspects those value dependencies.
The only public entry point is ``compile_graph()``. All other functions
are internal compilation helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from unitflow import Quantity

from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.connection_bindings import AllocationBinding
from tg_model.execution.dependency_graph import DependencyGraph, DependencyNode, NodeKind
from tg_model.execution.external_ops import (
    ExternalOpsError,
    materialize_external_result,
)
from tg_model.execution.external_ops import (
    resolve_attribute_ref_to_slot as _resolve_attr_ref_core,
)
from tg_model.execution.instances import ElementInstance, PartInstance, RequirementPackageInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.integrations.external_compute import (
    ExternalComputeBinding,
    ExternalComputeResult,
    assert_sync_external,
)
from tg_model.model.refs import AttributeRef


def _alloc_target_as_part(target: ElementInstance, *, where: str) -> PartInstance:
    """Narrow allocation targets to :class:`PartInstance` with a single graph-level check."""
    if not isinstance(target, PartInstance):
        raise GraphCompilationError(f"{where}: allocation target must be PartInstance, got {type(target).__name__}")
    return target


def _first_value_slot_under_requirement_package(
    pkg: RequirementPackageInstance,
) -> ValueSlot | None:
    """First package :class:`ValueSlot` in stable name order (including nested packages)."""
    for key in sorted(pkg._members.keys()):
        m = pkg._members[key]
        if isinstance(m, ValueSlot):
            return m
        if isinstance(m, RequirementPackageInstance):
            inner = _first_value_slot_under_requirement_package(m)
            if inner is not None:
                return inner
    return None


class GraphCompilationError(Exception):
    """Raised when graph compilation cannot resolve symbols, slots, or bindings."""


def compile_graph(model: ConfiguredModel) -> tuple[DependencyGraph, dict[str, Callable]]:
    """Compile dependency graph and per-node compute handlers from a configured model.

    This is the **only** supported public entry point for graph compilation.

    Parameters
    ----------
    model : ConfiguredModel
        Frozen topology from :func:`~tg_model.execution.configured_model.instantiate`.

    Returns
    -------
    graph : DependencyGraph
        Bipartite value/compute graph in topological-evaluable form.
    handlers : dict[str, Callable]
        Sync callables keyed by compute ``node_id`` (expressions, roll-ups, externals, constraints).

    Raises
    ------
    GraphCompilationError
        On unresolvable references, binding errors, or other compile failures.

    Notes
    -----
    Walks value slots, requirement acceptance, constraints, solve groups, and external nodes.
    Async externals are still scheduled from sync :meth:`~tg_model.execution.evaluator.Evaluator.evaluate_async`.

    Successful results are **cached** on ``model._compiled_graph`` so repeated calls and
    :meth:`~tg_model.execution.configured_model.ConfiguredModel.evaluate` reuse the same
    ``(graph, handlers)`` tuple without recompilation.
    """
    cached = getattr(model, "_compiled_graph", None)
    if cached is not None:
        return cached

    graph = DependencyGraph()
    handlers: dict[str, Callable] = {}

    _compile_part(model.root, graph, handlers, model)
    _compile_requirement_packages_from_parts(model.root, graph, handlers, model)
    _compile_constraints_for_part(model.root, graph, handlers, model)
    _compile_requirement_derived_slots(model, graph, handlers)
    _compile_requirement_acceptance(model, graph, handlers)
    _compile_solve_groups_for_part(model.root, graph, handlers, model)

    model._compiled_graph = (graph, handlers)
    return graph, handlers


def _compile_part(
    part: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    for slot in part.value_slots:
        _compile_slot(slot, part, graph, handlers, model)
    _compile_external_for_part(part, graph, handlers, model)
    for child in part.children:
        _compile_part(child, graph, handlers, model)


def _compile_slot(
    slot: ValueSlot,
    owner: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    slot_node_id = f"val:{slot.path_string}"

    if slot.is_parameter:
        graph.add_node(
            DependencyNode(
                slot_node_id,
                NodeKind.INPUT_PARAMETER,
                slot_id=slot.stable_id,
            )
        )
        return

    expr = slot.metadata.get("_expr")

    if expr is None:
        graph.add_node(
            DependencyNode(
                slot_node_id,
                NodeKind.ATTRIBUTE_VALUE,
                slot_id=slot.stable_id,
            )
        )
        return

    from tg_model.model.declarations.values import RollupDecl

    if isinstance(expr, RollupDecl):
        _compile_rollup(slot, slot_node_id, expr, owner, graph, handlers)
        return

    graph.add_node(
        DependencyNode(
            slot_node_id,
            NodeKind.ATTRIBUTE_VALUE,
            slot_id=slot.stable_id,
        )
    )

    expr_node_id = f"expr:{slot.path_string}"
    graph.add_node(
        DependencyNode(
            expr_node_id,
            NodeKind.LOCAL_EXPRESSION,
            slot_id=slot.stable_id,
        )
    )
    graph.add_edge(expr_node_id, slot_node_id)

    if isinstance(expr, AttributeRef):
        dep_slot = _resolve_attribute_ref_to_slot(expr, owner, model)
        dep_node_id = f"val:{dep_slot.path_string}"
        graph.add_edge(dep_node_id, expr_node_id)

        def make_ref_passthrough_handler(dnid: str) -> Callable[..., Any]:
            def handler(dep_values: dict[str, Any]) -> Any:
                return dep_values[dnid]

            return handler

        handlers[expr_node_id] = make_ref_passthrough_handler(dep_node_id)
        return

    if hasattr(expr, "free_symbols") and expr.free_symbols:
        for sym in expr.free_symbols:
            dep_slot = _resolve_symbol_to_slot(sym, owner, model)
            dep_node_id = f"val:{dep_slot.path_string}"
            graph.add_edge(dep_node_id, expr_node_id)

        def make_expr_handler(expression: Any, owner_part: PartInstance, cm: ConfiguredModel) -> Callable:
            def handler(dep_values: dict[str, Any]) -> Any:
                context = {}
                for sym in expression.free_symbols:
                    dep_slot = _resolve_symbol_to_slot(sym, owner_part, cm)
                    dep_node_id = f"val:{dep_slot.path_string}"
                    if dep_node_id in dep_values:
                        context[sym] = dep_values[dep_node_id]
                return expression.evaluate(context)

            return handler

        handlers[expr_node_id] = make_expr_handler(expr, owner, model)
    elif hasattr(expr, "evaluate"):
        handlers[expr_node_id] = lambda dep_values, e=expr: e.evaluate({})
    elif callable(expr):
        handlers[expr_node_id] = lambda dep_values, fn=expr: fn(dep_values)
    else:
        handlers[expr_node_id] = lambda dep_values, val=expr: val


def _resolve_attribute_ref_to_slot(
    ref: Any,
    owner: PartInstance,
    model: ConfiguredModel,
) -> ValueSlot:
    try:
        return _resolve_attr_ref_core(ref, owner, model)
    except ExternalOpsError as e:
        raise GraphCompilationError(str(e)) from e


def _compile_external_for_part(
    part: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    groups: dict[int, list[ValueSlot]] = {}
    for slot in part.value_slots:
        cb = slot.metadata.get("_computed_by")
        if cb is None:
            continue
        if not isinstance(cb, ExternalComputeBinding):
            raise GraphCompilationError(
                f"computed_by must be an ExternalComputeBinding at '{slot.path_string}', got {type(cb).__name__}"
            )
        if slot.metadata.get("_expr") is not None:
            raise GraphCompilationError(f"Attribute '{slot.path_string}' cannot combine expr= with computed_by=")
        groups.setdefault(id(cb), []).append(slot)

    for slots in groups.values():
        _build_external_compute_node(slots, part, graph, handlers, model)


def _build_external_compute_node(
    slots: list[ValueSlot],
    owner: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    binding: ExternalComputeBinding = slots[0].metadata["_computed_by"]
    for s in slots[1:]:
        if s.metadata.get("_computed_by") is not binding:
            raise GraphCompilationError("External binding identity mismatch within compute group")

    routes = binding.output_routes
    slot_ids = {s.stable_id for s in slots}

    if routes is None:
        if len(slots) != 1:
            raise GraphCompilationError(
                "Single-slot ExternalComputeBinding (output_routes is None) requires exactly "
                "one attribute with that binding on this part"
            )
        output_slot_ids = [slots[0].stable_id]
    else:
        resolved_by_key: dict[str, ValueSlot] = {}
        for key, ref in routes.items():
            resolved_by_key[key] = _resolve_attribute_ref_to_slot(ref, owner, model)
        route_ids = {vs.stable_id for vs in resolved_by_key.values()}
        if slot_ids != route_ids:
            raise GraphCompilationError(
                f"external output_routes target slots {route_ids!r} must match exactly "
                f"attributes carrying the same computed_by ({slot_ids!r}) "
                f"(part '{owner.path_string}')"
            )
        output_slot_ids = [resolved_by_key[k].stable_id for k in sorted(routes.keys())]

    node_id = f"ext:{id(binding)}:{owner.path_string}"
    if node_id in graph.nodes:
        raise GraphCompilationError(f"Duplicate external compute node '{node_id}'")

    input_name_to_dep: dict[str, str] = {}
    for _iname, ref in binding.inputs.items():
        in_slot = _resolve_attribute_ref_to_slot(ref, owner, model)
        dep_node = f"val:{in_slot.path_string}"
        input_name_to_dep[_iname] = dep_node

    # Live binding reference: treat as frozen after compile_graph(); mutating it afterward is UB.
    graph.add_node(
        DependencyNode(
            node_id,
            NodeKind.EXTERNAL_COMPUTATION,
            metadata={
                "output_slot_ids": tuple(output_slot_ids),
                "binding_id": id(binding),
                "binding": binding,
                "owner_path": tuple(owner.instance_path),
                "input_name_to_dep": dict(input_name_to_dep),
            },
        )
    )

    for _dep in input_name_to_dep.values():
        graph.add_edge(_dep, node_id)

    for s in slots:
        graph.add_edge(node_id, f"val:{s.path_string}")

    handlers[node_id] = _make_external_handler(
        binding=binding,
        owner=owner,
        model=model,
        input_name_to_dep=input_name_to_dep,
        slots=slots,
        node_id=node_id,
    )


def _make_external_handler(
    *,
    binding: ExternalComputeBinding,
    owner: PartInstance,
    model: ConfiguredModel,
    input_name_to_dep: dict[str, str],
    slots: list[ValueSlot],
    node_id: str,
) -> Callable[..., None]:
    from tg_model.execution.evaluator import RunResult
    from tg_model.execution.run_context import RunContext

    def handler(dep_values: dict[str, Any], ctx: RunContext, run_result: RunResult) -> None:
        try:
            assert_sync_external(binding.external, context=node_id)
        except TypeError as e:
            msg = str(e)
            for s in slots:
                ctx.get_or_create_record(s.stable_id).block(msg)
            run_result.failures.append(msg)
            return

        inputs_dict: dict[str, Quantity] = {}
        try:
            for name, dep_node_id in input_name_to_dep.items():
                if dep_node_id not in dep_values:
                    raise KeyError(f"missing dependency {dep_node_id}")
                inputs_dict[name] = dep_values[dep_node_id]
            compute_fn = getattr(binding.external, "compute", None)
            if compute_fn is None:
                raise TypeError("external object has no compute()")
            res = compute_fn(inputs_dict)
            if not isinstance(res, ExternalComputeResult):
                raise TypeError(f"External compute must return ExternalComputeResult, got {type(res).__name__}")
            materialize_external_result(binding, res, owner, model, ctx, slots)
        except Exception as e:
            msg = str(e)
            for s in slots:
                ctx.get_or_create_record(s.stable_id).fail(msg)
            run_result.failures.append(f"External compute '{node_id}' failed: {msg}")

    return handler


def _compile_rollup(
    slot: ValueSlot,
    slot_node_id: str,
    expr: Any,
    owner: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
) -> None:
    graph.add_node(
        DependencyNode(
            slot_node_id,
            NodeKind.ATTRIBUTE_VALUE,
            slot_id=slot.stable_id,
        )
    )

    expr_node_id = f"rollup:{slot.path_string}"
    graph.add_node(
        DependencyNode(
            expr_node_id,
            NodeKind.ROLLUP_COMPUTATION,
            slot_id=slot.stable_id,
        )
    )
    graph.add_edge(expr_node_id, slot_node_id)

    child_slots: list[str] = []
    for child in owner.children:
        try:
            target_slot = expr.value_func(child)
            if isinstance(target_slot, ValueSlot):
                dep_node_id = f"val:{target_slot.path_string}"
                graph.add_edge(dep_node_id, expr_node_id)
                child_slots.append(dep_node_id)
        except AttributeError:
            pass

    from tg_model.execution.rollups import build_rollup_handler

    handlers[expr_node_id] = build_rollup_handler(expr.kind, expr.value_func, child_slots)


def _resolve_symbol_for_requirement_acceptance(
    sym: Any,
    allocate_target: PartInstance,
    requirement_definition_type: type,
    _model: ConfiguredModel,
    alloc: AllocationBinding,
) -> ValueSlot:
    """Map a unitflow symbol to a :class:`ValueSlot` for requirement acceptance (Phase 7).

    If :class:`~tg_model.execution.connection_bindings.AllocationBinding` carries
    ``input_bindings`` (from ``allocate(..., inputs=…)``), symbols owned by the configured root
    whose path matches ``<requirement instance path tail> + (input_name,)`` resolve to the bound
    part slot.

    Otherwise: symbols declared on the **same type as the allocate() call site** use paths from
    that type's root (e.g. ``('motor', 'shaft_power')``); we strip the allocate target's path
    under the configured root and resolve the remainder from ``allocate_target``.

    Symbols declared on the **allocate target's part type** (e.g. attributes in ``Motor.define``)
    use paths relative to that part (e.g. ``('shaft_power',)``) and resolve directly from
    ``allocate_target``.

    Requirement-local :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_attribute`
    values are registered as :class:`~tg_model.execution.value_slots.ValueSlot` objects on the
    configured root and resolved via ``path_registry`` when not covered by ``inputs=`` bindings.
    """
    from tg_model.model.refs import _symbol_id_to_path

    result = _symbol_id_to_path.get(id(sym))
    if result is not None:
        sym_owner, tg_path = result
        req_inst = alloc.requirement
        if sym_owner is requirement_definition_type and isinstance(req_inst, ElementInstance):
            rtail = tuple(req_inst.instance_path[1:])
            if len(tg_path) == len(rtail) + 1 and tg_path[: len(rtail)] == rtail:
                iname = tg_path[-1]
                if alloc.input_bindings:
                    bound = alloc.input_bindings.get(iname)
                    if bound is not None:
                        return bound
                full_key = ".".join((req_inst.instance_path[0], *tg_path))
                hit = _model.path_registry.get(full_key)
                if isinstance(hit, ValueSlot):
                    return hit
                raise GraphCompilationError(
                    f"Requirement acceptance symbol {iname!r} at path {tg_path!r} has no "
                    f"matching entry in allocate(..., inputs=...) or requirement_attribute slot"
                )
        current: Any = allocate_target
        if sym_owner is allocate_target.definition_type:
            rel = tg_path
        elif sym_owner is requirement_definition_type:
            anchor = tuple(allocate_target.instance_path[1:])
            if len(tg_path) < len(anchor) or tg_path[: len(anchor)] != anchor:
                raise GraphCompilationError(
                    f"Symbol '{getattr(sym, 'name', '?')}' path {tg_path!r} is not under "
                    f"allocate target path {anchor!r} from configured root"
                )
            rel = tg_path[len(anchor) :]
        else:
            raise GraphCompilationError(
                f"Symbol '{getattr(sym, 'name', '?')}' is owned by {sym_owner.__name__}; "
                f"requirement acceptance allows symbols from {requirement_definition_type.__name__} "
                f"or from allocate target type {allocate_target.definition_type.__name__} only."
            )
        try:
            for segment in rel:
                current = getattr(current, segment)
            if isinstance(current, ValueSlot):
                return current
        except AttributeError:
            pass
        raise GraphCompilationError(
            f"Symbol '{getattr(sym, 'name', '?')}' path {tg_path!r} "
            f"could not be resolved under '{allocate_target.path_string}' for requirement acceptance"
        )

    raise GraphCompilationError(
        f"Symbol '{getattr(sym, 'name', '?')}' is not a canonical AttributeRef-derived symbol. "
        f"All expression symbols must originate from model.attribute() or model.parameter() refs."
    )


def _resolve_symbol_to_slot(
    sym: Any,
    owner: PartInstance,
    model: ConfiguredModel,
) -> ValueSlot:
    """Resolve a unitflow Symbol to its corresponding ValueSlot.

    Uses the canonical symbol-id registry from AttributeRef.sym.
    When the symbol belongs to a different type than ``owner`` (e.g. a root
    system parameter referenced via :func:`~tg_model.model.definition_context.parameter_ref`),
    resolution falls back to ``model.root``.

    Fails loudly if the symbol cannot be resolved — silent misbinding
    is not acceptable in a safety-critical context.
    """
    from tg_model.model.refs import _symbol_id_to_path

    result = _symbol_id_to_path.get(id(sym))
    if result is not None:
        _owner_type, tg_path = result
        current: Any = owner
        try:
            for segment in tg_path:
                current = getattr(current, segment)
            if isinstance(current, ValueSlot):
                return current
        except AttributeError:
            pass
        if _owner_type is not owner.definition_type and _owner_type is model.root.definition_type:
            current = model.root
            try:
                for segment in tg_path:
                    current = getattr(current, segment)
                if isinstance(current, ValueSlot):
                    return current
            except AttributeError:
                pass
        raise GraphCompilationError(
            f"Symbol '{getattr(sym, 'name', '?')}' has registered path {tg_path} "
            f"but could not be resolved under '{owner.path_string}'"
        )

    raise GraphCompilationError(
        f"Symbol '{getattr(sym, 'name', '?')}' is not a canonical AttributeRef-derived symbol. "
        f"All expression symbols must originate from model.attribute() or model.parameter() refs."
    )


def _resolve_sym_for_requirement_expr(
    sym: Any,
    allocate_target: PartInstance,
    requirement_definition_type: type,
    model: ConfiguredModel,
    alloc: AllocationBinding,
) -> ValueSlot:
    """Resolve a symbol for :meth:`requirement_attribute` expressions (inputs, derived, root, part)."""
    from tg_model.model.refs import _symbol_id_to_path

    info = _symbol_id_to_path.get(id(sym))
    if info is None:
        raise GraphCompilationError(
            f"Symbol '{getattr(sym, 'name', '?')}' is not a canonical AttributeRef-derived symbol."
        )
    sym_owner, tg_path = info
    req_inst = alloc.requirement
    if isinstance(req_inst, ElementInstance) and sym_owner is requirement_definition_type:
        rtail = tuple(req_inst.instance_path[1:])
        if len(tg_path) == len(rtail) + 1 and tg_path[: len(rtail)] == rtail:
            return _resolve_symbol_for_requirement_acceptance(
                sym,
                allocate_target,
                requirement_definition_type,
                model,
                alloc,
            )
    if sym_owner is model.root.definition_type:
        return _resolve_symbol_to_slot(sym, model.root, model)
    if sym_owner is allocate_target.definition_type:
        return _resolve_symbol_to_slot(sym, allocate_target, model)
    raise GraphCompilationError(
        f"Symbol '{getattr(sym, 'name', '?')}' cannot be resolved for requirement_attribute "
        f"(owner {sym_owner.__name__} is not root, allocate target, or requirement namespace)."
    )


def _compile_requirement_attribute_slot(
    slot: ValueSlot,
    alloc: AllocationBinding,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    """Compile one derived requirement slot (same graph pattern as :func:`_compile_slot`)."""
    target = alloc.target
    if not isinstance(target, PartInstance):
        raise GraphCompilationError(
            f"requirement_attribute needs allocate target PartInstance; got {type(target).__name__}"
        )
    req = alloc.requirement
    if not isinstance(req, ElementInstance) or req.kind != "requirement":
        raise GraphCompilationError("requirement_attribute allocation must reference a requirement instance")
    req_owner_type = req.definition_type

    expr = slot.metadata.get("_expr")
    if expr is None:
        graph.add_node(
            DependencyNode(
                f"val:{slot.path_string}",
                NodeKind.ATTRIBUTE_VALUE,
                slot_id=slot.stable_id,
            )
        )
        return

    slot_node_id = f"val:{slot.path_string}"
    graph.add_node(
        DependencyNode(
            slot_node_id,
            NodeKind.ATTRIBUTE_VALUE,
            slot_id=slot.stable_id,
        )
    )
    expr_node_id = f"expr:{slot.path_string}"
    graph.add_node(
        DependencyNode(
            expr_node_id,
            NodeKind.LOCAL_EXPRESSION,
            slot_id=slot.stable_id,
        )
    )
    graph.add_edge(expr_node_id, slot_node_id)

    if hasattr(expr, "free_symbols") and expr.free_symbols:
        for sym in expr.free_symbols:
            dep_slot = _resolve_sym_for_requirement_expr(sym, target, req_owner_type, model, alloc)
            dep_node_id = f"val:{dep_slot.path_string}"
            graph.add_edge(dep_node_id, expr_node_id)

        def make_handler(expression: Any, a: AllocationBinding, cm: ConfiguredModel) -> Callable:
            def handler(dep_values: dict[str, Any]) -> Any:
                context: dict[Any, Any] = {}
                tgt = _alloc_target_as_part(a.target, where="requirement_attribute expression")
                for sym in expression.free_symbols:
                    dep_slot = _resolve_sym_for_requirement_expr(
                        sym,
                        tgt,
                        a.requirement.definition_type,
                        cm,
                        a,
                    )
                    dep_node_id = f"val:{dep_slot.path_string}"
                    if dep_node_id in dep_values:
                        context[sym] = dep_values[dep_node_id]
                return expression.evaluate(context)

            return handler

        handlers[expr_node_id] = make_handler(expr, alloc, model)
    elif hasattr(expr, "evaluate"):
        handlers[expr_node_id] = lambda dep_values, e=expr: e.evaluate({})
    elif callable(expr):
        handlers[expr_node_id] = lambda dep_values, fn=expr: fn(dep_values)
    else:
        handlers[expr_node_id] = lambda dep_values, val=expr: val


def _compile_requirement_derived_slots(
    model: ConfiguredModel,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
) -> None:
    """Compile :meth:`requirement_attribute` value slots (before requirement acceptance checks)."""
    from collections import defaultdict

    if not model.requirement_value_slots:
        return

    by_req: dict[str, list[AllocationBinding]] = defaultdict(list)
    for a in model.allocations:
        r = a.requirement
        if isinstance(r, ElementInstance) and r.kind == "requirement":
            by_req[r.path_string].append(a)

    grouped: dict[str, list[ValueSlot]] = defaultdict(list)
    for slot in model.requirement_value_slots:
        parent = ".".join(slot.instance_path[:-1])
        grouped[parent].append(slot)

    for req_path, slots in grouped.items():
        allocs = by_req.get(req_path)
        if not allocs:
            raise GraphCompilationError(
                f"requirement_attribute slot(s) under {req_path!r} require a matching allocate(...) edge"
            )
        if len(allocs) > 1:
            raise GraphCompilationError(
                f"requirement {req_path!r} has requirement_attribute-derived slots but multiple "
                f"allocate(...) edges; use a single allocation for derived requirement attributes."
            )
        alloc = allocs[0]
        req = alloc.requirement
        if not isinstance(req, ElementInstance):
            raise GraphCompilationError("requirement allocation invalid for requirement_attribute compile")
        order = list(req.metadata.get("_requirement_attribute_names") or [])
        rank = {n: i for i, n in enumerate(order)}
        slots_sorted = sorted(slots, key=lambda s: rank.get(s.instance_path[-1], 10_000))
        for slot in slots_sorted:
            _compile_requirement_attribute_slot(slot, alloc, graph, handlers, model)


def _compile_requirement_packages_from_parts(
    part: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    """Compile value slots and constraints declared on composable requirement packages."""
    compiled = part.definition_type.compile()
    tr = compiled.get("_type_registry", {})
    for name, node in compiled.get("nodes", {}).items():
        if node.get("kind") != "requirement_block" or tr.get(name) is None:
            continue
        sub = getattr(part, name, None)
        if isinstance(sub, RequirementPackageInstance):
            _compile_requirement_package_tree(sub, graph, handlers, model)
    for child in part.children:
        _compile_requirement_packages_from_parts(child, graph, handlers, model)


def _compile_requirement_package_tree(
    pkg: RequirementPackageInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    from tg_model.model.declarations.values import RollupDecl

    compiled = pkg.package_type.compile()
    # Declaration order matches Python 3.7+ dict insertion order (same as compile_type recording).
    for name, node in compiled["nodes"].items():
        kind = node["kind"]
        if kind in ("parameter", "attribute"):
            slot = getattr(pkg, name)
            if not isinstance(slot, ValueSlot):
                raise GraphCompilationError(
                    f"Expected ValueSlot for {pkg.path_string}.{name}, got {type(slot).__name__}"
                )
            if slot.metadata.get("_computed_by") is not None:
                raise GraphCompilationError(
                    f"computed_by= is not supported on requirement package slot '{slot.path_string}'"
                )
            expr_m = slot.metadata.get("_expr")
            if isinstance(expr_m, RollupDecl):
                raise GraphCompilationError(
                    f"RollupDecl is not supported on requirement package slot '{slot.path_string}'"
                )
            _compile_slot(slot, model.root, graph, handlers, model)
        elif kind == "constraint":
            _compile_requirement_package_constraint(pkg, name, node, graph, handlers, model)
        elif kind == "requirement_block":
            inner = getattr(pkg, name, None)
            if isinstance(inner, RequirementPackageInstance):
                _compile_requirement_package_tree(inner, graph, handlers, model)


def _compile_requirement_package_constraint(
    pkg: RequirementPackageInstance,
    name: str,
    node: dict[str, Any],
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    constraint_node_id = f"check:{pkg.path_string}.{name}"
    graph.add_node(
        DependencyNode(
            constraint_node_id,
            NodeKind.CONSTRAINT_CHECK,
            metadata={"name": f"{pkg.path_string}.{name}"},
        )
    )
    expr = node.get("metadata", {}).get("_expr")
    if expr is None:
        raise GraphCompilationError(
            f"Requirement package constraint '{pkg.path_string}.{name}' has no expr "
            f"(expected compile-time validation to reject this)."
        )

    def make_pkg_constraint_handler(
        constraint_expr: Any,
        cm: ConfiguredModel,
    ) -> Callable[..., bool]:
        def handler(dep_values: dict[str, Any]) -> bool:
            context: dict[Any, Any] = {}
            for sym in constraint_expr.free_symbols:
                dep_slot = _resolve_symbol_to_slot(sym, cm.root, cm)
                dep_node_id = f"val:{dep_slot.path_string}"
                if dep_node_id in dep_values:
                    context[sym] = dep_values[dep_node_id]
            return constraint_expr.evaluate(context)

        return handler

    if hasattr(expr, "free_symbols") and expr.free_symbols:
        for sym in expr.free_symbols:
            dep_slot = _resolve_symbol_to_slot(sym, model.root, model)
            dep_node_id = f"val:{dep_slot.path_string}"
            graph.add_edge(dep_node_id, constraint_node_id)
        handlers[constraint_node_id] = make_pkg_constraint_handler(expr, model)
    elif hasattr(expr, "evaluate"):
        handlers[constraint_node_id] = lambda dep_values, e=expr: bool(e.evaluate({}))
    elif callable(expr):
        handlers[constraint_node_id] = lambda dep_values, fn=expr: bool(fn(dep_values))
    else:
        handlers[constraint_node_id] = lambda dep_values, val=expr: bool(val)

    # Constant / symbol-free constraints need at least one incoming edge so validation does not
    # treat the check node as orphaned, and so evaluation runs after package inputs exist.
    if not graph.dependencies_of(constraint_node_id):
        anchor = _first_value_slot_under_requirement_package(pkg)
        if anchor is not None:
            graph.add_edge(f"val:{anchor.path_string}", constraint_node_id)


def _compile_constraints_for_part(
    part: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    compiled = part.definition_type.compile()

    for name, node in compiled.get("nodes", {}).items():
        if node["kind"] != "constraint":
            continue

        constraint_node_id = f"check:{part.path_string}.{name}"
        graph.add_node(
            DependencyNode(
                constraint_node_id,
                NodeKind.CONSTRAINT_CHECK,
                metadata={"name": f"{part.path_string}.{name}"},
            )
        )

        expr = node["metadata"].get("_expr")
        if expr is not None and hasattr(expr, "free_symbols"):
            for sym in expr.free_symbols:
                dep_slot = _resolve_symbol_to_slot(sym, part, model)
                dep_node_id = f"val:{dep_slot.path_string}"
                graph.add_edge(dep_node_id, constraint_node_id)

            def make_constraint_handler(
                constraint_expr: Any,
                owner_part: PartInstance,
                cm: ConfiguredModel,
            ) -> Callable[..., bool]:
                def handler(dep_values: dict[str, Any]) -> bool:
                    context = {}
                    for sym in constraint_expr.free_symbols:
                        dep_slot = _resolve_symbol_to_slot(sym, owner_part, cm)
                        dep_node_id = f"val:{dep_slot.path_string}"
                        if dep_node_id in dep_values:
                            context[sym] = dep_values[dep_node_id]
                    return constraint_expr.evaluate(context)

                return handler

            handlers[constraint_node_id] = make_constraint_handler(expr, part, model)

    for child in part.children:
        _compile_constraints_for_part(child, graph, handlers, model)


def _compile_requirement_acceptance(
    model: ConfiguredModel,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
) -> None:
    """Add constraint-check nodes for requirements with ``_accept_expr`` per allocation (Phase 7).

    Uses :func:`_resolve_symbol_for_requirement_acceptance` (not :func:`_resolve_symbol_to_slot`):
    symbols may be authored on the requirement owner type (system path prefix stripped to the
    allocate target) or on the allocate target's part type. Same ``Evaluator`` / graph kinds as
    part constraints; resolution rules differ.
    """
    for alloc in model.allocations:
        req = alloc.requirement
        if not isinstance(req, ElementInstance) or req.kind != "requirement":
            continue
        expr = req.metadata.get("_accept_expr")
        if expr is None:
            continue
        target = alloc.target
        if not isinstance(target, PartInstance):
            raise GraphCompilationError(
                f"Requirement acceptance for '{req.path_string}' needs allocate target to be a "
                f"PartInstance; got {type(target).__name__} at '{target.path_string}'"
            )
        req_def_type = req.definition_type
        node_id = f"reqcheck:{req.path_string}@{alloc.stable_id}"
        graph.add_node(
            DependencyNode(
                node_id,
                NodeKind.CONSTRAINT_CHECK,
                metadata={
                    "name": node_id,
                    "requirement_path": req.path_string,
                    "allocation_target_path": target.path_string,
                    "check_kind": "requirement_acceptance",
                },
            )
        )
        if not hasattr(expr, "free_symbols"):
            raise GraphCompilationError(
                f"Requirement '{req.path_string}' acceptance expr has no free_symbols; "
                "use the same expression types as model.constraint(expr=...)."
            )
        for sym in expr.free_symbols:
            dep_slot = _resolve_symbol_for_requirement_acceptance(
                sym,
                target,
                req_def_type,
                model,
                alloc,
            )
            dep_node_id = f"val:{dep_slot.path_string}"
            graph.add_edge(dep_node_id, node_id)
        if not expr.free_symbols:
            anchor = _first_value_graph_node_id_under_part(target)
            if anchor is None:
                raise GraphCompilationError(
                    f"Requirement '{req.path_string}' has a constant acceptance expr but allocate "
                    f"target '{target.path_string}' has no value slots to order evaluation after."
                )
            graph.add_edge(anchor, node_id)

        def make_req_accept_handler(
            constraint_expr: Any,
            owner_part: PartInstance,
            cm: ConfiguredModel,
            req_owner_type: type,
            binding: AllocationBinding,
        ) -> Callable[..., bool]:
            def handler(dep_values: dict[str, Any]) -> bool:
                context: dict[Any, Any] = {}
                for sym in constraint_expr.free_symbols:
                    dep_slot = _resolve_symbol_for_requirement_acceptance(
                        sym,
                        owner_part,
                        req_owner_type,
                        cm,
                        binding,
                    )
                    dep_node_id = f"val:{dep_slot.path_string}"
                    if dep_node_id in dep_values:
                        context[sym] = dep_values[dep_node_id]
                return constraint_expr.evaluate(context)

            return handler

        handlers[node_id] = make_req_accept_handler(expr, target, model, req_def_type, alloc)


def _first_value_graph_node_id_under_part(part: PartInstance) -> str | None:
    """First ``val:...`` node id in a deterministic DFS under ``part`` (for ordering-only edges)."""
    for slot in part.value_slots:
        return f"val:{slot.path_string}"
    for child in part.children:
        found = _first_value_graph_node_id_under_part(child)
        if found is not None:
            return found
    return None


def _resolve_path_to_slot(
    path: list[str],
    part: PartInstance,
    group_name: str,
) -> ValueSlot:
    """Resolve a declaration path to its corresponding ValueSlot under a part."""
    current: Any = part
    try:
        for seg in path:
            current = getattr(current, seg)
        if isinstance(current, ValueSlot):
            return current
    except AttributeError:
        pass
    raise GraphCompilationError(
        f"Solve group '{group_name}': path {list(path)} could not be resolved to a ValueSlot under '{part.path_string}'"
    )


def _compile_solve_groups_for_part(
    part: PartInstance,
    graph: DependencyGraph,
    handlers: dict[str, Callable],
    model: ConfiguredModel,
) -> None:
    compiled = part.definition_type.compile()

    for name, node in compiled.get("nodes", {}).items():
        if node["kind"] != "solve_group":
            continue

        sg_node_id = f"solve:{part.path_string}.{name}"
        meta = node.get("metadata", {})

        unknown_paths = meta.get("_unknowns", [])
        given_paths = meta.get("_givens", [])
        equations = meta.get("_equations", [])

        unknown_slot_ids: set[str] = set()
        unknown_slot_by_path: dict[tuple[str, ...], str] = {}
        for upath in unknown_paths:
            slot = _resolve_path_to_slot(upath, part, name)
            if slot.stable_id in unknown_slot_ids:
                raise GraphCompilationError(f"Solve group '{name}': duplicate unknown '{'.'.join(upath)}'")
            unknown_slot_ids.add(slot.stable_id)
            unknown_slot_by_path[tuple(upath)] = slot.stable_id

        given_slot_ids: set[str] = set()
        for gpath in given_paths:
            slot = _resolve_path_to_slot(gpath, part, name)
            if slot.stable_id in given_slot_ids:
                raise GraphCompilationError(f"Solve group '{name}': duplicate given '{'.'.join(gpath)}'")
            if slot.stable_id in unknown_slot_ids:
                raise GraphCompilationError(
                    f"Solve group '{name}': '{'.'.join(gpath)}' declared as both unknown and given"
                )
            given_slot_ids.add(slot.stable_id)

        target_slots = {sid: sid for sid in unknown_slot_ids}
        graph.add_node(
            DependencyNode(
                sg_node_id,
                NodeKind.SOLVE_GROUP,
                metadata={"name": name, "target_slots": target_slots},
            )
        )

        unknown_syms: list[Any] = []
        given_syms: list[Any] = []
        given_to_node_id: dict[Any, str] = {}
        found_unknown_ids: set[str] = set()
        found_given_ids: set[str] = set()

        for eq in equations:
            if not hasattr(eq, "free_symbols"):
                continue
            for sym in eq.free_symbols:
                if any(s is sym for s in unknown_syms) or any(s is sym for s in given_syms):
                    continue
                slot = _resolve_symbol_to_slot(sym, part, model)
                dep_node_id = f"val:{slot.path_string}"

                if slot.stable_id in unknown_slot_ids:
                    unknown_syms.append(sym)
                    found_unknown_ids.add(slot.stable_id)
                    graph.add_edge(sg_node_id, dep_node_id)
                elif slot.stable_id in given_slot_ids:
                    given_syms.append(sym)
                    found_given_ids.add(slot.stable_id)
                    given_to_node_id[sym] = dep_node_id
                    graph.add_edge(dep_node_id, sg_node_id)
                else:
                    raise GraphCompilationError(
                        f"Solve group '{name}': symbol '{getattr(sym, 'name', '?')}' "
                        f"resolves to slot '{slot.path_string}' which is not declared "
                        f"as unknown or given."
                    )

        missing_unknowns = unknown_slot_ids - found_unknown_ids
        if missing_unknowns:
            raise GraphCompilationError(
                f"Solve group '{name}': declared unknowns not found in any equation. "
                f"Missing slot IDs: {missing_unknowns}"
            )

        missing_givens = given_slot_ids - found_given_ids
        if missing_givens:
            raise GraphCompilationError(
                f"Solve group '{name}': declared givens not found in any equation. Missing slot IDs: {missing_givens}"
            )

        sym_to_slot_id: dict[int, str] = {}
        for sym in unknown_syms:
            from tg_model.model.refs import _symbol_id_to_path

            result = _symbol_id_to_path.get(id(sym))
            if result is not None:
                _, sym_path = result
                slot_id = unknown_slot_by_path.get(tuple(sym_path))
                if slot_id is not None:
                    sym_to_slot_id[id(sym)] = slot_id

        from tg_model.execution.solve_groups import build_solve_group_handler

        handlers[sg_node_id] = build_solve_group_handler(
            equations,
            unknown_syms,
            given_syms,
            given_to_node_id,
            sym_to_slot_id,
        )

    for child in part.children:
        _compile_solve_groups_for_part(child, graph, handlers, model)
