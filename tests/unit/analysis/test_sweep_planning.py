"""Unit tests: sweep cartesian planning and pruning helpers."""

from __future__ import annotations

import pytest

from tg_model.analysis.sweep import sweep
from tg_model.execution.dependency_graph import DependencyGraph, DependencyNode, NodeKind
from tg_model.execution.value_slots import ValueSlot


def _slot(path: str, sid: str) -> ValueSlot:
    return ValueSlot(
        stable_id=sid,
        instance_path=tuple(path.split(".")),
        kind="parameter",
    )


class TestSweepCartesian:
    def test_empty_parameter_grid_single_run(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("p", NodeKind.INPUT_PARAMETER, slot_id="sp"))
        recs = sweep(graph=g, handlers={}, parameter_values={})
        assert len(recs) == 1
        assert recs[0].index == 0
        assert recs[0].inputs == {}
        r = recs[0].result
        assert not r.passed  # missing required input by default

    def test_rejects_empty_value_list(self) -> None:
        g = DependencyGraph()
        s = _slot("Sys.motor.torque", "t1")
        with pytest.raises(ValueError, match="Empty value sequence"):
            sweep(graph=g, handlers={}, parameter_values={s: []})

    def test_sink_called_per_row(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("val:Sys.m.p", NodeKind.INPUT_PARAMETER, slot_id="sp"))
        s = _slot("Sys.m.p", "sp")
        seen: list[int] = []

        def sink(rec: object) -> None:
            from tg_model.analysis.sweep import SweepRecord

            assert isinstance(rec, SweepRecord)
            seen.append(rec.index)

        sweep(
            graph=g,
            handlers={},
            parameter_values={s: [1, 2]},
            sink=sink,
        )
        assert seen == [0, 1]

    def test_collect_false_requires_sink(self) -> None:
        g = DependencyGraph()
        with pytest.raises(ValueError, match="collect=False"):
            sweep(graph=g, handlers={}, parameter_values={}, collect=False)

    def test_collect_false_returns_empty_list_with_sink(self) -> None:
        g = DependencyGraph()
        g.add_node(DependencyNode("val:Sys.m.p", NodeKind.INPUT_PARAMETER, slot_id="sp"))
        s = _slot("Sys.m.p", "sp")
        seen: list[int] = []

        def sink(rec: object) -> None:
            from tg_model.analysis.sweep import SweepRecord

            assert isinstance(rec, SweepRecord)
            seen.append(rec.index)

        recs = sweep(
            graph=g,
            handlers={},
            parameter_values={s: [7]},
            collect=False,
            sink=sink,
        )
        assert recs == []
        assert seen == [0]


class TestPrunedSweepStillEvaluates:
    def test_pruned_subgraph_runs(self) -> None:
        """Minimal chain: two params -> expr -> out; prune to out."""
        g = DependencyGraph()
        g.add_node(DependencyNode("val:root.a", NodeKind.INPUT_PARAMETER, slot_id="sa"))
        g.add_node(DependencyNode("val:root.b", NodeKind.INPUT_PARAMETER, slot_id="sb"))
        g.add_node(DependencyNode("expr", NodeKind.LOCAL_EXPRESSION, slot_id="sout"))
        g.add_node(DependencyNode("val:root.out", NodeKind.ATTRIBUTE_VALUE, slot_id="sout"))
        g.add_edge("val:root.a", "expr")
        g.add_edge("val:root.b", "expr")
        g.add_edge("expr", "val:root.out")

        handlers = {"expr": lambda deps: deps["val:root.a"] + deps["val:root.b"]}
        out_slot = _slot("root.out", "sout")
        a = _slot("root.a", "sa")
        b = _slot("root.b", "sb")

        recs = sweep(
            graph=g,
            handlers=handlers,
            parameter_values={a: [10], b: [3]},
            prune_to_slots=[out_slot],
        )
        assert len(recs) == 1
        assert recs[0].result.outputs.get("sout") == 13
