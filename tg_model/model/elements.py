"""Authoring element types: :class:`Element`, :class:`Part`, :class:`System`, :class:`RequirementBlock`.

Subclasses implement :meth:`Element.define` to record declarations on
:class:`~tg_model.model.definition_context.ModelDefinitionContext` and call
:meth:`Element.compile` (usually implicitly) to build cached definition artifacts.

See Also
--------
tg_model.model.definition_context.ModelDefinitionContext
tg_model.execution.configured_model.instantiate
"""

from __future__ import annotations

from typing import Any

from tg_model.model.compile_types import compile_type


class Element:
    """Abstract base for all model element types.

    Subclasses implement :meth:`define` to record structure; compilation produces a
    cached dict artifact consumed by instantiation and graph compilation.

    Notes
    -----
    :meth:`compile` is idempotent per class. Use :meth:`_reset_compilation` only in tests.
    """

    _compiled_definition: dict[str, Any] | None = None

    @classmethod
    def define(cls, model: Any) -> None:
        """Declare this type's structure (override in subclasses).

        Parameters
        ----------
        model : ModelDefinitionContext
            Definition-time recorder passed by the compiler.
        """

    @classmethod
    def compile(cls) -> dict[str, Any]:
        """Compile this type's definition (cached on the class).

        Returns
        -------
        dict
            Compiled artifact (nodes, edges, registries) used by
            :func:`~tg_model.execution.configured_model.instantiate`.
        """
        if cls._compiled_definition is None:
            cls._compiled_definition = compile_type(cls)
        return cls._compiled_definition

    @classmethod
    def _reset_compilation(cls) -> None:
        """Clear cached compilation and definition hooks (**tests only**)."""
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
    """Structural part in a hierarchy (may own child parts, ports, values, behavior)."""


class RequirementBlock(Element):
    """Composable requirements subtree (nested requirements and citations).

    Register on a :class:`Part` or :class:`System` via
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_block`;
    navigate with :class:`~tg_model.model.refs.RequirementBlockRef` dot access.

    Notes
    -----
    ``define()`` may only declare ``requirement``, ``requirement_input``,
    ``requirement_attribute``, ``citation``, nested ``requirement_block``, and ``references``
    (enforced at compile). Prefer
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_accept_expr`
    plus :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_input` /
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_attribute`
    and :meth:`~tg_model.model.definition_context.ModelDefinitionContext.allocate` ``inputs=``
    (for inputs wired from the design) for acceptance that avoids part refs inside the block.
    """


class System(Element):
    """Top-level system element that composes parts (typical configured root type)."""
