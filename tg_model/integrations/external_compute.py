"""External computation contracts (Phase 4 / v0_api Frozen decision 5)."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from unitflow import Quantity

from tg_model.model.refs import AttributeRef


class ExternalComputeValidationError(ValueError):
    """Raised when optional static validation of an external binding fails."""


@dataclass(frozen=True)
class ExternalComputeResult:
    """Structured return from one external run."""

    value: Quantity | Mapping[str, Quantity]
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ExternalComputeBinding:
    """Binds an external implementation to input refs and optional multi-slot routes.

    ``output_routes`` may be set after construction (once all ``AttributeRef``s exist)
    as long as it is finalized before the owning type is compiled.
    """

    external: object
    inputs: dict[str, AttributeRef]
    output_routes: dict[str, AttributeRef] | None = None


def link_external_routes(
    binding: ExternalComputeBinding,
    routes: dict[str, AttributeRef],
) -> None:
    """Attach fan-out routes after attributes exist (v0 authoring affordance)."""
    binding.output_routes = dict(routes)


@runtime_checkable
class ExternalCompute(Protocol):
    """Synchronous external backend."""

    @property
    def name(self) -> str: ...

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult: ...


@runtime_checkable
class AsyncExternalCompute(Protocol):
    """Async external backend (AsyncEvaluator only)."""

    @property
    def name(self) -> str: ...

    async def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult: ...


@runtime_checkable
class ValidatableExternalCompute(Protocol):
    """Optional static validation before any external call."""

    def validate_binding(
        self,
        *,
        input_specs: Mapping[str, Any],
        output_specs: Mapping[str, Any],
    ) -> None: ...


def is_async_external(obj: object) -> bool:
    """True if ``obj.compute`` is a coroutine function (must not run under sync Evaluator)."""
    fn = getattr(obj, "compute", None)
    return inspect.iscoroutinefunction(fn)


def assert_sync_external(obj: object, *, context: str = "") -> None:
    """Fail-fast for sync evaluation paths."""
    if is_async_external(obj):
        suffix = f" ({context})" if context else ""
        raise TypeError(
            f"Async external compute {getattr(obj, 'name', obj)!r} cannot run under "
            f"synchronous Evaluator.evaluate(){suffix}. Use Evaluator.evaluate_async(...)."
        )
