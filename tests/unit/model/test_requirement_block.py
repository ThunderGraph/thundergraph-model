"""RequirementBlock nesting, refs, instantiate, and requirement_ref."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg, m, rad, s
from unitflow.expr.expressions import QuantityExpr

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.model.definition_context import ModelDefinitionError, requirement_ref
from tg_model.model.elements import Part, RequirementBlock, System
from tg_model.model.refs import RequirementBlockRef


class _InnerMission(RequirementBlock):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        r = model.requirement("range_ok", "Range shall be positive.")
        c = model.citation("c_inner", title="inner", uri="https://example.invalid/inner")
        model.references(r, c)


class _Mission(RequirementBlock):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        r = model.requirement("payload_ok", "Payload shall be within limits.")
        c = model.citation("c_mission", title="m", uri="https://example.invalid/m")
        model.references(r, c)
        model.requirement_block("inner", _InnerMission)


class _Gadget(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        _ = requirement_ref(_RootSys, ("mission", "inner", "range_ok"))


class _RootSys(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("mass_kg", unit=kg)
        mref = model.requirement_block("mission", _Mission)
        assert isinstance(mref, RequirementBlockRef)
        assert mref.payload_ok.kind == "requirement"
        assert mref.payload_ok.path == ("mission", "payload_ok")
        assert mref.inner.range_ok.path == ("mission", "inner", "range_ok")
        g = model.part("gadget", _Gadget)
        model.allocate(mref.inner.range_ok, g)


def setup_function() -> None:
    _RootSys._reset_compilation()
    _Mission._reset_compilation()
    _InnerMission._reset_compilation()
    _Gadget._reset_compilation()


def test_requirement_block_compile_and_nested_paths() -> None:
    art = _RootSys.compile()
    assert art["nodes"]["mission"]["kind"] == "requirement_block"
    m_comp = _Mission.compile()
    assert "payload_ok" in m_comp["nodes"]
    assert m_comp["nodes"]["inner"]["kind"] == "requirement_block"


def test_allocate_nested_requirement_instantiate_and_graph() -> None:
    cm = instantiate(_RootSys)
    key = f"{_RootSys.__name__}.mission.inner.range_ok"
    assert key in cm.path_registry
    inputs = {cm.mass_kg.stable_id: Quantity(1.0, kg)}
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(RunContext(), inputs=inputs)
    assert not result.failures


def test_requirement_block_forbids_part() -> None:
    class _Leaf(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            pass

    class _Bad(RequirementBlock):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.part("nope", _Leaf)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_block("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    _Leaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="RequirementBlock cannot declare"):
        _S.compile()


def test_requirement_acceptance_expr_needs_allocate_full_path() -> None:
    class _R(RequirementBlock):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement(
                "q",
                "x",
                expr=QuantityExpr(Quantity(1, m)) > QuantityExpr(Quantity(0, m)),
            )

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            b = model.requirement_block("blk", _R)
            p = model.part()
            model.allocate(b.q, p)

    _S._reset_compilation()
    _R._reset_compilation()
    _S.compile()


def test_requirement_input_allocate_inputs_graph() -> None:
    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("rpm", unit=rad / s)

    class _R(RequirementBlock):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            r = model.requirement("speed_ok", "speed positive")
            rpm_in = model.requirement_input(r, "rpm", unit=rad / s)
            model.requirement_accept_expr(
                r,
                expr=rpm_in > QuantityExpr(Quantity(0, rad / s)),
            )

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            b = model.requirement_block("blk", _R)
            m = model.part("motor", _Motor)
            model.allocate(b.speed_ok, m, inputs={"rpm": m.rpm})

    _S._reset_compilation()
    _R._reset_compilation()
    _Motor._reset_compilation()
    cm = instantiate(_S)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs={cm.motor.rpm.stable_id: Quantity(10.0, rad / s)},
    )
    assert not result.failures


def test_allocate_omits_requirement_inputs_raises() -> None:
    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("rpm", unit=rad / s)

    class _R(RequirementBlock):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            r = model.requirement("speed_ok", "speed positive")
            rpm_in = model.requirement_input(r, "rpm", unit=rad / s)
            model.requirement_accept_expr(
                r,
                expr=rpm_in > QuantityExpr(Quantity(0, rad / s)),
            )

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            b = model.requirement_block("blk", _R)
            m = model.part("motor", _Motor)
            model.allocate(b.speed_ok, m)

    _S._reset_compilation()
    _R._reset_compilation()
    _Motor._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="must include inputs"):
        _S.compile()


def test_requirement_ref_wrong_terminal_kind_raises() -> None:
    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_block("mission", _Mission)

    _S._reset_compilation()
    _Mission._reset_compilation()
    _InnerMission._reset_compilation()
    _S.compile()
    with pytest.raises(ModelDefinitionError, match="terminal kind"):
        requirement_ref(_S, ("mission",))
