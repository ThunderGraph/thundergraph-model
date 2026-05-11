"""Definition-time recording API for :class:`~tg_model.execution.evaluation.Evaluation` subclasses.

:class:`ModelEvaluationContext` is passed as the ``model`` argument to
``Evaluation.define(cls, model)``.  It records:
  - The evaluation's display name and description.
  - The target ``System`` class.
  - Scenario default input values.

These are consumed by :meth:`~tg_model.execution.evaluation.Evaluation.run` and by
the projection layer's input-enumeration logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class EvaluationDefinitionError(Exception):
    """Raised when an ``Evaluation.define()`` call violates DSL rules."""


@dataclass
class EvalContext:
    """Frozen snapshot of everything declared inside ``define()``."""

    name: str
    doc: str
    system_cls: type
    scenario_defaults: dict[str, Any]  # relative path → Quantity


class ModelEvaluationContext:
    """Records declarations during ``Evaluation.define(cls, model)``.

    Methods mirror the tg-model DSL surface for consistency:
      - ``model.name(str)`` — display slug (required, exactly once).
      - ``model.doc(str)``  — description string (required, exactly once).
      - ``model.system(SystemClass)`` — target system class (required, exactly once).
      - ``model.scenario(path, quantity)`` — register one default input value.

    ``model.scenario(path, quantity)`` validates:
      - ``path`` is a non-empty string.
      - ``quantity`` is a ``unitflow.Quantity`` or plain number.

    Full path resolution against the live model occurs at projection time when
    ``_evaluation_record`` calls ``define()`` and validates each path via
    ``cm.handle(path)``.  This is the same timing as the old plain-module
    convention, but now structured and validatable.
    """

    def __init__(self, owner_type: type) -> None:
        self.owner_type = owner_type
        self._name: str | None = None
        self._doc: str | None = None
        self._system_cls: type | None = None
        self._scenario_defaults: dict[str, Any] = {}
        self._frozen = False

    def _check_frozen(self) -> None:
        if self._frozen:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: cannot mutate evaluation context after define() completes."
            )

    def name(self, human_name: str) -> None:
        """Declare the display slug for this evaluation scenario (required)."""
        self._check_frozen()
        if self._name is not None:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.name() called more than once"
            )
        if not isinstance(human_name, str) or not human_name.strip():
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.name() requires a non-empty string"
            )
        self._name = human_name

    def doc(self, text: str) -> None:
        """Declare a description for this evaluation scenario (required)."""
        self._check_frozen()
        if self._doc is not None:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.doc() called more than once"
            )
        if not isinstance(text, str) or not text.strip():
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.doc() requires a non-empty string"
            )
        self._doc = text

    def system(self, system_cls: type) -> None:
        """Declare the target System class for this evaluation (required)."""
        self._check_frozen()
        if self._system_cls is not None:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.system() called more than once"
            )
        from tg_model.model.elements import System
        if not (isinstance(system_cls, type) and issubclass(system_cls, System)):
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.system() requires a System subclass, "
                f"got {system_cls!r}"
            )
        self._system_cls = system_cls

    def scenario(self, path: str, quantity: Any) -> None:
        """Declare a default input value for the parameter at ``path``.

        Parameters
        ----------
        path : str
            Relative dotted path to the parameter slot under the system root
            (e.g. ``"mission.max_speed_m_s"`` or ``"power_budget_kw"``).
            Must be a non-empty string.  Full path resolution is deferred to
            projection time.
        quantity : Quantity or number
            Default value for the parameter.  Must be a ``unitflow.Quantity``
            or a plain numeric value.
        """
        self._check_frozen()
        if not isinstance(path, str) or not path.strip():
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.scenario() path must be a non-empty string, got {path!r}"
            )
        if path in self._scenario_defaults:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.scenario() duplicate path {path!r}"
            )
        self._scenario_defaults[path] = quantity

    def freeze(self) -> None:
        """Freeze context — called automatically by ``Evaluation._compile_eval()``."""
        if self._name is None:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.name() is required in Evaluation.define()"
            )
        if self._doc is None:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.doc() is required in Evaluation.define()"
            )
        if self._system_cls is None:
            raise EvaluationDefinitionError(
                f"{self.owner_type.__name__}: model.system() is required in Evaluation.define()"
            )
        self._frozen = True

    def build(self) -> EvalContext:
        """Return the frozen :class:`EvalContext` snapshot."""
        if not self._frozen:
            raise EvaluationDefinitionError("Context must be frozen before building.")
        return EvalContext(
            name=self._name,  # type: ignore[arg-type]
            doc=self._doc,  # type: ignore[arg-type]
            system_cls=self._system_cls,  # type: ignore[arg-type]
            scenario_defaults=dict(self._scenario_defaults),
        )
