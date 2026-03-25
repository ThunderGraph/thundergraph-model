"""Unit tests for runtime instance objects."""

from __future__ import annotations

import pytest

from tg_model.execution.instances import ElementInstance, PartInstance, PortInstance
from tg_model.execution.value_slots import ValueSlot
from tg_model.model.elements import Part


class TestElementInstance:
    def test_path_string(self) -> None:
        inst = ElementInstance(
            stable_id="abc", definition_type=Part,
            definition_path=("x",), instance_path=("root", "x"),
            kind="part",
        )
        assert inst.path_string == "root.x"

    def test_repr(self) -> None:
        inst = ElementInstance(
            stable_id="abc", definition_type=Part,
            definition_path=("x",), instance_path=("root", "x"),
            kind="port",
        )
        assert "root.x" in repr(inst)
        assert "port" in repr(inst)


class TestPartInstance:
    def test_add_child_and_lookup(self) -> None:
        parent = PartInstance(
            stable_id="p", definition_type=Part,
            definition_path=(), instance_path=("root",),
        )
        child = PartInstance(
            stable_id="c", definition_type=Part,
            definition_path=("child",), instance_path=("root", "child"),
        )
        parent.add_child("child", child)
        assert parent.children == [child]
        assert parent.child is child

    def test_add_port_and_lookup(self) -> None:
        parent = PartInstance(
            stable_id="p", definition_type=Part,
            definition_path=(), instance_path=("root",),
        )
        port = PortInstance(
            stable_id="pt", definition_type=Part,
            definition_path=("out",), instance_path=("root", "out"),
            metadata={"direction": "out"},
        )
        parent.add_port("out", port)
        assert parent.ports == [port]
        assert parent.out is port
        assert port.direction == "out"

    def test_add_value_slot_and_lookup(self) -> None:
        parent = PartInstance(
            stable_id="p", definition_type=Part,
            definition_path=(), instance_path=("root",),
        )
        slot = ValueSlot(
            stable_id="s", instance_path=("root", "mass"),
            kind="attribute", metadata={"unit": "kg"},
        )
        parent.add_value_slot("mass", slot)
        assert parent.value_slots == [slot]
        assert parent.mass is slot

    def test_missing_child_raises(self) -> None:
        parent = PartInstance(
            stable_id="p", definition_type=Part,
            definition_path=(), instance_path=("root",),
        )
        with pytest.raises(AttributeError, match="nonexistent"):
            _ = parent.nonexistent


class TestValueSlot:
    def test_parameter_detection(self) -> None:
        slot = ValueSlot(stable_id="s", instance_path=("r", "v"), kind="parameter")
        assert slot.is_parameter is True
        assert slot.is_attribute is False

    def test_attribute_detection(self) -> None:
        slot = ValueSlot(stable_id="s", instance_path=("r", "v"), kind="attribute")
        assert slot.is_parameter is False
        assert slot.is_attribute is True

    def test_path_string(self) -> None:
        slot = ValueSlot(stable_id="s", instance_path=("root", "battery", "voltage"), kind="parameter")
        assert slot.path_string == "root.battery.voltage"
