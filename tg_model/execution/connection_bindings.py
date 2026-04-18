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
        return f"<ConnectionBinding: {self.source.path_string} -> {self.target.path_string} carrying={self.carrying!r}>"


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
        return f"<ReferenceBinding: {self.source.path_string} -> {self.citation.path_string}>"


class AllocationBinding:
    """Resolved ``allocate`` edge from a requirement package to a target element.

    Parameters
    ----------
    parameter_overrides : dict[str, ValueSlot], optional
        Maps requirement package :meth:`~tg_model.model.definition_context.ModelDefinitionContext.parameter`
        names to concrete source value slots.  When present, the graph compiler wires the
        corresponding requirement package parameter slots as computed values (sourced from the
        mapped slots) rather than as free ``INPUT_PARAMETER`` nodes.
    """

    __slots__ = ("parameter_overrides", "requirement", "stable_id", "target")

    def __init__(
        self,
        *,
        stable_id: str,
        requirement: ElementInstance,
        target: ElementInstance,
        parameter_overrides: dict[str, ValueSlot] | None = None,
    ) -> None:
        self.stable_id = stable_id
        self.requirement = requirement
        self.target = target
        self.parameter_overrides = parameter_overrides or {}

    def __repr__(self) -> str:
        return f"<AllocationBinding: {self.requirement.path_string} -> {self.target.path_string}>"
