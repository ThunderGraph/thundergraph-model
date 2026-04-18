"""attribute_ref: root attributes visible to nested Part.define() like parameter_ref."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg
from unitflow.expr.expressions import QuantityExpr

from tg_model.model.definition_context import ModelDefinitionError, attribute_ref
from tg_model.model.elements import Part
from tg_model.model.identity import qualified_name


class _Leaf(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("__leaf")
        snap = attribute_ref(_MissionRoot, "sim_kg")
        model.attribute("mirrored_kg", unit=kg, expr=snap)


class _MissionRoot(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("__mission_root")
        model.attribute("sim_kg", unit=kg, expr=QuantityExpr(Quantity(3, kg)))
        model.composed_of("leaf", _Leaf)


def setup_function() -> None:
    _MissionRoot._reset_compilation()
    _Leaf._reset_compilation()


def test_attribute_ref_resolves_during_root_compile() -> None:
    compiled = _MissionRoot.compile()
    qname = qualified_name(_Leaf)
    leaf = compiled["child_types"][qname]
    meta = leaf["nodes"]["mirrored_kg"]["metadata"]
    expr = meta.get("_expr")
    assert expr is not None
    assert expr.owner_type is _MissionRoot
    assert expr.path == ("sim_kg",)
    assert expr.kind == "attribute"


def test_attribute_ref_wrong_name_raises() -> None:
    class _BadLeaf(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__bad_leaf")
            attribute_ref(_BadRoot, "nope")

    class _BadRoot(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__bad_root")
            model.attribute("sim_kg", unit=kg, expr=QuantityExpr(Quantity(1, kg)))
            model.composed_of("leaf", _BadLeaf)

    _BadRoot._reset_compilation()
    _BadLeaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="no such attribute"):
        _BadRoot.compile()


def test_attribute_ref_not_attribute_kind_raises() -> None:
    class _BadLeaf2(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__bad_leaf2")
            attribute_ref(_Root2, "only_param")

    class _Root2(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__root2")
            model.parameter("only_param", unit=kg)
            model.composed_of("leaf", _BadLeaf2)

    _Root2._reset_compilation()
    _BadLeaf2._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="expected kind 'attribute'"):
        _Root2.compile()
