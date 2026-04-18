"""Composable Requirement nesting, refs, instantiate, and requirement_ref — new API."""

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


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class _InnerMission(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("inner")
        model.doc("Range shall be positive.")


class _Mission(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("mission")
        model.doc("Payload shall be within limits.")
        c = model.citation("c_mission", title="m", uri="https://example.invalid/m")
        inner = model.composed_of("inner", _InnerMission)
        model.references(inner, c)


class _Gadget(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("gadget")
        _ = requirement_ref(_RootSys, ("mission", "inner"))


class _RootSys(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("root_sys")
        model.parameter("mass_kg", unit=kg)
        mref = model.composed_of("mission", _Mission)
        assert isinstance(mref, RequirementRef)
        assert mref.inner.kind == "requirement_block"
        assert mref.inner.path == ("mission", "inner")
        g = model.composed_of("gadget", _Gadget)
        model.allocate(mref.inner, g)


def setup_function() -> None:
    _RootSys._reset_compilation()
    _Mission._reset_compilation()
    _InnerMission._reset_compilation()
    _Gadget._reset_compilation()


def test_requirement_block_compile_and_nested_paths() -> None:
    art = _RootSys.compile()
    assert art["nodes"]["mission"]["kind"] == "requirement_block"
    m_comp = _Mission.compile()
    assert m_comp["nodes"]["inner"]["kind"] == "requirement_block"


def test_allocate_nested_requirement_instantiate_and_graph() -> None:
    cm = instantiate(_RootSys)
    # inner requirement block should appear in path registry
    key = f"{_RootSys.__name__}.mission.inner"
    assert key in cm.path_registry
    inputs = {cm.mass_kg.stable_id: Quantity(1.0, kg)}
    graph, handlers = compile_graph(cm)
    assert validate_graph(graph).passed
    result = Evaluator(graph, compute_handlers=handlers).evaluate(RunContext(), inputs=inputs)
    assert not result.failures


def test_requirement_block_allows_parameter_attribute_constraint() -> None:
    """Composable Requirement may own package-level parameters, attributes, constraints."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("x shall be usable")
            x = model.parameter("x_m", unit=m)
            _ = model.attribute("twice_m", expr=x + x, unit=m)
            model.constraint("x_positive", expr=x > QuantityExpr(Quantity(0, m)))
            c = model.citation("c1", title="t", uri="https://example.invalid/x")
            model.references(model.composed_of("sub", _InnerMission), c)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    root = _S.compile()
    assert root["nodes"]["pkg"]["kind"] == "requirement_block"
    inner = _R.compile()
    assert inner["nodes"]["x_m"]["kind"] == "parameter"
    assert inner["nodes"]["twice_m"]["kind"] == "attribute"
    assert inner["nodes"]["x_positive"]["kind"] == "constraint"


def test_requirement_block_instantiate_graph_evaluate() -> None:
    """Package parameters/attributes/constraints get slots and run in the graph."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("x shall be usable")
            x = model.parameter("x_m", unit=m)
            _ = model.attribute("twice_m", expr=x + x, unit=m)
            model.constraint("x_positive", expr=x > QuantityExpr(Quantity(0, m)))

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

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


def test_requirement_block_attribute_passthrough_attributeref_expr() -> None:
    """Package attribute may use bare ``AttributeRef`` as ``expr=`` (identity passthrough)."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("x passthrough")
            x = model.parameter("x_m", unit=m)
            _ = model.attribute("copy_m", expr=x, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

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


def test_requirement_block_constraint_requires_expr() -> None:
    """Composable requirement constraints must not omit ``expr``."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("stub.")
            model.constraint("empty", expr=None)  # type: ignore[arg-type]

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="must set expr"):
        _S.compile()


def test_requirement_block_nested_outer_inner_evaluate() -> None:
    """Inner package attributes/constraints may reference outer package parameters."""

    class _NestedOuter(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("nested_outer")
            model.doc("outer package")
            a = model.parameter("a_m", unit=m)

            class _NestedInner(Requirement):
                @classmethod
                def define(inner_cls, inner_model):  # type: ignore[override]
                    inner_model.name("nested_inner")
                    inner_model.doc("inner package")
                    y = inner_model.parameter("y_m", unit=m)
                    _ = inner_model.attribute("sum_m", expr=a + y, unit=m)
                    inner_model.constraint(
                        "sum_positive",
                        expr=(a + y) > QuantityExpr(Quantity(0, m)),
                    )

            model.composed_of("inner", _NestedInner)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("mission", _NestedOuter)

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


def test_slot_ids_for_part_subtree_includes_requirement_block_slots() -> None:
    """Subtree slot ids include values under composable requirement blocks."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("stub.")
            model.parameter("p_m", unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("q", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    cm = instantiate(_S)
    ids = slot_ids_for_part_subtree(cm.root)
    assert cm.q.p_m.stable_id in ids


def test_requirement_block_constant_constraint_no_symbols() -> None:
    """Package constraints with no free symbols still get an evaluator handler."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("stub.")
            model.parameter("x_m", unit=m)
            model.constraint("tautology", expr=True)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

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


def test_requirement_block_forbids_port() -> None:
    """Ports are structural; composable requirement blocks reject ``port`` declarations."""

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("bad")
            model.doc("stub.")
            model.port("in1", "in")

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement cannot declare"):
        _S.compile()


def test_requirement_block_forbids_allocate_edge() -> None:
    """``allocate`` must not appear inside a Requirement.define()."""

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("bad")
            model.doc("stub.")
            model.allocate(model.root_block(), model.root_block())

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement edge kind"):
        _S.compile()


def test_requirement_block_attribute_rejects_foreign_parameter_ref() -> None:
    """Package ``attribute`` expr must not pull symbols from unrelated element types."""

    class _Other(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("other")
            model.parameter("ext_m", unit=m)

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("stub.")
            p = model.parameter("p", unit=m)
            ext = parameter_ref(_Other, "ext_m")
            model.attribute("bad", expr=p + ext, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

    _Other._reset_compilation()
    _S._reset_compilation()
    _R._reset_compilation()
    _Other.compile()
    with pytest.raises(ModelDefinitionError, match="owned by"):
        _S.compile()


def test_requirement_block_attribute_rejects_undeclared_slot() -> None:
    """Flat package symbols in exprs must name parameters/attributes declared earlier."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("stub.")
            p = model.parameter("p", unit=m)
            ghost = AttributeRef(
                owner_type=_R,
                path=("ghost",),
                kind="parameter",
                metadata={"unit": m},
            )
            model.attribute("bad", expr=p + ghost, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="allowed prior"):
        _S.compile()


def test_requirement_block_attribute_rejects_attributeref_wrong_owner() -> None:
    """Bare ``AttributeRef`` in ``attribute`` ``expr=`` must use configured-root owner."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("stub.")
            model.parameter("p", unit=m)
            bad = AttributeRef(
                owner_type=_R,
                path=("pkg", "p"),
                kind="parameter",
                metadata={"unit": m},
            )
            model.attribute("bad", expr=bad, unit=m)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="must reference slots owned by"):
        _S.compile()


def test_requirement_block_attribute_rejects_attributeref_undeclared_leaf() -> None:
    """Bare ``AttributeRef`` must name a parameter or attribute declared earlier."""

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("r")
            model.doc("stub.")
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
            model.name("s")
            model.composed_of("pkg", _R)

    _S._reset_compilation()
    _R._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="allowed prior"):
        _S.compile()


def test_requirement_block_forbids_state() -> None:
    """Behavior / structure outside the allow-list remains rejected."""

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("bad")
            model.doc("stub.")
            model.state("s0", initial=True)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement cannot declare"):
        _S.compile()


def test_requirement_block_forbids_composed_of_part() -> None:
    """A Requirement block may not compose a Part child."""

    class _Leaf(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("leaf")

    class _Bad(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("bad")
            model.doc("stub.")
            model.composed_of("nope", _Leaf)

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            model.composed_of("b", _Bad)

    _S._reset_compilation()
    _Bad._reset_compilation()
    _Leaf._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="Requirement cannot declare"):
        _S.compile()


def test_requirement_ref_wrong_terminal_kind_raises() -> None:
    """requirement_ref raises when the terminal node is not a requirement_block."""

    class _SysWithParam(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sys_with_param")
            model.parameter("max_load", unit=kg)

    _SysWithParam._reset_compilation()
    _SysWithParam.compile()
    with pytest.raises(ModelDefinitionError, match="terminal kind"):
        requirement_ref(_SysWithParam, ("max_load",))


def test_requirement_block_with_allocate_and_parameter_override() -> None:
    """allocate(..., inputs=...) wires values into package-level parameters."""

    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("motor")
            model.parameter("rpm", unit=rad / s)

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("speed_req")
            model.doc("Speed shall be positive.")
            rpm_in = model.parameter("rpm", unit=rad / s)
            model.constraint("rpm_positive", expr=rpm_in > QuantityExpr(Quantity(0, rad / s)))

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            b = model.composed_of("blk", _R)
            motor = model.composed_of("motor", _Motor)
            model.allocate(b, motor, inputs={"rpm": motor.rpm})

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


def test_requirement_block_allocate_with_attribute_sum() -> None:
    """Package parameter + attribute + constraint work correctly end-to-end with allocate."""

    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("motor")
            model.parameter("a_m", unit=m)
            model.parameter("b_m", unit=m)

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("sum_req")
            model.doc("Sum shall be positive.")
            a = model.parameter("a_m", unit=m)
            b = model.parameter("b_m", unit=m)
            s = model.attribute("sum_m", expr=a + b, unit=m)
            model.constraint("sum_positive", expr=s > QuantityExpr(Quantity(0, m)))

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            blk = model.composed_of("blk", _R)
            motor = model.composed_of("motor", _Motor)
            model.allocate(blk, motor, inputs={"a_m": motor.a_m, "b_m": motor.b_m})

    _S._reset_compilation()
    _R._reset_compilation()
    _Motor._reset_compilation()
    cm = instantiate(_S)
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


def test_requirement_block_full_evaluate_pipeline() -> None:
    """compile + instantiate + graph + evaluate end-to-end."""

    class _Motor(Part):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("motor")
            model.parameter("rpm", unit=rad / s)

    class _R(Requirement):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("speed_req")
            model.doc("Speed shall be positive.")
            rpm = model.parameter("rpm", unit=rad / s)
            model.constraint("rpm_positive", expr=rpm > QuantityExpr(Quantity(0, rad / s)))

    class _S(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            model.name("s")
            b = model.composed_of("blk", _R)
            motor = model.composed_of("motor", _Motor)
            model.allocate(b, motor, inputs={"rpm": motor.rpm})

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
