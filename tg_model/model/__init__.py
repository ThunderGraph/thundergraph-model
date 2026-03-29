"""Public modeling API: elements, definition context, refs, and expression helpers.

Everything here is **definition-time** (``define(cls, model)``): symbolic refs,
declarations recorded on :class:`~tg_model.model.definition_context.ModelDefinitionContext`,
and helpers such as :func:`~tg_model.model.expr.sum_attributes` for unitflow-safe roll-ups.

See Also
--------
tg_model.execution
    Configure (instantiate) and evaluate compiled models.
"""

from tg_model.model.definition_context import ModelDefinitionContext, parameter_ref, requirement_ref
from tg_model.model.elements import Element, Part, Requirement, System
from tg_model.model.expr import as_expr_leaf, sum_attributes
from tg_model.model.refs import AttributeRef, PartRef, PortRef, Ref, RequirementRef

__all__ = [
    "AttributeRef",
    "Element",
    "ModelDefinitionContext",
    "Part",
    "PartRef",
    "PortRef",
    "Ref",
    "Requirement",
    "RequirementRef",
    "System",
    "as_expr_leaf",
    "parameter_ref",
    "requirement_ref",
    "sum_attributes",
]
