"""Authoring element types: :class:`Element`, :class:`Part`, :class:`System`, :class:`Requirement`.

Subclasses implement :meth:`Element.define` to record declarations on
:class:`~tg_model.model.definition_context.ModelDefinitionContext` and call
:meth:`Element.compile` (usually implicitly) to build cached definition artifacts.

See Also
--------
tg_model.model.definition_context.ModelDefinitionContext
tg_model.execution.configured_model.instantiate
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tg_model.model.compile_types import compile_type

if TYPE_CHECKING:
    from tg_model.execution.configured_model import ConfiguredModel


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


class Requirement(Element):
    """Composable requirements package: nested requirements, inputs, citations, and package values.

    Register on a :class:`Part` or :class:`System` via
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_package`;
    navigate with :class:`~tg_model.model.refs.RequirementRef` dot access.

    Notes
    -----
    ``define()`` may declare package-level ``parameter``, ``attribute``, and ``constraint``,
    plus ``requirement``, ``requirement_input``, ``requirement_attribute``, ``citation``, nested
    ``requirement_package``, and ``references`` (enforced at compile).
    Prefer
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_accept_expr`
    plus :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_input` /
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_attribute`
    and :meth:`~tg_model.model.definition_context.ModelDefinitionContext.allocate` ``inputs=``
    (for inputs wired from the design) for acceptance that avoids part refs inside the package.

    Package-level ``parameter``, ``attribute``, and ``constraint`` nodes become
    :class:`~tg_model.execution.value_slots.ValueSlot` / graph nodes under the configured root
    (dot access e.g. ``configured_root.pkg.param_name``); expressions are validated during
    :meth:`compile`. Package-level slots do not yet support ``computed_by=`` or
    :class:`~tg_model.model.declarations.values.RollupDecl` in graph compilation; every package
    ``constraint`` must supply ``expr=`` (including constant expressions with no symbols).

    """


class System(Element):
    """Top-level system element that composes parts (typical configured root type)."""

    @classmethod
    def instantiate(cls) -> ConfiguredModel:
        """Build a :class:`~tg_model.execution.configured_model.ConfiguredModel` for this root type.

        Delegates to :func:`~tg_model.execution.configured_model.instantiate` — same behavior and
        no extra compilation path.

        Returns
        -------
        ConfiguredModel
            Frozen topology for graph compile and evaluation. A **new** instance on every call;
            there is no shared singleton configured model.

        Notes
        -----
        Call this on a **concrete** ``System`` subclass that implements :meth:`Element.define`
        for your program root. That is the same requirement as passing that class to
        :func:`~tg_model.execution.configured_model.instantiate`.

        The base :class:`System` type itself is not a valid configured root; ``System.instantiate()``
        fails the same way as ``instantiate(System)``.

        Configured roots that are :class:`Part` subclasses still use
        :func:`~tg_model.execution.configured_model.instantiate` only (no class method on
        :class:`Part`).

        See Also
        --------
        tg_model.execution.configured_model.instantiate
        """
        from tg_model.execution.configured_model import instantiate as instantiate_configured

        return instantiate_configured(cls)
