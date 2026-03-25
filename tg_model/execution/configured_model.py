"""ConfiguredModel — the root runtime container for one configured system."""

from __future__ import annotations

from typing import Any

from tg_model.execution.connection_bindings import (
    AllocationBinding,
    ConnectionBinding,
    ReferenceBinding,
)
from tg_model.execution.instances import ElementInstance, PartInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.model.identity import derive_declaration_id


class ConfiguredModel:
    """An immutable configured topology built from a compiled type artifact.

    Topology is frozen after construction. Repeated evaluations create
    new RunContexts; they do not modify the configured model.
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
    ) -> None:
        self.root = root
        self.path_registry = path_registry
        self.id_registry = id_registry
        self.connections = connections
        self.allocations = allocations
        self.references = references

    def handle(self, path: str) -> ElementInstance | ValueSlot:
        """Look up an instance or slot by its dotted path string."""
        if path not in self.path_registry:
            raise KeyError(f"No handle found for path '{path}'")
        return self.path_registry[path]

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
    """Build a ConfiguredModel from a compiled type artifact.

    Walks the compiled definition depth-first, creating PartInstances,
    PortInstances, ValueSlots, ConnectionBindings, and AllocationBindings.
    Registers everything in path and id registries, then freezes topology.

    Identity rule: all instance IDs are derived from the configured root
    type + full instance path. This ensures consistent, non-overlapping
    identifiers regardless of which intermediate type owns the declaration.
    """
    compiled = root_type.compile()
    path_registry: dict[str, ElementInstance | ValueSlot] = {}
    id_registry: dict[str, ElementInstance | ValueSlot] = {}

    root_path = (root_type.__name__,)
    root_id = derive_declaration_id(root_type, *root_path)
    root_instance = PartInstance(
        stable_id=root_id,
        definition_type=root_type,
        definition_path=(),
        instance_path=root_path,
    )
    _register(root_instance, path_registry, id_registry)

    _instantiate_children(root_instance, compiled, root_type, path_registry, id_registry)

    connections = _instantiate_connections(compiled, root_instance, path_registry, root_type)
    allocations = _instantiate_allocations(compiled, root_instance, path_registry, root_type)
    references = _instantiate_all_references(root_instance, path_registry, root_type)

    root_instance.freeze()

    return ConfiguredModel(
        root=root_instance,
        path_registry=path_registry,
        id_registry=id_registry,
        connections=connections,
        allocations=allocations,
        references=references,
    )


def _instantiate_children(
    parent: PartInstance,
    compiled: dict[str, Any],
    root_type: type,
    path_registry: dict[str, ElementInstance | ValueSlot],
    id_registry: dict[str, ElementInstance | ValueSlot],
) -> None:
    """Walk compiled nodes and create child instances under parent."""
    type_registry: dict[str, type] = compiled.get("_type_registry", {})

    for name, node in compiled["nodes"].items():
        kind = node["kind"]
        metadata = node.get("metadata", {})
        child_path = parent.instance_path + (name,)
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
                    child_instance, child_compiled, root_type,
                    path_registry, id_registry,
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

        alloc_id = derive_declaration_id(root_type, "allocate", *edge["source"]["path"], *edge["target"]["path"])
        allocations.append(AllocationBinding(
            stable_id=alloc_id,
            requirement=req,
            target=tgt,
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
