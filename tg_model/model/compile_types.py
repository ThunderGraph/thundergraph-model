"""Compile :class:`~tg_model.model.elements.Element` subclasses into cached definition artifacts.

The public entry point for authors is usually :meth:`~tg_model.model.elements.Element.compile`;
this module implements the recursive compile pipeline, validation, and runtime facet caching.
"""

from __future__ import annotations

from typing import Any

from tg_model.model.declarations.behavior import check_transition_determinism
from tg_model.model.definition_context import ModelDefinitionError, NodeDecl
from tg_model.model.identity import qualified_name
from tg_model.model.refs import AttributeRef


def _requirement_block_compiled_artifact(block_type: type) -> dict[str, Any]:
    """Return the cached compiled dict for a requirement block type (internal).

    Parameters
    ----------
    block_type : type
        Subclass of :class:`~tg_model.model.elements.Requirement`.

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
    from tg_model.model.elements import Requirement

    if not issubclass(block_type, Requirement):
        raise TypeError("_requirement_block_compiled_artifact expects a Requirement subclass")
    art = getattr(block_type, "_compiled_definition", None)
    if art is None:
        raise ModelDefinitionError(
            f"{block_type.__name__}: Requirement has no compiled artifact yet "
            f"(internal error — register with requirement_package(...) before walking paths)"
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
        For :class:`~tg_model.model.elements.Requirement` only: configured root type that
        owns threaded requirement-input symbols.
    symbol_path_prefix : tuple[str, ...], optional
        Path prefix of nested composable requirement packages under that root.

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
    from tg_model.model.elements import Requirement

    cached = getattr(element_cls, "_compiled_definition", None)
    if cached is not None:
        return cached

    if issubclass(element_cls, Requirement):
        sym_owner = symbol_anchor_type if symbol_anchor_type is not None else element_cls
        sym_prefix = symbol_path_prefix
    else:
        sym_owner = element_cls
        sym_prefix = ()

    # Pyright narrows ``element_cls`` after ``issubclass(..., Requirement)``; framework types set
    # dynamic attributes (_tg_definition_context, _tg_behavior_spec, …) that are not on the
    # ``type`` stub. Use an explicit Any handle for those assignments instead of weakening
    # Element typing globally.
    cls_mut: Any = element_cls
    ctx = ModelDefinitionContext(
        element_cls,
        symbol_owner=sym_owner,
        symbol_path_prefix=sym_prefix,
    )
    cls_mut._tg_definition_context = ctx
    try:
        cls_mut.define(ctx)
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

        _validate_name_and_doc_required(element_cls, ctx)
        _validate_requirement_block_if_needed(element_cls, ctx)
        _validate_requirement_package_value_exprs(ctx)

        for edge in ctx.edges:
            if edge["kind"] == "connect":
                _validate_port_ref(ctx, edge["source"])
                _validate_port_ref(ctx, edge["target"])

        _validate_references_edges(ctx)

        if ctx.behavior_transitions:
            check_transition_determinism(ctx.behavior_transitions)
        _validate_behavior_transition_effects(ctx)
        _validate_initial_state_rule(ctx)
        _validate_behavior_control_flow(ctx)

        cls_mut._tg_behavior_spec = _runtime_behavior_transitions(ctx)
        _cache_behavior_runtime_facets(element_cls, ctx)

        artifact: dict[str, Any] = {
            "owner": qualified_name(element_cls),
            "declared_name": ctx._declared_name,
            "declared_doc": ctx._declared_doc,
            "nodes": {
                name: {
                    "kind": decl.kind,
                    "target_type": qualified_name(decl.target_type) if decl.target_type else None,
                    "metadata": dict(decl.metadata),
                }
                for name, decl in ctx.nodes.items()
            },
            "edges": [_serialize_edge(edge) for edge in ctx.edges],
            "child_types": child_types,
            "_type_registry": type_registry,
            # Threaded path prefix used by Requirement parameter()/attribute() refs.
            # Runtime needs this to translate refs that carry the threaded path
            # back to a local-relative path before prepending the instance path
            # of a composed Requirement block.
            "_symbol_path_prefix": tuple(ctx.symbol_path_prefix),
            "behavior_transitions": _serialize_behavior_transitions(ctx.behavior_transitions),
        }
        cls_mut._compiled_definition = artifact
        return artifact
    finally:
        cls_mut._tg_definition_context = None


def _serialize_behavior_transitions(transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for t in transitions:
        has_guard = t.get("when") is not None or t.get("guard_ref") is not None
        serialized.append(
            {
                "from": t["from_state"].path[-1],
                "to": t["to_state"].path[-1],
                "event": t["on"].path[-1],
                "effect": t.get("effect"),
                "has_guard": has_guard,
            }
        )
    return serialized


def _validate_behavior_transition_effects(ctx: Any) -> None:
    for t in ctx.behavior_transitions:
        eff = t.get("effect")
        if eff is None:
            continue
        decl = ctx.nodes.get(eff)
        if decl is None or decl.kind != "action":
            raise ModelDefinitionError(f"transition effect {eff!r} must name an action declared with model.action(...)")


def _validate_initial_state_rule(ctx: Any) -> None:
    state_names = [n for n, d in ctx.nodes.items() if d.kind == "state"]
    if not state_names:
        if ctx.behavior_transitions:
            raise ModelDefinitionError(f"{ctx.owner_type.__name__}: behavior transitions require at least one state")
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


def _validate_name_and_doc_required(element_cls: type, ctx: Any) -> None:
    """Enforce that every element calls ``model.name()`` and every Requirement calls ``model.doc()``."""
    from tg_model.model.elements import Element, Part, Requirement, System

    # Skip validation on the abstract base classes themselves
    if element_cls in (Element, Part, System, Requirement):
        return

    if ctx._declared_name is None:
        raise ModelDefinitionError(
            f"{element_cls.__name__}: model.name(...) is required in define()"
        )
    if issubclass(element_cls, Requirement) and ctx._declared_doc is None:
        raise ModelDefinitionError(
            f"{element_cls.__name__}: model.doc(...) is required in Requirement.define()"
        )


def _validate_requirement_block_if_needed(element_cls: type, ctx: Any) -> None:
    """Enforce authoring policy on :class:`~tg_model.model.elements.Requirement` composable packages.

    Structural value nodes (``parameter``, ``attribute``, ``constraint``) are allowed alongside
    requirement-specific declarations. Structural edges remain ``references`` only (no ``connect``,
    behavior wiring, etc.).

    Notes
    -----
    :class:`~tg_model.model.definition_context.ModelDefinitionContext` is shared with
    :class:`~tg_model.model.elements.Part` / :class:`~tg_model.model.elements.System`, so methods
    like :meth:`~tg_model.model.definition_context.ModelDefinitionContext.allocate` and
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.connect` are callable during
    ``Requirement.define()``; this validator rejects any resulting non-``references`` edges.
    """
    from tg_model.model.elements import Requirement

    if not issubclass(element_cls, Requirement):
        return
    allowed_nodes = frozenset(
        {
            "citation",
            "requirement_block",
            "parameter",
            "attribute",
            "constraint",
        }
    )
    for name, decl in ctx.nodes.items():
        if decl.kind not in allowed_nodes:
            raise ModelDefinitionError(
                f"{element_cls.__name__}: Requirement cannot declare {decl.kind!r} "
                f"({name!r}); allowed: {sorted(allowed_nodes)}"
            )
    for edge in ctx.edges:
        ek = edge.get("kind")
        if ek not in ("references",):
            raise ModelDefinitionError(
                f"{element_cls.__name__}: Requirement edge kind {ek!r} is not allowed (only 'references')"
            )


def _validate_requirement_pkg_expr_symbol(
    owner_name: str,
    ctx: Any,
    allowed: frozenset[str],
    sym: Any,
    context_msg: str,
) -> None:
    """Reject foreign or out-of-order refs in package-level ``attribute`` / ``constraint`` exprs."""
    from tg_model.model.refs import _symbol_id_to_path

    info = _symbol_id_to_path.get(id(sym))
    if info is None:
        return
    sym_owner, sym_path = info
    prefix = tuple(ctx.symbol_path_prefix)

    if sym_owner is ctx.symbol_owner:
        if len(sym_path) == len(prefix) + 1 and sym_path[: len(prefix)] == prefix:
            leaf = sym_path[-1]
            if leaf not in allowed:
                raise ModelDefinitionError(
                    f"{owner_name}: {context_msg} references {leaf!r} but allowed prior "
                    f"package parameters/attributes (in declaration order) are {sorted(allowed)!r}"
                )
            return
        return

    if sym_owner is ctx.owner_type:
        if len(sym_path) != 1:
            raise ModelDefinitionError(
                f"{owner_name}: {context_msg} uses a package-local ref with path {sym_path!r}; "
                f"expected a single segment (parameter or attribute name on this package)"
            )
        leaf = sym_path[0]
        if leaf not in allowed:
            raise ModelDefinitionError(
                f"{owner_name}: {context_msg} references {leaf!r} but allowed prior "
                f"package parameters/attributes (in declaration order) are {sorted(allowed)!r}"
            )
        return
    foreign = getattr(sym_owner, "__name__", sym_owner)
    raise ModelDefinitionError(
        f"{owner_name}: {context_msg} references a value symbol owned by {foreign!r}; "
        f"use only parameters and attributes declared earlier in this package, or threaded "
        f"requirement symbols from the same configured root"
    )


def _validate_requirement_pkg_attribute_ref_expr(
    owner_name: str,
    ctx: Any,
    frozen: frozenset[str],
    expr: AttributeRef,
    attr_name: str,
) -> None:
    """Require package attribute ``expr=`` :class:`~tg_model.model.refs.AttributeRef` to name a prior slot."""
    if expr.owner_type is not ctx.symbol_owner:
        raise ModelDefinitionError(
            f"{owner_name}: attribute {attr_name!r} expr= AttributeRef must reference slots owned by "
            f"{ctx.symbol_owner.__name__!r} (same configured-root threading as package parameters)"
        )
    prefix = tuple(ctx.symbol_path_prefix)
    if len(expr.path) != len(prefix) + 1 or expr.path[:-1] != prefix:
        raise ModelDefinitionError(
            f"{owner_name}: attribute {attr_name!r} AttributeRef path {expr.path!r} must be "
            f"(*symbol_path_prefix, '<prior_name>') = {(*prefix, '<prior_name>')!r} for this package"
        )
    leaf = expr.path[-1]
    if leaf not in frozen:
        raise ModelDefinitionError(
            f"{owner_name}: attribute {attr_name!r} references {leaf!r} but allowed prior "
            f"package parameters/attributes (in declaration order) are {sorted(frozen)!r}"
        )


def _validate_requirement_package_value_exprs(ctx: Any) -> None:
    """Compile-time checks for ``parameter`` / ``attribute`` / ``constraint`` exprs on packages.

    Ensures tracked symbols either use ``symbol_owner`` with path ``symbol_path_prefix + (name,)``
    for prior package parameters/attributes (declaration order), pass through longer
    ``symbol_owner`` paths (e.g. requirement inputs), or match legacy flat ``owner_type`` refs.
    """
    from tg_model.model.elements import Requirement

    if not issubclass(ctx.owner_type, Requirement):
        return

    owner_name = ctx.owner_type.__name__
    allowed: set[str] = set()

    for name, decl in ctx.nodes.items():
        if decl.kind == "parameter":
            allowed.add(name)
        elif decl.kind == "attribute":
            expr = decl.metadata.get("_expr")
            frozen = frozenset(allowed)
            if expr is not None:
                if isinstance(expr, AttributeRef):
                    _validate_requirement_pkg_attribute_ref_expr(owner_name, ctx, frozen, expr, name)
                elif hasattr(expr, "free_symbols") and expr.free_symbols:
                    for sym in expr.free_symbols:
                        _validate_requirement_pkg_expr_symbol(owner_name, ctx, frozen, sym, f"attribute {name!r}")
            allowed.add(name)
        elif decl.kind == "constraint":
            expr = decl.metadata.get("_expr")
            if expr is None:
                raise ModelDefinitionError(
                    f"{owner_name}: constraint {name!r} must set expr= to a boolean expression "
                    f"(requirement package constraints cannot be empty)."
                )
            if hasattr(expr, "free_symbols"):
                frozen = frozenset(allowed)
                for sym in expr.free_symbols:
                    _validate_requirement_pkg_expr_symbol(owner_name, ctx, frozen, sym, f"constraint {name!r}")


def _validate_references_edges(ctx: Any) -> None:
    """``references`` edges must resolve to declared nodes; target must be a citation.

    Source refs may also point at the root_block (``path=()``, ``kind='part'``,
    ``owner_type is ctx.owner_type``), which represents a citation on the class
    itself rather than on one of its declared members. We treat that as valid
    without requiring a node lookup.
    """
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
        # Self-reference (root_block): empty path, kind=part, owner_type matches.
        # No node decl exists for the class itself — accept without lookup.
        if (
            getattr(src, "path", None) == ()
            and getattr(src, "kind", None) == "part"
            and getattr(src, "owner_type", None) is ctx.owner_type
        ):
            pass
        else:
            sdecl = _lookup_node_decl_for_ref(ctx, src)
            if sdecl is None:
                raise ModelDefinitionError(
                    f"{ctx.owner_type.__name__}: references source path {getattr(src, 'path', ())!r} does not resolve"
                )
        tdecl = _lookup_node_decl_for_ref(ctx, tgt)
        if tdecl is None or tdecl.kind != "citation":
            raise ModelDefinitionError(
                f"{ctx.owner_type.__name__}: references target path {getattr(tgt, 'path', ())!r} is not a citation node"
            )


def _lookup_node_decl_for_ref(ctx: Any, ref: Any) -> NodeDecl | None:
    """Resolve a definition-time ref using the owning type's definition context (no recursive ``compile()``).

    Refs from ``Requirement`` ``parameter()`` / ``attribute()`` calls are threaded
    under ``ctx.symbol_owner`` (typically the configured root type) with a path
    prefixed by ``ctx.symbol_path_prefix``. Strip that prefix before walking the
    local context so refs and locally-declared nodes line up.
    """
    path = getattr(ref, "path", ())
    if not path:
        return None
    ref_owner = getattr(ref, "owner_type", None)
    if ref_owner is ctx.owner_type:
        return _walk_path_in_definition_ctx(ctx, path)
    symbol_owner = getattr(ctx, "symbol_owner", None)
    symbol_prefix = tuple(getattr(ctx, "symbol_path_prefix", ()) or ())
    if ref_owner is symbol_owner and (not symbol_prefix or path[: len(symbol_prefix)] == symbol_prefix):
        local_path = path[len(symbol_prefix):]
        if local_path:
            return _walk_path_in_definition_ctx(ctx, local_path)
    return None


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
            out["_allocate_inputs"] = {k: {"path": list(v.path), "kind": v.kind} for k, v in raw_in.items()}
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
        raise ModelDefinitionError(f"Reference '{ref.local_name}' starts with unknown symbol '{top}'")

    if len(path) == 1:
        if owner_decl.kind != "port":
            raise ModelDefinitionError(f"Reference '{ref.local_name}' points to '{top}', which is not a port")
        return

    current_decl = owner_decl
    for i in range(1, len(path)):
        if current_decl.kind != "part" or current_decl.target_type is None:
            raise ModelDefinitionError(f"Reference '{ref.local_name}' expects '{path[i - 1]}' to be a part")
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
                raise ModelDefinitionError(f"Reference '{ref.local_name}' points to '{segment}', which is not a port")
        else:
            from tg_model.model.definition_context import NodeDecl

            current_decl = NodeDecl(
                name=segment,
                kind=member["kind"],
                target_type=child_def.get("_type_registry", {}).get(segment),
                metadata=member.get("metadata", {}),
            )
