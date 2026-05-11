"""Phase 0 unit tests for the Evaluation base class, ConstraintResult, and stable_ids.

Covers the nine test cases specified in §9 of implementation_plan_v3.md:

  test_evaluation_base_class_dsl
  test_run_evaluation_default_impl
  test_run_evaluation_custom_impl
  test_on_run_complete_hook_fires
  test_constraint_result_blocked_emitted
  test_constraint_result_failed_with_operand_values
  test_constraint_result_passed
  test_blocked_makes_result_not_passed
  test_evaluation_issues_typed
  test_stable_ids_match_bundle_walker  (cross-validation)
"""

from __future__ import annotations

import pytest

from tg_model.execution.evaluation import Evaluation
from tg_model.execution.evaluator import EvaluationIssue, RunResult
from tg_model.execution.run_context import ConstraintResult
from tg_model.model.evaluation_context import EvaluationDefinitionError
from tg_model.model.elements import Part, Requirement, System


# ---------------------------------------------------------------------------
# Minimal test model (shared across tests)
# ---------------------------------------------------------------------------

# A Part with two parameters and one derived constraint.
class _PowerPart(Part):
    @classmethod
    def define(cls, model):
        from unitflow.catalogs.si import kW
        model.name("power_part")
        model.parameter("available_kw", unit=kW)
        model.parameter("required_kw", unit=kW)
        model.attribute("headroom_kw", unit=kW, expr=model.parameter("available_kw", unit=kW))  # noqa: F841


# Simpler Part: one input parameter + one constraint that compares two parameters.
class _MinPart(Part):
    @classmethod
    def define(cls, model):
        from unitflow.catalogs.si import kW
        model.name("min_part")
        p_avail = model.parameter("avail_kw", unit=kW)
        p_req   = model.parameter("req_kw",   unit=kW)
        headroom = model.attribute("headroom_kw", unit=kW, expr=p_avail - p_req)
        model.constraint("headroom_non_negative", expr=headroom >= 0 * kW)


class _MinSystem(System):
    @classmethod
    def define(cls, model):
        model.name("min_system")
        model.composed_of("part", _MinPart)


# ---------------------------------------------------------------------------
# Helper: minimal Evaluation subclass targeting _MinSystem
# ---------------------------------------------------------------------------

def _make_eval_cls(name: str = "test_eval", scenario_defaults: dict | None = None):
    """Return a fresh Evaluation subclass each time to avoid _eval_context cache collisions."""
    from unitflow.catalogs.si import kW

    _defaults = {
        "part.avail_kw": 10.0 * kW,
        "part.req_kw":   8.0 * kW,
    } if scenario_defaults is None else scenario_defaults

    class _Eval(Evaluation):
        @classmethod
        def define(cls, model):
            model.name(name)
            model.doc(f"Test evaluation: {name}")
            model.system(_MinSystem)
            for path, qty in _defaults.items():
                model.scenario(path, qty)

    _Eval.__name__ = f"_Eval_{name}"
    _Eval.__qualname__ = f"_Eval_{name}"
    return _Eval


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvaluationBaseClassDsl:
    """test_evaluation_base_class_dsl — §9 plan."""

    def test_name_doc_system_scenario_stored(self):
        cls = _make_eval_cls("dsl_happy")
        ctx = cls._compile_eval()
        assert ctx.name == "dsl_happy"
        assert "dsl_happy" in ctx.doc
        assert ctx.system_cls is _MinSystem
        assert "part.avail_kw" in ctx.scenario_defaults

    def test_missing_name_raises_definition_error(self):
        class _BadEval(Evaluation):
            @classmethod
            def define(cls, model):
                model.doc("forgot name")
                model.system(_MinSystem)

        with pytest.raises(EvaluationDefinitionError, match="model.name()"):
            _BadEval._compile_eval()

    def test_missing_doc_raises_definition_error(self):
        class _BadEval(Evaluation):
            @classmethod
            def define(cls, model):
                model.name("no_doc")
                model.system(_MinSystem)

        with pytest.raises(EvaluationDefinitionError, match="model.doc()"):
            _BadEval._compile_eval()

    def test_missing_system_raises_definition_error(self):
        class _BadEval(Evaluation):
            @classmethod
            def define(cls, model):
                model.name("no_system")
                model.doc("missing system")

        with pytest.raises(EvaluationDefinitionError, match="model.system()"):
            _BadEval._compile_eval()

    def test_duplicate_name_raises(self):
        class _BadEval(Evaluation):
            @classmethod
            def define(cls, model):
                model.name("a")
                model.name("a")  # duplicate

        with pytest.raises(EvaluationDefinitionError):
            _BadEval._compile_eval()

    def test_duplicate_scenario_path_raises(self):
        class _BadEval(Evaluation):
            @classmethod
            def define(cls, model):
                from unitflow.catalogs.si import kW
                model.name("dup_scenario")
                model.doc("dup")
                model.system(_MinSystem)
                model.scenario("part.avail_kw", 5.0 * kW)
                model.scenario("part.avail_kw", 6.0 * kW)  # duplicate path

        with pytest.raises(EvaluationDefinitionError):
            _BadEval._compile_eval()


