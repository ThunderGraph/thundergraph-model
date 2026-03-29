"""Runtime instances: :class:`ElementInstance`, :class:`PartInstance`, :class:`PortInstance`."""

from __future__ import annotations

from typing import Any

from tg_model.execution.value_slots import ValueSlot


class ElementInstance:
    """One materialized declaration (requirement, port, block, …) under the configured root."""

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
        """Parameters mirror attributes (constructed by instantiation, not by library users)."""
        self.stable_id = stable_id
        self.definition_type = definition_type
        self.definition_path = definition_path
        self.instance_path = instance_path
        self.kind = kind
        self.metadata = metadata or {}

    @property
    def path_string(self) -> str:
        """Dotted path from configured root to this instance."""
        return ".".join(self.instance_path)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.path_string} ({self.kind})>"


class RequirementPackageInstance(ElementInstance):
    """Materialized composable requirement package under the configured root.

    Exposes nested requirements, citations, nested packages, and package-level value slots via
    attribute access (e.g. ``root.mission.x_m`` for a package parameter).
    """

    __slots__ = ("_frozen", "_members", "package_type")

    def __init__(
        self,
        *,
        stable_id: str,
        definition_type: type,
        definition_path: tuple[str, ...],
        instance_path: tuple[str, ...],
        package_type: type,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            stable_id=stable_id,
            definition_type=definition_type,
            definition_path=definition_path,
            instance_path=instance_path,
            kind="requirement_block",
            metadata=metadata,
        )
        self.package_type = package_type
        self._members: dict[str, ElementInstance | ValueSlot | RequirementPackageInstance] = {}
        self._frozen = False

    def _check_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError(f"Cannot modify frozen RequirementPackageInstance '{self.path_string}'")

    def add_member(self, name: str, obj: ElementInstance | ValueSlot | RequirementPackageInstance) -> None:
        """Register a child (instantiation only)."""
        self._check_frozen()
        self._members[name] = obj

    def freeze(self) -> None:
        """Freeze this package and nested packages recursively."""
        self._frozen = True
        for m in self._members.values():
            if isinstance(m, RequirementPackageInstance):
                m.freeze()

    def __getattr__(self, name: str) -> ElementInstance | ValueSlot | RequirementPackageInstance:
        if name.startswith("_"):
            raise AttributeError(name)
        members = object.__getattribute__(self, "_members")
        if name in members:
            return members[name]
        raise AttributeError(f"{self.path_string} has no member named '{name}'")


class PortInstance(ElementInstance):
    """Concrete port endpoint; ``direction`` comes from declaration metadata."""

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
        """Build a port instance (see :func:`~tg_model.execution.configured_model.instantiate`)."""
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
    """Materialized :class:`~tg_model.model.elements.Part` / :class:`~tg_model.model.elements.System`.

    Owns child parts, ports, and value slots. After :meth:`freeze`, structure is immutable.

    Raises
    ------
    RuntimeError
        If mutators run after :meth:`freeze`.
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
        self._child_lookup: dict[str, PartInstance | PortInstance | ValueSlot | RequirementPackageInstance] = {}
        self._frozen = False

    def _check_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError(f"Cannot modify frozen PartInstance '{self.path_string}'")

    def freeze(self) -> None:
        """Recursively freeze this part subtree (called on the full model after instantiate)."""
        self._frozen = True
        for child in self._children:
            child.freeze()
        for obj in self._child_lookup.values():
            if isinstance(obj, RequirementPackageInstance):
                obj.freeze()

    def add_child(self, name: str, child: PartInstance) -> None:
        """Register a child part under ``name`` (instantiation only).

        Raises
        ------
        RuntimeError
            If this instance is frozen.
        """
        self._check_frozen()
        self._children.append(child)
        self._child_lookup[name] = child

    def add_port(self, name: str, port: PortInstance) -> None:
        """Register a port under ``name`` (instantiation only)."""
        self._check_frozen()
        self._ports.append(port)
        self._child_lookup[name] = port

    def add_value_slot(self, name: str, slot: ValueSlot) -> None:
        """Register a value slot under ``name`` (instantiation only)."""
        self._check_frozen()
        self._value_slots.append(slot)
        self._child_lookup[name] = slot

    def add_requirement_package(self, name: str, pkg: RequirementPackageInstance) -> None:
        """Register a composable requirement package under ``name`` (instantiation only)."""
        self._check_frozen()
        self._child_lookup[name] = pkg

    @property
    def children(self) -> list[PartInstance]:
        """Shallow copy of child parts."""
        return list(self._children)

    @property
    def ports(self) -> list[PortInstance]:
        """Shallow copy of owned ports."""
        return list(self._ports)

    @property
    def value_slots(self) -> list[ValueSlot]:
        """Shallow copy of owned parameter/attribute slots."""
        return list(self._value_slots)

    def __getattr__(self, name: str) -> PartInstance | PortInstance | ValueSlot | RequirementPackageInstance:
        """Resolve ``name`` against registered children, ports, and value slots.

        Raises
        ------
        AttributeError
            If ``name`` is unknown or private.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        lookup = object.__getattribute__(self, "_child_lookup")
        if name in lookup:
            return lookup[name]
        raise AttributeError(f"{self.path_string} has no child named '{name}'")


def _collect_slot_ids_from_requirement_package(pkg: RequirementPackageInstance, out: set[str]) -> None:
    """Gather slot ids under a composable requirement package (including nested packages)."""
    for obj in pkg._members.values():
        if isinstance(obj, ValueSlot):
            out.add(obj.stable_id)
        elif isinstance(obj, RequirementPackageInstance):
            _collect_slot_ids_from_requirement_package(obj, out)


def slot_ids_for_part_subtree(part: PartInstance) -> frozenset[str]:
    """Return every :class:`~tg_model.execution.value_slots.ValueSlot` ``stable_id`` under ``part``.

    Includes slots on the part and its descendant parts, and value slots declared on composable
    requirement packages attached to those parts (nested packages included). Ports and non-slot
    elements under packages are not included.

    Parameters
    ----------
    part : PartInstance
        Root of the subtree to walk.

    Returns
    -------
    frozenset[str]
        Stable ids for behavior subtree scoping.
    """
    ids: set[str] = set()
    stack: list[PartInstance] = [part]
    while stack:
        p = stack.pop()
        for vs in p.value_slots:
            ids.add(vs.stable_id)
        # ``ConfiguredModel`` forwards ``value_slots`` / ``children`` via ``__getattr__`` but has
        # no ``_child_lookup``; skip package walk in that mistaken-API case (behavior tests).
        child_lookup = getattr(p, "_child_lookup", None)
        if child_lookup is not None:
            for obj in child_lookup.values():
                if isinstance(obj, RequirementPackageInstance):
                    _collect_slot_ids_from_requirement_package(obj, ids)
        stack.extend(p.children)
    return frozenset(ids)
