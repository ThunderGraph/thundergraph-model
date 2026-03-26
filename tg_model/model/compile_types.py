"""Compile :class:`~tg_model.model.elements.Element` subclasses into cached definition artifacts.

The public entry point for authors is usually :meth:`~tg_model.model.elements.Element.compile`;
this module implements the recursive compile pipeline, validation, and runtime facet caching.
"""

from __future__ import annotations

from typing import Any

from tg_model.model.declarations.behavior import check_transition_determinism
from tg_model.model.definition_context import ModelDefinitionError, NodeDecl
from tg_model.model.identity import qualified_name


def _requirement_block_compiled_artifact(block_type: type) -> dict[str, Any]:
    """Return the cached compiled dict for a requirement block type (internal).

    Parameters
    ----------
    block_type : type
        Subclass of :class:`~tg_model.model.elements.RequirementBlock`.

    Returns
    -------
    dict
        Compiled artifact.

    Raises
    ------
    TypeError
        If ``block_type`` is not a requirement block subclass.
    ModelDefinitionError
        If the type has not been compiled yet (registration order bug).
    """
    from tg_model.model.elements import RequirementBlock

    if not issubclass(block_type, RequirementBlock):
        raise TypeError("_requirement_block_compiled_artifact expects a RequirementBlock subclass")
    art = getattr(block_type, "_compiled_definition", None)
    if art is None:
        raise ModelDefinitionError(
            f"{block_type.__name__}: RequirementBlock has no compiled artifact yet "
            f"(internal error — register with requirement_block(...) before walking paths)"
        )
    return art


