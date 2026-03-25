"""Integration: Phase 5 analysis orchestration reuses Evaluator + compile_graph."""

from __future__ import annotations

import asyncio

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import N, m
from unitflow.catalogs.si import s as s_unit

from tg_model.analysis.compare_variants import compare_variants, compare_variants_async
from tg_model.analysis.impact import dependency_impact, value_graph_propagation
from tg_model.analysis.sweep import sweep, sweep_async
from tg_model.execution.configured_model import instantiate
from tg_model.execution.dependency_graph import DependencyGraph
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.validation import validate_graph
from tg_model.model.elements import Part, System


class Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        torque = model.parameter("torque", unit=N * m)
        speed = model.parameter("shaft_speed", unit=m / (m * s_unit))
        power = model.attribute(
            "shaft_power",
            unit=N * m / s_unit,
            expr=torque * speed,
        )
        model.constraint(
            "power_positive",
            expr=power > Quantity(0, N * m / s_unit),
        )


class SimpleSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.part("motor", Motor)


class OtherSystem(System):
    """Same motor subtree, different root type (for variant guard tests)."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.part("motor", Motor)


def setup_function() -> None:
    Motor._reset_compilation()
    SimpleSystem._reset_compilation()
    OtherSystem._reset_compilation()


@pytest.fixture
def motor_system() -> tuple[object, object, object, object]:
    cm = instantiate(SimpleSystem)
    graph, handlers = compile_graph(cm)
    v = validate_graph(graph)
    assert v.passed
    torque = cm.motor.torque
    speed = cm.motor.shaft_speed
    power = cm.motor.shaft_power
    return cm, graph, handlers, (torque, speed, power)


class TestSweepIntegration:
    def test_cartesian_sweep_isolated_results(self, motor_system: tuple) -> None:
        cm, graph, handlers, (torque, speed, power) = motor_system

        t_vals = [Quantity(10, N * m), Quantity(20, N * m)]
        s_vals = [Quantity(2, m / (m * s_unit)), Quantity(3, m / (m * s_unit))]
        recs = sweep(
            graph=graph,
            handlers=handlers,
            parameter_values={torque: t_vals, speed: s_vals},
            configured_model=cm,
        )
        assert len(recs) == 4
        for rec in recs:
            tid = torque.stable_id
            sid = speed.stable_id
            assert tid in rec.inputs and sid in rec.inputs

        expected_products = {20.0, 30.0, 40.0, 60.0}
        magnitudes = {rec.result.outputs[power.stable_id].magnitude for rec in recs}
        assert magnitudes == expected_products

    def test_pruned_sweep_omits_constraints(self, motor_system: tuple) -> None:
        cm, graph, handlers, (torque, speed, power) = motor_system
        recs = sweep(
            graph=graph,
            handlers=handlers,
            parameter_values={torque: [Quantity(5, N * m)], speed: [Quantity(2, m / (m * s_unit))]},
            configured_model=cm,
            prune_to_slots=[power],
        )
        assert len(recs) == 1
        assert recs[0].result.constraint_results == []

    def test_sweep_rejects_graph_slot_mismatch(self, motor_system: tuple) -> None:
        cm, _, _, (torque, *_rest) = motor_system
        empty = DependencyGraph()
        with pytest.raises(ValueError, match="no graph node"):
            sweep(
                graph=empty,
                handlers={},
                parameter_values={torque: [Quantity(1, N * m)]},
                configured_model=cm,
            )

    def test_value_graph_propagation_alias_matches_dependency_impact(self, motor_system: tuple) -> None:
        _, graph, _, (torque, _, _) = motor_system
        assert (
            value_graph_propagation(graph, [torque]).downstream_slot_ids
            == dependency_impact(graph, [torque]).downstream_slot_ids
        )


class TestCompareVariantsIntegration:
    def test_two_input_sets_same_topology(self, motor_system: tuple) -> None:
        cm, _, _, (torque, speed, power) = motor_system
        path = power.path_string
        low_t = torque.stable_id
        low_s = speed.stable_id
        rows = compare_variants(
            scenarios=[
                ("low", cm, {low_t: Quantity(1, N * m), low_s: Quantity(1, m / (m * s_unit))}),
                ("high", cm, {low_t: Quantity(50, N * m), low_s: Quantity(2, m / (m * s_unit))}),
            ],
            output_paths=[path],
        )
        assert [r.label for r in rows] == ["low", "high"]
        assert rows[0].outputs[path].present_in_run_outputs
        assert rows[0].outputs[path].value is not None
        assert rows[0].outputs[path].value.is_close(Quantity(1, N * m / s_unit))
        assert rows[1].outputs[path].value.is_close(Quantity(100, N * m / s_unit))

    def test_require_same_root_definition_type_rejects_mixed_roots(self) -> None:
        cm_a = instantiate(SimpleSystem)
        cm_b = instantiate(OtherSystem)
        t_a, s_a = cm_a.motor.torque.stable_id, cm_a.motor.shaft_speed.stable_id
        t_b, s_b = cm_b.motor.torque.stable_id, cm_b.motor.shaft_speed.stable_id
        with pytest.raises(ValueError, match="root type"):
            compare_variants(
                scenarios=[
                    ("a", cm_a, {t_a: Quantity(1, N * m), s_a: Quantity(1, m / (m * s_unit))}),
                    ("b", cm_b, {t_b: Quantity(1, N * m), s_b: Quantity(1, m / (m * s_unit))}),
                ],
                output_paths=[cm_a.motor.shaft_power.path_string],
                require_same_root_definition_type=True,
            )


class TestImpactIntegration:
    def test_downstream_from_parameter(self, motor_system: tuple) -> None:
        _, graph, _, (torque, speed, power) = motor_system
        rep = dependency_impact(graph, [torque], upstream=True, downstream=True)
        assert torque.stable_id not in rep.downstream_slot_ids
        assert speed.stable_id not in rep.downstream_slot_ids
        assert power.stable_id in rep.downstream_slot_ids
        assert rep.upstream_slot_ids == frozenset()

    def test_upstream_from_derived_power(self, motor_system: tuple) -> None:
        _, graph, _, (torque, speed, power) = motor_system
        rep = dependency_impact(graph, [power], upstream=True, downstream=True)
        assert torque.stable_id in rep.upstream_slot_ids
        assert speed.stable_id in rep.upstream_slot_ids
        assert power.stable_id not in rep.upstream_slot_ids
        assert rep.downstream_slot_ids == frozenset()


class TestSweepAsyncIntegration:
    def test_sweep_async_matches_sync(self, motor_system: tuple) -> None:
        cm, graph, handlers, (torque, speed, power) = motor_system

        async def run() -> None:
            a = await sweep_async(
                configured_model=cm,
                graph=graph,
                handlers=handlers,
                parameter_values={
                    torque: [Quantity(2, N * m)],
                    speed: [Quantity(4, m / (m * s_unit))],
                },
            )
            sync_recs = sweep(
                graph=graph,
                handlers=handlers,
                parameter_values={
                    torque: [Quantity(2, N * m)],
                    speed: [Quantity(4, m / (m * s_unit))],
                },
                configured_model=cm,
            )
            assert len(a) == len(sync_recs) == 1
            assert a[0].result.outputs[power.stable_id].is_close(sync_recs[0].result.outputs[power.stable_id])

        asyncio.run(run())


class TestCompareVariantsAsyncIntegration:
    def test_compare_async_matches_sync(self, motor_system: tuple) -> None:
        cm, _, _, (torque, speed, power) = motor_system
        path = power.path_string
        low_t = torque.stable_id
        low_s = speed.stable_id
        scenarios = [
            ("a", cm, {low_t: Quantity(3, N * m), low_s: Quantity(2, m / (m * s_unit))}),
            ("b", cm, {low_t: Quantity(4, N * m), low_s: Quantity(2, m / (m * s_unit))}),
        ]

        async def run() -> None:
            ar = await compare_variants_async(scenarios=scenarios, output_paths=[path])
            sr = compare_variants(scenarios=scenarios, output_paths=[path])
            assert [r.outputs[path].value.magnitude for r in ar] == [
                r.outputs[path].value.magnitude for r in sr
            ]

        asyncio.run(run())
