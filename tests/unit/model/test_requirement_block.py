"""Composable Requirement nesting, refs, instantiate, and requirement_ref."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kg, m, rad, s
from unitflow.expr.expressions import QuantityExpr

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.instances import slot_ids_for_part_subtree
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.execution.value_slots import ValueSlot
from tg_model.model.definition_context import (
    ModelDefinitionError,
    parameter_ref,
    requirement_ref,
)
from tg_model.model.elements import Part, Requirement, System
from tg_model.model.refs import AttributeRef, RequirementRef


class _InnerMission(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        r = model.requirement("range_ok", "Range shall be positive.")
        c = model.citation("c_inner", title="inner", uri="https://example.invalid/inner")
        model.references(r, c)


class _Mission(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        r = model.requirement("payload_ok", "Payload shall be within limits.")
        c = model.citation("c_mission", title="m", uri="https://example.invalid/m")
        model.references(r, c)
        model.requirement_package("inner", _InnerMission)


class _Gadget(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        _ = requirement_ref(_RootSys, ("mission", "inner", "range_ok"))


class _RootSys(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("mass_kg", unit=kg)
        mref = model.requirement_package("mission", _Mission)
        assert isinstance(mref, RequirementRef)
        assert mref.payload_ok.kind == "requirement"
        assert mref.payload_ok.path == ("mission", "payload_ok")
        inner_m = mref.inner
        assert isinstance(inner_m, RequirementRef)
        assert inner_m.range_ok.path == ("mission", "inner", "range_ok")
        g = model.part("gadget", _Gadget)
        model.allocate(inner_m.range_ok, g)


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


def test_requirement_package_allows_parameter_attribute_constraint() -> None:
    """Phase 2: composable Requirement may own package-level parameters, attributes, constraints."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            x = model.parameter("x_m", unit=m)
            _ = model.attribute("twice_m", expr=x + x, unit=m)
            model.constraint("x_positive", expr=x > QuantityExpr(Quantity(0, m)))
            r = model.requirement("r_ok", "x shall be usable")
            c = model.citation("c1", title="t", uri="https://example.invalid/x")
            model.references(r, c)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    root = _S.compile()
    assert root["nodes"]["pkg"]["kind"] == "requirement_block"
    inner = _R.compile()
    assert inner["nodes"]["x_m"]["kind"] == "parameter"
    assert inner["nodes"]["twice_m"]["kind"] == "attribute"
    assert inner["nodes"]["x_positive"]["kind"] == "constraint"


def test_requirement_package_instantiate_graph_evaluate() -> None:
    """Phase 3: package parameters/attributes/constraints get slots and run in the graph."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            x = model.parameter("x_m", unit=m)
            _ = model.attribute("twice_m", expr=x + x, unit=m)
            model.constraint("x_positive", expr=x > QuantityExpr(Quantity(0, m)))
            r = model.requirement("r_ok", "x shall be usable")
            c = model.citation("c1", title="t", uri="https://example.invalid/x")
            model.references(r, c)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    cm = instantiate(_S)
    assert isinstance(cm.pkg.x_m, ValueSlot)
    assert isinstance(cm.pkg.twice_m, ValueSlot)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs={cm.pkg.x_m.stable_id: Quantity(3.0, m)},
    )
    assert not result.failures
    result_handles = cm.evaluate(inputs={cm.pkg.x_m: Quantity(4.0, m)})
    assert not result_handles.failures


def test_requirement_package_attribute_passthrough_attributeref_expr() -> None:
    """Package attribute may use bare ``AttributeRef`` as ``expr=`` (identity passthrough)."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            x = model.parameter("x_m", unit=m)
            _ = model.attribute("copy_m", expr=x, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    cm = instantiate(_S)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs={cm.pkg.x_m.stable_id: Quantity(2.25, m)},
    )
    assert not result.failures
    out = result.outputs[cm.pkg.copy_m.stable_id]
    assert out.is_close(Quantity(2.25, m))


def test_requirement_package_constraint_requires_expr() -> None:
    """Composable requirement package constraints must not omit ``expr``."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.constraint("empty", expr=None)  # type: ignore[arg-type]

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="must set expr"):
        _S.compile()


def test_requirement_package_nested_outer_inner_evaluate() -> None:
    """Inner package attributes/constraints may reference outer package parameters (threaded symbols)."""

    class _NestedOuter(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            a = model.parameter("a_m", unit=m)

            class _NestedInner(Requirement):
                @classmethod
                def define(inner_cls, inner_model):  # type: ignore[override]
                    y = inner_model.parameter("y_m", unit=m)
                    _ = inner_model.attribute("sum_m", expr=a + y, unit=m)
                    inner_model.constraint(
                        "sum_positive",
                        expr=(a + y) > QuantityExpr(Quantity(0, m)),
                    )

            model.requirement_package("inner", _NestedInner)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("mission", _NestedOuter)

    _S._reset_compilation()
    _NestedOuter._reset_compilation()
    cm = instantiate(_S)
    assert isinstance(cm.mission.a_m, ValueSlot)
    assert isinstance(cm.mission.inner.y_m, ValueSlot)
    assert isinstance(cm.mission.inner.sum_m, ValueSlot)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs={
            cm.mission.a_m.stable_id: Quantity(2.0, m),
            cm.mission.inner.y_m.stable_id: Quantity(1.0, m),
        },
    )
    assert not result.failures


def test_slot_ids_for_part_subtree_includes_requirement_package_slots() -> None:
    """Subtree slot ids include values under composable requirement packages."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("p_m", unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("q", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    cm = instantiate(_S)
    ids = slot_ids_for_part_subtree(cm.root)
    assert cm.q.p_m.stable_id in ids


