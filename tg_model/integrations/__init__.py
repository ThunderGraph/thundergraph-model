"""Integration boundaries for external computation and async-capable backends.

Bindings declared at definition time are compiled into graph nodes; sync evaluation
uses :class:`~tg_model.integrations.external_compute.ExternalCompute`, while
:class:`~tg_model.integrations.external_compute.AsyncExternalCompute` requires
:class:`~tg_model.execution.evaluator.Evaluator.evaluate_async`.

See Also
--------
tg_model.execution.graph_compiler.compile_graph
tg_model.execution.evaluator.Evaluator
"""

from tg_model.integrations.external_compute import (
    AsyncExternalCompute,
    ExternalCompute,
    ExternalComputeBinding,
    ExternalComputeResult,
    ExternalComputeValidationError,
    ValidatableExternalCompute,
    assert_sync_external,
    is_async_external,
    link_external_routes,
)

__all__ = [
    "AsyncExternalCompute",
    "ExternalCompute",
    "ExternalComputeBinding",
    "ExternalComputeResult",
    "ExternalComputeValidationError",
    "ValidatableExternalCompute",
    "assert_sync_external",
    "is_async_external",
    "link_external_routes",
]
