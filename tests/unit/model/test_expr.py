"""Helpers for building expressions from AttributeRefs."""

from __future__ import annotations

from unitflow.catalogs.si import kg

from tg_model.model.elements import Part
from tg_model.model.expr import sum_attributes


class _RollupHost(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        a = model.parameter("a", unit=kg)
        b = model.parameter("b", unit=kg)
        c = model.parameter("c", unit=kg)
        model.attribute("sum_abc", unit=kg, expr=sum_attributes(a, b, c))


def setup_function() -> None:
    _RollupHost._reset_compilation()


def test_sum_attributes_three_parameters_builds_expr() -> None:
    """Raw ``a + b + c`` fails at define time (Expr + AttributeRef); sum_attributes does not."""
    compiled = _RollupHost.compile()
    expr = compiled["nodes"]["sum_abc"]["metadata"]["_expr"]
    assert hasattr(expr, "free_symbols")
    assert len(expr.free_symbols) == 3
