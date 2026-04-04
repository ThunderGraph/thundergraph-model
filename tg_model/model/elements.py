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
    """Composable requirements package — **use ``parameter`` / ``attribute`` / ``constraint``**.

    **DEFAULT PATTERN (always start here):** Inside ``define(cls, model)``, declare
    ``model.parameter``, ``model.attribute``, and ``model.constraint`` at **package scope** —
    the same value/check authoring surface as :class:`Part` (unlike :class:`System`,
    which is restricted to structural composition and top-level parameters). Use
    ``model.requirement(id, text)`` for leaf traceability statements, ``model.citation`` for
    provenance, ``model.references`` for edges, and ``model.allocate`` for structural allocation.
    **This is the standard, recommended API for all new requirement packages.**

    Register on a :class:`Part` or :class:`System` via
    :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_package`;
    navigate with :class:`~tg_model.model.refs.RequirementRef` dot access.

    **Advanced (rare — leaf reqcheck only):** ``requirement_input``, ``requirement_attribute``,
    and ``requirement_accept_expr`` are low-level helpers for INCOSE-style executable acceptance
    on a **single leaf** ``model.requirement(...)``, wired through ``allocate(..., inputs=...)``.
    Use them **only** when you need ``summarize_requirement_satisfaction`` per-requirement rows.
    **Do not use them as the default pattern.** If your check can be a package-level
    ``constraint``, use that instead.

    Notes
    -----
    Package-level ``parameter``, ``attribute``, and ``constraint`` nodes become
    :class:`~tg_model.execution.value_slots.ValueSlot` / graph nodes under the configured root
    (dot access e.g. ``configured_root.pkg.param_name``); expressions are validated during
    :meth:`compile`. Package-level slots do not yet support ``computed_by=`` or
    :class:`~tg_model.model.declarations.values.RollupDecl` in graph compilation; every package
    ``constraint`` must supply ``expr=`` (including constant expressions with no symbols).
    """


class System(Element):
    """Top-level system element for composition and top-level input parameters.

    ``System.define()`` is intentionally structural: compose child parts, declare
    ports/requirements/citations as needed, and keep mission or scenario inputs as
    top-level ``parameter(...)`` declarations. Derived values and executable checks
    belong on owned :class:`Part` instances or requirement packages, not on the
    root ``System`` itself.
    """

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
