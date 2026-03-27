"""ConfiguredModel.evaluate facade and compile_graph cache sharing."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import GraphCompilationError, compile_graph
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import GraphValidationError, ValidationResult
from tg_model.model.elements import Part, System


class _Leaf(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("mass_kg", unit=kg)


class _Root(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.part("leaf", _Leaf)


def setup_function() -> None:
    _Root._reset_compilation()
    _Leaf._reset_compilation()


def test_compile_graph_caches_on_configured_model() -> None:
    cm = instantiate(_Root)
    g1, h1 = compile_graph(cm)
    g2, h2 = compile_graph(cm)
    assert g1 is g2
    assert h1 is h2


def test_evaluate_primes_compile_graph_cache() -> None:
    """§5.2 / §9.2: first ``evaluate`` compiles; later ``compile_graph`` reuses the same tuple."""
    cm = instantiate(_Root)
    cm.evaluate(inputs={cm.leaf.mass_kg: Quantity(1.0, kg)})
    g1, h1 = compile_graph(cm)
    g2, h2 = compile_graph(cm)
    assert g1 is g2
    assert h1 is h2


def test_evaluate_matches_explicit_pipeline() -> None:
    cm = instantiate(_Root)
    inputs = {cm.leaf.mass_kg: Quantity(2.5, kg)}
    result_facade = cm.evaluate(inputs=inputs)
    graph, handlers = compile_graph(cm)
    inputs_by_id = {slot.stable_id: val for slot, val in inputs.items()}
    result_explicit = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs=inputs_by_id,
    )
    assert result_facade.passed == result_explicit.passed
    assert result_facade.failures == result_explicit.failures


def test_evaluate_accepts_stable_id_str_keys() -> None:
    cm = instantiate(_Root)
    sid = cm.leaf.mass_kg.stable_id
    result = cm.evaluate(inputs={sid: Quantity(1.0, kg)})
    assert result.passed


def test_evaluate_rejects_foreign_value_slot() -> None:
    cm_a = instantiate(_Root)
    cm_b = instantiate(_Root)
    with pytest.raises(ValueError, match="not registered on this ConfiguredModel"):
        cm_a.evaluate(inputs={cm_b.leaf.mass_kg: Quantity(1.0, kg)})


def test_evaluate_rejects_non_slot_str_key() -> None:
    """String keys must refer to a ValueSlot in the id registry, not parts or elements."""
    cm = instantiate(_Root)
    part_id = cm.leaf.stable_id
    with pytest.raises(ValueError, match="not a ValueSlot"):
        cm.evaluate(inputs={part_id: Quantity(1.0, kg)})


def test_evaluate_rejects_bad_key_type() -> None:
    cm = instantiate(_Root)
    with pytest.raises(TypeError, match="ValueSlot or str"):
        cm.evaluate(inputs={123: Quantity(1.0, kg)})  # type: ignore[dict-item]


def test_evaluate_unknown_stable_id_str_key_raises_keyerror() -> None:
    cm = instantiate(_Root)
    with pytest.raises(KeyError, match="Unknown stable_id"):
        cm.evaluate(inputs={"definitely-not-a-slot-id-xyz": Quantity(1.0, kg)})


def test_evaluate_missing_required_inputs_matches_explicit_pipeline() -> None:
    """Runtime gaps surface in RunResult; façade matches explicit evaluator."""
    cm = instantiate(_Root)
    result_facade = cm.evaluate(inputs={})
    graph, handlers = compile_graph(cm)
    result_explicit = Evaluator(graph, compute_handlers=handlers).evaluate(RunContext(), inputs={})
    assert result_facade.passed == result_explicit.passed
    assert result_facade.failures == result_explicit.failures
    assert len(result_facade.constraint_results) == len(result_explicit.constraint_results)
    assert [c.passed for c in result_facade.constraint_results] == [
        c.passed for c in result_explicit.constraint_results
    ]


def test_evaluate_propagates_graph_compilation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_model: object) -> tuple[object, object]:
        raise GraphCompilationError("forced compile failure")

    monkeypatch.setattr("tg_model.execution.graph_compiler.compile_graph", _boom)
    cm = instantiate(_Root)
    with pytest.raises(GraphCompilationError, match="forced compile failure"):
        cm.evaluate(inputs={cm.leaf.mass_kg: Quantity(1.0, kg)})


def test_evaluate_propagates_graph_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(
        graph: object,
        *,
        configured_model: object | None = None,
    ) -> ValidationResult:
        r = ValidationResult()
        r.add("forced", "validation blocked")
        return r

    monkeypatch.setattr("tg_model.execution.validation.validate_graph", _fail)
    cm = instantiate(_Root)
    with pytest.raises(GraphValidationError) as exc_info:
        cm.evaluate(inputs={cm.leaf.mass_kg: Quantity(1.0, kg)})
    assert exc_info.value.result.failures[0].message == "validation blocked"


def test_evaluate_validate_false_skips_validate_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    cm = instantiate(_Root)

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("validate_graph should not be called when validate=False")

    monkeypatch.setattr("tg_model.execution.validation.validate_graph", _boom)
    result = cm.evaluate(inputs={cm.leaf.mass_kg: Quantity(1.0, kg)}, validate=False)
    assert result.passed
