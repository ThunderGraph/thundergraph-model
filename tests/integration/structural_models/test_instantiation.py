"""Integration test: full instantiation of a DriveSystem into navigable topology."""

from __future__ import annotations

from tg_model.execution.configured_model import instantiate
from tg_model.execution.instances import PartInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.model.elements import Part, System


class Battery(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.attribute("charge", unit="%")
        model.parameter("voltage", unit="V")
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
        req = model.requirement("shall_propel", "The system shall provide propulsion.")
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)
        model.connect(source=battery.power_out, target=motor.power_in, carrying="electrical_power")
        model.allocate(req, motor)


def setup_function() -> None:
    Battery._reset_compilation()
    Motor._reset_compilation()
    DriveSystem._reset_compilation()


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
