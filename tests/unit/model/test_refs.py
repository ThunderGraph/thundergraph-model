"""Unit tests for Ref types and PartRef chained resolution."""

from __future__ import annotations

import pytest

from tg_model.model.elements import Part, System
from tg_model.model.refs import AttributeRef, PartRef, PortRef, Ref


class SimplePart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.attribute("mass", unit="kg")
        model.port("power_out", direction="out")


class SimpleSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.part("child", SimplePart)


class TestRefBasics:
    def test_ref_local_name(self) -> None:
        r = Ref(owner_type=Part, path=("battery", "power_out"), kind="port")
        assert r.local_name == "battery.power_out"

    def test_ref_to_dict(self) -> None:
        r = Ref(owner_type=Part, path=("x",), kind="attribute", metadata={"unit": "m"})
        d = r.to_dict()
        assert d["owner"] == "Part"
        assert d["path"] == ["x"]
        assert d["kind"] == "attribute"
        assert d["metadata"] == {"unit": "m"}

    def test_ref_repr(self) -> None:
        r = PortRef(owner_type=Part, path=("out",), kind="port")
        assert "PortRef" in repr(r)
        assert "Part.out" in repr(r)


class TestPartRefChainedAccess:
    def test_resolves_port(self) -> None:
        SimplePart._reset_compilation()
        ref = PartRef(owner_type=SimpleSystem, path=("child",), kind="part", target_type=SimplePart)
        port_ref = ref.power_out
        assert isinstance(port_ref, PortRef)
        assert port_ref.path == ("child", "power_out")
        assert port_ref.kind == "port"

    def test_resolves_attribute(self) -> None:
        SimplePart._reset_compilation()
        ref = PartRef(owner_type=SimpleSystem, path=("child",), kind="part", target_type=SimplePart)
        attr_ref = ref.mass
        assert isinstance(attr_ref, AttributeRef)
        assert attr_ref.path == ("child", "mass")

    def test_invalid_member_raises(self) -> None:
        SimplePart._reset_compilation()
        ref = PartRef(owner_type=SimpleSystem, path=("child",), kind="part", target_type=SimplePart)
        with pytest.raises(AttributeError, match="no declared member named 'nonexistent'"):
            _ = ref.nonexistent

    def test_no_target_type_raises(self) -> None:
        ref = PartRef(owner_type=SimpleSystem, path=("orphan",), kind="part", target_type=None)
        with pytest.raises(AttributeError, match="no target_type"):
            _ = ref.anything
