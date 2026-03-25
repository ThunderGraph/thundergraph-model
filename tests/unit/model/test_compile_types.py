"""Unit tests for type compilation."""

from __future__ import annotations

import pytest

from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part, System


class Battery(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.attribute("charge", unit="%")
        model.port("power_out", direction="out")


class Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.port("power_in", direction="in")
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


class TestBasicCompilation:
    def test_battery_compiles(self) -> None:
        result = Battery.compile()
        assert "Battery" in result["owner"]
        assert "charge" in result["nodes"]
        assert "power_out" in result["nodes"]
        assert result["nodes"]["charge"]["kind"] == "attribute"
        assert result["nodes"]["power_out"]["kind"] == "port"

    def test_motor_compiles(self) -> None:
        result = Motor.compile()
        assert "Motor" in result["owner"]
        assert "power_in" in result["nodes"]
        assert "torque" in result["nodes"]

    def test_drive_system_compiles_with_children(self) -> None:
        result = DriveSystem.compile()
        assert "DriveSystem" in result["owner"]
        assert "battery" in result["nodes"]
        assert "motor" in result["nodes"]
        assert result["nodes"]["battery"]["kind"] == "part"
        assert "Battery" in result["nodes"]["battery"]["target_type"]

    def test_child_types_are_embedded(self) -> None:
        result = DriveSystem.compile()
        child_keys = list(result["child_types"].keys())
        assert any("Battery" in k for k in child_keys)
        assert any("Motor" in k for k in child_keys)

    def test_owner_is_fully_qualified(self) -> None:
        result = Battery.compile()
        assert "." in result["owner"]

    def test_edges_are_serialized(self) -> None:
        result = DriveSystem.compile()
        assert len(result["edges"]) == 1
        edge = result["edges"][0]
        assert edge["kind"] == "connect"
        assert edge["source"]["path"] == ["battery", "power_out"]
        assert edge["target"]["path"] == ["motor", "power_in"]
        assert edge["carrying"] == "electrical_power"


class TestCompilationIdempotency:
    def test_compile_is_idempotent(self) -> None:
        r1 = Battery.compile()
        r2 = Battery.compile()
        assert r1 is r2


class TestCompilationCachesChildTypes:
    def test_child_type_reuses_cached_compilation(self) -> None:
        drv = DriveSystem.compile()
        bat_key = next(k for k in drv["child_types"] if "Battery" in k)
        bat_from_child = drv["child_types"][bat_key]
        bat_direct = Battery.compile()
        assert bat_from_child == bat_direct


class TestDeepNestedValidation:
    def test_two_level_nested_connection_validates(self) -> None:
        class InnerPart(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.port("deep_port", direction="out")

        class MiddlePart(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.part("inner", InnerPart)

        class OuterSystem(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                middle = model.part("middle", MiddlePart)
                local_in = model.port("local_in", direction="in")
                model.connect(source=middle.inner.deep_port, target=local_in)

        result = OuterSystem.compile()
        assert len(result["edges"]) == 1
        edge = result["edges"][0]
        assert edge["source"]["path"] == ["middle", "inner", "deep_port"]
        InnerPart._reset_compilation()
        MiddlePart._reset_compilation()
        OuterSystem._reset_compilation()


class TestInvalidConnections:
    def test_connect_to_nonexistent_member_raises(self) -> None:
        class BadSystem(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                battery = model.part("battery", Battery)
                from tg_model.model.refs import PortRef
                fake_ref = PortRef(
                    owner_type=BadSystem,
                    path=("battery", "nonexistent_port"),
                    kind="port",
                )
                local_port = model.port("local", direction="in")
                model.connect(source=fake_ref, target=local_port)

        with pytest.raises(ModelDefinitionError, match="missing member"):
            BadSystem.compile()
        BadSystem._reset_compilation()

    def test_connect_to_non_port_member_raises(self) -> None:
        class BadSystem2(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                battery = model.part("battery", Battery)
                from tg_model.model.refs import PortRef
                fake_ref = PortRef(
                    owner_type=BadSystem2,
                    path=("battery", "charge"),
                    kind="port",
                )
                local_port = model.port("local", direction="in")
                model.connect(source=fake_ref, target=local_port)

        with pytest.raises(ModelDefinitionError, match="not a port"):
            BadSystem2.compile()
        BadSystem2._reset_compilation()
