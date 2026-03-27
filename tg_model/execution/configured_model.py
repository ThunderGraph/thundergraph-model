"""Frozen configured topology: :class:`ConfiguredModel` and :func:`instantiate`.

A configured model holds the root :class:`~tg_model.execution.instances.PartInstance`,
registries of handles, structural connections, allocations, and references.

Per-run **values** (slot state for one evaluation) live in
:class:`~tg_model.execution.run_context.RunContext`, not on the model. The model may cache a
compiled dependency graph and handlers (see :meth:`ConfiguredModel.evaluate` and
:func:`~tg_model.execution.graph_compiler.compile_graph`) for reuse; that cache is **not**
per-run scenario data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tg_model.execution.evaluator import RunResult
    from tg_model.execution.run_context import RunContext

from tg_model.execution.connection_bindings import (
    AllocationBinding,
    ConnectionBinding,
    ReferenceBinding,
)
from tg_model.execution.instances import ElementInstance, PartInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.model.compile_types import _requirement_block_compiled_artifact
from tg_model.model.identity import derive_declaration_id


class ConfiguredModel:
    """Immutable configured topology for one root type instance.

    Notes
    -----
    Evaluations use fresh :class:`~tg_model.execution.run_context.RunContext` objects per
    :meth:`evaluate` call; the part tree and registries do not change. A successful compile may
    be cached on this instance (``_compiled_graph``) for reuse.

    **Thread safety:** Do not call :meth:`evaluate` or :func:`~tg_model.execution.graph_compiler.compile_graph`
    concurrently on the **same** instance from multiple threads; the cache is not locked.

    **Copy / pickle:** Caching a compiled graph on the instance means copying or unpickling a
    configured model without clearing ``_compiled_graph`` is **unsupported**; treat cached graphs as
    invalid across process or deep-copy boundaries unless you add an explicit clear or rebuild.

    Attribute access delegates to the root part for ergonomics.
    """

    def __init__(
        self,
        root: PartInstance,
        *,
        path_registry: dict[str, ElementInstance | ValueSlot],
        id_registry: dict[str, ElementInstance | ValueSlot],
        connections: list[ConnectionBinding],
        allocations: list[AllocationBinding],
        references: list[ReferenceBinding],
        requirement_value_slots: list[ValueSlot] | None = None,
    ) -> None:
        """Assemble a frozen topology (call via :func:`instantiate`, not directly).

        Parameters
        ----------
        root : PartInstance
            Configured root part instance.
        path_registry : dict
            Maps dotted path strings to instances or slots.
        id_registry : dict
            Maps ``stable_id`` strings to instances or slots.
        connections : list[ConnectionBinding]
            Structural port connections.
        allocations : list[AllocationBinding]
            Resolved requirement allocations.
        references : list[ReferenceBinding]
            Resolved citation reference edges.
        requirement_value_slots : list[ValueSlot], optional
            Derived :class:`~tg_model.execution.value_slots.ValueSlot` nodes for
            :meth:`tg_model.model.definition_context.ModelDefinitionContext.requirement_attribute`
            declarations (registered in ``path_registry`` / ``id_registry``).
        """
        self.root = root
        self.path_registry = path_registry
        self.id_registry = id_registry
        self.connections = connections
        self.allocations = allocations
        self.references = references
        self.requirement_value_slots = requirement_value_slots or []
        #: Cached ``(DependencyGraph, handlers)`` from ``compile_graph``; lazily set.
        self._compiled_graph: tuple[Any, Any] | None = None

    def handle(self, path: str) -> ElementInstance | ValueSlot:
        """Look up an instance or value slot by dotted path string.

        Parameters
        ----------
        path : str
            Instance path such as ``Rocket.tank.mass_kg``.

        Returns
        -------
        ElementInstance or ValueSlot
            Registered topology object.

        Raises
        ------
        KeyError
            If ``path`` is not in ``path_registry``.
        """
        if path not in self.path_registry:
            raise KeyError(f"No handle found for path '{path}'")
        return self.path_registry[path]

    def evaluate(
        self,
        inputs: dict[Any, Any] | None = None,
        *,
        run_context: RunContext | None = None,
        validate: bool = True,
    ) -> RunResult:
        """Run one synchronous evaluation over the compiled dependency graph.

        Compiles the graph on first use (same cache as :func:`~tg_model.execution.graph_compiler.compile_graph`),
        optionally runs :func:`~tg_model.execution.validation.validate_graph`, then delegates to
        :class:`~tg_model.execution.evaluator.Evaluator`.

        Parameters
        ----------
        inputs : dict, optional
            Per-run values keyed by :class:`~tg_model.execution.value_slots.ValueSlot` handles
            belonging to this model, or by ``str`` giving the
            :attr:`~tg_model.execution.value_slots.ValueSlot.stable_id` of such a slot **only**
            (not arbitrary element or part ids). Values are typically :class:`unitflow.Quantity`
            instances.
        run_context : RunContext, optional
            Fresh context per call by default. Supply only for advanced testing or tooling.
        validate : bool, default True
            When True, runs :func:`~tg_model.execution.validation.validate_graph` before **each**
            evaluation (static checks). For tight loops, sweeps, or optimizers, pass
            ``validate=False`` after you have validated once out-of-band, to avoid repeating that
            work every run. On validation failure, raises :class:`~tg_model.execution.validation.GraphValidationError`.

        Returns
        -------
        RunResult
            Same aggregate type as :meth:`tg_model.execution.evaluator.Evaluator.evaluate`.
            Missing inputs, failed constraints, and other **runtime** issues appear in
            ``failures`` / ``constraint_results`` — not as exceptions from this method.

        Raises
        ------
        GraphCompilationError
            If graph compilation fails (from :func:`~tg_model.execution.graph_compiler.compile_graph`).
        GraphValidationError
            If ``validate`` is True and static validation fails (subclass of :class:`Exception`).
        KeyError
            If a string key is not present in this model's id registry.
        TypeError
            Propagated from the evaluator when an async external is used in sync mode.
        ValueError
            If an input key is a :class:`~tg_model.execution.value_slots.ValueSlot` not registered on
            this model, or a string id that does not refer to a :class:`~tg_model.execution.value_slots.ValueSlot`.

        See Also
        --------
        tg_model.execution.graph_compiler.compile_graph
        tg_model.execution.evaluator.Evaluator
        """
        from tg_model.execution.evaluator import Evaluator
        from tg_model.execution.graph_compiler import compile_graph
        from tg_model.execution.run_context import RunContext as FreshRunContext
        from tg_model.execution.validation import GraphValidationError, validate_graph

        graph, handlers = compile_graph(self)
        if validate:
            val = validate_graph(graph, configured_model=self)
            if not val.passed:
                msg = "; ".join(f"{f.category}: {f.message}" for f in val.failures)
                raise GraphValidationError(
                    f"Graph validation failed: {msg}",
                    result=val,
                )

        ctx = run_context if run_context is not None else FreshRunContext()
        bound = _normalize_evaluate_inputs(self, inputs or {})
        ev = Evaluator(graph, compute_handlers=handlers)
        return ev.evaluate(ctx, inputs=bound)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.root, name)

    def __repr__(self) -> str:
        return (
            f"<ConfiguredModel: {self.root.path_string} "
            f"({len(self.path_registry)} handles, {len(self.connections)} connections, "
            f"{len(self.references)} references)>"
        )


def instantiate(root_type: type) -> ConfiguredModel:
    """Build a :class:`ConfiguredModel` from a compiled root type.

    Walks the compiled definition depth-first, creating
    :class:`~tg_model.execution.instances.PartInstance`,
    :class:`~tg_model.execution.instances.PortInstance`,
    :class:`~tg_model.execution.value_slots.ValueSlot`, connection bindings, and
    allocation bindings. Registers handles then freezes all parts.

    Parameters
    ----------
    root_type : type
        Compiled :class:`~tg_model.model.elements.System` / :class:`~tg_model.model.elements.Part` subclass.

    Returns
    -------
    ConfiguredModel
        Frozen topology ready for :func:`~tg_model.execution.graph_compiler.compile_graph`.

    Notes
    -----
    Stable IDs derive from the configured root type plus full instance path so identities
    stay unique regardless of which intermediate type owns a declaration.

    See Also
    --------
    tg_model.execution.graph_compiler.compile_graph
    tg_model.execution.evaluator.Evaluator
    """
    compiled = root_type.compile()
    path_registry: dict[str, ElementInstance | ValueSlot] = {}
    id_registry: dict[str, ElementInstance | ValueSlot] = {}
    requirement_value_slots: list[ValueSlot] = []

    root_path = (root_type.__name__,)
    root_id = derive_declaration_id(root_type, *root_path)
    root_instance = PartInstance(
        stable_id=root_id,
        definition_type=root_type,
        definition_path=(),
        instance_path=root_path,
    )
    _register(root_instance, path_registry, id_registry)

    ref_accumulator: list[ReferenceBinding] = []
    _instantiate_children(
        root_instance,
        compiled,
        root_type,
        path_registry,
        id_registry,
        ref_accumulator,
        requirement_value_slots,
    )

    connections = _instantiate_connections(compiled, root_instance, path_registry, root_type)
    allocations = _instantiate_allocations(compiled, root_instance, path_registry, root_type)
    references = (
        _instantiate_all_references(root_instance, path_registry, root_type) + ref_accumulator
    )

    root_instance.freeze()

    return ConfiguredModel(
        root=root_instance,
        path_registry=path_registry,
        id_registry=id_registry,
        connections=connections,
        allocations=allocations,
        references=references,
        requirement_value_slots=requirement_value_slots,
    )


def _instantiate_children(
    parent: PartInstance,
    compiled: dict[str, Any],
    root_type: type,
    path_registry: dict[str, ElementInstance | ValueSlot],
    id_registry: dict[str, ElementInstance | ValueSlot],
    ref_accumulator: list[ReferenceBinding] | None = None,
    requirement_value_slots: list[ValueSlot] | None = None,
) -> None:
    """Walk compiled nodes and create child instances under parent."""
    type_registry: dict[str, type] = compiled.get("_type_registry", {})

    for name, node in compiled["nodes"].items():
        kind = node["kind"]
        metadata = node.get("metadata", {})
        child_path = (*parent.instance_path, name)
        child_id = derive_declaration_id(root_type, *child_path)

        if kind == "part":
            child_type = type_registry.get(name)
            child_instance = PartInstance(
                stable_id=child_id,
                definition_type=child_type or type(parent),
                definition_path=(name,),
                instance_path=child_path,
                metadata=metadata,
            )
            parent.add_child(name, child_instance)
            _register(child_instance, path_registry, id_registry)

            if child_type is not None:
                child_compiled = child_type.compile()
                _instantiate_children(
                    child_instance,
                    child_compiled,
                    root_type,
                    path_registry,
                    id_registry,
                    ref_accumulator,
                    requirement_value_slots,
                )

        elif kind == "port":
            port_instance = PortInstance(
                stable_id=child_id,
                definition_type=parent.definition_type,
                definition_path=(name,),
                instance_path=child_path,
                metadata=metadata,
            )
            parent.add_port(name, port_instance)
            _register(port_instance, path_registry, id_registry)

        elif kind in ("attribute", "parameter"):
            slot = ValueSlot(
                stable_id=child_id,
                instance_path=child_path,
                kind=kind,
                definition_type=parent.definition_type,
                definition_path=(name,),
                metadata=metadata,
                has_expr="_expr" in metadata,
                has_computed_by="_computed_by" in metadata,
            )
            parent.add_value_slot(name, slot)
            _register_slot(slot, path_registry, id_registry)

        elif kind == "requirement":
            req_instance = ElementInstance(
                stable_id=child_id,
                definition_type=parent.definition_type,
                definition_path=(name,),
                instance_path=child_path,
                kind="requirement",
                metadata=metadata,
            )
            _register(req_instance, path_registry, id_registry)

        elif kind == "requirement_block":
            block_type = type_registry.get(name)
            block_instance = ElementInstance(
                stable_id=child_id,
                definition_type=root_type,
                definition_path=(name,),
                instance_path=child_path,
                kind="requirement_block",
                metadata=metadata,
            )
            _register(block_instance, path_registry, id_registry)
            if block_type is not None:
                sub_compiled = _requirement_block_compiled_artifact(block_type)
                _instantiate_requirement_block_children(
                    child_path,
                    sub_compiled,
                    root_type,
                    root_type,
                    path_registry,
                    id_registry,
                    ref_accumulator,
                    requirement_value_slots,
                )

        elif kind == "constraint":
            constraint_instance = ElementInstance(
                stable_id=child_id,
                definition_type=parent.definition_type,
                definition_path=(name,),
                instance_path=child_path,
                kind="constraint",
                metadata=metadata,
            )
            _register(constraint_instance, path_registry, id_registry)

        elif kind == "citation":
            cite_instance = ElementInstance(
                stable_id=child_id,
                definition_type=parent.definition_type,
                definition_path=(name,),
                instance_path=child_path,
                kind="citation",
                metadata=metadata,
            )
            _register(cite_instance, path_registry, id_registry)


def _instantiate_requirement_block_children(
    prefix_path: tuple[str, ...],
    compiled: dict[str, Any],
    definition_root_type: type,
    root_type: type,
    path_registry: dict[str, ElementInstance | ValueSlot],
    id_registry: dict[str, ElementInstance | ValueSlot],
    ref_accumulator: list[ReferenceBinding] | None = None,
    requirement_value_slots: list[ValueSlot] | None = None,
) -> None:
    """Materialize requirements/citations/nested blocks under a requirement_block (no PartInstance parent)."""
    type_registry: dict[str, type] = compiled.get("_type_registry", {})

    for name, node in compiled["nodes"].items():
        kind = node["kind"]
        metadata = node.get("metadata", {})
        child_path = (*prefix_path, name)
        child_id = derive_declaration_id(root_type, *child_path)

        if kind == "requirement":
            req_instance = ElementInstance(
                stable_id=child_id,
                definition_type=definition_root_type,
                definition_path=tuple(child_path[1:]),
                instance_path=child_path,
                kind="requirement",
                metadata=metadata,
            )
            _register(req_instance, path_registry, id_registry)
        elif kind == "citation":
            cite_instance = ElementInstance(
                stable_id=child_id,
                definition_type=definition_root_type,
                definition_path=tuple(child_path[1:]),
                instance_path=child_path,
                kind="citation",
                metadata=metadata,
            )
            _register(cite_instance, path_registry, id_registry)
        elif kind == "requirement_block":
            block_type = type_registry.get(name)
            block_instance = ElementInstance(
                stable_id=child_id,
                definition_type=definition_root_type,
                definition_path=tuple(child_path[1:]),
                instance_path=child_path,
                kind="requirement_block",
                metadata=metadata,
            )
            _register(block_instance, path_registry, id_registry)
            if block_type is not None:
                _instantiate_requirement_block_children(
                    child_path,
                    _requirement_block_compiled_artifact(block_type),
                    definition_root_type,
                    root_type,
                    path_registry,
                    id_registry,
                    ref_accumulator,
                    requirement_value_slots,
                )

        elif kind == "requirement_attribute":
            if requirement_value_slots is None:
                raise ValueError(
                    "requirement_attribute nodes require requirement_value_slots accumulator"
                )
            req_key = metadata["_requirement_key"]
            aname = metadata["_attr_name"]
            slot_path = (*prefix_path, req_key, aname)
            meta = dict(metadata)
            meta["_requirement_derived"] = True
            slot = ValueSlot(
                stable_id=child_id,
                instance_path=slot_path,
                kind="attribute",
                definition_type=definition_root_type,
                definition_path=tuple(slot_path[1:]),
                metadata=meta,
                has_expr="_expr" in meta,
            )
            _register_slot(slot, path_registry, id_registry)
            requirement_value_slots.append(slot)

    if ref_accumulator is not None:
        _wire_requirement_block_references(
            prefix_path, compiled, root_type, path_registry, ref_accumulator,
        )


def _wire_requirement_block_references(
    block_instance_path: tuple[str, ...],
    compiled: dict[str, Any],
    root_type: type,
    path_registry: dict[str, ElementInstance | ValueSlot],
    out: list[ReferenceBinding],
) -> None:
    """Bind ``references`` edges authored inside a :class:`~tg_model.model.elements.RequirementBlock`."""
    for edge in compiled.get("edges", []):
        if edge.get("kind") != "references":
            continue
        src_path = block_instance_path + tuple(edge["source"]["path"])
        tgt_path = block_instance_path + tuple(edge["target"]["path"])
        src_key = ".".join(src_path)
        tgt_key = ".".join(tgt_path)
        src = path_registry.get(src_key)
        tgt = path_registry.get(tgt_key)
        if src is None:
            raise ValueError(f"references source '{src_key}' not found in registry")
        if tgt is None:
            raise ValueError(f"references citation '{tgt_key}' not found in registry")
        if not isinstance(tgt, ElementInstance) or tgt.kind != "citation":
            raise ValueError(f"references target '{tgt_key}' is not a citation ElementInstance")
        ref_id = derive_declaration_id(
            root_type,
            "references",
            *[str(x) for x in src_path],
            *[str(x) for x in tgt_path],
        )
        out.append(
            ReferenceBinding(
                stable_id=ref_id,
                source=src,
                citation=tgt,
            )
        )


def _instantiate_connections(
    compiled: dict[str, Any],
    root: PartInstance,
    path_registry: dict[str, ElementInstance | ValueSlot],
    root_type: type,
) -> list[ConnectionBinding]:
    """Resolve compiled connection edges into ConnectionBindings."""
    connections: list[ConnectionBinding] = []

    for edge in compiled.get("edges", []):
        if edge["kind"] != "connect":
            continue

        src_path = root.instance_path + tuple(edge["source"]["path"])
        tgt_path = root.instance_path + tuple(edge["target"]["path"])
        src_key = ".".join(src_path)
        tgt_key = ".".join(tgt_path)

        src = path_registry.get(src_key)
        tgt = path_registry.get(tgt_key)

        if not isinstance(src, PortInstance):
            raise ValueError(f"Connection source '{src_key}' is not a PortInstance")
        if not isinstance(tgt, PortInstance):
            raise ValueError(f"Connection target '{tgt_key}' is not a PortInstance")

        conn_id = derive_declaration_id(root_type, "connect", *edge["source"]["path"], *edge["target"]["path"])
        connections.append(ConnectionBinding(
            stable_id=conn_id,
            source=src,
            target=tgt,
            carrying=edge.get("carrying"),
        ))

    return connections


def _instantiate_allocations(
    compiled: dict[str, Any],
    root: PartInstance,
    path_registry: dict[str, ElementInstance | ValueSlot],
    root_type: type,
) -> list[AllocationBinding]:
    """Resolve compiled allocation edges into AllocationBindings."""
    allocations: list[AllocationBinding] = []

    for edge in compiled.get("edges", []):
        if edge["kind"] != "allocate":
            continue

        req_path = root.instance_path + tuple(edge["source"]["path"])
        tgt_path = root.instance_path + tuple(edge["target"]["path"])
        req_key = ".".join(req_path)
        tgt_key = ".".join(tgt_path)

        req = path_registry.get(req_key)
        tgt = path_registry.get(tgt_key)

        if req is None:
            raise ValueError(f"Allocation requirement '{req_key}' not found in registry")
        if tgt is None:
            raise ValueError(f"Allocation target '{tgt_key}' not found in registry")
        if not isinstance(req, ElementInstance):
            raise ValueError(f"Allocation requirement '{req_key}' is not an ElementInstance")
        if not isinstance(tgt, ElementInstance):
            raise ValueError(f"Allocation target '{tgt_key}' is not an ElementInstance")

        input_bindings: dict[str, ValueSlot] = {}
        raw_inputs = edge.get("_allocate_inputs")
        if raw_inputs:
            for iname, spec in raw_inputs.items():
                rel = tuple(spec["path"])
                slot_key = ".".join((root.path_string, *rel))
                slot = path_registry.get(slot_key)
                if not isinstance(slot, ValueSlot):
                    raise ValueError(
                        f"allocate inputs[{iname!r}] path {slot_key!r} is not a ValueSlot in registry"
                    )
                input_bindings[str(iname)] = slot

        alloc_id = derive_declaration_id(root_type, "allocate", *edge["source"]["path"], *edge["target"]["path"])
        allocations.append(AllocationBinding(
            stable_id=alloc_id,
            requirement=req,
            target=tgt,
            input_bindings=input_bindings,
        ))

    return allocations


def _instantiate_all_references(
    root: PartInstance,
    path_registry: dict[str, ElementInstance | ValueSlot],
    root_type: type,
) -> list[ReferenceBinding]:
    """Resolve ``references`` edges from every part type in the instance tree (Phase 8)."""
    out: list[ReferenceBinding] = []
    stack: list[PartInstance] = [root]
    while stack:
        part = stack.pop()
        compiled = part.definition_type.compile()
        for edge in compiled.get("edges", []):
            if edge["kind"] != "references":
                continue

            src_path = part.instance_path + tuple(edge["source"]["path"])
            tgt_path = part.instance_path + tuple(edge["target"]["path"])
            src_key = ".".join(src_path)
            tgt_key = ".".join(tgt_path)

            src = path_registry.get(src_key)
            tgt = path_registry.get(tgt_key)

            if src is None:
                raise ValueError(f"references source '{src_key}' not found in registry")
            if tgt is None:
                raise ValueError(f"references citation '{tgt_key}' not found in registry")
            if not isinstance(tgt, ElementInstance) or tgt.kind != "citation":
                raise ValueError(f"references target '{tgt_key}' is not a citation ElementInstance")

            ref_id = derive_declaration_id(
                root_type,
                "references",
                *[str(x) for x in src_path],
                *[str(x) for x in tgt_path],
            )
            out.append(
                ReferenceBinding(
                    stable_id=ref_id,
                    source=src,
                    citation=tgt,
                )
            )
        stack.extend(part.children)

    return out


def _register(
    instance: ElementInstance,
    path_registry: dict[str, ElementInstance | ValueSlot],
    id_registry: dict[str, ElementInstance | ValueSlot],
) -> None:
    path_registry[instance.path_string] = instance
    id_registry[instance.stable_id] = instance


def _register_slot(
    slot: ValueSlot,
    path_registry: dict[str, ElementInstance | ValueSlot],
    id_registry: dict[str, ElementInstance | ValueSlot],
) -> None:
    path_registry[slot.path_string] = slot
    id_registry[slot.stable_id] = slot


def _normalize_evaluate_inputs(model: ConfiguredModel, inputs: dict[Any, Any]) -> dict[str, Any]:
    """Map ``ValueSlot`` / slot-id ``str`` keys to ``stable_id`` strings for ``Evaluator``."""
    out: dict[str, Any] = {}
    for key, value in inputs.items():
        if isinstance(key, ValueSlot):
            reg = model.id_registry.get(key.stable_id)
            if reg is not key:
                raise ValueError(
                    f"ValueSlot {key.path_string!r} is not registered on this ConfiguredModel "
                    "(foreign slot or stale handle).",
                )
            out[key.stable_id] = value
        elif isinstance(key, str):
            reg = model.id_registry.get(key)
            if reg is None:
                raise KeyError(f"Unknown stable_id {key!r} for this ConfiguredModel")
            if not isinstance(reg, ValueSlot):
                raise ValueError(
                    f"String key {key!r} refers to {type(reg).__name__}, not a ValueSlot; "
                    "use ValueSlot handles or the stable_id of a parameter/attribute slot.",
                )
            out[key] = value
        else:
            raise TypeError(
                f"Input keys must be ValueSlot or str (slot stable_id), got {type(key).__name__}",
            )
    return out
