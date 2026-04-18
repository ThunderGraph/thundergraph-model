"""Integration: external compute bindings (Phase 4)."""

from __future__ import annotations

import asyncio

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import m

from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import GraphCompilationError, compile_graph
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.integrations.external_compute import (
    ExternalComputeBinding,
    ExternalComputeResult,
)
from tg_model.model.elements import Part, System


class _FakeAreaProduct:
    name = "fake_area"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        a, b = inputs["a"], inputs["b"]
        return ExternalComputeResult(
            value=a * b,
            provenance={"tool": "fake_area", "version": "1"},
        )


class _FakeSplit:
    name = "fake_split"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        x = inputs["x"]
        return ExternalComputeResult(
            value={"p": x * 2, "q": x * 3},
            provenance={"job": "split"},
        )


class _PickyExternal:
    name = "picky"

    def validate_binding(
        self,
        *,
        input_specs: dict[str, object],
        output_specs: dict[str, object],
    ) -> None:
        raise ValueError("validation rejected")

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        return ExternalComputeResult(value=Quantity(1, m))


class _FakeAsyncScale:
    name = "fake_async_scale"

    async def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        x = inputs["x"]
        return ExternalComputeResult(value=x * 5, provenance={"async": True})


class ExtPart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("ext_part")
        a = model.parameter("a", unit=m)
        b = model.parameter("b", unit=m)
        binding = ExternalComputeBinding(
            _FakeAreaProduct(),
            inputs={"a": a, "b": b},
        )
        model.attribute("area", unit=m * m, computed_by=binding)


class MultiOutPart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("multi_out_part")
        x = model.parameter("x", unit=m)
        binding = ExternalComputeBinding(_FakeSplit(), inputs={"x": x})
        p = model.attribute("p", unit=m, computed_by=binding)
        q = model.attribute("q", unit=m, computed_by=binding)
        model.link_external_routes(binding, {"p": p, "q": q})


class AsyncPart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("async_part")
        x = model.parameter("x", unit=m)
        binding = ExternalComputeBinding(_FakeAsyncScale(), inputs={"x": x})
        model.attribute("scaled", unit=m, computed_by=binding)


class ValidatedPart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("validated_part")
        a = model.parameter("a", unit=m)
        b = model.parameter("b", unit=m)
        binding = ExternalComputeBinding(
            _PickyExternal(),
            inputs={"a": a, "b": b},
        )
        model.attribute("c", unit=m, computed_by=binding)


class WrapValidated(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("wrap_validated")
        model.composed_of("v", ValidatedPart)


class Wrap(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("wrap")
        model.composed_of("ext", ExtPart)


class WrapMulti(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("wrap_multi")
        model.composed_of("m", MultiOutPart)


class WrapAsync(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("wrap_async")
        model.composed_of("a", AsyncPart)


def setup_function() -> None:
    for t in (
        ExtPart,
        MultiOutPart,
        AsyncPart,
        ValidatedPart,
        Wrap,
        WrapMulti,
        WrapAsync,
        WrapValidated,
    ):
        t._reset_compilation()


class TestExternalComputeIntegration:
    def test_sync_external_single_slot_end_to_end(self) -> None:
        cm = instantiate(Wrap)
        graph, handlers = compile_graph(cm)
        assert validate_graph(graph).passed

        a_slot = cm.ext.a
        b_slot = cm.ext.b
        area_slot = cm.ext.area

        ev = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        res = ev.evaluate(
            ctx,
            inputs={
                a_slot.stable_id: Quantity(3, m),
                b_slot.stable_id: Quantity(4, m),
            },
        )

        assert res.passed
        area = ctx.get_value(area_slot.stable_id)
        assert area.is_close(Quantity(12, m * m))

    def test_sync_evaluator_rejects_async_external(self) -> None:
        cm = instantiate(WrapAsync)
        graph, handlers = compile_graph(cm)
        x_slot = cm.a.x
        scaled_slot = cm.a.scaled

        ev = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        res = ev.evaluate(ctx, inputs={x_slot.stable_id: Quantity(2, m)})

        assert not res.passed
        assert any("evaluate_async" in f for f in res.failures)
        with pytest.raises(ValueError):
            ctx.get_value(scaled_slot.stable_id)

    def test_evaluate_async_runs_async_external(self) -> None:
        cm = instantiate(WrapAsync)
        graph, handlers = compile_graph(cm)
        x_slot = cm.a.x
        scaled_slot = cm.a.scaled

        ev = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()

        async def _run() -> None:
            r = await ev.evaluate_async(
                ctx,
                configured_model=cm,
                inputs={x_slot.stable_id: Quantity(2, m)},
            )
            assert r.passed

        asyncio.run(_run())
        out = ctx.get_value(scaled_slot.stable_id)
        assert out.is_close(Quantity(10, m))

    def test_validate_graph_calls_validate_binding_when_configured_model_given(self) -> None:
        cm = instantiate(WrapValidated)
        graph, _handlers = compile_graph(cm)
        plain = validate_graph(graph)
        assert plain.passed
        with_cm = validate_graph(graph, configured_model=cm)
        assert not with_cm.passed
        assert any("validation rejected" in f.message for f in with_cm.failures)

    def test_multi_output_fanout(self) -> None:
        cm = instantiate(WrapMulti)
        graph, handlers = compile_graph(cm)
        assert validate_graph(graph).passed

        x_slot = cm.m.x
        p_slot = cm.m.p
        q_slot = cm.m.q

        ev = Evaluator(graph, compute_handlers=handlers)
        ctx = RunContext()
        res = ev.evaluate(ctx, inputs={x_slot.stable_id: Quantity(5, m)})
        assert res.passed
        assert ctx.get_value(p_slot.stable_id).is_close(Quantity(10, m))
        assert ctx.get_value(q_slot.stable_id).is_close(Quantity(15, m))

    def test_expr_and_computed_by_rejected(self) -> None:
        class Bad(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("bad")
                x = model.parameter("x", unit=m)
                b = ExternalComputeBinding(_FakeSplit(), inputs={"x": x})
                model.attribute("y", unit=m, expr=x * 2, computed_by=b)

        class BadWrap(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("bad_wrap")
                model.composed_of("b", Bad)

        Bad._reset_compilation()
        BadWrap._reset_compilation()
        cm = instantiate(BadWrap)
        with pytest.raises(GraphCompilationError, match="combine"):
            compile_graph(cm)
