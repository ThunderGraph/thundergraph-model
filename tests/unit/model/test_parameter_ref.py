"""parameter_ref: root parameters visible to nested define() without globals."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg, m
from unitflow.expr.expressions import QuantityExpr

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


def setup_function() -> None:
    _Mission._reset_compilation()
    _Leaf._reset_compilation()


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
    class _HasAttr(System):
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
