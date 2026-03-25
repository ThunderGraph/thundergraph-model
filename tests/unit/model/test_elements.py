"""Unit tests for base element types."""

from __future__ import annotations

from tg_model.model.elements import Element, Part, System


class TestElementHierarchy:
    def test_part_is_element(self) -> None:
        assert issubclass(Part, Element)

    def test_system_is_element(self) -> None:
        assert issubclass(System, Element)

    def test_element_define_is_noop_by_default(self) -> None:
        Element.define(None)  # type: ignore[arg-type]

    def test_element_compile_returns_dict(self) -> None:
        result = Element.compile()
        assert isinstance(result, dict)
        assert "Element" in result["owner"]
        assert result["nodes"] == {}
        assert result["edges"] == []
        Element._reset_compilation()
