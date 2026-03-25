"""ValueSlot — topology-level cell definition for parameters and attributes."""

from __future__ import annotations

from typing import Any


class ValueSlot:
    """Describes what can hold a value in the configured topology.

    A ValueSlot is part of the configured topology. It describes the
    slot, not the per-run mutable value. Per-run state lives in RunContext.
    """

    __slots__ = ("stable_id", "instance_path", "kind", "metadata", "definition_type", "definition_path", "has_expr", "has_computed_by")

    def __init__(
        self,
        *,
        stable_id: str,
        instance_path: tuple[str, ...],
        kind: str,
        definition_type: type | None = None,
        definition_path: tuple[str, ...] | None = None,
        metadata: dict[str, Any] | None = None,
        has_expr: bool = False,
        has_computed_by: bool = False,
    ) -> None:
        self.stable_id = stable_id
        self.instance_path = instance_path
        self.kind = kind
        self.definition_type = definition_type
        self.definition_path = definition_path
        self.metadata = metadata or {}
        self.has_expr = has_expr
        self.has_computed_by = has_computed_by

    @property
    def path_string(self) -> str:
        return ".".join(self.instance_path)

    @property
    def is_parameter(self) -> bool:
        return self.kind == "parameter"

    @property
    def is_attribute(self) -> bool:
        return self.kind == "attribute"

    def __repr__(self) -> str:
        return f"<ValueSlot: {self.path_string} ({self.kind})>"
