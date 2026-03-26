"""Base element types for the tg-model authoring surface."""

from __future__ import annotations

from typing import Any

from tg_model.model.compile_types import compile_type


class Element:
    """Abstract base for all model element types.

    Subclasses define their structure by implementing the ``define``
    classmethod. The framework calls ``define`` during compilation and
    passes a ``ModelDefinitionContext`` that records declarations.
    """

    _compiled_definition: dict[str, Any] | None = None

    @classmethod
    def define(cls, model: Any) -> None:
        """Override to declare parts, ports, attributes, behavior, and relationships."""

    @classmethod
    def compile(cls) -> dict[str, Any]:
        """Compile this type's definition. Idempotent per type."""
        if cls._compiled_definition is None:
            cls._compiled_definition = compile_type(cls)
        return cls._compiled_definition

    @classmethod
    def _reset_compilation(cls) -> None:
        """Reset cached compilation. For testing only."""
        cls._compiled_definition = None
        if getattr(cls, "_tg_definition_context", None) is not None:
            cls._tg_definition_context = None
        for attr in (
            "_tg_behavior_spec",
            "_tg_action_effects",
            "_tg_initial_state_name",
            "_tg_decision_specs",
            "_tg_fork_join_specs",
            "_tg_merge_specs",
            "_tg_sequence_specs",
            "_tg_guard_predicates",
        ):
            if hasattr(cls, attr):
                delattr(cls, attr)


class Part(Element):
    """A concrete structural part in a system hierarchy."""


class RequirementBlock(Element):
    """A composable requirements subtree (nested requirements and citations).

    Use :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_block`
    from a :class:`Part` or :class:`System` ``define()`` to register a block; use
    :class:`~tg_model.model.refs.RequirementBlockRef` dot access for child requirements.

    ``define()`` may only declare ``requirement``, ``requirement_input``, ``citation``, nested
    ``requirement_block``, and ``references`` edges (enforced at compile time). Call
    ``model.requirement_accept_expr(...)`` to attach acceptance to a requirement using only
    ``requirement_input`` symbols; bind those inputs to parts with ``allocate(..., inputs=…)``
    on the configured root.
    """


class System(Element):
    """A top-level system element that composes parts."""
