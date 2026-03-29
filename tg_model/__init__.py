"""ThunderGraph Model — executable systems modeling in Python.

This package re-exports the **primary authoring surface** (elements, definition
context, refs, and roll-up helpers). For configure-time and run-time APIs
(:class:`~tg_model.execution.configured_model.ConfiguredModel`, graph compile,
evaluation), import :mod:`tg_model.execution` explicitly.

Notes
-----
Types are **compiled** once per class (cached). :func:`~tg_model.execution.configured_model.instantiate`
builds a frozen topology; :class:`~tg_model.execution.run_context.RunContext` holds
per-run values. See the user documentation plan in ``docs/user_docs/``.
"""

from tg_model.model.declarations.values import rollup
from tg_model.model.definition_context import (
    ModelDefinitionContext,
    ModelDefinitionError,
    parameter_ref,
    requirement_ref,
)
from tg_model.model.elements import Element, Part, Requirement, System
from tg_model.model.refs import (
    AttributeRef,
    PartRef,
    PortRef,
    Ref,
    RequirementRef,
)

__all__ = [
    "AttributeRef",
    "Element",
    "ModelDefinitionContext",
    "ModelDefinitionError",
    "Part",
    "PartRef",
    "PortRef",
    "Ref",
    "Requirement",
    "RequirementRef",
    "System",
    "parameter_ref",
    "requirement_ref",
    "rollup",
]
