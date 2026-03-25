"""tg-model: Executable systems modeling in Python."""

from tg_model.model.declarations.values import rollup
from tg_model.model.definition_context import ModelDefinitionContext, ModelDefinitionError, parameter_ref
from tg_model.model.elements import Element, Part, System
from tg_model.model.refs import AttributeRef, PartRef, PortRef, Ref

__all__ = [
    "AttributeRef",
    "Element",
    "ModelDefinitionContext",
    "ModelDefinitionError",
    "parameter_ref",
    "Part",
    "PartRef",
    "PortRef",
    "Ref",
    "System",
    "rollup",
]