class TestRunEvaluationDefaultImpl:
    """test_run_evaluation_default_impl — §9 plan."""

    def test_returns_run_result_with_constraint_entries(self):
        cls = _make_eval_cls("default_impl")
        result = cls.run()
        assert isinstance(result, RunResult)
        assert len(result.constraint_results) >= 1

    def test_passed_when_all_constraints_satisfied(self):
        cls = _make_eval_cls("default_impl_pass")
        result = cls.run()
        assert result.passed

    def test_diagnostic_output_attached(self):
        cls = _make_eval_cls("default_impl_diag")
        result = cls.run()
        assert hasattr(result, "_diagnostic_output")
        assert isinstance(result._diagnostic_output, list)


class TestRunEvaluationCustomImpl:
    """test_run_evaluation_custom_impl — §9 plan."""

    def test_custom_impl_validate_false_called_and_result_returned(self):
        from unitflow.catalogs.si import kW

        class _CustomEval(Evaluation):
            custom_called = False

            @classmethod
            def define(cls, model):
                model.name("custom_impl")
                model.doc("Tests custom run_evaluation override.")
                model.system(_MinSystem)
                model.scenario("part.avail_kw", 10.0 * kW)
                model.scenario("part.req_kw",   8.0 * kW)

            def run_evaluation(self, cm, inputs):
                _CustomEval.custom_called = True
                return cm.evaluate(inputs=inputs, validate=False)

        result = _CustomEval.run()
        assert _CustomEval.custom_called
        assert isinstance(result, RunResult)
        assert result.passed


class TestOnRunCompleteHookFires:
    """test_on_run_complete_hook_fires — §9 plan."""

    def test_log_output_captured_in_diagnostic_output(self):
        from unitflow.catalogs.si import kW

        class _LogEval(Evaluation):
            @classmethod
            def define(cls, model):
                model.name("log_hook")
                model.doc("Tests on_run_complete self.log()")
                model.system(_MinSystem)
                model.scenario("part.avail_kw", 10.0 * kW)
                model.scenario("part.req_kw",   8.0 * kW)

            def on_run_complete(self, result):
                self.log("hello from hook")
                self.log(f"passed={result.passed}")

        result = _LogEval.run()
        assert "hello from hook" in result._diagnostic_output
        assert any("passed=" in line for line in result._diagnostic_output)

    def test_hook_exception_goes_to_diagnostic_not_status(self):
        from unitflow.catalogs.si import kW

        class _BrokenHook(Evaluation):
            @classmethod
            def define(cls, model):
                model.name("broken_hook")
                model.doc("Hook raises but run status stays unchanged.")
                model.system(_MinSystem)
                model.scenario("part.avail_kw", 10.0 * kW)
                model.scenario("part.req_kw",   8.0 * kW)

            def on_run_complete(self, result):
                raise RuntimeError("intentional diagnostic error")

        result = _BrokenHook.run()
        # The run itself succeeded — status must reflect the evaluation, not the hook.
        assert result.passed
        # The hook exception goes to the diagnostic buffer.
        assert any("[diagnostic error]" in line for line in result._diagnostic_output)


class TestConstraintResultBlockedEmitted:
    """test_constraint_result_blocked_emitted — §9 plan.

    A required parameter with no bound value must produce state="blocked" on every
    constraint that depends on it.  Before Phase 0, these were silently skipped.
    """

    def test_blocked_constraint_emitted_for_missing_input(self):
        cls = _make_eval_cls("blocked_test", scenario_defaults={})  # no defaults — all required
        result = cls.run({})  # no overrides either
        # Every constraint should be blocked (not silently missing).
        assert len(result.constraint_results) >= 1, "Constraints must be emitted, not skipped"
        assert all(cr.state == "blocked" for cr in result.constraint_results), (
            f"Expected all blocked, got: {[cr.state for cr in result.constraint_results]}"
        )

    def test_blocked_state_accessible_via_public_state_property(self):
        cls = _make_eval_cls("blocked_state_prop", scenario_defaults={})
        result = cls.run({})
        for cr in result.constraint_results:
            # state must be a public, readable attribute — not _state.
            assert cr.state == "blocked"
            # passed is computed from state.
            assert not cr.passed


