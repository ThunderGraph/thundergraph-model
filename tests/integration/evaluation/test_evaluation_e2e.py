"""Integration test: end-to-end evaluation of a DriveSystem model.

Proves: compile -> instantiate -> build dependency graph -> validate -> evaluate.
"""

from __future__ import annotations

from tg_model.execution.configured_model import instantiate
from tg_model.execution.dependency_graph import DependencyGraph, DependencyNode, NodeKind
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph
from tg_model.model.elements import Part, System


class Battery(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("voltage", unit="V")
        model.attribute("charge", unit="%")
        model.port("power_out", direction="out")


class Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.port("power_in", direction="in")
        model.parameter("shaft_speed", unit="rpm")
        model.attribute("torque", unit="N*m")
        model.attribute("shaft_power", unit="W")


class DriveSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)
        model.connect(source=battery.power_out, target=motor.power_in)


def setup_function() -> None:
    Battery._reset_compilation()
    Motor._reset_compilation()
    DriveSystem._reset_compilation()


def _build_graph_for_drive_system(cm):  # type: ignore[no-untyped-def]
    """Build a dependency graph from the configured DriveSystem."""
    g = DependencyGraph()

    voltage_slot = cm.battery.voltage
    speed_slot = cm.motor.shaft_speed
    torque_slot = cm.motor.torque
    power_slot = cm.motor.shaft_power

    g.add_node(DependencyNode("voltage", NodeKind.INPUT_PARAMETER, slot_id=voltage_slot.stable_id, metadata={"required": False}))
    g.add_node(DependencyNode("speed", NodeKind.INPUT_PARAMETER, slot_id=speed_slot.stable_id))
    g.add_node(DependencyNode("torque", NodeKind.INPUT_PARAMETER, slot_id=torque_slot.stable_id))
    g.add_node(DependencyNode("power_expr", NodeKind.LOCAL_EXPRESSION, slot_id=power_slot.stable_id))
    g.add_node(DependencyNode("power_val", NodeKind.ATTRIBUTE_VALUE, slot_id=power_slot.stable_id))
    g.add_node(DependencyNode("power_check", NodeKind.CONSTRAINT_CHECK, metadata={"name": "power_positive"}))

    g.add_edge("speed", "power_expr")
    g.add_edge("torque", "power_expr")
    g.add_edge("power_expr", "power_val")
    g.add_edge("power_val", "power_check")

    return g


class TestEndToEndEvaluation:
    def test_full_pipeline(self) -> None:
        cm = instantiate(DriveSystem)

        g = _build_graph_for_drive_system(cm)

        validation = validate_graph(g)
        assert validation.passed, f"Validation failed: {validation.failures}"

        speed_id = cm.motor.shaft_speed.stable_id
        torque_id = cm.motor.torque.stable_id
        power_id = cm.motor.shaft_power.stable_id

        handlers = {
            "power_expr": lambda deps: deps["speed"] * deps["torque"],
            "power_check": lambda deps: deps["power_val"] > 0,
        }
        evaluator = Evaluator(g, compute_handlers=handlers)

        ctx = RunContext()
        result = evaluator.evaluate(ctx, inputs={
            speed_id: 3000.0,
            torque_id: 50.0,
        })

        assert result.passed
        assert ctx.get_value(power_id) == 150000.0
        assert len(result.constraint_results) == 1
        assert result.constraint_results[0].passed is True

    def test_repeated_runs_isolated(self) -> None:
        cm = instantiate(DriveSystem)
        g = _build_graph_for_drive_system(cm)

        speed_id = cm.motor.shaft_speed.stable_id
        torque_id = cm.motor.torque.stable_id
        power_id = cm.motor.shaft_power.stable_id

        handlers = {
            "power_expr": lambda deps: deps["speed"] * deps["torque"],
            "power_check": lambda deps: deps["power_val"] > 0,
        }
        evaluator = Evaluator(g, compute_handlers=handlers)

        ctx1 = RunContext()
        evaluator.evaluate(ctx1, inputs={speed_id: 1000.0, torque_id: 10.0})

        ctx2 = RunContext()
        evaluator.evaluate(ctx2, inputs={speed_id: 2000.0, torque_id: 20.0})

        assert ctx1.get_value(power_id) == 10000.0
        assert ctx2.get_value(power_id) == 40000.0

    def test_constraint_fails_on_invalid_value(self) -> None:
        cm = instantiate(DriveSystem)
        g = _build_graph_for_drive_system(cm)

        speed_id = cm.motor.shaft_speed.stable_id
        torque_id = cm.motor.torque.stable_id

        handlers = {
            "power_expr": lambda deps: deps["speed"] * deps["torque"],
            "power_check": lambda deps: deps["power_val"] > 0,
        }
        evaluator = Evaluator(g, compute_handlers=handlers)

        ctx = RunContext()
        result = evaluator.evaluate(ctx, inputs={speed_id: 0.0, torque_id: 50.0})

        assert len(result.constraint_results) == 1
        assert result.constraint_results[0].passed is False
