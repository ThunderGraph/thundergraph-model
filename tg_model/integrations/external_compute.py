"""External computation protocols, bindings, and route wiring.

Bindings connect declared :class:`~tg_model.model.refs.AttributeRef` inputs to Python
callables that return :class:`ExternalComputeResult`. Sync paths use
:class:`ExternalCompute`; async callables use :class:`AsyncExternalCompute` with
:class:`~tg_model.execution.evaluator.Evaluator.evaluate_async`.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from unitflow import Quantity

from tg_model.model.refs import AttributeRef


class ExternalComputeValidationError(ValueError):
    """Raised when :meth:`ValidatableExternalCompute.validate_binding` rejects a spec."""


@dataclass(frozen=True)
class ExternalComputeResult:
    """Return value from :meth:`ExternalCompute.compute` / :meth:`AsyncExternalCompute.compute`.

    Attributes
    ----------
    value : Quantity or mapping
        Single output quantity or mapping of route name → quantity.
    provenance : mapping
        Opaque structured provenance (tool ids, versions, URIs).
    """

    value: Quantity | Mapping[str, Quantity]
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ExternalComputeBinding:
    """Bind a callable to named input refs and optional output route refs.

    Attributes
    ----------
    external : object
        Implementation satisfying :class:`ExternalCompute` or :class:`AsyncExternalCompute`.
    inputs : dict[str, AttributeRef]
        Logical input name → attribute/parameter ref supplying unitflow symbols at compile time.
    output_routes : dict[str, AttributeRef], optional
        External output name → attribute refs (may be set after construction via
        :func:`link_external_routes` or :meth:`tg_model.model.definition_context.ModelDefinitionContext.link_external_routes`).
    """

    external: object
    inputs: dict[str, AttributeRef]
    output_routes: dict[str, AttributeRef] | None = None


def link_external_routes(
    binding: ExternalComputeBinding,
    routes: dict[str, AttributeRef],
) -> None:
    """Mutate ``binding.output_routes`` in place (authoring convenience).

    Parameters
    ----------
    binding : ExternalComputeBinding
        Target binding.
    routes : dict[str, AttributeRef]
        Output name → attribute ref to realize.
    """
    binding.output_routes = dict(routes)


@runtime_checkable
class ExternalCompute(Protocol):
    """Synchronous external backend (safe for :meth:`~tg_model.execution.evaluator.Evaluator.evaluate`)."""

    @property
    def name(self) -> str: ...

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult: ...


@runtime_checkable
class AsyncExternalCompute(Protocol):
    """Coroutine ``compute`` backend (requires :meth:`~tg_model.execution.evaluator.Evaluator.evaluate_async`)."""

    @property
    def name(self) -> str: ...

    async def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult: ...


@runtime_checkable
class ValidatableExternalCompute(Protocol):
    """Optional static validation hook used by :func:`tg_model.execution.validation.validate_graph`."""

    def validate_binding(
        self,
        *,
        input_specs: Mapping[str, Any],
        output_specs: Mapping[str, Any],
    ) -> None:
        """Raise :class:`ExternalComputeValidationError` or ``ValueError`` when specs are inconsistent."""


def is_async_external(obj: object) -> bool:
    """Return True when ``compute`` is a coroutine function.

    Notes
    -----
    Async externals must not run under :meth:`~tg_model.execution.evaluator.Evaluator.evaluate`.
    """
    fn = getattr(obj, "compute", None)
    return inspect.iscoroutinefunction(fn)


def assert_sync_external(obj: object, *, context: str = "") -> None:
    """Raise ``TypeError`` if ``obj`` is an async external.

    Parameters
    ----------
    obj : object
        External implementation about to run under sync evaluation.
    context : str, optional
        Suffix appended to the error message.

    Raises
    ------
    TypeError
        When :func:`is_async_external` is true.
    """
    if is_async_external(obj):
        suffix = f" ({context})" if context else ""
        raise TypeError(
            f"Async external compute {getattr(obj, 'name', obj)!r} cannot run under "
            f"synchronous Evaluator.evaluate(){suffix}. Use Evaluator.evaluate_async(...)."
        )
