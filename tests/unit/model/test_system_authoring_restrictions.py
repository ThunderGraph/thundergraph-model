"""System authoring restrictions: attribute and constraint are forbidden; parameter and composition are allowed."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg

from tg_model.integrations.external_compute import ExternalComputeBinding, ExternalComputeResult
from tg_model.model.declarations.values import rollup
from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part, Requirement, System


class _MassLeaf(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("__mass_leaf")
        model.parameter("mass", unit=kg)


class _StubExternal:
    name = "stub"

    def compute(self, inputs):
        return ExternalComputeResult(value=Quantity(1, kg), provenance={"source": self.name})


def test_system_attribute_expr_raises() -> None:
    class _Sys(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__sys")
            payload = model.parameter("payload_kg", unit=kg)
            model.attribute("payload_margin_kg", unit=kg, expr=payload * 1.1)

    _Sys._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="attribute"):
        _Sys.compile()


def test_system_attribute_computed_by_raises() -> None:
    class _Sys(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__sys")
            payload = model.parameter("payload_kg", unit=kg)
            binding = ExternalComputeBinding(_StubExternal(), inputs={"payload": payload})
            model.attribute("payload_total_kg", unit=kg, computed_by=binding)

    _Sys._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="attribute"):
        _Sys.compile()


def test_system_attribute_rollup_raises() -> None:
    class _Sys(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__sys")
            model.composed_of("left", _MassLeaf)
            model.composed_of("right", _MassLeaf)
            model.attribute("total_mass", unit=kg, expr=rollup.sum(model.parts(), value=lambda c: c.mass))

    _Sys._reset_compilation()
    _MassLeaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="attribute"):
        _Sys.compile()


def test_system_constraint_raises() -> None:
    class _Sys(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__sys")
            payload = model.parameter("payload_kg", unit=kg)
            model.constraint("payload_positive", expr=payload > Quantity(0, kg))

    _Sys._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="constraint"):
        _Sys.compile()


def test_system_subclass_allows_parameters_and_parts() -> None:
    class _GoodSystem(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__good_system")
            model.parameter("payload_kg", unit=kg)
            model.composed_of("leaf", _MassLeaf)

    _GoodSystem._reset_compilation()
    _MassLeaf._reset_compilation()
    art = _GoodSystem.compile()
    assert art["nodes"]["payload_kg"]["kind"] == "parameter"
    assert art["nodes"]["leaf"]["kind"] == "part"


def test_part_and_requirement_value_authoring_remain_legal() -> None:
    class _GoodRequirement(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__good_requirement")
            model.doc("stub.")
            x = model.parameter("x", unit=kg)
            model.attribute("double_x", unit=kg, expr=x + x)
            model.constraint("x_non_negative", expr=x >= Quantity(0, kg))

    class _GoodPart(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("__good_part")
            x = model.parameter("x", unit=kg)
            model.attribute("double_x", unit=kg, expr=x + x)
            model.constraint("x_non_negative", expr=x >= Quantity(0, kg))
            model.composed_of("reqs", _GoodRequirement)

    _GoodRequirement._reset_compilation()
    _GoodPart._reset_compilation()
    art = _GoodPart.compile()
    assert art["nodes"]["double_x"]["kind"] == "attribute"
    assert art["nodes"]["x_non_negative"]["kind"] == "constraint"
    assert art["nodes"]["reqs"]["kind"] == "requirement_block"