def test_requirement_package_constant_constraint_no_symbols() -> None:
    """Package constraints with no free symbols still get an evaluator handler."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("x_m", unit=m)
            model.constraint("tautology", expr=True)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    cm = instantiate(_S)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs={cm.pkg.x_m.stable_id: Quantity(1.0, m)},
    )
    assert not result.failures


def test_requirement_package_forbids_port() -> None:
    """Ports are structural; composable requirement packages reject ``port`` declarations."""

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.port("in1", "in")

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement cannot declare"):
        _S.compile()


def test_requirement_package_forbids_allocate_edge() -> None:
    """``allocate`` is valid on System/Part contexts but must not appear inside a package."""

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            r = model.requirement("q", "text")
            model.allocate(r, model.root_block())

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement edge kind"):
        _S.compile()


def test_requirement_package_attribute_rejects_foreign_parameter_ref() -> None:
    """Package ``attribute`` expr must not pull symbols from unrelated element types."""

    class _Other(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("ext_m", unit=m)

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            p = model.parameter("p", unit=m)
            ext = parameter_ref(_Other, "ext_m")
            model.attribute("bad", expr=p + ext, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _Other._reset_compilation()
    _S._reset_compilation()
    _R._reset_compilation()
    _Other.compile()
    with pytest.raises(ModelDefinitionError, match="owned by"):
        _S.compile()


def test_requirement_package_attribute_rejects_undeclared_slot() -> None:
    """Flat package symbols in exprs must name parameters/attributes declared earlier."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            p = model.parameter("p", unit=m)
            ghost = AttributeRef(
                owner_type=cls,
                path=("ghost",),
                kind="parameter",
                metadata={"unit": m},
            )
            model.attribute("bad", expr=p + ghost, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="allowed prior"):
        _S.compile()


def test_requirement_package_attribute_rejects_attributeref_wrong_owner() -> None:
    """Bare ``AttributeRef`` in ``attribute`` ``expr=`` must use configured-root owner, not ``Requirement`` type."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("p", unit=m)
            bad = AttributeRef(
                owner_type=cls,
                path=("pkg", "p"),
                kind="parameter",
                metadata={"unit": m},
            )
            model.attribute("bad", expr=bad, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="must reference slots owned by"):
        _S.compile()


def test_requirement_package_attribute_rejects_attributeref_undeclared_leaf() -> None:
    """Bare ``AttributeRef`` must name a parameter or attribute declared earlier in the package."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            _ = model.parameter("p", unit=m)
            bad = AttributeRef(
                owner_type=_S,
                path=("pkg", "ghost"),
                kind="parameter",
                metadata={"unit": m},
            )
            model.attribute("bad", expr=bad, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="allowed prior"):
        _S.compile()


def test_requirement_package_forbids_state() -> None:
    """Behavior / structure outside the allow-list remains rejected."""

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.state("s0", initial=True)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement cannot declare"):
        _S.compile()


def test_requirement_block_forbids_part() -> None:
    class _Leaf(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            pass

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.part("nope", _Leaf)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.requirement_package("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    _Leaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement cannot declare"):
        _S.compile()


def test_requirement_acceptance_expr_needs_allocate_full_path() -> None:
    class _R(Requirement):
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
            b = model.requirement_package("blk", _R)
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

    class _R(Requirement):
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
            b = model.requirement_package("blk", _R)
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


def test_requirement_attribute_sum_and_acceptance() -> None:
    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("a_m", unit=m)
            model.parameter("b_m", unit=m)

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            r = model.requirement("sum_positive", "sum positive")
            a = model.requirement_input(r, "a_m", unit=m)
            b = model.requirement_input(r, "b_m", unit=m)
            s = model.requirement_attribute(r, "sum_m", expr=a + b, unit=m)
            model.requirement_accept_expr(
                r,
                expr=s > QuantityExpr(Quantity(0, m)),
            )

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            blk = model.requirement_package("blk", _R)
            m = model.part("motor", _Motor)
            model.allocate(
                blk.sum_positive,
                m,
                inputs={"a_m": m.a_m, "b_m": m.b_m},
            )

    _S._reset_compilation()
    _R._reset_compilation()
    _Motor._reset_compilation()
    cm = instantiate(_S)
    assert any("sum_m" in s.path_string for s in cm.requirement_value_slots)
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(
        RunContext(),
        inputs={
            cm.motor.a_m.stable_id: Quantity(1.0, m),
            cm.motor.b_m.stable_id: Quantity(2.0, m),
        },
    )
    assert not result.failures


def test_allocate_omits_requirement_inputs_raises() -> None:
    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("rpm", unit=rad / s)

    class _R(Requirement):
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
            b = model.requirement_package("blk", _R)
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
            model.requirement_package("mission", _Mission)

    _S._reset_compilation()
    _Mission._reset_compilation()
    _InnerMission._reset_compilation()
    _S.compile()
    with pytest.raises(ModelDefinitionError, match="terminal kind"):
        requirement_ref(_S, ("mission",))


def test_requirement_package_full_evaluate_pipeline() -> None:
    """compile + instantiate + graph + evaluate for a registered requirement package."""

    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.parameter("rpm", unit=rad / s)

    class _R(Requirement):
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
            b = model.requirement_package("blk", _R)
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
