"""Integration test: full instantiation of a DriveSystem into navigable topology."""

from __future__ import annotations

from tg_model.execution.configured_model import instantiate
from tg_model.execution.instances import PartInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.model.elements import Part, Requirement, System


class ShallPropelRequirement(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("shall_propel")
        model.doc("The system shall provide propulsion.")


class Battery(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("battery")
        model.attribute("charge", unit="%")
        model.parameter("voltage", unit="V")
        model.port("power_out", direction="out")


class Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("motor")
        model.port("power_in", direction="in")
        model.parameter("shaft_speed", unit="rpm")
        model.attribute("torque", unit="N*m")
        model.attribute("shaft_power", unit="W")


class DriveSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("drive_system")
        req = model.composed_of("shall_propel", ShallPropelRequirement)
        battery = model.composed_of("battery", Battery)
        motor = model.composed_of("motor", Motor)
        model.connect(source=battery.power_out, target=motor.power_in, carrying="electrical_power")
        model.allocate(req, motor)


def setup_function() -> None:
    Battery._reset_compilation()
    Motor._reset_compilation()
    DriveSystem._reset_compilation()
    ShallPropelRequirement._reset_compilation()


# ---------------------------------------------------------------------------
# System-in-System composition fixtures
# ---------------------------------------------------------------------------

from unitflow.catalogs.si import W, m  # noqa: E402 — after setup_function to keep layout


class Sensor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("sensor")
        model.parameter("range_m", unit=m)
        model.port("data_out", direction="out")


class SensorSubsystem(System):
    """An inner System with its own Part, ports, and parameter."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("sensor_subsystem")
        model.parameter("power_budget_w", unit=W)
        model.composed_of("sensor", Sensor)
        model.port("data_link", direction="out")


class Actuator(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("actuator")
        model.port("cmd_in", direction="in")


class FleetSystem(System):
    """Outer System composing an inner System alongside a plain Part."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("fleet_system")
        sensors = model.composed_of("sensors", SensorSubsystem)
        actuator = model.composed_of("actuator", Actuator)
        # Cross-boundary port connection: inner System port → plain Part port
        model.connect(sensors.data_link, actuator.cmd_in)


class TestFullInstantiationWorkflow:
    def test_ergonomic_navigation(self) -> None:
        cm = instantiate(DriveSystem)
        assert isinstance(cm.battery, PartInstance)
        assert isinstance(cm.battery.power_out, PortInstance)
        assert isinstance(cm.battery.voltage, ValueSlot)
        assert isinstance(cm.motor.torque, ValueSlot)
        assert cm.battery.voltage.is_parameter
        assert cm.motor.torque.is_attribute

    def test_handle_lookup_matches_projection(self) -> None:
        cm = instantiate(DriveSystem)
        battery_via_attr = cm.battery
        battery_via_handle = cm.handle("DriveSystem.battery")
        assert battery_via_attr is battery_via_handle

    def test_all_value_slots_reachable(self) -> None:
        cm = instantiate(DriveSystem)
        slot_paths = [path for path, obj in cm.path_registry.items() if isinstance(obj, ValueSlot)]
        assert "DriveSystem.battery.charge" in slot_paths
        assert "DriveSystem.battery.voltage" in slot_paths
        assert "DriveSystem.motor.shaft_speed" in slot_paths
        assert "DriveSystem.motor.torque" in slot_paths
        assert "DriveSystem.motor.shaft_power" in slot_paths

    def test_connection_resolved_correctly(self) -> None:
        cm = instantiate(DriveSystem)
        assert len(cm.connections) == 1
        conn = cm.connections[0]
        assert conn.source is cm.battery.power_out
        assert conn.target is cm.motor.power_in

    def test_repeated_instantiation_yields_equivalent_ids(self) -> None:
        cm1 = instantiate(DriveSystem)
        DriveSystem._reset_compilation()
        Battery._reset_compilation()
        Motor._reset_compilation()
        cm2 = instantiate(DriveSystem)

        paths1 = sorted(cm1.path_registry.keys())
        paths2 = sorted(cm2.path_registry.keys())
        assert paths1 == paths2

        ids1 = sorted(cm1.id_registry.keys())
        ids2 = sorted(cm2.id_registry.keys())
        assert ids1 == ids2

    def test_topology_is_immutable_shape(self) -> None:
        cm = instantiate(DriveSystem)
        initial_count = len(cm.path_registry)
        _ = cm.battery.voltage
        _ = cm.motor.torque
        assert len(cm.path_registry) == initial_count

    def test_allocation_survives_instantiation(self) -> None:
        cm = instantiate(DriveSystem)
        assert len(cm.allocations) == 1
        alloc = cm.allocations[0]
        assert "shall_propel" in alloc.requirement.path_string
        assert "motor" in alloc.target.path_string

    def test_topology_frozen_rejects_mutation(self) -> None:
        import pytest

        from tg_model.execution.instances import PartInstance

        cm = instantiate(DriveSystem)
        with pytest.raises(RuntimeError, match="frozen"):
            cm.root.add_child(
                "hack",
                PartInstance(
                    stable_id="x",
                    definition_type=Part,
                    definition_path=("x",),
                    instance_path=("x",),
                ),
            )


# ---------------------------------------------------------------------------
# System-in-System integration tests
# ---------------------------------------------------------------------------


class TestSystemInSystemComposition:
    def setup_method(self) -> None:
        Sensor._reset_compilation()
        SensorSubsystem._reset_compilation()
        Actuator._reset_compilation()
        FleetSystem._reset_compilation()

    def test_outer_system_compiles(self) -> None:
        """FleetSystem composes SensorSubsystem (a System) without error."""
        art = FleetSystem.compile()
        assert art is not None
        assert "sensors" in art["nodes"]
        assert art["nodes"]["sensors"]["kind"] == "part"

    def test_inner_system_child_is_reachable(self) -> None:
        """The composed System's part instance is navigable via dot-access."""
        cm = instantiate(FleetSystem)
        assert isinstance(cm.sensors, PartInstance)

    def test_inner_system_nested_part_is_reachable(self) -> None:
        """Parts nested inside the composed System are reachable at full depth."""
        cm = instantiate(FleetSystem)
        assert isinstance(cm.sensors.sensor, PartInstance)

    def test_inner_system_value_slot_is_reachable(self) -> None:
        """Value slots declared on the composed System are in the topology."""
        cm = instantiate(FleetSystem)
        assert isinstance(cm.sensors.power_budget_w, ValueSlot)
        assert cm.sensors.power_budget_w.is_parameter

    def test_inner_system_nested_value_slot_is_reachable(self) -> None:
        """Value slots on Parts inside the composed System are reachable."""
        cm = instantiate(FleetSystem)
        assert isinstance(cm.sensors.sensor.range_m, ValueSlot)

    def test_cross_boundary_port_connection(self) -> None:
        """model.connect() between a composed System's port and a sibling Part's port works."""
        cm = instantiate(FleetSystem)
        assert len(cm.connections) == 1
        conn = cm.connections[0]
        assert isinstance(conn.source, PortInstance)
        assert isinstance(conn.target, PortInstance)
        assert "data_link" in conn.source.path_string
        assert "cmd_in" in conn.target.path_string

    def test_path_registry_contains_inner_system_paths(self) -> None:
        """All instances inside the composed System appear in the path registry."""
        cm = instantiate(FleetSystem)
        paths = set(cm.path_registry.keys())
        assert "FleetSystem.sensors" in paths
        assert "FleetSystem.sensors.sensor" in paths
        assert "FleetSystem.sensors.power_budget_w" in paths
        assert "FleetSystem.sensors.sensor.range_m" in paths

    def test_sibling_part_still_works(self) -> None:
        """Composing a System alongside a plain Part does not break the Part."""
        cm = instantiate(FleetSystem)
        assert isinstance(cm.actuator, PartInstance)
        assert isinstance(cm.actuator.cmd_in, PortInstance)
