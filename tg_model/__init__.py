"""tg-model: Executable systems modeling in Python."""

from tg_model.model.declarations.values import rollup
from tg_model.model.definition_context import (
    ModelDefinitionContext,
    ModelDefinitionError,
    parameter_ref,
    requirement_ref,
)
from tg_model.model.elements import Element, Part, RequirementBlock, System
from tg_model.model.refs import AttributeRef, PartRef, PortRef, Ref, RequirementBlockRef

__all__ = [
    "AttributeRef",
    "Element",
    "ModelDefinitionContext",
    "ModelDefinitionError",
    "Part",
    "PartRef",
    "PortRef",
    "Ref",
    "RequirementBlock",
    "RequirementBlockRef",
    "System",
    "parameter_ref",
    "requirement_ref",
    "rollup",
]
