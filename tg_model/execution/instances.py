"""Runtime instance objects for the configured topology."""

from __future__ import annotations

from typing import Any

from tg_model.execution.value_slots import ValueSlot


class ElementInstance:
    """Generic runtime representation of one materialized semantic element."""

    __slots__ = ("definition_path", "definition_type", "instance_path", "kind", "metadata", "stable_id")

    def __init__(
        self,
        *,
        stable_id: str,
        definition_type: type,
        definition_path: tuple[str, ...],
        instance_path: tuple[str, ...],
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.stable_id = stable_id
        self.definition_type = definition_type
        self.definition_path = definition_path
        self.instance_path = instance_path
        self.kind = kind
        self.metadata = metadata or {}

    @property
    def path_string(self) -> str:
        return ".".join(self.instance_path)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.path_string} ({self.kind})>"


class PortInstance(ElementInstance):
    """A concrete port endpoint in the configured topology."""

    __slots__ = ("direction",)

    def __init__(
        self,
        *,
        stable_id: str,
        definition_type: type,
        definition_path: tuple[str, ...],
        instance_path: tuple[str, ...],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        direction = (metadata or {}).get("direction", "unknown")
        super().__init__(
            stable_id=stable_id,
            definition_type=definition_type,
            definition_path=definition_path,
            instance_path=instance_path,
            kind="port",
            metadata=metadata,
        )
        self.direction = direction


class PartInstance(ElementInstance):
    """A materialized Part or System in the configured topology.

    Owns child parts, ports, value slots, and connection bindings.
    Supports attribute-style navigation for ergonomic access.
    """

    __slots__ = ("_child_lookup", "_children", "_frozen", "_ports", "_value_slots")

    def __init__(
        self,
        *,
        stable_id: str,
        definition_type: type,
        definition_path: tuple[str, ...],
        instance_path: tuple[str, ...],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            stable_id=stable_id,
            definition_type=definition_type,
            definition_path=definition_path,
            instance_path=instance_path,
            kind="part",
            metadata=metadata,
        )
        self._children: list[PartInstance] = []
        self._ports: list[PortInstance] = []
        self._value_slots: list[ValueSlot] = []
        self._child_lookup: dict[str, PartInstance | PortInstance | ValueSlot] = {}
        self._frozen = False

    def _check_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError(f"Cannot modify frozen PartInstance '{self.path_string}'")

    def freeze(self) -> None:
        """Freeze this instance and all children. No structural mutations after this."""
        self._frozen = True
        for child in self._children:
            child.freeze()

    def add_child(self, name: str, child: PartInstance) -> None:
        self._check_frozen()
        self._children.append(child)
        self._child_lookup[name] = child

    def add_port(self, name: str, port: PortInstance) -> None:
        self._check_frozen()
        self._ports.append(port)
        self._child_lookup[name] = port

    def add_value_slot(self, name: str, slot: ValueSlot) -> None:
        self._check_frozen()
        self._value_slots.append(slot)
        self._child_lookup[name] = slot

    @property
    def children(self) -> list[PartInstance]:
        return list(self._children)

    @property
    def ports(self) -> list[PortInstance]:
        return list(self._ports)

    @property
    def value_slots(self) -> list[ValueSlot]:
        return list(self._value_slots)

    def __getattr__(self, name: str) -> PartInstance | PortInstance | ValueSlot:
        if name.startswith("_"):
            raise AttributeError(name)
        lookup = object.__getattribute__(self, "_child_lookup")
        if name in lookup:
            return lookup[name]
        raise AttributeError(
            f"{self.path_string} has no child named '{name}'"
        )


def slot_ids_for_part_subtree(part: PartInstance) -> frozenset[str]:
    """All :class:`ValueSlot` ``stable_id`` values under ``part`` (including nested parts)."""
    ids: set[str] = set()
    stack: list[PartInstance] = [part]
    while stack:
        p = stack.pop()
        for vs in p.value_slots:
            ids.add(vs.stable_id)
        stack.extend(p.children)
    return frozenset(ids)
