"""parameter_ref: root parameters visible to nested define() without globals."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg, m
from unitflow.expr.expressions import QuantityExpr

from tg_model.execution.configured_model import instantiate
from tg_model.execution.graph_compiler import compile_graph
from tg_model.integrations.external_compute import ExternalComputeBinding
from tg_model.model.definition_context import ModelDefinitionError, parameter_ref
from tg_model.model.elements import Part, System
from tg_model.model.identity import qualified_name


class _StubExt:
    name = "stub"

    def compute(self, inputs):
        from tg_model.integrations.external_compute import ExternalComputeResult

        return ExternalComputeResult(value=Quantity(1.0, kg), provenance={})


class _Leaf(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        orbit = parameter_ref(_Mission, "scenario_orbit_m")
        assert orbit.owner_type is _Mission
        b = ExternalComputeBinding(_StubExt(), inputs={"orbit_m": orbit})
        model.attribute("tool_out_kg", unit=kg, computed_by=b)


class _Mission(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("scenario_orbit_m", unit=m)
        model.parameter("scenario_payload_kg", unit=kg)
        model.part("leaf", _Leaf)


class _ExprLeaf(Part):
    """Child part that references root parameters directly in expr= and constraint(expr=...)."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        local_mass = model.parameter("local_mass_kg", unit=kg)
        root_payload = parameter_ref(_ExprRoot, "payload_kg")
        model.attribute("total_kg", unit=kg, expr=local_mass + root_payload)
        model.constraint("total_positive", expr=local_mass + root_payload > Quantity(0, kg))
        model.constraint("payload_below_limit", expr=root_payload <= Quantity(500, kg))


class _ExprRoot(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("payload_kg", unit=kg)
        model.part("child", _ExprLeaf)


_ALL_TYPES = (_Mission, _Leaf, _ExprRoot, _ExprLeaf)


def setup_function() -> None:
    for t in _ALL_TYPES:
        t._reset_compilation()


def test_parameter_ref_resolves_during_root_compile() -> None:
    """Nested part define() runs while mission compile_type holds _tg_definition_context."""
    compiled = _Mission.compile()
    qname = qualified_name(_Leaf)
    leaf = compiled["child_types"][qname]
    meta = leaf["nodes"]["tool_out_kg"]["metadata"]
    cb = meta["_computed_by"]
    assert isinstance(cb, ExternalComputeBinding)
    orbit_ref = cb.inputs["orbit_m"]
    assert orbit_ref.owner_type is _Mission
    assert orbit_ref.path == ("scenario_orbit_m",)


def test_parameter_ref_wrong_name_raises() -> None:
    class _BadLeaf(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            parameter_ref(_BadMission, "nope")

    class _BadMission(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("scenario_orbit_m", unit=m)
            model.part("leaf", _BadLeaf)

    _BadMission._reset_compilation()
    _BadLeaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="no such parameter"):
        _BadMission.compile()


def test_parameter_ref_not_parameter_kind_raises() -> None:
    class _HasAttr(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.attribute("not_a_param", unit=kg, expr=QuantityExpr(Quantity(0, kg)))

    class _Bad(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            parameter_ref(_HasAttr, "not_a_param")

    class _Root(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.part("leaf", _Bad)

    _HasAttr.compile()
    _Root._reset_compilation()
    _Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="expected kind 'parameter'"):
        _Root.compile()


def test_leaf_compile_without_root_compiled_first_fails() -> None:
    """parameter_ref requires root compiled or mid-compile."""

    class _LonelyLeaf(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            parameter_ref(_Mission, "scenario_orbit_m")

    _Mission._reset_compilation()
    _LonelyLeaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="not compiling and not compiled"):
        _LonelyLeaf.compile()


def test_parameter_ref_in_child_attribute_expr() -> None:
    """parameter_ref used in a child part attribute expr= compiles and evaluates correctly."""
    cm = instantiate(_ExprRoot)
    inputs = {
        cm.payload_kg: Quantity(100, kg),
        cm.child.local_mass_kg: Quantity(50, kg),
    }
    result = cm.evaluate(inputs=inputs)
    assert result.passed, result.failures
    total = result.outputs[cm.child.total_kg.stable_id]
    assert total == Quantity(150, kg)


def test_parameter_ref_in_child_constraint_expr() -> None:
    """parameter_ref used in a child part constraint expr= resolves and checks correctly."""
    cm = instantiate(_ExprRoot)
    inputs = {
        cm.payload_kg: Quantity(100, kg),
        cm.child.local_mass_kg: Quantity(50, kg),
    }
    result = cm.evaluate(inputs=inputs)
    assert result.passed, result.failures
    constraint_names = {c.name.split(".")[-1] for c in result.constraint_results}
    assert "total_positive" in constraint_names
    assert "payload_below_limit" in constraint_names
    assert all(c.passed for c in result.constraint_results)


def test_parameter_ref_in_child_constraint_fails_when_violated() -> None:
    """Constraint referencing root parameter correctly detects a violation."""
    cm = instantiate(_ExprRoot)
    inputs = {
        cm.payload_kg: Quantity(600, kg),
        cm.child.local_mass_kg: Quantity(50, kg),
    }
    result = cm.evaluate(inputs=inputs)
    assert not result.passed
    failed = [c for c in result.constraint_results if not c.passed]
    failed_names = {c.name.split(".")[-1] for c in failed}
    assert "payload_below_limit" in failed_names


def test_parameter_ref_graph_compiles_with_cross_hierarchy_edges() -> None:
    """Compiled graph has dependency edges from root parameter to child expression nodes."""
    cm = instantiate(_ExprRoot)
    graph, _ = compile_graph(cm)
    root_payload_node = f"val:{cm.payload_kg.path_string}"
    child_total_expr = f"expr:{cm.child.total_kg.path_string}"
    assert root_payload_node in graph.nodes
    assert child_total_expr in graph.nodes
    deps = graph.dependencies_of(child_total_expr)
    assert root_payload_node in deps