class TestConstraintResultFailedWithOperandValues:
    """test_constraint_result_failed_with_operand_values — §9 plan."""

    def test_failed_constraint_has_operand_values(self):
        from unitflow.catalogs.si import kW
        cls = _make_eval_cls("failed_test", scenario_defaults={
            "part.avail_kw": 5.0 * kW,    # avail < req → fails
            "part.req_kw":   10.0 * kW,
        })
        result = cls.run()
        failing = [cr for cr in result.constraint_results if cr.state == "failed"]
        assert len(failing) >= 1, "Expected at least one failing constraint"
        for cr in failing:
            # operand_values must be populated so the user can see what was compared.
            assert cr.operand_values, (
                f"Failing constraint '{cr.name}' has no operand_values — "
                "user cannot diagnose the failure"
            )

    def test_failed_constraint_has_expression_str(self):
        from unitflow.catalogs.si import kW
        cls = _make_eval_cls("failed_expr", scenario_defaults={
            "part.avail_kw": 5.0 * kW,
            "part.req_kw":   10.0 * kW,
        })
        result = cls.run()
        failing = [cr for cr in result.constraint_results if cr.state == "failed"]
        assert len(failing) >= 1
        for cr in failing:
            assert cr.expression_str, (
                f"Failing constraint '{cr.name}' has no expression_str"
            )


class TestConstraintResultPassed:
    """test_constraint_result_passed — §9 plan."""

    def test_passing_constraint_has_state_passed(self):
        cls = _make_eval_cls("passed_test")  # avail=10 > req=8 — passes
        result = cls.run()
        assert result.passed
        for cr in result.constraint_results:
            assert cr.state == "passed"
            assert cr.passed is True

    def test_passed_state_accessible_via_public_property(self):
        cls = _make_eval_cls("passed_state")
        result = cls.run()
        for cr in result.constraint_results:
            # Both the property and direct state access must work.
            assert cr.state == "passed"
            assert cr.passed is True


class TestBlockedMakesResultNotPassed:
    """test_blocked_makes_result_not_passed — §9 plan."""

    def test_one_blocked_marks_result_failed(self):
        from unitflow.catalogs.si import kW
        # Provide only one of the two required inputs — req_kw is missing.
        cls = _make_eval_cls("mixed_blocked", scenario_defaults={
            "part.avail_kw": 10.0 * kW,
            # "part.req_kw" intentionally omitted → constraint will be blocked
        })
        result = cls.run()
        assert not result.passed, "A blocked constraint must make the run not-passed"
        states = {cr.state for cr in result.constraint_results}
        assert "blocked" in states, f"Expected at least one blocked, got: {states}"

    def test_constraint_results_all_present_not_silently_missing(self):
        """No constraints may disappear from the result — the previous bug was silent skipping."""
        cls = _make_eval_cls("no_missing", scenario_defaults={})
        result = cls.run({})
        # We know the model has exactly 1 constraint (headroom_non_negative).
        assert len(result.constraint_results) == 1, (
            f"Expected 1 constraint result, got {len(result.constraint_results)} "
            f"— constraints are being silently dropped"
        )


class TestEvaluationIssuesTyped:
    """test_evaluation_issues_typed — §9 plan."""

    def test_missing_input_produces_evaluation_issue(self):
        cls = _make_eval_cls("issues_test", scenario_defaults={})
        result = cls.run({})
        assert len(result.issues) >= 1, "Missing inputs must produce EvaluationIssue entries"
        for issue in result.issues:
            assert isinstance(issue, EvaluationIssue)
            assert issue.kind == "missing_input"
            assert issue.message

    def test_failures_backward_compat_returns_messages(self):
        """result.failures is a backward-compat list of message strings."""
        cls = _make_eval_cls("failures_compat", scenario_defaults={})
        result = cls.run({})
        # failures is computed from issues — it must be a list of strings.
        failures = result.failures
        assert isinstance(failures, list)
        assert all(isinstance(f, str) for f in failures)
        assert len(failures) == len(result.issues)


