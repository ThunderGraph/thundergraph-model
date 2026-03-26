"""Resolved topology edges: connections, allocations, and citation references."""

from __future__ import annotations

from tg_model.execution.instances import ElementInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot


class ConnectionBinding:
    """Resolved connection between two :class:`~tg_model.execution.instances.PortInstance` objects.

    Parameters
    ----------
    stable_id : str
        Unique edge id (derived at instantiate time).
    source, target : PortInstance
        Endpoint ports.
    carrying : str, optional
        Item kind discriminator for :func:`~tg_model.execution.behavior.emit_item`.
    """

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
    """Resolved ``references`` edge from a declaration to a citation node (provenance)."""

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
    """Resolved ``allocate`` edge from a requirement to a target element.

    Parameters
    ----------
    input_bindings : dict[str, ValueSlot], optional
        Maps :meth:`tg_model.model.definition_context.ModelDefinitionContext.requirement_input`
        names to concrete value slots on the allocated subtree.
    """

    __slots__ = ("input_bindings", "requirement", "stable_id", "target")

    def __init__(
        self,
        *,
        stable_id: str,
        requirement: ElementInstance,
        target: ElementInstance,
        input_bindings: dict[str, ValueSlot] | None = None,
    ) -> None:
        self.stable_id = stable_id
        self.requirement = requirement
        self.target = target
        self.input_bindings = input_bindings or {}

    def __repr__(self) -> str:
        return (
            f"<AllocationBinding: {self.requirement.path_string} -> "
            f"{self.target.path_string}>"
        )
