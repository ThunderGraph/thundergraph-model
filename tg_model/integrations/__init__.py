"""Integration boundaries (external computation, async orchestration)."""

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