class TestStableIdsMatchBundleWalker:
    """test_stable_ids_match_bundle_walker — §9 plan.

    Verifies that class_scoped_constraint_sid() and class_scoped_slot_sid() from
    tg_model.execution.stable_ids produce results that:
      1. Follow the expected format (prefix + module + qualname + local_name).
      2. Are consistent with the element record stable_ids stored by bundle_walker.

    The cross-validation is done by comparing against the formula that bundle_walker
    uses in _element_record / _value_slot_record — both now delegate to stable_ids.py,
    so this test verifies the module is importable and produces well-formed IDs.
    """

    def test_class_scoped_constraint_sid_format(self):
        from tg_model.execution.stable_ids import class_scoped_constraint_sid

        cm = _MinSystem.instantiate()
        constraint_elements = [
            obj for obj in cm.id_registry.values()
            if getattr(obj, "kind", None) == "constraint"
        ]
        assert constraint_elements, "Test model must have at least one constraint"

        for element in constraint_elements:
            sid = class_scoped_constraint_sid(element, cm.path_registry)
            assert sid is not None
            assert sid.startswith("class_constraint:"), f"Bad format: {sid!r}"
            # Must contain module, qualname, and local name.
            parts = sid.split(":")
            assert len(parts) == 3, f"Expected 3 colon-delimited parts in: {sid!r}"
            assert "." in parts[1], f"Module.qualname part has no dot: {parts[1]!r}"
            local_name = element.instance_path[-1]
            assert parts[2] == local_name, (
                f"Local name mismatch: expected {local_name!r}, got {parts[2]!r}"
            )

    def test_class_scoped_slot_sid_format(self):
        from tg_model.execution.stable_ids import class_scoped_slot_sid
        from tg_model.execution.value_slots import ValueSlot

        cm = _MinSystem.instantiate()
        slots = [
            obj for obj in cm.path_registry.values()
            if isinstance(obj, ValueSlot)
        ]
        assert slots, "Test model must have at least one value slot"

        for slot in slots:
            sid = class_scoped_slot_sid(slot, cm.path_registry)
            assert sid is not None
            assert sid.startswith("class_slot:"), f"Bad format: {sid!r}"
            parts = sid.split(":")
            assert len(parts) == 3, f"Expected 3 colon-delimited parts in: {sid!r}"
            assert "." in parts[1], f"Module.qualname part has no dot: {parts[1]!r}"

    def test_constraint_sid_matches_bundle_walker_element_record(self):
        """The stable_id produced by class_scoped_constraint_sid must match the one
        that bundle_walker's _element_record writes to Neo4j for the same element."""
        import sys
        sys.path.insert(0, ".")

        from tg_model.execution.stable_ids import class_scoped_constraint_sid

        cm = _MinSystem.instantiate()
        for obj in cm.id_registry.values():
            if getattr(obj, "kind", None) != "constraint":
                continue
            # Replicate the formula _element_record uses directly (same as stable_ids.py).
            from tg_model.execution.instances import RequirementPackageInstance
            local_name = obj.instance_path[-1]
            ip = obj.instance_path
            expected_cls = None
            for i in range(len(ip) - 1, 0, -1):
                parent = cm.path_registry.get(".".join(ip[:i]))
                if isinstance(parent, RequirementPackageInstance):
                    expected_cls = parent.package_type
                    break
            if expected_cls is None:
                expected_cls = obj.definition_type
            expected_sid = f"class_constraint:{expected_cls.__module__}.{expected_cls.__qualname__}:{local_name}"
            actual_sid = class_scoped_constraint_sid(obj, cm.path_registry)
            assert actual_sid == expected_sid, (
                f"stable_ids.class_scoped_constraint_sid mismatch for {local_name!r}: "
                f"got {actual_sid!r}, expected {expected_sid!r}"
            )

    def test_slot_sid_matches_bundle_walker_value_slot_record(self):
        """The stable_id produced by class_scoped_slot_sid must match the one
        that bundle_walker's _value_slot_record writes to Neo4j for the same slot."""
        from tg_model.execution.instances import PartInstance, RequirementPackageInstance
        from tg_model.execution.stable_ids import class_scoped_slot_sid
        from tg_model.execution.value_slots import ValueSlot

        cm = _MinSystem.instantiate()
        for obj in cm.path_registry.values():
            if not isinstance(obj, ValueSlot):
                continue
            local_name = obj.definition_path[-1] if obj.definition_path else (
                obj.instance_path[-1] if obj.instance_path else ""
            )
            # Replicate the formula _value_slot_record uses.
            ip = obj.instance_path
            expected_cls = None
            for i in range(len(ip) - 1, 0, -1):
                parent = cm.path_registry.get(".".join(ip[:i]))
                if isinstance(parent, RequirementPackageInstance):
                    expected_cls = parent.package_type
                    break
                if isinstance(parent, PartInstance):
                    expected_cls = parent.definition_type
                    break
            if expected_cls is None:
                continue  # no match expected — stable_ids returns None too
            expected_sid = f"class_slot:{expected_cls.__module__}.{expected_cls.__qualname__}:{local_name}"
            actual_sid = class_scoped_slot_sid(obj, cm.path_registry)
            assert actual_sid == expected_sid, (
                f"stable_ids.class_scoped_slot_sid mismatch for {local_name!r}: "
                f"got {actual_sid!r}, expected {expected_sid!r}"
            )
