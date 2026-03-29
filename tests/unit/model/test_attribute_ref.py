"""attribute_ref: root attributes visible to nested Part.define() like parameter_ref."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg
from unitflow.expr.expressions import QuantityExpr

from tg_model.model.definition_context import ModelDefinitionError, attribute_ref
from tg_model.model.elements import Part, System
from tg_model.model.identity import qualified_name


class _Leaf(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        snap = attribute_ref(_Mission, "sim_kg")
        model.attribute("mirrored_kg", unit=kg, expr=snap)


class _Mission(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.attribute("sim_kg", unit=kg, expr=QuantityExpr(Quantity(3, kg)))
        model.part("leaf", _Leaf)


def setup_function() -> None:
    _Mission._reset_compilation()
    _Leaf._reset_compilation()


def test_attribute_ref_resolves_during_root_compile() -> None:
    compiled = _Mission.compile()
    qname = qualified_name(_Leaf)
    leaf = compiled["child_types"][qname]
    meta = leaf["nodes"]["mirrored_kg"]["metadata"]
    expr = meta.get("_expr")
    assert expr is not None
    assert expr.owner_type is _Mission
    assert expr.path == ("sim_kg",)
    assert expr.kind == "attribute"


def test_attribute_ref_wrong_name_raises() -> None:
    class _BadLeaf(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            attribute_ref(_BadMission, "nope")

    class _BadMission(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.attribute("sim_kg", unit=kg, expr=QuantityExpr(Quantity(1, kg)))
            model.part("leaf", _BadLeaf)

    _BadMission._reset_compilation()
    _BadLeaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="no such attribute"):
        _BadMission.compile()


def test_attribute_ref_not_attribute_kind_raises() -> None:
    class _BadLeaf2(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            attribute_ref(_Root2, "only_param")

    class _Root2(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("only_param", unit=kg)
            model.part("leaf", _BadLeaf2)

    _Root2._reset_compilation()
    _BadLeaf2._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="expected kind 'attribute'"):
        _Root2.compile()
