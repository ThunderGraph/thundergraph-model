"""Regression coverage for the System authoring restriction."""

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
        model.parameter("mass", unit=kg)


class _StubExternal:
    name = "stub"

    def compute(self, inputs):
        return ExternalComputeResult(value=Quantity(1, kg), provenance={"source": self.name})


def test_system_attribute_expr_is_rejected_at_compile_time() -> None:
    class _BadSystem(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            payload = model.parameter("payload_kg", unit=kg)
            model.attribute("payload_margin_kg", unit=kg, expr=payload * 1.1)

    _BadSystem._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="System\\.define\\(\\) may not declare attribute"):
        _BadSystem.compile()


def test_system_attribute_computed_by_is_rejected_at_compile_time() -> None:
    class _BadSystem(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            payload = model.parameter("payload_kg", unit=kg)
            binding = ExternalComputeBinding(_StubExternal(), inputs={"payload": payload})
            model.attribute("payload_total_kg", unit=kg, computed_by=binding)

    _BadSystem._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="System\\.define\\(\\) may not declare attribute"):
        _BadSystem.compile()


def test_system_attribute_rollup_is_rejected_at_compile_time() -> None:
    class _BadSystem(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.part("left", _MassLeaf)
            model.part("right", _MassLeaf)
            model.attribute("total_mass", unit=kg, expr=rollup.sum(model.parts(), value=lambda c: c.mass))

    _BadSystem._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="System\\.define\\(\\) may not declare attribute"):
        _BadSystem.compile()


def test_system_constraint_is_rejected_at_compile_time() -> None:
    class _BadSystem(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            payload = model.parameter("payload_kg", unit=kg)
            model.constraint("payload_positive", expr=payload > Quantity(0, kg))

    _BadSystem._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="System\\.define\\(\\) may not declare constraint"):
        _BadSystem.compile()


def test_system_subclass_still_allows_parameters_and_parts() -> None:
    class _GoodSystem(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("payload_kg", unit=kg)
            model.part("leaf", _MassLeaf)

    _GoodSystem._reset_compilation()
    art = _GoodSystem.compile()
    assert art["nodes"]["payload_kg"]["kind"] == "parameter"
    assert art["nodes"]["leaf"]["kind"] == "part"


def test_part_and_requirement_value_authoring_remain_legal() -> None:
    class _GoodRequirement(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            x = model.parameter("x", unit=kg)
            model.attribute("double_x", unit=kg, expr=x + x)
            model.constraint("x_non_negative", expr=x >= Quantity(0, kg))

    class _GoodPart(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            x = model.parameter("x", unit=kg)
            model.attribute("double_x", unit=kg, expr=x + x)
            model.constraint("x_non_negative", expr=x >= Quantity(0, kg))
            model.requirement_package("reqs", _GoodRequirement)

    _GoodRequirement._reset_compilation()
    _GoodPart._reset_compilation()
    art = _GoodPart.compile()
    assert art["nodes"]["double_x"]["kind"] == "attribute"
    assert art["nodes"]["x_non_negative"]["kind"] == "constraint"
    assert art["nodes"]["reqs"]["kind"] == "requirement_block"
