"""Definition-time recording API: the ``model`` argument to ``define(cls, model)``.

:class:`ModelDefinitionContext` is framework-owned; subclasses of
:class:`~tg_model.model.elements.Element` only **record** declarations here.
Compilation (:func:`~tg_model.model.compile_types.compile_type`) consumes these
recorded nodes and edges to produce cached artifacts used by
:func:`~tg_model.execution.configured_model.instantiate` and the dependency graph.

Notes
-----
Duplicate local names, invalid ref kinds, and mutations after :meth:`ModelDefinitionContext.freeze`
raise :class:`ModelDefinitionError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, overload

from tg_model.model.refs import AttributeRef, PartRef, PortRef, Ref, RequirementRef


class ModelDefinitionError(Exception):
    """Raised when a model definition is invalid (duplicate names, wrong ref kind, frozen context)."""


def parameter_ref(root_block_type: type, name: str) -> AttributeRef:
    """Return a reference to a parameter on the configured (or compiling) root type.

    Use inside nested ``define()`` to point at **mission / scenario** parameters on the
    root without globals—e.g. for :class:`~tg_model.integrations.external_compute.ExternalComputeBinding`
    inputs or constraint expressions.

    Parameters
    ----------
    root_block_type : type
        The root ``System`` / ``Part`` subclass that owns the parameter declaration.
    name : str
        Parameter declaration name on ``root_block_type``.

    Returns
    -------
    AttributeRef
        Symbolic ref (``kind='parameter'``) for graph compilation and expressions.

    Raises
    ------
    ModelDefinitionError
        If the node is missing, is not a parameter, or ``root_block_type`` is neither
        compiling nor compiled.

    Notes
    -----
    Resolution order:

    1. If ``root_block_type`` is **fully compiled**, read from the cached artifact.
    2. If **mid-compile**, read from the active definition context; declare parameters
       on the root **before** child ``model.part(...)`` types that call this function.

    See Also
    --------
    ModelDefinitionContext.parameter_ref
    requirement_ref
    """
    meta: dict[str, Any]

    compiled = getattr(root_block_type, "_compiled_definition", None)
    if compiled is not None:
        node = compiled.get("nodes", {}).get(name)
        if node is None:
            raise ModelDefinitionError(f"parameter_ref({root_block_type.__name__}, {name!r}): no such node")
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
                f"parameter_ref({root_block_type.__name__}, {name!r}): expected kind 'parameter', got {decl.kind!r}"
            )
        meta = dict(decl.metadata)

    return AttributeRef(
        owner_type=root_block_type,
        path=(name,),
        kind="parameter",
        metadata=meta,
    )


def requirement_ref(root_block_type: type, path: tuple[str, ...]) -> Ref:
    """Return a :class:`~tg_model.model.refs.Ref` to a requirement under the root type.

    ``path`` is declaration names from the root (e.g. ``("mission", "range")`` for
    requirement ``range`` inside package ``mission``). Use from nested ``Part.define()``
    when dot notation from a :class:`~tg_model.model.refs.PartRef` is not available.

    Parameters
    ----------
    root_block_type : type
        Configured root type owning the requirement subtree.
    path : tuple[str, ...]
        Non-empty path of segments: intermediate steps are **composable requirement packages**
        (internal compiled kind ``requirement_block``); the last segment is a leaf **requirement**.

    Returns
    -------
    Ref
        ``kind='requirement'`` ref with metadata from the compiled declaration.

    Raises
    ------
    ModelDefinitionError
        If ``path`` is empty, a segment is missing, kinds along the path are wrong, or
        the root is neither compiling nor compiled.

    Notes
    -----
    Resolution matches :func:`parameter_ref`: prefer the compiled root artifact; while
    compiling, the first segment comes from the active context and nested segments
    from **compiled** composable-requirement artifacts (eager compile when registering
    via :meth:`ModelDefinitionContext.requirement_package`).

    See Also
    --------
    parameter_ref
    ModelDefinitionContext.requirement_ref
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
                    f"requirement_ref({owner.__name__}, {original_path!r}): no node {segment!r} at suffix index {i}"
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
                    f"{segment!r} must be a composable requirement package (internal kind "
                    f"'requirement_block'), got {kind!r}"
                )
            bt = tr.get(segment)
            if bt is None:
                raise ModelDefinitionError(
                    f"requirement_ref({owner.__name__}, {original_path!r}): missing target_type for package {segment!r}"
                )
            from tg_model.model.compile_types import _requirement_block_compiled_artifact

            current = _requirement_block_compiled_artifact(bt)
            tr = current.get("_type_registry", {})
        raise ModelDefinitionError(f"requirement_ref({owner.__name__}, {original_path!r}): unreachable")

    compiled_root = getattr(root_block_type, "_compiled_definition", None)
    if compiled_root is not None:
        return _from_compiled(root_block_type, path, compiled_root, original_path=path)

    active = getattr(root_block_type, "_tg_definition_context", None)
    if active is None:
        raise ModelDefinitionError(
            f"requirement_ref({root_block_type.__name__}, {path!r}): type is not compiling and not compiled."
        )
    first = path[0]
    decl = active.nodes.get(first)
    if decl is None:
        raise ModelDefinitionError(
            f"requirement_ref({root_block_type.__name__}, {path!r}): no declaration {first!r} "
            f"on the root (declare requirement_package entries before parts that use requirement_ref)."
        )
    if len(path) == 1:
        if decl.kind != "requirement":
            raise ModelDefinitionError(
                f"requirement_ref({root_block_type.__name__}, {path!r}): expected kind 'requirement', got {decl.kind!r}"
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
            f"a composable requirement package (internal kind 'requirement_block') with "
            f"target_type for a multi-segment path"
        )
    from tg_model.model.compile_types import _requirement_block_compiled_artifact

    inner = _requirement_block_compiled_artifact(decl.target_type)
    return _from_compiled(root_block_type, path[1:], inner, original_path=path)


