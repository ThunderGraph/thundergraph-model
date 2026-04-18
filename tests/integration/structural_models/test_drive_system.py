"""Integration test: a realistic DriveSystem model compiles end to end."""

from __future__ import annotations

from tg_model.model.elements import Part, Requirement, System
from tg_model.model.refs import AttributeRef, PartRef, PortRef


class ShallProvidePropulsionRequirement(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("shall_provide_propulsion")
        model.doc("The drive system shall provide propulsion torque.")


class PowerInterface(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("power_interface")
        model.attribute("voltage", unit="V")
        model.attribute("current", unit="A")


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
        shall_propel = model.composed_of("shall_provide_propulsion", ShallProvidePropulsionRequirement)
        battery = model.composed_of("battery", Battery)
        motor = model.composed_of("motor", Motor)
        model.connect(
            source=battery.power_out,
            target=motor.power_in,
            carrying="electrical_power",
        )
        model.allocate(shall_propel, motor)


def setup_function() -> None:
    PowerInterface._reset_compilation()
    Battery._reset_compilation()
    Motor._reset_compilation()
    DriveSystem._reset_compilation()
    ShallProvidePropulsionRequirement._reset_compilation()


class TestDriveSystemEndToEnd:
    def test_compiles_successfully(self) -> None:
        result = DriveSystem.compile()
        assert "DriveSystem" in result["owner"]

    def test_has_expected_parts(self) -> None:
        result = DriveSystem.compile()
        assert "battery" in result["nodes"]
        assert "motor" in result["nodes"]
        assert result["nodes"]["battery"]["kind"] == "part"
        assert result["nodes"]["motor"]["kind"] == "part"

    def test_has_requirement(self) -> None:
        result = DriveSystem.compile()
        assert "shall_provide_propulsion" in result["nodes"]
        node = result["nodes"]["shall_provide_propulsion"]
        assert node["kind"] == "requirement_block"

    def test_has_connection_edge(self) -> None:
        result = DriveSystem.compile()
        connect_edges = [e for e in result["edges"] if e["kind"] == "connect"]
        assert len(connect_edges) == 1
        edge = connect_edges[0]
        assert edge["source"]["path"] == ["battery", "power_out"]
        assert edge["target"]["path"] == ["motor", "power_in"]
        assert edge["carrying"] == "electrical_power"

    def test_has_allocation_edge(self) -> None:
        result = DriveSystem.compile()
        alloc_edges = [e for e in result["edges"] if e["kind"] == "allocate"]
        assert len(alloc_edges) == 1

    def test_child_types_compiled_recursively(self) -> None:
        result = DriveSystem.compile()
        child_keys = list(result["child_types"].keys())
        bat_key = next(k for k in child_keys if "Battery" in k)
        mot_key = next(k for k in child_keys if "Motor" in k)
        bat = result["child_types"][bat_key]
        assert "charge" in bat["nodes"]
        assert "power_out" in bat["nodes"]
        assert "voltage" in bat["nodes"]
        mot = result["child_types"][mot_key]
        assert "power_in" in mot["nodes"]
        assert "torque" in mot["nodes"]
        assert "shaft_speed" in mot["nodes"]
        assert mot["nodes"]["shaft_speed"]["kind"] == "parameter"

    def test_nested_ref_resolution_works(self) -> None:
        Battery._reset_compilation()
        ref = PartRef(owner_type=DriveSystem, path=("battery",), kind="part", target_type=Battery)
        port = ref.power_out
        assert isinstance(port, PortRef)
        assert port.path == ("battery", "power_out")

        attr = ref.charge
        assert isinstance(attr, AttributeRef)
        assert attr.path == ("battery", "charge")

    def test_repeated_compilation_is_idempotent(self) -> None:
        r1 = DriveSystem.compile()
        r2 = DriveSystem.compile()
        assert r1 is r2

    def test_compilation_from_separate_types_is_consistent(self) -> None:
        drv = DriveSystem.compile()
        bat = Battery.compile()
        bat_key = next(k for k in drv["child_types"] if "Battery" in k)
        assert drv["child_types"][bat_key] == bat

    def test_no_live_class_objects_in_canonical_nodes(self) -> None:
        result = DriveSystem.compile()
        for node in result["nodes"].values():
            assert "target_type_cls" not in node

    def test_type_registry_separated_from_nodes(self) -> None:
        result = DriveSystem.compile()
        assert "_type_registry" in result
        assert "battery" in result["_type_registry"]
        assert result["_type_registry"]["battery"] is Battery
