"""ModelDefinitionContext — the ``model`` object passed into ``define(cls, model)``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, overload

from tg_model.model.refs import AttributeRef, PartRef, PortRef, Ref, RequirementBlockRef


class ModelDefinitionError(Exception):
    """Raised when a model definition is invalid."""


def parameter_ref(root_block_type: type, name: str) -> AttributeRef:
    """Return a reference to a parameter declared on ``root_block_type`` (typically the configured root).

    Use in nested ``define()`` to wire :class:`~tg_model.integrations.external_compute.ExternalComputeBinding`
    inputs or expressions to **mission / scenario** parameters without module-level globals.

    Resolution order:

    1. If ``root_block_type`` is **fully compiled**, the node is read from the cached artifact.
    2. Else if ``root_block_type`` is **mid-compile** (nested part types are compiling before the
       root's ``compile()`` returns), the node is read from the active definition context.
       **Declare parameters on the root before** ``model.part(...)`` for child types that call
       ``parameter_ref``.

    If the type is not compiling and not compiled, raises :class:`ModelDefinitionError`.
    """
    meta: dict[str, Any]

    compiled = getattr(root_block_type, "_compiled_definition", None)
    if compiled is not None:
        node = compiled.get("nodes", {}).get(name)
        if node is None:
            raise ModelDefinitionError(
                f"parameter_ref({root_block_type.__name__}, {name!r}): no such node"
            )
        if node.get("kind") != "parameter":
            raise ModelDefinitionError(
                f"parameter_ref({root_block_type.__name__}, {name!r}): expected kind 'parameter', "
                f"got {node.get('kind')!r}"
            )
        meta = dict(node.get("metadata", {}))
    else:
        active = getattr(root_block_type, "_tg_definition_context", None)
        if active is None:
            raise ModelDefinitionError(
                f"parameter_ref({root_block_type.__name__}, {name!r}): type is not compiling and "
                f"not compiled; call {root_block_type.__name__}.compile() first, or declare "
                f"parameters on the root before nested parts that reference them."
            )
        decl: NodeDecl | None = active.nodes.get(name)
        if decl is None:
            raise ModelDefinitionError(
                f"parameter_ref({root_block_type.__name__}, {name!r}): no such parameter "
                f"(declare it on the root before composing parts that use parameter_ref)."
            )
        if decl.kind != "parameter":
            raise ModelDefinitionError(
                f"parameter_ref({root_block_type.__name__}, {name!r}): expected kind 'parameter', "
                f"got {decl.kind!r}"
            )
        meta = dict(decl.metadata)

    return AttributeRef(
        owner_type=root_block_type,
        path=(name,),
        kind="parameter",
        metadata=meta,
    )


def requirement_ref(root_block_type: type, path: tuple[str, ...]) -> Ref:
    """Return a :class:`~tg_model.model.refs.Ref` to a requirement at ``path`` under ``root_block_type``.

    ``path`` is a tuple of declaration names starting at the root (e.g. ``(\"mission\", \"range\")``
    for a requirement ``range`` inside block ``mission``).

    Resolution order matches :func:`parameter_ref`: compiled root artifact when available; while the
    root is compiling, the first segment is read from the active definition context and nested
    segments from **compiled** requirement-block artifacts (blocks are compiled eagerly when
    registered via :meth:`ModelDefinitionContext.requirement_block`).

    Use from nested ``Part.define()`` to reference requirements on an ancestor ``System`` without
    dot access from a :class:`~tg_model.model.refs.PartRef`.
    """
    if not path:
        raise ModelDefinitionError("requirement_ref: path must be non-empty")

    def _from_compiled(
        owner: type,
        suffix_path: tuple[str, ...],
        current: dict[str, Any],
        *,
        original_path: tuple[str, ...],
    ) -> Ref:
        tr: dict[str, type] = current.get("_type_registry", {})
        for i, segment in enumerate(suffix_path):
            nodes = current.get("nodes", {})
            node = nodes.get(segment)
            if node is None:
                raise ModelDefinitionError(
                    f"requirement_ref({owner.__name__}, {original_path!r}): no node {segment!r} "
                    f"at suffix index {i}"
                )
            kind = node.get("kind")
            meta = dict(node.get("metadata", {}))
            is_last = i == len(suffix_path) - 1
            if is_last:
                if kind != "requirement":
                    raise ModelDefinitionError(
                        f"requirement_ref({owner.__name__}, {original_path!r}): terminal kind must "
                        f"be 'requirement', got {kind!r}"
                    )
                return Ref(
                    owner_type=owner,
                    path=original_path,
                    kind="requirement",
                    metadata=meta,
                )
            if kind != "requirement_block":
                raise ModelDefinitionError(
                    f"requirement_ref({owner.__name__}, {original_path!r}): intermediate segment "
                    f"{segment!r} must be requirement_block, got {kind!r}"
                )
            bt = tr.get(segment)
            if bt is None:
                raise ModelDefinitionError(
                    f"requirement_ref({owner.__name__}, {original_path!r}): missing target_type "
                    f"for block {segment!r}"
                )
            from tg_model.model.compile_types import _requirement_block_compiled_artifact

            current = _requirement_block_compiled_artifact(bt)
            tr = current.get("_type_registry", {})
        raise ModelDefinitionError(
            f"requirement_ref({owner.__name__}, {original_path!r}): unreachable"
        )

    compiled_root = getattr(root_block_type, "_compiled_definition", None)
    if compiled_root is not None:
        return _from_compiled(root_block_type, path, compiled_root, original_path=path)

    active = getattr(root_block_type, "_tg_definition_context", None)
    if active is None:
        raise ModelDefinitionError(
            f"requirement_ref({root_block_type.__name__}, {path!r}): type is not compiling and "
            f"not compiled."
        )
    first = path[0]
    decl = active.nodes.get(first)
    if decl is None:
        raise ModelDefinitionError(
            f"requirement_ref({root_block_type.__name__}, {path!r}): no declaration {first!r} "
            f"on the root (declare requirement blocks before parts that use requirement_ref)."
        )
    if len(path) == 1:
        if decl.kind != "requirement":
            raise ModelDefinitionError(
                f"requirement_ref({root_block_type.__name__}, {path!r}): expected kind 'requirement', "
                f"got {decl.kind!r}"
            )
        return Ref(
            owner_type=root_block_type,
            path=path,
            kind="requirement",
            metadata=dict(decl.metadata),
        )
    if decl.kind != "requirement_block" or decl.target_type is None:
        raise ModelDefinitionError(
            f"requirement_ref({root_block_type.__name__}, {path!r}): first segment must be "
            f"requirement_block with target_type for a multi-segment path"
        )
    from tg_model.model.compile_types import _requirement_block_compiled_artifact

    inner = _requirement_block_compiled_artifact(decl.target_type)
    return _from_compiled(root_block_type, path[1:], inner, original_path=path)


@dataclass(frozen=True)
class NodeDecl:
    """One declared node in a type definition."""

    name: str
    kind: str
    target_type: type | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelDefinitionContext:
    """Records declarations during ``define(cls, model)`` and compiles them.

    This is the ``model`` object. It is framework-controlled and
    constrained to definition-time recording only.

    All declaration names (parts, ports, parameters, states, events, actions,
    scenarios, …) share one namespace per owner type; duplicate local names raise
    :class:`ModelDefinitionError`.

    For :class:`~tg_model.model.elements.RequirementBlock`, ``symbol_owner`` and
    ``symbol_path_prefix`` thread the **configured root** type and path prefix so
    :meth:`requirement_input` registers :class:`~tg_model.model.refs.AttributeRef`
    symbols that the graph compiler can resolve after :func:`allocate` bindings.
    """

    def __init__(
        self,
        owner_type: type,
        *,
        symbol_owner: type | None = None,
        symbol_path_prefix: tuple[str, ...] = (),
    ) -> None:
        self.owner_type = owner_type
        self.symbol_owner = symbol_owner if symbol_owner is not None else owner_type
        self.symbol_path_prefix = symbol_path_prefix
        self.nodes: dict[str, NodeDecl] = {}
        self.edges: list[dict[str, Any]] = []
        self.behavior_transitions: list[dict[str, Any]] = []
        self._frozen = False

    def _check_frozen(self) -> None:
        if self._frozen:
            raise ModelDefinitionError("Cannot mutate model after define() phase is complete.")

    def _register_node(
        self,
        *,
        name: str,
        kind: str,
        target_type: type | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NodeDecl:
        self._check_frozen()
        if name in self.nodes:
            raise ModelDefinitionError(
                f"Duplicate declaration '{name}' in {self.owner_type.__name__}"
            )
        decl = NodeDecl(name=name, kind=kind, target_type=target_type, metadata=metadata or {})
        self.nodes[name] = decl
        return decl

    @overload
    def part(self) -> PartRef: ...

    @overload
    def part(self, name: str, part_type: type) -> PartRef: ...

    def part(self, name: str | None = None, part_type: type | None = None) -> PartRef:
        """Declare a child part, or return a ref to **this** block as the configured root.

        **No arguments** — does **not** register a child. Returns a :class:`~tg_model.model.refs.PartRef` to
        **this** block: the **parent** you are defining in ``define()``. All other ``model.part(name, Type)``
        calls in the same ``define()`` become **children** of that parent at
        :func:`~tg_model.execution.configured_model.instantiate` time (same root ``PartInstance`` owns them).
        Typical pattern::

            rocket = model.part()  # parent / configured root
            tank = model.part("tank", TankType)  # child of rocket
            model.allocate(req, rocket)

        **Two arguments** — register a composed **child** part (``name``, ``part_type``) and return its ref.
        """
        if name is None and part_type is None:
            return self.root_block()
        if name is None or part_type is None:
            raise ModelDefinitionError(
                "part() takes no arguments (ref to this root block) or both name and part_type (child part)."
            )
        self._register_node(name=name, kind="part", target_type=part_type)
        return PartRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="part",
            target_type=part_type,
        )

    def root_block(self) -> PartRef:
        """Ref to **this** system/part when it is the configured root.

        Same as ``model.part()`` with no arguments. Prefer **`model.part()`** when you want
        one API for both ``rocket = model.part()`` and ``model.part(\"motor\", Motor)``.
        """
        return PartRef(
            owner_type=self.owner_type,
            path=(),
            kind="part",
            target_type=self.owner_type,
        )

    def owner_part(self) -> PartRef:
        """Alias of :meth:`root_block`."""
        return self.root_block()

    def port(self, name: str, direction: str, **metadata: Any) -> PortRef:
        """Declare a port."""
        meta = {"direction": direction, **metadata}
        self._register_node(name=name, kind="port", metadata=meta)
        return PortRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="port",
            metadata=meta,
        )

    def attribute(
        self,
        name: str,
        *,
        expr: Any | None = None,
        computed_by: Any | None = None,
        **metadata: Any,
    ) -> AttributeRef:
        """Declare an attribute, optionally with a derived expression or external computation.

        **Chaining ``ref + ref + ref``:** Python parses ``a + b + c`` as ``(a + b) + c``. The first sum
        yields a unitflow :class:`~unitflow.expr.expressions.Expr`; the outer ``+ c`` then fails to
        combine with a bare :class:`~tg_model.model.refs.AttributeRef`. Use parentheses ``a + (b + c)``,
        use ``a.sym + b.sym + …``, or use :func:`~tg_model.model.expr.sum_attributes`.
        """
        meta = {**metadata}
        if expr is not None:
            meta["_expr"] = expr
        if computed_by is not None:
            meta["_computed_by"] = computed_by
        self._register_node(name=name, kind="attribute", metadata=meta)
        return AttributeRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="attribute",
            metadata=meta,
        )

    def parameter(self, name: str, **metadata: Any) -> AttributeRef:
        """Declare an externally bindable parameter."""
        self._register_node(name=name, kind="parameter", metadata=metadata)
        return AttributeRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="parameter",
            metadata=metadata,
        )

    def parameter_ref(self, root_block_type: type, name: str) -> AttributeRef:
        """Shorthand for :func:`parameter_ref` (same semantics)."""
        return parameter_ref(root_block_type, name)

    def requirement_ref(self, root_block_type: type, path: tuple[str, ...]) -> Ref:
        """Shorthand for :func:`requirement_ref` (same semantics)."""
        return requirement_ref(root_block_type, path)

    def citation(self, name: str, **metadata: Any) -> Ref:
        """Declare an external provenance node (standards, reports, URIs, clauses).

        Link other declarations with :meth:`references`. Phase 8: authoring + compile + export;
        no evaluator participation in v0.
        """
        self._register_node(name=name, kind="citation", metadata=dict(metadata))
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="citation",
            metadata=dict(metadata),
        )

    def requirement(self, name: str, text: str, *, expr: Any | None = None, **metadata: Any) -> Ref:
        """Declare a requirement.

        Optional ``expr`` is an executable acceptance criterion (same expression family as
        :meth:`constraint`): symbols must resolve under the :meth:`allocate` target part subtree
        at graph-compile time. A requirement with ``expr`` must have at least one ``allocate``
        edge from it (Phase 7).

        Prefer :meth:`requirement_input` plus :meth:`requirement_accept_expr` inside
        :class:`~tg_model.model.elements.RequirementBlock` ``define()`` so acceptance uses
        requirement-local symbols bound with :meth:`allocate` ``inputs=`` (no part refs in the
        block).
        """
        meta = {"text": text, **metadata}
        if expr is not None:
            meta["_accept_expr"] = expr
        self._register_node(name=name, kind="requirement", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="requirement",
            metadata=meta,
        )

    def requirement_input(self, requirement: Ref, name: str, **metadata: Any) -> AttributeRef:
        """Declare an input slot on ``requirement`` (RequirementBlock authoring only).

        Registers a value-bearing symbol under the configured root (see threaded
        ``symbol_owner`` / ``symbol_path_prefix`` during compile). Bind each input to a part
        parameter or attribute with :meth:`allocate` ``inputs={name: part_ref.…}``.
        """
        from tg_model.model.elements import RequirementBlock

        if not issubclass(self.owner_type, RequirementBlock):
            raise ModelDefinitionError(
                "requirement_input(...) is only valid inside RequirementBlock.define()"
            )
        if requirement.kind != "requirement" or requirement.owner_type is not self.owner_type:
            raise ModelDefinitionError(
                "requirement_input: first argument must be a requirement Ref from this block"
            )
        req_key = requirement.path[-1]
        req_decl = self.nodes.get(req_key)
        if req_decl is None or req_decl.kind != "requirement":
            raise ModelDefinitionError(
                f"requirement_input: no requirement {req_key!r} in this block (declare it first)"
            )
        if req_decl.metadata.get("_accept_expr") is not None:
            raise ModelDefinitionError(
                f"requirement_input({name!r}): requirement {req_key!r} already has acceptance expr"
            )
        internal = f"{req_key}__in__{name}"
        if internal in self.nodes:
            raise ModelDefinitionError(f"Duplicate requirement_input {name!r} for {req_key!r}")
        self._register_node(
            name=internal,
            kind="requirement_input",
            metadata={**metadata, "_requirement_key": req_key, "_input_name": name},
        )
        names = req_decl.metadata.setdefault("_requirement_input_names", [])
        if name in names:
            raise ModelDefinitionError(f"Duplicate requirement_input {name!r} on {req_key!r}")
        names.append(name)
        sym_path = self.symbol_path_prefix + requirement.path + (name,)
        return AttributeRef(
            owner_type=self.symbol_owner,
            path=sym_path,
            kind="parameter",
            metadata=dict(metadata),
        )

    def requirement_accept_expr(self, requirement: Ref, *, expr: Any) -> None:
        """Set executable acceptance for ``requirement`` (after :meth:`requirement_input` calls)."""
        from tg_model.model.elements import RequirementBlock

        if not issubclass(self.owner_type, RequirementBlock):
            raise ModelDefinitionError(
                "requirement_accept_expr(...) is only valid inside RequirementBlock.define()"
            )
        if requirement.kind != "requirement" or requirement.owner_type is not self.owner_type:
            raise ModelDefinitionError(
                "requirement_accept_expr: first argument must be a requirement Ref from this block"
            )
        if len(requirement.path) != 1:
            raise ModelDefinitionError(
                "requirement_accept_expr: only single-segment requirement paths are supported here"
            )
        key = requirement.path[0]
        decl = self.nodes.get(key)
        if decl is None or decl.kind != "requirement":
            raise ModelDefinitionError(f"requirement_accept_expr: no requirement {key!r}")
        if decl.metadata.get("_accept_expr") is not None:
            raise ModelDefinitionError(
                f"requirement_accept_expr: requirement {key!r} already has acceptance (use one of "
                f"requirement(..., expr=) or requirement_accept_expr)"
            )
        decl.metadata["_accept_expr"] = expr

    def requirement_block(self, name: str, block_type: type) -> RequirementBlockRef:
        """Declare a nested requirements subtree (see :class:`~tg_model.model.elements.RequirementBlock`).

        Compiles ``block_type`` eagerly so nested :func:`requirement_ref` works from sibling
        declarations in the same ``define()``.
        """
        from tg_model.model.compile_types import compile_type
        from tg_model.model.elements import RequirementBlock

        if not issubclass(block_type, RequirementBlock):
            raise ModelDefinitionError(
                f"requirement_block({name!r}, ...): {block_type!r} must be a subclass of RequirementBlock"
            )
        self._register_node(name=name, kind="requirement_block", target_type=block_type)
        compile_type(
            block_type,
            symbol_anchor_type=self.symbol_owner,
            symbol_path_prefix=self.symbol_path_prefix + (name,),
        )
        return RequirementBlockRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="requirement_block",
            target_type=block_type,
        )

    def constraint(self, name: str, *, expr: Any, **metadata: Any) -> Ref:
        """Declare a constraint (validity check over realized values)."""
        meta = {"_expr": expr, **metadata}
        self._register_node(name=name, kind="constraint", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="constraint",
            metadata=meta,
        )

    def state(self, name: str, *, initial: bool = False, **metadata: Any) -> Ref:
        """Declare a discrete behavioral state (Phase 6)."""
        meta = {"initial": initial, **metadata}
        self._register_node(name=name, kind="state", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="state",
            metadata=meta,
        )

    def event(self, name: str, **metadata: Any) -> Ref:
        """Declare a discrete behavioral event (Phase 6)."""
        self._register_node(name=name, kind="event", metadata=metadata)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="event",
            metadata=metadata,
        )

    def action(self, name: str, *, effect: Any | None = None, **metadata: Any) -> Ref:
        """Declare a named action; optional ``effect`` is ``(RunContext, PartInstance) -> None``."""
        meta = {**metadata}
        if effect is not None:
            meta["_effect"] = effect
        self._register_node(name=name, kind="action", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="action",
            metadata=meta,
        )

    def guard(self, name: str, *, predicate: Any, **metadata: Any) -> Ref:
        """Declare a first-class guard: ``predicate`` is ``(RunContext, PartInstance) -> bool``."""
        meta = {"_predicate": predicate, **metadata}
        self._register_node(name=name, kind="guard", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="guard",
            metadata=meta,
        )

    def merge(self, name: str, *, then_action: str | None = None, **metadata: Any) -> Ref:
        """Declare a merge: optional ``then_action`` runs at :func:`~tg_model.execution.behavior.dispatch_merge`.

        When a :meth:`decision` uses ``merge_point=`` to this merge, :func:`~tg_model.execution.behavior.dispatch_decision`
        runs the merge continuation automatically (do not also call ``dispatch_merge`` for that path).
        """
        meta = {**metadata}
        if then_action is not None:
            meta["_merge_then"] = then_action
        self._register_node(name=name, kind="merge", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="merge",
            metadata=meta,
        )

    def item_kind(self, name: str, **metadata: Any) -> Ref:
        """Declare a named kind of item that may flow across connections (see ``emit_item``)."""
        self._register_node(name=name, kind="item_kind", metadata=dict(metadata))
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="item_kind",
            metadata=dict(metadata),
        )

    def decision(
        self,
        name: str,
        *,
        branches: list[tuple[Ref | None, str]],
        default_action: str | None = None,
        merge_point: Ref | None = None,
        **metadata: Any,
    ) -> Ref:
        """Declare exclusive branches: first branch whose guard passes runs its action name.

        Each branch is ``(guard_ref | None, action_name)``. ``None`` guard means unconditional
        (typically one default branch). ``default_action`` runs when no branch matches.

        Optional ``merge_point`` names a :meth:`merge` node; :func:`~tg_model.execution.behavior.dispatch_decision`
        then runs that merge's continuation after the chosen branch (compile-time pairing).
        """
        self._check_frozen()
        normalized: list[tuple[Ref | None, str]] = []
        for tup in branches:
            if len(tup) != 2:
                raise ModelDefinitionError("decision branch must be (guard_ref | None, action_name)")
            gref, aname = tup
            if gref is not None:
                if gref.kind != "guard":
                    raise ModelDefinitionError(
                        f"decision branch guard must be guard ref, got {gref.kind!r}"
                    )
                if gref.owner_type is not self.owner_type:
                    raise ModelDefinitionError("decision guard must belong to this part type")
            if not isinstance(aname, str):
                raise ModelDefinitionError("decision branch action name must be str")
            normalized.append((gref, aname))
        meta = {
            "_decision_branches": normalized,
            "_default_action": default_action,
            **metadata,
        }
        if merge_point is not None:
            if merge_point.kind != "merge":
                raise ModelDefinitionError("decision merge_point= must be a merge ref")
            if merge_point.owner_type is not self.owner_type:
                raise ModelDefinitionError("decision merge_point must belong to this part type")
            meta["_decision_merge"] = merge_point.path[-1]
        self._register_node(name=name, kind="decision", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="decision",
            metadata=meta,
        )

    def fork_join(
        self,
        name: str,
        *,
        branches: list[list[str]],
        then_action: str | None = None,
        **metadata: Any,
    ) -> Ref:
        """Declare a fork/join block: each inner list is one branch (action names in order).

        At runtime, branches execute in list order (deterministic v0). After all branches,
        ``then_action`` runs if set. See :func:`~tg_model.execution.behavior.dispatch_fork_join`.
        """
        self._check_frozen()
        if not branches or not all(isinstance(b, list) for b in branches):
            raise ModelDefinitionError("fork_join requires non-empty list of branch action lists")
        meta = {
            "_fj_branches": branches,
            "_fj_then": then_action,
            **metadata,
        }
        self._register_node(name=name, kind="fork_join", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="fork_join",
            metadata=meta,
        )

    def sequence(self, name: str, *, steps: list[str], **metadata: Any) -> Ref:
        """Declare a linear sequence of action names (intra-part activity graph; methodology default path)."""
        self._check_frozen()
        if not steps or not all(isinstance(s, str) for s in steps):
            raise ModelDefinitionError("sequence requires a non-empty list of action name strings")
        meta = {"_sequence_steps": list(steps), **metadata}
        self._register_node(name=name, kind="sequence", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="sequence",
            metadata=meta,
        )

    def transition(
        self,
        from_state: Ref,
        to_state: Ref,
        on: Ref,
        *,
        when: Any | None = None,
        guard: Ref | None = None,
        effect: str | None = None,
    ) -> None:
        """Declare a state transition on an event, optional guard and named action effect.

        Use either inline ``when=`` **or** first-class ``guard=`` ref, not both.
        """
        self._check_frozen()
        if when is not None and guard is not None:
            raise ModelDefinitionError("transition(): use only one of when= or guard=")
        if guard is not None:
            if guard.kind != "guard":
                raise ModelDefinitionError(f"transition guard= must be a guard ref, got {guard.kind!r}")
            if guard.owner_type is not self.owner_type:
                raise ModelDefinitionError("transition guard must belong to this part type")
        for r, kind in (
            (from_state, "state"),
            (to_state, "state"),
            (on, "event"),
        ):
            if r.kind != kind:
                raise ModelDefinitionError(
                    f"transition() expects {kind} ref for {kind}, got {r.kind!r} ({r.local_name!r})"
                )
            if r.owner_type is not self.owner_type:
                raise ModelDefinitionError(
                    f"transition() reference {r.local_name!r} must belong to {self.owner_type.__name__}"
                )
        self.behavior_transitions.append({
            "from_state": from_state,
            "to_state": to_state,
            "on": on,
            "when": when,
            "guard_ref": guard,
            "effect": effect,
        })

    def scenario(
        self,
        name: str,
        *,
        expected_event_order: list[Ref],
        initial_behavior_state: str | None = None,
        expected_final_behavior_state: str | None = None,
        expected_interaction_order: list[tuple[str, str]] | None = None,
        expected_item_kind_order: list[str] | None = None,
        **metadata: Any,
    ) -> Ref:
        """Declare an authored scenario: event order and optional state expectations for one part type.

        ``expected_interaction_order`` is a list of ``(relative_part_path, event_name)`` from this
        type's instance root (e.g. ``("snd", "Ping")`` under a system). Validate with
        :func:`~tg_model.execution.behavior.validate_scenario_trace` passing ``root=`` the configured
        root part instance.

        ``expected_item_kind_order`` checks :class:`~tg_model.execution.behavior.ItemFlowStep` kinds
        in trace order (inter-part flows).
        """
        order: list[str] = []
        for r in expected_event_order:
            if r.kind != "event":
                raise ModelDefinitionError(
                    f"scenario expected_event_order must be event refs, got {r.kind!r} for {r.local_name!r}"
                )
            if r.owner_type is not self.owner_type:
                raise ModelDefinitionError(
                    f"scenario event {r.local_name!r} must belong to {self.owner_type.__name__}"
                )
            order.append(r.path[-1])
        iord: list[list[str]] | None = None
        if expected_interaction_order is not None:
            iord = [[a, b] for a, b in expected_interaction_order]
        meta = {
            "_expected_event_order": order,
            "_initial_behavior_state": initial_behavior_state,
            "_expected_final_behavior_state": expected_final_behavior_state,
            **metadata,
        }
        if iord is not None:
            meta["_expected_interaction_order"] = iord
        if expected_item_kind_order is not None:
            meta["_expected_item_kind_order"] = list(expected_item_kind_order)
        self._register_node(name=name, kind="scenario", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="scenario",
            metadata=meta,
        )

    def solve_group(
        self,
        name: str,
        *,
        equations: list[Any],
        unknowns: list[AttributeRef],
        givens: list[AttributeRef],
        **metadata: Any,
    ) -> Ref:
        """Declare an explicit solve group for coupled equations."""
        meta = {
            "_equations": equations,
            "_unknowns": [u.path for u in unknowns],
            "_givens": [g.path for g in givens],
            **metadata,
        }
        self._register_node(name=name, kind="solve_group", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="solve_group",
            metadata=meta,
        )

    def references(self, source: Ref, citation: Ref) -> None:
        """Declare provenance: ``source`` references external ``citation`` (Phase 8).

        ``source`` must be a :class:`~tg_model.model.refs.Ref` to a node declared on this
        type (part, port, parameter, requirement, constraint, …). ``citation`` must be a
        ``kind='citation'`` ref from this type.
        """
        self._check_frozen()
        if citation.kind != "citation":
            raise ModelDefinitionError(
                f"references(): citation must be a citation ref, got kind={citation.kind!r}"
            )
        if source.owner_type is not self.owner_type or citation.owner_type is not self.owner_type:
            raise ModelDefinitionError("references(): source and citation must belong to this type")
        self.edges.append({
            "kind": "references",
            "source": source,
            "target": citation,
        })

    def allocate(
        self,
        requirement_ref: Ref,
        target_ref: Ref,
        *,
        inputs: dict[str, AttributeRef] | None = None,
    ) -> None:
        """Declare an allocation from a requirement to a model element.

        Optional ``inputs`` maps :meth:`requirement_input` names to part parameter/attribute refs
        (same :class:`~tg_model.model.refs.AttributeRef` family as ``constraint``). Required for
        acceptance expressions that only reference requirement input symbols.
        """
        self._check_frozen()
        edge: dict[str, Any] = {
            "kind": "allocate",
            "source": requirement_ref,
            "target": target_ref,
        }
        if inputs:
            for k, v in inputs.items():
                if not isinstance(v, AttributeRef):
                    raise ModelDefinitionError(
                        f"allocate inputs[{k!r}] must be an AttributeRef, got {type(v).__name__}"
                    )
            edge["_allocate_inputs"] = dict(inputs)
        self.edges.append(edge)

    def allocate_to_root(self, requirement_ref: Ref) -> None:
        """Shorthand for ``allocate(requirement, root_block())`` when acceptance is checked on this root."""
        self.allocate(requirement_ref, self.root_block())

    def connect(
        self,
        source: PortRef,
        target: PortRef,
        carrying: str | None = None,
    ) -> None:
        """Declare a structural connection between ports."""
        self._check_frozen()
        if not isinstance(source, PortRef) or source.kind != "port":
            raise ModelDefinitionError(
                f"connect() source must be a PortRef, got {type(source).__name__} with kind '{source.kind}'"
            )
        if not isinstance(target, PortRef) or target.kind != "port":
            raise ModelDefinitionError(
                f"connect() target must be a PortRef, got {type(target).__name__} with kind '{target.kind}'"
            )
        self.edges.append({
            "kind": "connect",
            "source": source,
            "target": target,
            "carrying": carrying,
        })

    def parts(self) -> Any:
        """Return a structural selector for all child parts."""
        return "ALL_PARTS"

    def link_external_routes(
        self,
        binding: Any,
        routes: dict[str, AttributeRef],
    ) -> None:
        """Wire ``output_routes`` on an :class:`~tg_model.integrations.ExternalComputeBinding`.

        Call after declaring attributes so ``AttributeRef`` values exist (Phase 4 affordance).
        """
        from tg_model.integrations.external_compute import (
            ExternalComputeBinding as _ExtBinding,
        )
        from tg_model.integrations.external_compute import (
            link_external_routes as _link_routes,
        )

        if not isinstance(binding, _ExtBinding):
            raise ModelDefinitionError(
                f"link_external_routes expects ExternalComputeBinding, got {type(binding).__name__}"
            )
        _link_routes(binding, routes)

    def freeze(self) -> None:
        """Freeze the context. Called by the compiler after define()."""
        self._frozen = True
