"""Shared helpers for external compute (graph compiler + async evaluator)."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any

from unitflow import Quantity

from tg_model.execution.configured_model import ConfiguredModel
from tg_model.execution.instances import PartInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.integrations.external_compute import ExternalComputeBinding, ExternalComputeResult
from tg_model.model.refs import AttributeRef


class ExternalOpsError(Exception):
    """Raised when external binding materialization cannot proceed."""


def navigate_to_part(root: PartInstance, path: tuple[str, ...]) -> PartInstance:
    """Resolve ``path`` (``PartInstance.instance_path`` tuple) under ``root``'s tree."""
    if path == root.instance_path:
        return root
    current: Any = root
    for segment in path[len(root.instance_path) :]:
        current = getattr(current, segment)
    if not isinstance(current, PartInstance):
        raise ExternalOpsError(
            f"Path {path!r} did not resolve to a PartInstance (got {type(current).__name__})"
        )
    return current


def resolve_attribute_ref_to_slot(
    ref: AttributeRef,
    owner: PartInstance,
    model: ConfiguredModel,
) -> ValueSlot:
    """Resolve a definition-time AttributeRef to a ValueSlot on this configuration."""
    start: Any
    if ref.owner_type == owner.definition_type:
        start = owner
    elif ref.owner_type == model.root.definition_type:
        start = model.root
    else:
        raise ExternalOpsError(
            f"Cannot resolve AttributeRef {ref!r}: owner_type {ref.owner_type.__name__} "
            f"does not match part '{owner.path_string}' or configured root type"
        )
    current: Any = start
    try:
        for segment in ref.path:
            current = getattr(current, segment)
        if isinstance(current, ValueSlot):
            return current
    except AttributeError as e:
        raise ExternalOpsError(
            f"Could not resolve AttributeRef path {ref.path} from {start.path_string}: {e}"
        ) from e
    raise ExternalOpsError(
        f"AttributeRef {ref.path} did not resolve to a ValueSlot (got {type(current).__name__})"
    )


def materialize_external_result(
    binding: ExternalComputeBinding,
    res: ExternalComputeResult,
    owner: PartInstance,
    model: ConfiguredModel,
    ctx: Any,
    slots: list[ValueSlot],
) -> None:
    """Write external results into the run context (sync or async path)."""
    prov = dict(res.provenance)
    routes = binding.output_routes
    if routes is None:
        if not isinstance(res.value, Quantity):
            raise TypeError(
                "Single-slot external binding requires ExternalComputeResult.value to be a Quantity"
            )
        ctx.realize(slots[0].stable_id, res.value, provenance=prov)
        return
    if not isinstance(res.value, MappingABC):
        raise TypeError(
            "Multi-slot external binding requires ExternalComputeResult.value to be Mapping[str, Quantity]"
        )
    value_keys = set(res.value.keys())
    route_keys = set(routes.keys())
    if value_keys != route_keys:
        raise ValueError(
            f"External result keys {value_keys!r} must match output_routes keys {route_keys!r}"
        )
    for key in routes:
        ref = routes[key]
        qty = res.value[key]
        tgt = resolve_attribute_ref_to_slot(ref, owner, model)
        ctx.realize(tgt.stable_id, qty, provenance=prov)
