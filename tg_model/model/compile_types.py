"""Type compilation: runs define() and produces canonical type artifacts."""

from __future__ import annotations

from typing import Any

from tg_model.model.declarations.behavior import check_transition_determinism
from tg_model.model.definition_context import ModelDefinitionError, NodeDecl
from tg_model.model.identity import qualified_name


def compile_type(element_cls: type) -> dict[str, Any]:
    """Compile a single element type into a canonical artifact.

    Walks the define() hook, freezes the context, recursively compiles
    child part types, validates edges, and returns a canonical dict.

    The returned artifact has two layers:
    - canonical fields (owner, nodes, edges, child_types) are inspectable
      and serialization-safe (no live class objects)
    - internal fields (_type_registry) carry live class references for
      framework use only (e.g. PartRef.__getattr__ resolution)
    """
    from tg_model.model.definition_context import ModelDefinitionContext

    ctx = ModelDefinitionContext(element_cls)
    element_cls._tg_definition_context = ctx
    try:
        element_cls.define(ctx)
        ctx.freeze()

        type_registry: dict[str, type] = {}
        child_types: dict[str, dict[str, Any]] = {}
        for decl in ctx.nodes.values():
            if decl.kind == "part" and decl.target_type is not None:
                qname = qualified_name(decl.target_type)
                child_types[qname] = decl.target_type.compile()
                type_registry[decl.name] = decl.target_type

        for edge in ctx.edges:
            if edge["kind"] == "connect":
                _validate_port_ref(ctx, edge["source"])
                _validate_port_ref(ctx, edge["target"])

        _validate_requirement_acceptance(ctx)
        _validate_references_edges(ctx)

        if ctx.behavior_transitions:
            check_transition_determinism(ctx.behavior_transitions)
        _validate_behavior_transition_effects(ctx)
        _validate_initial_state_rule(ctx)
        _validate_behavior_control_flow(ctx)

        element_cls._tg_behavior_spec = _runtime_behavior_transitions(ctx)
        _cache_behavior_runtime_facets(element_cls, ctx)

        return {
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
    """Walk ``path`` in ``ctx.nodes``, descending into child part types with a fresh definition context."""
    if not path:
        return None
    decl = ctx.nodes.get(path[0])
    if decl is None:
        return None
    if len(path) == 1:
        return decl
    if decl.kind != "part" or decl.target_type is None:
        return None
    from tg_model.model.definition_context import ModelDefinitionContext

    sub = ModelDefinitionContext(decl.target_type)
    decl.target_type.define(sub)
    sub.freeze()
    return _walk_path_in_definition_ctx(sub, path[1:])


def _validate_requirement_acceptance(ctx: Any) -> None:
    """Requirements with ``_accept_expr`` must have at least one ``allocate`` from that requirement."""
    reqs_with_expr = {
        name
        for name, decl in ctx.nodes.items()
        if decl.kind == "requirement" and decl.metadata.get("_accept_expr") is not None
    }
    if not reqs_with_expr:
        return
    allocated: set[str] = set()
    for edge in ctx.edges:
        if edge.get("kind") != "allocate":
            continue
        src = edge.get("source")
        if src is None or getattr(src, "kind", None) != "requirement":
            continue
        path = getattr(src, "path", ())
        if path:
            allocated.add(path[-1])
    missing = sorted(reqs_with_expr - allocated)
    if missing:
        raise ModelDefinitionError(
            f"{ctx.owner_type.__name__}: requirement(s) with acceptance expr but no "
            f"allocate(...) from them: {missing!r}"
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
        return {
            "kind": "allocate",
            "source": edge["source"].to_dict(),
            "target": edge["target"].to_dict(),
        }
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