def compile_type(
    element_cls: type,
    *,
    symbol_anchor_type: type | None = None,
    symbol_path_prefix: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Compile ``element_cls`` and cache the result on the class.

    Parameters
    ----------
    element_cls : type
        Subclass of :class:`~tg_model.model.elements.Element` to compile.
    symbol_anchor_type : type, optional
        For :class:`~tg_model.model.elements.RequirementBlock` only: configured root type that
        owns threaded requirement-input symbols.
    symbol_path_prefix : tuple[str, ...], optional
        Path prefix of nested requirement blocks under that root.

    Returns
    -------
    dict
        Canonical artifact with ``owner``, ``nodes``, ``edges``, ``child_types``, plus internal
        ``_type_registry`` (live classes for :class:`~tg_model.model.refs.PartRef` resolution).

    Raises
    ------
    ModelDefinitionError
        On invalid definitions, nondeterministic transitions, bad ports, allocate inputs,
        requirement acceptance, references edges, or other compile-time rules.
    TypeError
        Internal misuse of requirement-block artifacts.

    Notes
    -----
    Idempotent: repeated calls return the same cached dict. Serialization-friendly fields avoid
    embedding class objects; ``_type_registry`` is framework-only.
    """
    from tg_model.model.definition_context import ModelDefinitionContext
    from tg_model.model.elements import RequirementBlock

    cached = getattr(element_cls, "_compiled_definition", None)
    if cached is not None:
        return cached

    if issubclass(element_cls, RequirementBlock):
        sym_owner = symbol_anchor_type if symbol_anchor_type is not None else element_cls
        sym_prefix = symbol_path_prefix
    else:
        sym_owner = element_cls
        sym_prefix = ()

    ctx = ModelDefinitionContext(
        element_cls,
        symbol_owner=sym_owner,
        symbol_path_prefix=sym_prefix,
    )
    element_cls._tg_definition_context = ctx
    try:
        element_cls.define(ctx)
        ctx.freeze()

        type_registry: dict[str, type] = {}
        child_types: dict[str, dict[str, Any]] = {}
        for decl in ctx.nodes.values():
            if decl.kind == "part" and decl.target_type is not None:
                qname = qualified_name(decl.target_type)
                child_types[qname] = compile_type(decl.target_type)
                type_registry[decl.name] = decl.target_type
            if decl.kind == "requirement_block" and decl.target_type is not None:
                qname = qualified_name(decl.target_type)
                child_types[qname] = compile_type(
                    decl.target_type,
                    symbol_anchor_type=ctx.symbol_owner,
                    symbol_path_prefix=(*ctx.symbol_path_prefix, decl.name),
                )
                type_registry[decl.name] = decl.target_type

        _validate_requirement_block_if_needed(element_cls, ctx)

        for edge in ctx.edges:
            if edge["kind"] == "connect":
                _validate_port_ref(ctx, edge["source"])
                _validate_port_ref(ctx, edge["target"])

        _validate_requirement_acceptance(ctx, child_types, type_registry)
        _validate_requirement_attributes_exprs(ctx)
        _validate_allocate_input_bindings(ctx)
        _validate_references_edges(ctx)

        if ctx.behavior_transitions:
            check_transition_determinism(ctx.behavior_transitions)
        _validate_behavior_transition_effects(ctx)
        _validate_initial_state_rule(ctx)
        _validate_behavior_control_flow(ctx)

        element_cls._tg_behavior_spec = _runtime_behavior_transitions(ctx)
        _cache_behavior_runtime_facets(element_cls, ctx)

        artifact: dict[str, Any] = {
            "owner": qualified_name(element_cls),
            "nodes": {
                name: {
                    "kind": decl.kind,
                    "target_type": qualified_name(decl.target_type) if decl.target_type else None,
                    "metadata": dict(decl.metadata),
                }
                for name, decl in ctx.nodes.items()
            },
            "edges": [
                _serialize_edge(edge)
                for edge in ctx.edges
            ],
            "child_types": child_types,
            "_type_registry": type_registry,
            "behavior_transitions": _serialize_behavior_transitions(ctx.behavior_transitions),
        }
        element_cls._compiled_definition = artifact
        return artifact
    finally:
        element_cls._tg_definition_context = None


def _serialize_behavior_transitions(transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for t in transitions:
        has_guard = t.get("when") is not None or t.get("guard_ref") is not None
        serialized.append({
            "from": t["from_state"].path[-1],
            "to": t["to_state"].path[-1],
            "event": t["on"].path[-1],
            "effect": t.get("effect"),
            "has_guard": has_guard,
        })
    return serialized


def _validate_behavior_transition_effects(ctx: Any) -> None:
    for t in ctx.behavior_transitions:
        eff = t.get("effect")
        if eff is None:
            continue
        decl = ctx.nodes.get(eff)
        if decl is None or decl.kind != "action":
            raise ModelDefinitionError(
                f"transition effect {eff!r} must name an action declared with model.action(...)"
            )


def _validate_initial_state_rule(ctx: Any) -> None:
    state_names = [n for n, d in ctx.nodes.items() if d.kind == "state"]
    if not state_names:
        if ctx.behavior_transitions:
            raise ModelDefinitionError(
                f"{ctx.owner_type.__name__}: behavior transitions require at least one state"
            )
        return
    initials = [n for n, d in ctx.nodes.items() if d.kind == "state" and d.metadata.get("initial")]
    if len(initials) != 1:
        raise ModelDefinitionError(
            f"{ctx.owner_type.__name__}: exactly one initial state required when states exist, "
            f"found initial={initials!r} among states {state_names!r}"
        )


def _runtime_behavior_transitions(ctx: Any) -> list[dict[str, Any]]:
    """Strip definition refs from transitions; merge ``guard_ref`` into ``when`` callable."""
    out: list[dict[str, Any]] = []
    for t in ctx.behavior_transitions:
        when = t.get("when")
        gref = t.get("guard_ref")
        if gref is not None:
            gdecl = ctx.nodes.get(gref.path[-1])
            if gdecl is None or gdecl.kind != "guard":
                raise ModelDefinitionError(f"transition guard ref {gref!r} is not a declared guard")
            pred = gdecl.metadata.get("_predicate")
            if not callable(pred):
                raise ModelDefinitionError(f"guard {gref.path[-1]!r} has no callable predicate")
            when = pred
        row = {
            "from_state": t["from_state"],
            "to_state": t["to_state"],
            "on": t["on"],
            "when": when,
            "effect": t.get("effect"),
        }
        out.append(row)
    return out


def _validate_action_name(ctx: Any, action_name: str) -> None:
    decl = ctx.nodes.get(action_name)
    if decl is None or decl.kind != "action":
        raise ModelDefinitionError(
            f"behavior references unknown action {action_name!r}; declare with model.action(...)"
        )


def _validate_behavior_control_flow(ctx: Any) -> None:
    for name, decl in ctx.nodes.items():
        if decl.kind == "decision":
            for gref, aname in decl.metadata.get("_decision_branches", ()):
                _validate_action_name(ctx, aname)
                if gref is not None and ctx.nodes.get(gref.path[-1], None) is None:
                    raise ModelDefinitionError(f"decision {name!r} references unknown guard")
            default_a = decl.metadata.get("_default_action")
            if default_a:
                _validate_action_name(ctx, default_a)
            dm = decl.metadata.get("_decision_merge")
            if dm:
                mdecl = ctx.nodes.get(dm)
                if mdecl is None or mdecl.kind != "merge":
                    raise ModelDefinitionError(
                        f"decision {name!r} merge_point must reference a merge node on this type"
                    )
        if decl.kind == "fork_join":
            for seq in decl.metadata.get("_fj_branches", ()):
                for aname in seq:
                    _validate_action_name(ctx, aname)
            then_a = decl.metadata.get("_fj_then")
            if then_a:
                _validate_action_name(ctx, then_a)
        if decl.kind == "merge":
            then_m = decl.metadata.get("_merge_then")
            if then_m:
                _validate_action_name(ctx, then_m)
        if decl.kind == "sequence":
            for aname in decl.metadata.get("_sequence_steps", ()):
                _validate_action_name(ctx, aname)


def _cache_behavior_runtime_facets(element_cls: type, ctx: Any) -> None:
    """Avoid repeated compile() during dispatch: initial state, actions, guards, decisions, fork/join."""
    element_cls._tg_action_effects = {
        name: decl.metadata["_effect"]
        for name, decl in ctx.nodes.items()
        if decl.kind == "action" and callable(decl.metadata.get("_effect"))
    }
    element_cls._tg_guard_predicates = {
        name: decl.metadata["_predicate"]
        for name, decl in ctx.nodes.items()
        if decl.kind == "guard" and callable(decl.metadata.get("_predicate"))
    }
    decisions: dict[str, Any] = {}
    for name, decl in ctx.nodes.items():
        if decl.kind != "decision":
            continue
        branches: list[tuple[Any, str]] = []
        for gref, aname in decl.metadata.get("_decision_branches", ()):
            pred = None
            if gref is not None:
                gdecl = ctx.nodes.get(gref.path[-1])
                if gdecl is None or gdecl.kind != "guard":
                    raise ModelDefinitionError(f"decision {name!r} branch guard is invalid")
                pred = gdecl.metadata.get("_predicate")
                if not callable(pred):
                    raise ModelDefinitionError(f"guard {gref.path[-1]!r} predicate not callable")
            branches.append((pred, aname))
        decisions[name] = {
            "branches": branches,
            "default_action": decl.metadata.get("_default_action"),
            "merge_name": decl.metadata.get("_decision_merge"),
        }
    element_cls._tg_decision_specs = decisions

    fork_joins: dict[str, Any] = {}
    for name, decl in ctx.nodes.items():
        if decl.kind != "fork_join":
            continue
        fork_joins[name] = {
            "branches": list(decl.metadata.get("_fj_branches", ())),
            "then_action": decl.metadata.get("_fj_then"),
        }
    element_cls._tg_fork_join_specs = fork_joins

    merges: dict[str, Any] = {}
    for name, decl in ctx.nodes.items():
        if decl.kind != "merge":
            continue
        merges[name] = {"then_action": decl.metadata.get("_merge_then")}
    element_cls._tg_merge_specs = merges

    sequences: dict[str, list[str]] = {}
    for name, decl in ctx.nodes.items():
        if decl.kind != "sequence":
            continue
        sequences[name] = list(decl.metadata.get("_sequence_steps", ()))
    element_cls._tg_sequence_specs = sequences

    initials = [n for n, d in ctx.nodes.items() if d.kind == "state" and d.metadata.get("initial")]
    element_cls._tg_initial_state_name = initials[0] if len(initials) == 1 else None


def _validate_requirement_block_if_needed(element_cls: type, ctx: Any) -> None:
    """Enforce narrow authoring surface on :class:`~tg_model.model.elements.RequirementBlock` types."""
    from tg_model.model.elements import RequirementBlock

    if not issubclass(element_cls, RequirementBlock):
        return
    allowed_nodes = frozenset({
        "requirement",
        "citation",
        "requirement_block",
        "requirement_input",
        "requirement_attribute",
    })
    for name, decl in ctx.nodes.items():
        if decl.kind not in allowed_nodes:
            raise ModelDefinitionError(
                f"{element_cls.__name__}: RequirementBlock cannot declare {decl.kind!r} "
                f"({name!r}); allowed: {sorted(allowed_nodes)}"
            )
    for edge in ctx.edges:
        ek = edge.get("kind")
        if ek not in ("references",):
            raise ModelDefinitionError(
                f"{element_cls.__name__}: RequirementBlock edge kind {ek!r} is not allowed "
                f"(only 'references')"
            )


def _validate_references_edges(ctx: Any) -> None:
    """``references`` edges must resolve to declared nodes; target must be a citation."""
    for edge in ctx.edges:
        if edge.get("kind") != "references":
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if src is None or tgt is None:
            raise ModelDefinitionError(f"{ctx.owner_type.__name__}: references edge missing source or target")
        if getattr(tgt, "kind", None) != "citation":
            raise ModelDefinitionError(
                f"{ctx.owner_type.__name__}: references target must be a citation ref, "
                f"got {getattr(tgt, 'kind', None)!r}"
            )
        sdecl = _lookup_node_decl_for_ref(ctx, src)
        if sdecl is None:
            raise ModelDefinitionError(
                f"{ctx.owner_type.__name__}: references source path {getattr(src, 'path', ())!r} does not resolve"
            )
        tdecl = _lookup_node_decl_for_ref(ctx, tgt)
        if tdecl is None or tdecl.kind != "citation":
            raise ModelDefinitionError(
                f"{ctx.owner_type.__name__}: references target path {getattr(tgt, 'path', ())!r} "
                f"is not a citation node"
            )


def _lookup_node_decl_for_ref(ctx: Any, ref: Any) -> NodeDecl | None:
    """Resolve a definition-time ref using the owning type's definition context (no recursive ``compile()``)."""
    path = getattr(ref, "path", ())
    if not path:
        return None
    if getattr(ref, "owner_type", None) is not ctx.owner_type:
        return None
    return _walk_path_in_definition_ctx(ctx, path)


def _walk_path_in_definition_ctx(ctx: Any, path: tuple[str, ...]) -> NodeDecl | None:
    """Walk ``path`` in ``ctx.nodes``, descending into child part / requirement_block compiled subtrees."""
    if not path:
        return None
    decl = ctx.nodes.get(path[0])
    if decl is None:
        return None
    if len(path) == 1:
        return decl
    if decl.kind == "part" and decl.target_type is not None:
        sub = decl.target_type.compile()
        return _walk_path_in_compiled_subtree(path[1:], sub)
    if decl.kind == "requirement_block" and decl.target_type is not None:
        sub = _requirement_block_compiled_artifact(decl.target_type)
        return _walk_path_in_compiled_subtree(path[1:], sub)
    return None


def _walk_path_in_compiled_subtree(path: tuple[str, ...], compiled: dict[str, Any]) -> NodeDecl | None:
    """Resolve remaining ``path`` inside an already-compiled child artifact (no second ``define()``)."""
    if not path:
        return None
    tr: dict[str, type] = compiled.get("_type_registry", {})
    name = path[0]
    node = compiled.get("nodes", {}).get(name)
    if node is None:
        return None
    if len(path) == 1:
        return NodeDecl(
            name=name,
            kind=node["kind"],
            target_type=tr.get(name),
            metadata=dict(node.get("metadata", {})),
        )
    kind = node["kind"]
    if kind == "part" and tr.get(name) is not None:
        return _walk_path_in_compiled_subtree(path[1:], tr[name].compile())
    if kind == "requirement_block" and tr.get(name) is not None:
        sub = _requirement_block_compiled_artifact(tr[name])
        return _walk_path_in_compiled_subtree(path[1:], sub)
    return None


def _collect_requirement_paths_with_accept_expr(ctx: Any) -> set[tuple[str, ...]]:
    """All requirement paths (including under requirement_block subtrees) that carry ``_accept_expr``."""
    out: set[tuple[str, ...]] = set()

    def walk_subtree(prefix: tuple[str, ...], nodes: dict[str, Any], tr: dict[str, type]) -> None:
        for name, node in nodes.items():
            path = (*prefix, name)
            meta = node.get("metadata", {})
            if node.get("kind") == "requirement" and meta.get("_accept_expr") is not None:
                out.add(path)
            if node.get("kind") == "requirement_block":
                bt = tr.get(name)
                if bt is not None:
                    sub = _requirement_block_compiled_artifact(bt)
                    walk_subtree(path, sub["nodes"], sub.get("_type_registry", {}))

    for name, decl in ctx.nodes.items():
        if decl.kind == "requirement" and decl.metadata.get("_accept_expr") is not None:
            out.add((name,))
        if decl.kind == "requirement_block" and decl.target_type is not None:
            sub = _requirement_block_compiled_artifact(decl.target_type)
            walk_subtree((name,), sub["nodes"], sub.get("_type_registry", {}))
    return out


def _validate_requirement_acceptance(
    ctx: Any,
    child_types: dict[str, dict[str, Any]],
    type_registry: dict[str, type],
) -> None:
    """Requirements with ``_accept_expr`` must have at least one ``allocate`` from that requirement path."""
    from tg_model.model.elements import RequirementBlock

    _ = child_types, type_registry
    if issubclass(ctx.owner_type, RequirementBlock):
        return
    reqs_with_expr = _collect_requirement_paths_with_accept_expr(ctx)
    if not reqs_with_expr:
        return
    allocated: set[tuple[str, ...]] = set()
    for edge in ctx.edges:
        if edge.get("kind") != "allocate":
            continue
        src = edge.get("source")
        if src is None or getattr(src, "kind", None) != "requirement":
            continue
        path = tuple(getattr(src, "path", ()))
        if path:
            allocated.add(path)
    missing = sorted(reqs_with_expr - allocated, key=lambda p: (len(p), p))
    if missing:
        raise ModelDefinitionError(
            f"{ctx.owner_type.__name__}: requirement(s) with acceptance expr but no "
            f"allocate(...) from them: {missing!r}"
        )


def _requirement_metadata_at_path(ctx: Any, path: tuple[str, ...]) -> dict[str, Any] | None:
    """Return requirement node metadata for a full path from the root owner (e.g. allocate source)."""
    if not path:
        return None
    decl = ctx.nodes.get(path[0])
    if decl is None:
        return None
    if len(path) == 1:
        if decl.kind != "requirement":
            return None
        return dict(decl.metadata)
    if decl.kind != "requirement_block" or decl.target_type is None:
        return None
    sub = getattr(decl.target_type, "_compiled_definition", None)
    if sub is None:
        return None
    return _requirement_metadata_at_path_compiled(sub, path[1:])


def _requirement_metadata_at_path_compiled(
    compiled: dict[str, Any],
    path: tuple[str, ...],
) -> dict[str, Any] | None:
    if not path:
        return None
    name, *rest = path
    node = compiled.get("nodes", {}).get(name)
    if node is None:
        return None
    if not rest:
        if node.get("kind") != "requirement":
            return None
        return dict(node.get("metadata") or {})
    if node.get("kind") != "requirement_block":
        return None
    tr: dict[str, type] = compiled.get("_type_registry", {})
    bt = tr.get(name)
    if bt is None:
        return None
    sub = getattr(bt, "_compiled_definition", None)
    if sub is None:
        return None
    return _requirement_metadata_at_path_compiled(sub, tuple(rest))


def _requirement_allowed_symbol_names(meta: dict[str, Any]) -> frozenset[str]:
    """Requirement-local names (inputs + derived attributes) for acceptance validation."""
    inames = list(meta.get("_requirement_input_names") or [])
    anames = list(meta.get("_requirement_attribute_names") or [])
    return frozenset([*inames, *anames])


def _validate_requirement_attributes_exprs(ctx: Any) -> None:
    """Each ``requirement_attribute`` expr may only reference allowed symbols."""
    from tg_model.model.elements import RequirementBlock

    if issubclass(ctx.owner_type, RequirementBlock):
        return

    def walk_subtree(prefix: tuple[str, ...], nodes: dict[str, Any], tr: dict[str, type]) -> None:
        for name, node in nodes.items():
            path = (*prefix, name)
            meta = node.get("metadata", {})
            if node.get("kind") == "requirement" and meta.get("_requirement_attributes"):
                _validate_one_requirement_attributes(
                    ctx.owner_type.__name__,
                    ctx.owner_type,
                    path,
                    meta,
                )
            if node.get("kind") == "requirement_block":
                bt = tr.get(name)
                if bt is not None:
                    sub = _requirement_block_compiled_artifact(bt)
                    walk_subtree(path, sub["nodes"], sub.get("_type_registry", {}))

    for name, decl in ctx.nodes.items():
        if decl.kind == "requirement" and decl.metadata.get("_requirement_attributes"):
            _validate_one_requirement_attributes(
                ctx.owner_type.__name__,
                ctx.owner_type,
                (name,),
                dict(decl.metadata),
            )
        if decl.kind == "requirement_block" and decl.target_type is not None:
            sub = _requirement_block_compiled_artifact(decl.target_type)
            walk_subtree((name,), sub["nodes"], sub.get("_type_registry", {}))


def _validate_one_requirement_attributes(
    owner_name: str,
    root_owner: type,
    path: tuple[str, ...],
    meta: dict[str, Any],
) -> None:
    from tg_model.model.definition_context import ModelDefinitionError
    from tg_model.model.refs import _symbol_id_to_path

    inames = list(meta.get("_requirement_input_names") or [])
    decls = list(meta.get("_requirement_attributes") or [])
    seen_attr: set[str] = set()
    for idx, (aname, expr) in enumerate(decls):
        if aname in seen_attr:
            raise ModelDefinitionError(
                f"{owner_name}: duplicate requirement_attribute name {aname!r} under requirement {path!r}"
            )
        seen_attr.add(aname)
        if expr is None or not hasattr(expr, "free_symbols"):
            continue
        allowed_prev = frozenset([*inames, *[n for n, _ in decls[:idx]]])
        for sym in expr.free_symbols:
            info = _symbol_id_to_path.get(id(sym))
            if info is None:
                continue
            sym_owner, sym_path = info
            if sym_owner is not root_owner:
                continue
            if len(sym_path) != len(path) + 1 or sym_path[: len(path)] != path:
                continue
            leaf = sym_path[-1]
            if leaf in allowed_prev:
                continue
            raise ModelDefinitionError(
                f"{owner_name}: requirement_attribute {aname!r} expr references {leaf!r} under "
                f"{path!r} but allowed names (inputs + earlier attributes) are {sorted(allowed_prev)!r}"
            )


def _validate_allocate_input_bindings(ctx: Any) -> None:
    """If a requirement declares inputs, every allocate must supply them; expr symbols must be bound."""
    from tg_model.model.elements import RequirementBlock
    from tg_model.model.refs import _symbol_id_to_path

    if issubclass(ctx.owner_type, RequirementBlock):
        return

    for edge in ctx.edges:
        if edge.get("kind") != "allocate":
            continue
        src = edge.get("source")
        if src is None or getattr(src, "kind", None) != "requirement":
            continue
        path = tuple(getattr(src, "path", ()))
        meta = _requirement_metadata_at_path(ctx, path)
        if meta is None:
            continue
        inames = list(meta.get("_requirement_input_names") or [])
        allowed_names = _requirement_allowed_symbol_names(meta)
        inputs = edge.get("_allocate_inputs") or {}
        if inames:
            missing = [n for n in inames if n not in inputs]
            if missing:
                raise ModelDefinitionError(
                    f"{ctx.owner_type.__name__}: allocate(..., {path!r}, ...) must include "
                    f"inputs= for requirement inputs {inames!r}; missing {missing!r}"
                )
        expr = meta.get("_accept_expr")
        if expr is None or not hasattr(expr, "free_symbols"):
            continue
        root_owner = ctx.owner_type
        for sym in expr.free_symbols:
            info = _symbol_id_to_path.get(id(sym))
            if info is None:
                continue
            sym_owner, sym_path = info
            if sym_owner is not root_owner:
                continue
            if len(sym_path) == len(path) + 1 and sym_path[: len(path)] == path:
                iname = sym_path[-1]
                if iname not in allowed_names:
                    raise ModelDefinitionError(
                        f"{ctx.owner_type.__name__}: acceptance expr uses symbol {iname!r} under "
                        f"{path!r} but declared requirement_input / requirement_attribute names are "
                        f"{sorted(allowed_names)!r}"
                    )
                if iname in inames and iname not in inputs:
                    raise ModelDefinitionError(
                        f"{ctx.owner_type.__name__}: allocate(..., {path!r}, ...) needs "
                        f"inputs[{iname!r}] for acceptance expression"
                    )


def _serialize_edge(edge: dict[str, Any]) -> dict[str, Any]:
    if edge["kind"] == "connect":
        return {
            "kind": "connect",
            "source": edge["source"].to_dict(),
            "target": edge["target"].to_dict(),
            "carrying": edge.get("carrying"),
        }
    if edge["kind"] == "allocate":
        out: dict[str, Any] = {
            "kind": "allocate",
            "source": edge["source"].to_dict(),
            "target": edge["target"].to_dict(),
        }
        raw_in = edge.get("_allocate_inputs")
        if raw_in:
            out["_allocate_inputs"] = {
                k: {"path": list(v.path), "kind": v.kind} for k, v in raw_in.items()
            }
        return out
    if edge["kind"] == "references":
        return {
            "kind": "references",
            "source": edge["source"].to_dict(),
            "target": edge["target"].to_dict(),
        }
    return dict(edge)


def _validate_port_ref(
    ctx: Any,
    ref: Any,
) -> None:
    """Validate a port reference, walking the full path depth."""
    from tg_model.model.definition_context import ModelDefinitionError

    if ref.kind != "port":
        raise ModelDefinitionError(f"Expected a port reference, got {ref.kind}")

    path = ref.path
    if not path:
        raise ModelDefinitionError("Empty port reference path.")

    top = path[0]
    owner_decl = ctx.nodes.get(top)
    if owner_decl is None:
        raise ModelDefinitionError(
            f"Reference '{ref.local_name}' starts with unknown symbol '{top}'"
        )

    if len(path) == 1:
        if owner_decl.kind != "port":
            raise ModelDefinitionError(
                f"Reference '{ref.local_name}' points to '{top}', which is not a port"
            )
        return

    current_decl = owner_decl
    for i in range(1, len(path)):
        if current_decl.kind != "part" or current_decl.target_type is None:
            raise ModelDefinitionError(
                f"Reference '{ref.local_name}' expects '{path[i-1]}' to be a part"
            )
        child_def = current_decl.target_type.compile()
        segment = path[i]
        member = child_def["nodes"].get(segment)
        if member is None:
            raise ModelDefinitionError(
                f"Reference '{ref.local_name}' points to missing member '{segment}' "
                f"on {current_decl.target_type.__name__}"
            )
        if i == len(path) - 1:
            if member["kind"] != "port":
                raise ModelDefinitionError(
                    f"Reference '{ref.local_name}' points to '{segment}', which is not a port"
                )
        else:
            from tg_model.model.definition_context import NodeDecl
            current_decl = NodeDecl(
                name=segment,
                kind=member["kind"],
                target_type=child_def.get("_type_registry", {}).get(segment),
                metadata=member.get("metadata", {}),
            )
