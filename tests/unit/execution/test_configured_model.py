"""Unit tests for ConfiguredModel and instantiation."""

from __future__ import annotations

import pytest

from tg_model.execution.configured_model import ConfiguredModel, instantiate
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


class DriveSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)
        model.connect(source=battery.power_out, target=motor.power_in, carrying="electrical_power")


def setup_function() -> None:
    Battery._reset_compilation()
    Motor._reset_compilation()
    DriveSystem._reset_compilation()


class TestInstantiation:
    def test_instantiate_returns_configured_model(self) -> None:
        cm = instantiate(DriveSystem)
        assert isinstance(cm, ConfiguredModel)

    def test_root_is_part_instance(self) -> None:
        cm = instantiate(DriveSystem)
        assert isinstance(cm.root, PartInstance)
        assert "DriveSystem" in cm.root.path_string

    def test_children_instantiated(self) -> None:
        cm = instantiate(DriveSystem)
        battery = cm.root.battery
        motor = cm.root.motor
        assert isinstance(battery, PartInstance)
        assert isinstance(motor, PartInstance)

    def test_ports_instantiated(self) -> None:
        cm = instantiate(DriveSystem)
        power_out = cm.root.battery.power_out
        power_in = cm.root.motor.power_in
        assert isinstance(power_out, PortInstance)
        assert isinstance(power_in, PortInstance)
        assert power_out.direction == "out"
        assert power_in.direction == "in"

    def test_value_slots_instantiated(self) -> None:
        cm = instantiate(DriveSystem)
        charge = cm.root.battery.charge
        voltage = cm.root.battery.voltage
        torque = cm.root.motor.torque
        speed = cm.root.motor.shaft_speed
        assert isinstance(charge, ValueSlot)
        assert isinstance(voltage, ValueSlot)
        assert isinstance(torque, ValueSlot)
        assert isinstance(speed, ValueSlot)
        assert charge.is_attribute
        assert voltage.is_parameter
        assert torque.is_attribute
        assert speed.is_parameter


class TestPathRegistry:
    def test_root_in_registry(self) -> None:
        cm = instantiate(DriveSystem)
        assert cm.root.path_string in cm.path_registry

    def test_child_parts_in_registry(self) -> None:
        cm = instantiate(DriveSystem)
        assert "DriveSystem.battery" in cm.path_registry
        assert "DriveSystem.motor" in cm.path_registry

    def test_ports_in_registry(self) -> None:
        cm = instantiate(DriveSystem)
        assert "DriveSystem.battery.power_out" in cm.path_registry
        assert "DriveSystem.motor.power_in" in cm.path_registry

    def test_value_slots_in_registry(self) -> None:
        cm = instantiate(DriveSystem)
        assert "DriveSystem.battery.charge" in cm.path_registry
        assert "DriveSystem.battery.voltage" in cm.path_registry
        assert "DriveSystem.motor.torque" in cm.path_registry

    def test_handle_returns_correct_instance(self) -> None:
        cm = instantiate(DriveSystem)
        battery = cm.handle("DriveSystem.battery")
        assert isinstance(battery, PartInstance)
        assert battery is cm.root.battery

    def test_handle_missing_raises(self) -> None:
        cm = instantiate(DriveSystem)
        with pytest.raises(KeyError, match="nonexistent"):
            cm.handle("DriveSystem.nonexistent")


class TestIdRegistry:
    def test_all_instances_have_stable_ids(self) -> None:
        cm = instantiate(DriveSystem)
        for instance in cm.id_registry.values():
            assert instance.stable_id is not None
            assert len(instance.stable_id) > 0

    def test_ids_are_deterministic(self) -> None:
        cm1 = instantiate(DriveSystem)
        DriveSystem._reset_compilation()
        Battery._reset_compilation()
        Motor._reset_compilation()
        cm2 = instantiate(DriveSystem)
        ids1 = sorted(cm1.id_registry.keys())
        ids2 = sorted(cm2.id_registry.keys())
        assert ids1 == ids2


class TestConnections:
    def test_connections_resolved(self) -> None:
        cm = instantiate(DriveSystem)
        assert len(cm.connections) == 1
        conn = cm.connections[0]
        assert isinstance(conn.source, PortInstance)
        assert isinstance(conn.target, PortInstance)
        assert "power_out" in conn.source.path_string
        assert "power_in" in conn.target.path_string
        assert conn.carrying == "electrical_power"


class TestAllocations:
    def test_allocations_resolved(self) -> None:
        class AllocSystem(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                req = model.requirement("req1", "Shall do X.")
                motor = model.part("motor", Motor)
                model.allocate(req, motor)

        cm = instantiate(AllocSystem)
        assert len(cm.allocations) == 1
        alloc = cm.allocations[0]
        assert alloc.requirement.kind == "requirement"
        assert alloc.target.kind == "part"
        assert "req1" in alloc.requirement.path_string
        assert "motor" in alloc.target.path_string
        AllocSystem._reset_compilation()


class TestTopologyFreeze:
    def test_topology_is_frozen_after_instantiation(self) -> None:
        cm = instantiate(DriveSystem)
        import pytest
        with pytest.raises(RuntimeError, match="frozen"):
            cm.root.add_child("illegal", PartInstance(
                stable_id="x", definition_type=Part,
                definition_path=("x",), instance_path=("x",),
            ))

    def test_child_parts_are_also_frozen(self) -> None:
        cm = instantiate(DriveSystem)
        import pytest
        with pytest.raises(RuntimeError, match="frozen"):
            cm.root.battery.add_port("illegal", PortInstance(
                stable_id="x", definition_type=Part,
                definition_path=("x",), instance_path=("x",),
            ))


class TestIdentityConsistency:
    def test_all_ids_use_root_type_prefix(self) -> None:
        cm = instantiate(DriveSystem)
        root_seed_prefix = "DriveSystem"
        for path_str in cm.path_registry:
            assert root_seed_prefix in path_str


class TestAttributeProjection:
    def test_configured_model_delegates_to_root(self) -> None:
        cm = instantiate(DriveSystem)
        assert cm.battery is cm.root.battery
        assert cm.motor is cm.root.motor

    def test_deep_navigation(self) -> None:
        cm = instantiate(DriveSystem)
        slot = cm.battery.voltage
        assert isinstance(slot, ValueSlot)
        assert slot.is_parameter
