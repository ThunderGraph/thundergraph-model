"""ConnectionBinding and AllocationBinding — resolved structural edges."""

from __future__ import annotations

from tg_model.execution.instances import ElementInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot


class ConnectionBinding:
    """A resolved structural connection between two concrete PortInstances."""

    __slots__ = ("carrying", "source", "stable_id", "target")

    def __init__(
        self,
        *,
        stable_id: str,
        source: PortInstance,
        target: PortInstance,
        carrying: str | None = None,
    ) -> None:
        self.stable_id = stable_id
        self.source = source
        self.target = target
        self.carrying = carrying

    def __repr__(self) -> str:
        return (
            f"<ConnectionBinding: {self.source.path_string} -> "
            f"{self.target.path_string} carrying={self.carrying!r}>"
        )


class ReferenceBinding:
    """A resolved **references** edge: a declaration points at a citation (Phase 8)."""

    __slots__ = ("citation", "source", "stable_id")

    def __init__(
        self,
        *,
        stable_id: str,
        source: ElementInstance | PortInstance | ValueSlot,
        citation: ElementInstance,
    ) -> None:
        self.stable_id = stable_id
        self.source = source
        self.citation = citation

    def __repr__(self) -> str:
        return (
            f"<ReferenceBinding: {self.source.path_string} -> "
            f"{self.citation.path_string}>"
        )


class AllocationBinding:
    """A resolved allocation from a requirement to a model element."""

    __slots__ = ("requirement", "stable_id", "target")

    def __init__(
        self,
        *,
        stable_id: str,
        requirement: ElementInstance,
        target: ElementInstance,
    ) -> None:
        self.stable_id = stable_id
        self.requirement = requirement
        self.target = target

    def __repr__(self) -> str:
        return (
            f"<AllocationBinding: {self.requirement.path_string} -> "
            f"{self.target.path_string}>"
        )
