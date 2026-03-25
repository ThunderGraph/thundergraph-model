"""Unit tests for deterministic identity derivation."""

from __future__ import annotations

import uuid

from tg_model.model.elements import Part, System
from tg_model.model.identity import derive_declaration_id, derive_type_id, qualified_name


class TestQualifiedName:
    def test_includes_module_and_qualname(self) -> None:
        qn = qualified_name(Part)
        assert "tg_model" in qn
        assert "Part" in qn

    def test_different_classes_different_names(self) -> None:
        assert qualified_name(Part) != qualified_name(System)


class TestDeterministicIdentity:
    def test_type_id_is_deterministic(self) -> None:
        id1 = derive_type_id(Part)
        id2 = derive_type_id(Part)
        assert id1 == id2

    def test_different_types_get_different_ids(self) -> None:
        id1 = derive_type_id(Part)
        id2 = derive_type_id(System)
        assert id1 != id2

    def test_declaration_id_is_deterministic(self) -> None:
        id1 = derive_declaration_id(System, "battery", "power_out")
        id2 = derive_declaration_id(System, "battery", "power_out")
        assert id1 == id2

    def test_different_paths_get_different_ids(self) -> None:
        id1 = derive_declaration_id(System, "battery", "power_out")
        id2 = derive_declaration_id(System, "motor", "power_in")
        assert id1 != id2

    def test_ids_are_valid_uuid_strings(self) -> None:
        id_str = derive_type_id(Part)
        parsed = uuid.UUID(id_str)
        assert str(parsed) == id_str

    def test_same_name_different_module_gets_different_id(self) -> None:
        class Battery(Part):
            pass

        id_local = derive_type_id(Battery)
        id_part = derive_type_id(Part)
        assert id_local != id_part
