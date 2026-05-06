"""Unit tests for the new authoring-surface validators introduced in the API cleanup.

Covers:
- model.name() required on every Part / System / Requirement
- model.doc() required on every Requirement
- model.name() and model.doc() are at-most-once
- model.composed_of() dispatches correctly (Part → PartRef, Requirement → RequirementRef)
- model.composed_of() rejects non-Part / non-Requirement types
- Deleted methods raise AttributeError (requirement, requirement_input, requirement_attribute,
  requirement_accept_expr, requirement_package, part)
"""

from __future__ import annotations

import pytest
from unitflow.catalogs.si import kg

from tg_model.model.definition_context import ModelDefinitionContext, ModelDefinitionError
from tg_model.model.elements import Part, Requirement, System
from tg_model.model.refs import PartRef, RequirementRef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _LeafPart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("leaf")


class _LeafReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("leaf_req")
        model.doc("Stub leaf requirement.")


# ---------------------------------------------------------------------------
# model.name() required
# ---------------------------------------------------------------------------


class TestNameRequired:
    def test_part_missing_name_raises(self) -> None:
        class _P(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                pass

        _P._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="model\\.name"):
            _P.compile()

    def test_system_missing_name_raises(self) -> None:
        class _S(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                pass

        _S._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="model\\.name"):
            _S.compile()

    def test_requirement_missing_name_raises(self) -> None:
        class _R(Requirement):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.doc("has doc but no name.")

        _R._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="model\\.name"):
            _R.compile()

    def test_part_with_name_compiles(self) -> None:
        _LeafPart._reset_compilation()
        art = _LeafPart.compile()
        assert art is not None


# ---------------------------------------------------------------------------
# model.doc() required on Requirement
# ---------------------------------------------------------------------------


class TestDocRequired:
    def test_requirement_missing_doc_raises(self) -> None:
        class _R(Requirement):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("no_doc_req")

        _R._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="model\\.doc"):
            _R.compile()

    def test_part_without_doc_is_fine(self) -> None:
        """Parts do not require model.doc()."""
        _LeafPart._reset_compilation()
        art = _LeafPart.compile()
        assert art is not None

    def test_requirement_with_doc_compiles(self) -> None:
        _LeafReq._reset_compilation()
        art = _LeafReq.compile()
        assert art is not None


# ---------------------------------------------------------------------------
# At-most-once enforcement
# ---------------------------------------------------------------------------


class TestAtMostOnce:
    def test_name_called_twice_raises(self) -> None:
        class _P(Part):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("first")
                model.name("second")

        _P._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="model\\.name.*once"):
            _P.compile()

    def test_doc_called_twice_raises(self) -> None:
        class _R(Requirement):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("r")
                model.doc("first doc.")
                model.doc("second doc.")

        _R._reset_compilation()
        with pytest.raises(ModelDefinitionError, match="model\\.doc.*once"):
            _R.compile()


# ---------------------------------------------------------------------------
# model.composed_of() dispatch
# ---------------------------------------------------------------------------


class TestComposedOfDispatch:
    def test_part_child_returns_part_ref(self) -> None:
        ctx = ModelDefinitionContext(System)
        ref = ctx.composed_of("engine", _LeafPart)
        assert isinstance(ref, PartRef)
        assert ref.path == ("engine",)
        assert ref.kind == "part"
        assert ref.target_type is _LeafPart

    def test_requirement_child_returns_requirement_ref(self) -> None:
        ctx = ModelDefinitionContext(System)
        ref = ctx.composed_of("thrust_req", _LeafReq)
        assert isinstance(ref, RequirementRef)
        assert ref.path == ("thrust_req",)
        assert ref.kind == "requirement_block"
        assert ref.target_type is _LeafReq

    def test_non_element_type_raises(self) -> None:
        ctx = ModelDefinitionContext(System)
        with pytest.raises(ModelDefinitionError, match="Part, System, or Requirement"):
            ctx.composed_of("bad", str)  # type: ignore[arg-type]

    def test_system_child_returns_part_ref(self) -> None:
        class _ChildSys(System):
            @classmethod
            def define(cls, model):  # type: ignore[override]
                model.name("child_sys")

        ctx = ModelDefinitionContext(System)
        ref = ctx.composed_of("subsystem", _ChildSys)
        assert isinstance(ref, PartRef)
        assert ref.kind == "part"
        assert ref.target_type is _ChildSys

    def test_part_node_recorded_with_correct_kind(self) -> None:
        ctx = ModelDefinitionContext(System)
        ctx.composed_of("engine", _LeafPart)
        assert ctx.nodes["engine"].kind == "part"

    def test_requirement_node_recorded_with_correct_kind(self) -> None:
        ctx = ModelDefinitionContext(System)
        ctx.composed_of("thrust_req", _LeafReq)
        assert ctx.nodes["thrust_req"].kind == "requirement_block"


# ---------------------------------------------------------------------------
# Deleted methods raise AttributeError
# ---------------------------------------------------------------------------


class TestDeletedMethods:
    """Every removed method must be absent from ModelDefinitionContext."""

    def setup_method(self) -> None:
        self.ctx = ModelDefinitionContext(Part)

    def _assert_gone(self, name: str) -> None:
        assert not hasattr(self.ctx, name), f"Expected '{name}' to be deleted but it still exists"

    def test_requirement_deleted(self) -> None:
        self._assert_gone("requirement")

    def test_requirement_input_deleted(self) -> None:
        self._assert_gone("requirement_input")

    def test_requirement_attribute_deleted(self) -> None:
        self._assert_gone("requirement_attribute")

    def test_requirement_accept_expr_deleted(self) -> None:
        self._assert_gone("requirement_accept_expr")

    def test_requirement_package_deleted(self) -> None:
        self._assert_gone("requirement_package")

    def test_part_deleted(self) -> None:
        self._assert_gone("part")