@dataclass(frozen=True)
class NodeDecl:
    """One recorded declaration within a type's definition context.

    Attributes
    ----------
    name : str
        Local declaration name (single namespace per owner type).
    kind : str
        Node kind string (``part``, ``parameter``, ``requirement``, ...).
    target_type : type or None
        Composed type for ``part`` or composable requirement package (internal kind ``requirement_block``).
    metadata : dict
        Kind-specific metadata (expressions, text, behavior hooks, ...).
    """

    name: str
    kind: str
    target_type: type | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelDefinitionContext:
    """Records declarations during ``define(cls, model)`` (the ``model`` argument).

    Framework-controlled: only **recording** is allowed until :meth:`freeze`.
    All declaration names share one namespace per owner type; duplicates raise
    :class:`ModelDefinitionError`.

    For :class:`~tg_model.model.elements.Requirement`, ``symbol_owner`` and
    ``symbol_path_prefix`` thread the configured root type and path prefix so
    :meth:`requirement_input` builds :class:`~tg_model.model.refs.AttributeRef`
    paths the graph compiler resolves after :meth:`allocate` ``inputs=`` bindings.

    Attributes
    ----------
    owner_type : type
        The ``Element`` subclass whose ``define()`` is running.
    symbol_owner : type
        Root type used as ``AttributeRef.owner_type`` for threaded requirement inputs.
    symbol_path_prefix : tuple[str, ...]
        Prefix of requirement-block names under the root (internal threading).
    nodes : dict[str, NodeDecl]
        Declarations keyed by local name.
    edges : list[dict]
        Structural and semantic edges (``connect``, ``allocate``, ``references``, ...).
    behavior_transitions : list[dict]
        Recorded state-machine transitions (Phase 6).
    """

    def __init__(
        self,
        owner_type: type,
        *,
        symbol_owner: type | None = None,
        symbol_path_prefix: tuple[str, ...] = (),
    ) -> None:
        """Create a context for ``owner_type.define(cls, model)``.

        Parameters
        ----------
        owner_type : type
            Class currently being defined.
        symbol_owner : type, optional
            For requirement blocks: root type for input symbol ownership (defaults to ``owner_type``).
        symbol_path_prefix : tuple[str, ...], optional
            Path prefix under the root for nested requirement blocks (framework use).
        """
        self.owner_type = owner_type
        self.symbol_owner = symbol_owner if symbol_owner is not None else owner_type
        self.symbol_path_prefix = symbol_path_prefix
        self.nodes: dict[str, NodeDecl] = {}
        self.edges: list[dict[str, Any]] = []
        self.behavior_transitions: list[dict[str, Any]] = []
        self._frozen = False

    def _check_frozen(self) -> None:
        """Raise :class:`ModelDefinitionError` if :meth:`freeze` already ran."""
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
        """Insert a new node declaration or raise on duplicate name (internal)."""
        self._check_frozen()
        if name in self.nodes:
            raise ModelDefinitionError(f"Duplicate declaration '{name}' in {self.owner_type.__name__}")
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
        **Two arguments** — register a composed **child** part and return its ref.

        Parameters
        ----------
        name : str, optional
            Child part declaration name (required with ``part_type``).
        part_type : type, optional
            Subclass of :class:`~tg_model.model.elements.Part` / :class:`~tg_model.model.elements.System`.

        Returns
        -------
        PartRef
            Root ref (empty path) or child ref.

        Raises
        ------
        ModelDefinitionError
            On wrong arity (only one of ``name`` / ``part_type``), duplicate name, or frozen context.

        Examples
        --------
        Typical root + child pattern::

            rocket = model.part()
            tank = model.part("tank", TankType)
            model.allocate(req, rocket)
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
        """Return a ref to this type as the configured structural root (empty path).

        Returns
        -------
        PartRef
            ``path=()`` and ``target_type=self.owner_type``.

        Notes
        -----
        Same as :meth:`part` with no arguments. Prefer :meth:`part` when mixing root and
        child declarations in one call style.

        See Also
        --------
        part
        owner_part
        """
        return PartRef(
            owner_type=self.owner_type,
            path=(),
            kind="part",
            target_type=self.owner_type,
        )

    def owner_part(self) -> PartRef:
        """Alias of :meth:`root_block` (historical name).

        Returns
        -------
        PartRef
            Same as :meth:`root_block`.
        """
        return self.root_block()

    def port(self, name: str, direction: str, **metadata: Any) -> PortRef:
        """Declare a structural port on this part or system.

        Parameters
        ----------
        name : str
            Local port name (unique in this type's node namespace).
        direction : str
            Flow direction label (e.g. ``in``, ``out``, ``inout`` — project convention).
        **metadata
            Additional port metadata stored on the compiled node.

        Returns
        -------
        PortRef
            Reference for use in :meth:`connect`.

        Raises
        ------
        ModelDefinitionError
            On duplicate ``name`` or if the context is frozen.
        """
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
        """Declare an attribute (bindable/computed value slot).

        Parameters
        ----------
        name : str
            Local attribute name.
        expr
            Optional unitflow expression or :class:`~tg_model.model.declarations.values.RollupDecl`
            for derived values.
        computed_by
            Optional :class:`~tg_model.integrations.external_compute.ExternalComputeBinding`
            for external computation.
        **metadata
            Must include ``unit=`` (and any other declaration metadata) for symbol construction.

        Returns
        -------
        AttributeRef
            Reference for constraints, expressions, and graph compilation.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.

        Notes
        -----
        **Chaining** ``a + b + c`` is left-associative; use ``a + (b + c)``, ``.sym``, or
        :func:`~tg_model.model.expr.sum_attributes` to avoid mixed ``Expr`` / ``AttributeRef`` errors.
        """
        meta = {**metadata}
        if expr is not None:
            meta["_expr"] = expr
        if computed_by is not None:
            meta["_computed_by"] = computed_by
        self._register_node(name=name, kind="attribute", metadata=meta)
        return self._value_ref_for_current_owner(name, "attribute", meta)

    def parameter(self, name: str, **metadata: Any) -> AttributeRef:
        """Declare an externally bindable parameter (input slot at evaluation time).

        Parameters
        ----------
        name : str
            Local parameter name.
        **metadata
            Typically includes ``unit=`` for quantity inputs.

        Returns
        -------
        AttributeRef
            ``kind='parameter'`` reference.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.
        """
        self._register_node(name=name, kind="parameter", metadata=metadata)
        return self._value_ref_for_current_owner(name, "parameter", dict(metadata))

    def _value_ref_for_current_owner(
        self,
        name: str,
        kind: str,
        metadata: dict[str, Any],
    ) -> AttributeRef:
        """AttributeRef for ``parameter`` / ``attribute``: threaded under root when in a package."""
        from tg_model.model.elements import Requirement

        if issubclass(self.owner_type, Requirement):
            path = (*self.symbol_path_prefix, name)
            return AttributeRef(
                owner_type=self.symbol_owner,
                path=path,
                kind=kind,
                metadata=metadata,
            )
        return AttributeRef(
            owner_type=self.owner_type,
            path=(name,),
            kind=kind,
            metadata=metadata,
        )

    def parameter_ref(self, root_block_type: type, name: str) -> AttributeRef:
        """Call :func:`parameter_ref` (same resolution rules and errors)."""
        return parameter_ref(root_block_type, name)

    def requirement_ref(self, root_block_type: type, path: tuple[str, ...]) -> Ref:
        """Call :func:`requirement_ref` (same resolution rules and errors)."""
        return requirement_ref(root_block_type, path)

    def citation(self, name: str, **metadata: Any) -> Ref:
        """Declare an external provenance node (standards, reports, URIs, clauses).

        Parameters
        ----------
        name : str
            Citation node name.
        **metadata
            Free-form citation fields (URI, clause id, revision, …).

        Returns
        -------
        Ref
            ``kind='citation'`` for :meth:`references` edges.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.

        Notes
        -----
        v0 does not execute citations in the evaluator; they support export and traceability hooks.
        """
        self._register_node(name=name, kind="citation", metadata=dict(metadata))
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="citation",
            metadata=dict(metadata),
        )

    def requirement(self, name: str, text: str, *, expr: Any | None = None, **metadata: Any) -> Ref:
        """Declare a requirement (human ``text`` plus optional executable acceptance).

        Parameters
        ----------
        name : str
            Requirement node name.
        text : str
            Human-readable statement (not evaluated).
        expr
            Optional boolean acceptance expression (same family as :meth:`constraint`).
        **metadata
            Additional requirement metadata.

        Returns
        -------
        Ref
            ``kind='requirement'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.

        Notes
        -----
        With ``expr=``, symbols must resolve against the :meth:`allocate` target subtree at compile
        time, and an ``allocate`` edge must exist. Prefer :meth:`requirement_input` and
        :meth:`requirement_accept_expr` inside :class:`~tg_model.model.elements.Requirement`
        when acceptance should use only requirement-local inputs bound via ``allocate(..., inputs=)``.
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
        """Declare an input slot on ``requirement`` (composable :class:`~tg_model.model.elements.Requirement` only).

        Registers a value-bearing symbol under the configured root (threaded
        ``symbol_owner`` / ``symbol_path_prefix``). Bind each input with
        :meth:`allocate` ``inputs={name: part_ref.…}``.

        Parameters
        ----------
        requirement : Ref
            ``kind='requirement'`` ref declared in this block.
        name : str
            Input slot name (referenced in acceptance expressions).
        **metadata
            Forwarded to the internal parameter declaration (e.g. ``unit=``).

        Returns
        -------
        AttributeRef
            Symbol for use in :meth:`requirement_accept_expr` (``kind='parameter'`` on ``symbol_owner``).

        Raises
        ------
        ModelDefinitionError
            If not inside a requirement block, ``requirement`` is wrong, inputs conflict with
            ``requirement(..., expr=)``, or names duplicate.
        """
        from tg_model.model.elements import Requirement

        if not issubclass(self.owner_type, Requirement):
            raise ModelDefinitionError("requirement_input(...) is only valid inside Requirement.define()")
        if requirement.kind != "requirement" or requirement.owner_type is not self.owner_type:
            raise ModelDefinitionError("requirement_input: first argument must be a requirement Ref from this package")
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
        attr_names = req_decl.metadata.get("_requirement_attribute_names") or []
        if name in attr_names:
            raise ModelDefinitionError(
                f"requirement_input({name!r}): name clashes with requirement_attribute on {req_key!r}"
            )
        names.append(name)
        sym_path = self.symbol_path_prefix + requirement.path + (name,)
        return AttributeRef(
            owner_type=self.symbol_owner,
            path=sym_path,
            kind="parameter",
            metadata=dict(metadata),
        )

    def requirement_attribute(
        self,
        requirement: Ref,
        name: str,
        *,
        expr: Any,
        **metadata: Any,
    ) -> AttributeRef:
        """Declare a derived value on ``requirement`` (composable :class:`~tg_model.model.elements.Requirement` only).

        Registers a requirement-local **attribute** whose value is computed from an
        expression (typically over :meth:`requirement_input` symbols, other
        ``requirement_attribute`` symbols declared earlier in the same ``define()``,
        and root parameters). Use ``unit=`` in ``metadata`` so :attr:`AttributeRef.sym`
        can be built.

        Unlike :meth:`requirement_input`, attributes are **not** wired via
        :meth:`allocate` ``inputs=``; they are evaluated from their ``expr=`` and
        materialized as value slots on the configured root for graph compilation.

        Parameters
        ----------
        requirement : Ref
            ``kind='requirement'`` ref declared in this block.
        name : str
            Attribute name (must not collide with a ``requirement_input`` name on the
            same requirement).
        expr
            Scalar expression (same family as :meth:`attribute` ``expr=``).
        **metadata
            Must include ``unit=`` (and any other declaration metadata).

        Returns
        -------
        AttributeRef
            ``kind='attribute'`` symbol for use in :meth:`requirement_accept_expr` or
            in later ``requirement_attribute`` calls.

        Raises
        ------
        ModelDefinitionError
            If not in a block, ``requirement`` is wrong, names collide, ``expr`` is
            missing, or acceptance was already set via ``requirement_accept_expr``.
        """
        from tg_model.model.elements import Requirement

        if not issubclass(self.owner_type, Requirement):
            raise ModelDefinitionError("requirement_attribute(...) is only valid inside Requirement.define()")
        if requirement.kind != "requirement" or requirement.owner_type is not self.owner_type:
            raise ModelDefinitionError(
                "requirement_attribute: first argument must be a requirement Ref from this package"
            )
        req_key = requirement.path[-1]
        req_decl = self.nodes.get(req_key)
        if req_decl is None or req_decl.kind != "requirement":
            raise ModelDefinitionError(
                f"requirement_attribute: no requirement {req_key!r} in this block (declare it first)"
            )
        if req_decl.metadata.get("_accept_expr") is not None:
            raise ModelDefinitionError(
                f"requirement_attribute({name!r}): requirement {req_key!r} already has acceptance expr"
            )
        inames = req_decl.metadata.get("_requirement_input_names") or []
        if name in inames:
            raise ModelDefinitionError(
                f"requirement_attribute({name!r}): name clashes with requirement_input on {req_key!r}"
            )
        internal = f"{req_key}__attr__{name}"
        if internal in self.nodes:
            raise ModelDefinitionError(f"Duplicate requirement_attribute {name!r} for {req_key!r}")
        meta = dict(metadata)
        meta["_expr"] = expr
        meta["_requirement_key"] = req_key
        meta["_attr_name"] = name
        self._register_node(
            name=internal,
            kind="requirement_attribute",
            metadata=meta,
        )
        anames = req_decl.metadata.setdefault("_requirement_attribute_names", [])
        if name in anames:
            raise ModelDefinitionError(f"Duplicate requirement_attribute {name!r} on {req_key!r}")
        anames.append(name)
        decls = req_decl.metadata.setdefault("_requirement_attributes", [])
        decls.append((name, expr))
        sym_path = self.symbol_path_prefix + requirement.path + (name,)
        return AttributeRef(
            owner_type=self.symbol_owner,
            path=sym_path,
            kind="attribute",
            metadata=dict(metadata),
        )

    def requirement_accept_expr(self, requirement: Ref, *, expr: Any) -> None:
        """Set executable acceptance for ``requirement`` (after :meth:`requirement_input` calls).

        Parameters
        ----------
        requirement : Ref
            Requirement ref from this block (single-segment path only).
        expr
            Boolean expression over requirement input symbols (and unitflow quantities).

        Raises
        ------
        ModelDefinitionError
            If not in a block, ref is invalid, path is not a single segment, or acceptance
            was already set via ``requirement(..., expr=)`` or a prior call.
        """
        from tg_model.model.elements import Requirement

        if not issubclass(self.owner_type, Requirement):
            raise ModelDefinitionError("requirement_accept_expr(...) is only valid inside Requirement.define()")
        if requirement.kind != "requirement" or requirement.owner_type is not self.owner_type:
            raise ModelDefinitionError(
                "requirement_accept_expr: first argument must be a requirement Ref from this package"
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

    def requirement_package(self, name: str, package_type: type) -> RequirementRef:
        """Declare a nested composable requirements package (:class:`~tg_model.model.elements.Requirement`).

        Parameters
        ----------
        name : str
            Package name in this owner's namespace.
        package_type : type
            Subclass of :class:`~tg_model.model.elements.Requirement`.

        Returns
        -------
        RequirementRef
            Dot-access ref to nested requirements.

        Raises
        ------
        ModelDefinitionError
            If ``package_type`` is not a composable requirement, on duplicate name, or frozen context.

        Notes
        -----
        Compiles ``package_type`` eagerly so :func:`requirement_ref` and sibling dot access work
        within the same ``define()`` call. The internal node kind remains ``requirement_block`` for
        artifact compatibility.

        Inside ``package_type.define()``, package-level :meth:`parameter`, :meth:`attribute`, and
        :meth:`constraint` are allowed when :class:`~tg_model.model.elements.Requirement` compile
        policy permits them.
        """
        from tg_model.model.compile_types import compile_type
        from tg_model.model.elements import Requirement

        if not issubclass(package_type, Requirement):
            raise ModelDefinitionError(
                f"requirement_package({name!r}, ...): {package_type!r} must be a subclass of Requirement"
            )
        self._register_node(name=name, kind="requirement_block", target_type=package_type)
        compile_type(
            package_type,
            symbol_anchor_type=self.symbol_owner,
            symbol_path_prefix=(*self.symbol_path_prefix, name),
        )
        return RequirementRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="requirement_block",
            target_type=package_type,
        )

    def constraint(self, name: str, *, expr: Any, **metadata: Any) -> Ref:
        """Declare a constraint (boolean check over realized slot values).

        Parameters
        ----------
        name : str
            Constraint name (appears in :class:`~tg_model.execution.run_context.ConstraintResult`).
        expr
            Boolean expression over :class:`~tg_model.model.refs.AttributeRef` / unitflow symbols.
        **metadata
            Extra metadata attached to the compiled node.

        Returns
        -------
        Ref
            ``kind='constraint'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.
        """
        meta = {"_expr": expr, **metadata}
        self._register_node(name=name, kind="constraint", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="constraint",
            metadata=meta,
        )

    def state(self, name: str, *, initial: bool = False, **metadata: Any) -> Ref:
        """Declare a discrete behavioral state (state machine vertex).

        Parameters
        ----------
        name : str
            State name (used in :meth:`transition` and runtime state string).
        initial : bool, default False
            Mark the initial state for this part type (exactly one should be initial).
        **metadata
            Optional extra state metadata.

        Returns
        -------
        Ref
            ``kind='state'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.
        """
        meta = {"initial": initial, **metadata}
        self._register_node(name=name, kind="state", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="state",
            metadata=meta,
        )

    def event(self, name: str, **metadata: Any) -> Ref:
        """Declare a discrete behavioral event (state machine stimulus).

        Parameters
        ----------
        name : str
            Event name string used with :func:`~tg_model.execution.behavior.dispatch_event`.
        **metadata
            Optional event metadata.

        Returns
        -------
        Ref
            ``kind='event'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.
        """
        self._register_node(name=name, kind="event", metadata=metadata)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="event",
            metadata=metadata,
        )

    def action(self, name: str, *, effect: Any | None = None, **metadata: Any) -> Ref:
        """Declare a named action (callable side effect on a part instance).

        Parameters
        ----------
        name : str
            Action name referenced by transitions, sequences, decisions, etc.
        effect : callable, optional
            ``(RunContext, PartInstance) -> None`` executed under behavior subtree scope.
        **metadata
            Stored on the compiled action node if ``effect`` is omitted (legacy inline hook).

        Returns
        -------
        Ref
            ``kind='action'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.
        """
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
        """Declare a reusable guard for decisions and transitions.

        Parameters
        ----------
        name : str
            Guard name.
        predicate
            ``(RunContext, PartInstance) -> bool`` evaluated under behavior subtree scope.
        **metadata
            Optional metadata.

        Returns
        -------
        Ref
            ``kind='guard'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.
        """
        meta = {"_predicate": predicate, **metadata}
        self._register_node(name=name, kind="guard", metadata=meta)
        return Ref(
            owner_type=self.owner_type,
            path=(name,),
            kind="guard",
            metadata=meta,
        )

    def merge(self, name: str, *, then_action: str | None = None, **metadata: Any) -> Ref:
        """Declare a merge node (shared continuation after branching).

        Parameters
        ----------
        name : str
            Merge node name.
        then_action : str, optional
            Action name to run when :func:`~tg_model.execution.behavior.dispatch_merge` fires.
        **metadata
            Optional metadata.

        Returns
        -------
        Ref
            ``kind='merge'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.

        Notes
        -----
        When :meth:`decision` uses ``merge_point=`` to this merge,
        :func:`~tg_model.execution.behavior.dispatch_decision` runs the continuation automatically;
        do not also call :func:`~tg_model.execution.behavior.dispatch_merge` for that path.
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
        """Declare an item kind label for inter-part flows (:func:`~tg_model.execution.behavior.emit_item`).

        Parameters
        ----------
        name : str
            Kind / event name carried across connections.
        **metadata
            Optional metadata.

        Returns
        -------
        Ref
            ``kind='item_kind'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.
        """
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
        """Declare an exclusive decision (first matching guard wins).

        Parameters
        ----------
        name : str
            Decision node name.
        branches : list[tuple[Ref | None, str]]
            Each entry is ``(guard_ref or None, action_name)``. ``None`` guard is unconditional.
        default_action : str, optional
            Action name when no branch matches.
        merge_point : Ref, optional
            ``kind='merge'`` ref for automatic continuation (see :meth:`merge`).
        **metadata
            Extra metadata.

        Returns
        -------
        Ref
            ``kind='decision'``.

        Raises
        ------
        ModelDefinitionError
            On malformed branches, wrong ref kinds/owners, unknown merge, duplicate name, or frozen context.

        Notes
        -----
        Runtime API: :func:`~tg_model.execution.behavior.dispatch_decision`.
        """
        self._check_frozen()
        normalized: list[tuple[Ref | None, str]] = []
        for tup in branches:
            if len(tup) != 2:
                raise ModelDefinitionError("decision branch must be (guard_ref | None, action_name)")
            gref, aname = tup
            if gref is not None:
                if gref.kind != "guard":
                    raise ModelDefinitionError(f"decision branch guard must be guard ref, got {gref.kind!r}")
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
        """Declare a fork/join activity region (serial branch execution in v0).

        Parameters
        ----------
        name : str
            Block name.
        branches : list[list[str]]
            Each inner list is one branch: action names run in order within the branch.
        then_action : str, optional
            Action name after all branches complete.
        **metadata
            Extra metadata.

        Returns
        -------
        Ref
            ``kind='fork_join'``.

        Raises
        ------
        ModelDefinitionError
            On empty/malformed ``branches``, duplicate name, or frozen context.

        Notes
        -----
        v0 runs branches **serially** in list order; see :func:`~tg_model.execution.behavior.dispatch_fork_join`.
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
        """Declare a linear sequence of action names (in-order execution).

        Parameters
        ----------
        name : str
            Sequence node name.
        steps : list[str]
            Non-empty list of declared action names.
        **metadata
            Extra metadata.

        Returns
        -------
        Ref
            ``kind='sequence'``.

        Raises
        ------
        ModelDefinitionError
            On empty/non-string steps, duplicate name, or frozen context.

        See Also
        --------
        tg_model.execution.behavior.dispatch_sequence
        """
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
        """Record one state-machine transition for this part type.

        Parameters
        ----------
        from_state, to_state : Ref
            ``kind='state'`` refs on this type.
        on : Ref
            ``kind='event'`` ref.
        when : callable, optional
            ``(RunContext, PartInstance) -> bool`` inline guard (mutually exclusive with ``guard=``).
        guard : Ref, optional
            ``kind='guard'`` ref (mutually exclusive with ``when=``).
        effect : str, optional
            Declared action name run after the state advances.

        Raises
        ------
        ModelDefinitionError
            If both ``when`` and ``guard`` are set, refs have wrong kinds/owners, or context is frozen.

        Notes
        -----
        Determinism: at most one transition per ``(from_state, event)`` (checked at compile time).
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
        self.behavior_transitions.append(
            {
                "from_state": from_state,
                "to_state": to_state,
                "on": on,
                "when": when,
                "guard_ref": guard,
                "effect": effect,
            }
        )

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
        """Declare a behavioral scenario contract (partial trace checks).

        Parameters
        ----------
        name : str
            Scenario node name.
        expected_event_order : list[Ref]
            Event refs in expected firing order for the scenario owner type.
        initial_behavior_state : str, optional
            Expected ``from_state`` of the first transition on ``part_path`` under validation.
        expected_final_behavior_state : str, optional
            Expected discrete state after the trace (needs ``ctx`` in validation).
        expected_interaction_order : list[tuple[str, str]], optional
            ``(relative_part_path, event_name)`` pairs from this type's root for global ordering checks.
        expected_item_kind_order : list[str], optional
            Expected :class:`~tg_model.execution.behavior.ItemFlowStep` ``item_kind`` sequence.
        **metadata
            Extra scenario metadata.

        Returns
        -------
        Ref
            ``kind='scenario'``.

        Raises
        ------
        ModelDefinitionError
            If event refs are wrong, duplicate name, or frozen context.

        See Also
        --------
        tg_model.execution.behavior.validate_scenario_trace
        """
        order: list[str] = []
        for r in expected_event_order:
            if r.kind != "event":
                raise ModelDefinitionError(
                    f"scenario expected_event_order must be event refs, got {r.kind!r} for {r.local_name!r}"
                )
            if r.owner_type is not self.owner_type:
                raise ModelDefinitionError(f"scenario event {r.local_name!r} must belong to {self.owner_type.__name__}")
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
        """Declare a coupled equation solve group (requires SciPy at evaluation).

        Parameters
        ----------
        name : str
            Solve group name.
        equations : list
            Scalar expressions (same count as ``unknowns``) compiled to residuals.
        unknowns : list[AttributeRef]
            Attributes to solve for.
        givens : list[AttributeRef]
            Bound inputs to the solver.
        **metadata
            Extra metadata.

        Returns
        -------
        Ref
            ``kind='solve_group'``.

        Raises
        ------
        ModelDefinitionError
            On duplicate name or frozen context.

        Notes
        -----
        Execution uses ``scipy.optimize``; see :mod:`tg_model.execution.solve_groups`.
        """
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
        """Record a provenance edge from ``source`` to ``citation``.

        Parameters
        ----------
        source : Ref
            Any declared node on this type (part, port, parameter, requirement, …).
        citation : Ref
            Must be ``kind='citation'`` on this type.

        Raises
        ------
        ModelDefinitionError
            If kinds/ownership are invalid or context is frozen.
        """
        self._check_frozen()
        if citation.kind != "citation":
            raise ModelDefinitionError(f"references(): citation must be a citation ref, got kind={citation.kind!r}")
        if source.owner_type is not self.owner_type or citation.owner_type is not self.owner_type:
            raise ModelDefinitionError("references(): source and citation must belong to this type")
        self.edges.append(
            {
                "kind": "references",
                "source": source,
                "target": citation,
            }
        )

    def allocate(
        self,
        requirement_ref: Ref,
        target_ref: Ref,
        *,
        inputs: dict[str, AttributeRef] | None = None,
    ) -> None:
        """Declare an allocation from a requirement to a model element.

        Optional ``inputs`` maps :meth:`requirement_input` names to part parameter/attribute refs.
        Required when acceptance uses only requirement-local symbols.

        Parameters
        ----------
        requirement_ref : Ref
            ``kind='requirement'`` ref being allocated.
        target_ref : Ref
            Part or root ref that supplies values for acceptance (per compiler rules).
        inputs : dict[str, AttributeRef], optional
            Maps input name → :class:`~tg_model.model.refs.AttributeRef` on the allocated subtree.

        Raises
        ------
        ModelDefinitionError
            If context is frozen or ``inputs`` values are not :class:`~tg_model.model.refs.AttributeRef`.
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
        """Shorthand for ``allocate(requirement_ref, root_block())``.

        Parameters
        ----------
        requirement_ref : Ref
            Requirement to allocate to this type's structural root.

        Raises
        ------
        ModelDefinitionError
            Same as :meth:`allocate`.
        """
        self.allocate(requirement_ref, self.root_block())

    def connect(
        self,
        source: PortRef,
        target: PortRef,
        carrying: str | None = None,
    ) -> None:
        """Declare a structural connection between two ports.

        Parameters
        ----------
        source, target : PortRef
            Port refs declared on (possibly different) composed types under one configured root.
        carrying : str, optional
            When set, :func:`~tg_model.execution.behavior.emit_item` only uses this binding if
            ``item_kind`` matches.

        Raises
        ------
        ModelDefinitionError
            If either endpoint is not a :class:`~tg_model.model.refs.PortRef`, or context is frozen.
        """
        self._check_frozen()
        if not isinstance(source, PortRef) or source.kind != "port":
            raise ModelDefinitionError(
                f"connect() source must be a PortRef, got {type(source).__name__} with kind '{source.kind}'"
            )
        if not isinstance(target, PortRef) or target.kind != "port":
            raise ModelDefinitionError(
                f"connect() target must be a PortRef, got {type(target).__name__} with kind '{target.kind}'"
            )
        self.edges.append(
            {
                "kind": "connect",
                "source": source,
                "target": target,
                "carrying": carrying,
            }
        )

    def parts(self) -> Any:
        """Return the internal selector token for “all child parts” in roll-up expressions.

        Returns
        -------
        str
            The sentinel ``\"ALL_PARTS\"`` understood by roll-up compilation.

        See Also
        --------
        tg_model.model.declarations.values.RollupBuilder.sum
        """
        return "ALL_PARTS"

    def link_external_routes(
        self,
        binding: Any,
        routes: dict[str, AttributeRef],
    ) -> None:
        """Wire ``output_routes`` on an :class:`~tg_model.integrations.ExternalComputeBinding`.

        Call after declaring attributes so :class:`~tg_model.model.refs.AttributeRef` targets exist.

        Parameters
        ----------
        binding : ExternalComputeBinding
            Binding created for this type.
        routes : dict[str, AttributeRef]
            External output name → attribute slot ref.

        Raises
        ------
        ModelDefinitionError
            If ``binding`` is not an :class:`~tg_model.integrations.external_compute.ExternalComputeBinding`.
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
        """Freeze the context so no further declarations or edges are allowed.

        Notes
        -----
        Invoked by :func:`~tg_model.model.compile_types.compile_type` after ``define`` returns.
        """
        self._frozen = True
