"""Unit tests for ConfiguredModel and instantiation."""

from __future__ import annotations

import pytest

from tg_model.execution.configured_model import ConfiguredModel, instantiate
from tg_model.execution.instances import PartInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.model.elements import Part, Requirement, System


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


class DriveSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("drive_system")
        battery = model.composed_of("battery", Battery)
        motor = model.composed_of("motor", Motor)
        model.connect(source=battery.power_out, target=motor.power_in, carrying="electrical_power")


def setup_function() -> None:
    Battery._reset_compilation()
    Motor._reset_compilation()
    DriveSystem._reset_compilation()


class TestInstantiation:
    def test_system_instantiate_matches_module_instantiate(self) -> None:
        """``RootType.instantiate()`` matches ``instantiate(RootType)`` (topology + binding counts)."""
        cm_fn = instantiate(DriveSystem)
        cm_cls = DriveSystem.instantiate()
        assert cm_fn.root.stable_id == cm_cls.root.stable_id
        assert set(cm_fn.path_registry.keys()) == set(cm_cls.path_registry.keys())
        assert set(cm_fn.id_registry.keys()) == set(cm_cls.id_registry.keys())
        assert len(cm_fn.connections) == len(cm_cls.connections)
        assert len(cm_fn.allocations) == len(cm_cls.allocations)
        assert len(cm_fn.references) == len(cm_cls.references)
        assert len(cm_fn.requirement_value_slots) == len(cm_cls.requirement_value_slots)

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
        battery = cm.root.battery
        motor = cm.root.motor
        assert isinstance(battery, PartInstance)
        assert isinstance(motor, PartInstance)
        power_out = battery.power_out
        power_in = motor.power_in
        assert isinstance(power_out, PortInstance)
        assert isinstance(power_in, PortInstance)
        assert power_out.direction == "out"
        assert power_in.direction == "in"

    def test_value_slots_instantiated(self) -> None:
        cm = instantiate(DriveSystem)
        battery = cm.root.battery
        motor = cm.root.motor
        assert isinstance(battery, PartInstance)
        assert isinstance(motor, PartInstance)
        charge = battery.charge
        voltage = battery.voltage
        torque = motor.torque
        speed = motor.shaft_speed
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
        class Req1Requirement(Requirement):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("req1")
                model.doc("Shall do X.")

        class AllocSystem(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("alloc_system")
                req = model.composed_of("req1", Req1Requirement)
                motor = model.composed_of("motor", Motor)
                model.allocate(req, motor)

        Req1Requirement._reset_compilation()
        cm = instantiate(AllocSystem)
        assert len(cm.allocations) == 1
        alloc = cm.allocations[0]
        assert alloc.requirement.kind == "requirement_block"
        assert alloc.target.kind == "part"
        assert "req1" in alloc.requirement.path_string
        assert "motor" in alloc.target.path_string
        AllocSystem._reset_compilation()
        Req1Requirement._reset_compilation()


class TestTopologyFreeze:
    def test_topology_is_frozen_after_instantiation(self) -> None:
        cm = instantiate(DriveSystem)
        import pytest

        with pytest.raises(RuntimeError, match="frozen"):
            cm.root.add_child(
                "illegal",
                PartInstance(
                    stable_id="x",
                    definition_type=Part,
                    definition_path=("x",),
                    instance_path=("x",),
                ),
            )

    def test_child_parts_are_also_frozen(self) -> None:
        cm = instantiate(DriveSystem)
        import pytest

        battery = cm.root.battery
        assert isinstance(battery, PartInstance)
        with pytest.raises(RuntimeError, match="frozen"):
            battery.add_port(
                "illegal",
                PortInstance(
                    stable_id="x",
                    definition_type=Part,
                    definition_path=("x",),
                    instance_path=("x",),
                ),
            )


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
