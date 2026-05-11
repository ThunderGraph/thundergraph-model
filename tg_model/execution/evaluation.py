"""``Evaluation`` base class for authoring executable evaluation scenarios.

Users subclass ``Evaluation`` to define a scenario:

    from tg_model.execution.evaluation import Evaluation

    class NominalLoad(Evaluation):
        @classmethod
        def define(cls, model):
            model.name("nominal_load")
            model.doc("Verify the system meets power and thermal budgets under nominal load.")
            model.system(MySystem)
            model.scenario("power_budget_kw", 10.0 * kW)

Subclasses may override ``run_evaluation`` or ``on_run_complete`` for custom
diagnostics; the base-class implementations provide standard behavior.

Runner protocol: the subprocess runner calls ``cls.run(overrides)`` — a classmethod
that orchestrates instantiation, input binding, evaluation, and the post-run hook.
The result includes ``diagnostic_output`` from any ``self.log()`` calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tg_model.execution.configured_model import ConfiguredModel
    from tg_model.execution.evaluator import RunResult
    from tg_model.model.evaluation_context import EvalContext


class Evaluation:
    """Base class for executable evaluation scenarios.

    DSL surface (call inside ``define()`` classmethod):
      - ``model.name(str)``         — required display slug.
      - ``model.doc(str)``          — required description.
      - ``model.system(SystemClass)`` — required target system.
      - ``model.scenario(path, qty)`` — default input value for one parameter.

    Runtime surface (override in subclass):
      - ``run_evaluation(self, cm, inputs) → RunResult``
        Controls how evaluation executes.  Default: ``cm.evaluate(inputs=inputs)``.
      - ``on_run_complete(self, result) → None``
        Called after evaluation completes.  Default: no-op.
        Use ``self.log(message)`` to emit diagnostic lines.

    Orchestration (do NOT override):
      - ``run(cls, overrides) → RunResult`` — classmethod called by subprocess runner.
    """

    # Set by _compile_eval() after the first define() call.
    _eval_context: "EvalContext | None" = None  # type: ignore[name-defined]

    def __init__(self) -> None:
        self._log_buffer: list[str] = []

    # ------------------------------------------------------------------
    # DSL authoring — override this in subclasses
    # ------------------------------------------------------------------

    @classmethod
    def define(cls, model: Any) -> None:
        """Declare the evaluation's DSL properties.

        Override this classmethod and call ``model.name()``, ``model.doc()``,
        ``model.system()``, and optionally ``model.scenario()`` to register
        defaults.
        """
        pass

    # ------------------------------------------------------------------
    # Runtime seams — override these in subclasses for custom behaviour
    # ------------------------------------------------------------------

    def run_evaluation(self, cm: "ConfiguredModel", inputs: dict) -> "RunResult":
        """Execute the evaluation.  Default: ``cm.evaluate(inputs=inputs)``.

        Subclasses may override to call ``cm.evaluate(validate=False)`` for
        tight loops, run multiple scenarios, call external tools, etc.
        Must return a :class:`~tg_model.execution.evaluator.RunResult`.
        """
        return cm.evaluate(inputs=inputs)

    def on_run_complete(self, result: "RunResult") -> None:
        """Hook called after :meth:`run_evaluation` returns successfully.

        Default is a no-op.  Override to emit diagnostics, summary tables, or
        custom artifacts.  Use ``self.log(message)`` to append lines to the
        diagnostic buffer — output is captured and returned to the dashboard
        terminal even if ``on_run_complete`` raises.
        """
        pass

    def log(self, message: str) -> None:
        """Append ``message`` to the diagnostic buffer.

        Only valid during ``run_evaluation`` or ``on_run_complete``.
        Calling from ``define()`` has no effect because there is no live instance.
        """
        self._log_buffer.append(str(message))

    # ------------------------------------------------------------------
    # Orchestration — do NOT override
    # ------------------------------------------------------------------

    @classmethod
    def run(
        cls,
        overrides: dict[str, Any] | None = None,
        *,
        _configured_model: "ConfiguredModel | None" = None,
    ) -> "RunResult":
        """Orchestrate a complete evaluation run.

        Called by the subprocess runner: ``cls.run(overrides)``.

        1. Compile eval context (lazy, first time only).
        2. Instantiate the target system (or use ``_configured_model`` if provided).
        3. Resolve scenario defaults into slot-stable-id inputs; apply overrides.
        4. Call ``run_evaluation()``.
        5. Call ``on_run_complete()`` on success.
        6. Return the result with ``diagnostic_output`` attached.

        The diagnostic buffer (``self.log()`` output) is always captured in a
        ``finally`` block — it is included in every result regardless of whether
        ``run_evaluation`` or ``on_run_complete`` raised.

        Parameters
        ----------
        overrides:
            Slot-stable-id → value dict of user-supplied inputs.  Wins over
            scenario defaults declared in ``define()``.
        _configured_model:
            Optional pre-instantiated :class:`~tg_model.execution.configured_model.ConfiguredModel`.
            When provided, instantiation is skipped (avoids redundant work when the
            caller already holds a model instance).
        """
        from tg_model.execution.evaluator import EvaluationIssue, RunResult

        # Guard _compile_eval() — a buggy define() must produce a usable error result.
        try:
            ctx = cls._compile_eval()
        except Exception as exc:
            err = RunResult(issues=[EvaluationIssue(kind="compute_error", path="", message=str(exc))])
            err._diagnostic_output = []  # type: ignore[attr-defined]
            return err

        instance = cls()
        result: RunResult | None = None

        try:
            from tg_model.execution.configured_model import instantiate as _instantiate
            cm = _configured_model if _configured_model is not None else _instantiate(ctx.system_cls)
            resolved_inputs = _resolve_scenario_defaults(cm, ctx.system_cls.__name__, ctx.scenario_defaults)
            if overrides:
                resolved_inputs.update(overrides)

            result = instance.run_evaluation(cm, resolved_inputs)

            if not isinstance(result, RunResult):
                instance._log_buffer.append(
                    f"[run_evaluation error]: expected RunResult, got {type(result).__name__}"
                )
                result = RunResult(issues=[EvaluationIssue(
                    kind="compute_error",
                    path="",
                    message=f"run_evaluation() must return RunResult, got {type(result).__name__}",
                )])
            else:
                try:
                    instance.on_run_complete(result)
                except Exception as exc:
                    instance._log_buffer.append(f"[diagnostic error]: {exc}")

        except Exception as exc:
            import traceback as _tb
            instance._log_buffer.append(f"[run_evaluation error]: {exc}\n{_tb.format_exc()}")
            result = RunResult(issues=[EvaluationIssue(kind="compute_error", path="", message=str(exc))])

        finally:
            if result is None:
                result = RunResult()
            result._diagnostic_output = list(instance._log_buffer)  # type: ignore[attr-defined]

        return result

    # ------------------------------------------------------------------
    # Compilation (lazy, once per subclass)
    # ------------------------------------------------------------------

    @classmethod
    def _compile_eval(cls) -> "EvalContext":
        """Run ``define()`` once and cache the result as ``cls._eval_context``."""
        from tg_model.model.evaluation_context import EvalContext, ModelEvaluationContext

        if cls._eval_context is not None and cls._eval_context.__class__ is EvalContext:
            return cls._eval_context  # type: ignore[return-value]

        ctx = ModelEvaluationContext(owner_type=cls)
        cls.define(ctx)
        ctx.freeze()
        result = ctx.build()
        cls._eval_context = result  # type: ignore[assignment]
        return result


def _resolve_scenario_defaults(
    cm: "ConfiguredModel",
    system_class_name: str,
    scenario_defaults: dict[str, Any],
) -> dict[str, Any]:
    """Resolve relative slot paths to slot stable-ids.

    Parameters
    ----------
    cm:
        Instantiated ConfiguredModel for the evaluation's target system.
    system_class_name:
        ``SYSTEM.__name__`` — used to form absolute paths like
        ``"MySystem.mission.max_speed"``.
    scenario_defaults:
        ``{relative_path: value}`` declared by ``model.scenario()``.

    Returns
    -------
    dict
        ``{slot.stable_id: value}`` ready for ``cm.evaluate(inputs=...)``.
    """
    from tg_model.execution.value_slots import ValueSlot

    resolved: dict[str, Any] = {}
    for rel_path, value in scenario_defaults.items():
        abs_path = f"{system_class_name}.{rel_path}"
        try:
            obj = cm.handle(abs_path)
        except KeyError:
            # Path doesn't resolve — skip silently; the evaluator will mark it
            # as a missing_input issue when the constraint needs it.
            continue
        if isinstance(obj, ValueSlot):
            resolved[obj.stable_id] = value
    return resolved
