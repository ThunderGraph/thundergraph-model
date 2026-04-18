"""Unit tests for ModelDefinitionContext."""

from __future__ import annotations

import pytest

from tg_model.model.definition_context import ModelDefinitionContext, ModelDefinitionError
from tg_model.model.elements import Part, Requirement, System
from tg_model.model.refs import AttributeRef, PartRef, PortRef, RequirementRef


class DummyPart(Part):
    pass


class DummyRequirement(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("dummy_requirement")
        model.doc("Stub requirement for unit tests.")


class TestDeclarations:
    def test_composed_of_part_declaration(self) -> None:
        ctx = ModelDefinitionContext(System)
        ref = ctx.composed_of("battery", DummyPart)
        assert isinstance(ref, PartRef)
        assert ref.path == ("battery",)
        assert ref.kind == "part"
        assert ref.target_type is DummyPart
        assert "battery" in ctx.nodes

    def test_composed_of_requirement_declaration(self) -> None:
        ctx = ModelDefinitionContext(System)
        ref = ctx.composed_of("req1", DummyRequirement)
        assert isinstance(ref, RequirementRef)
        assert ref.path == ("req1",)
        assert ref.kind == "requirement_block"
        assert ref.target_type is DummyRequirement
        assert "req1" in ctx.nodes

    def test_port_declaration(self) -> None:
        ctx = ModelDefinitionContext(Part)
        ref = ctx.port("power_out", direction="out")
        assert isinstance(ref, PortRef)
        assert ref.path == ("power_out",)
        assert ref.metadata["direction"] == "out"

    def test_attribute_declaration(self) -> None:
        ctx = ModelDefinitionContext(Part)
        ref = ctx.attribute("mass", unit="kg")
        assert isinstance(ref, AttributeRef)
        assert ref.path == ("mass",)
        assert ref.metadata["unit"] == "kg"

    def test_parameter_declaration(self) -> None:
        ctx = ModelDefinitionContext(Part)
        ref = ctx.parameter("voltage", unit="V")
        assert isinstance(ref, AttributeRef)
        assert ref.kind == "parameter"
        assert ref.metadata["unit"] == "V"


class TestDuplicateRejection:
    def test_duplicate_name_raises(self) -> None:
        ctx = ModelDefinitionContext(Part)
        ctx.port("out", direction="out")
        with pytest.raises(ModelDefinitionError, match="Duplicate"):
            ctx.port("out", direction="in")


class TestConnections:
    def test_connect_valid_ports(self) -> None:
        ctx = ModelDefinitionContext(System)
        src = ctx.port("src", direction="out")
        tgt = ctx.port("tgt", direction="in")
        ctx.connect(src, tgt, carrying="power")
        assert len(ctx.edges) == 1
        assert ctx.edges[0]["kind"] == "connect"
        assert ctx.edges[0]["carrying"] == "power"

    def test_connect_rejects_non_port(self) -> None:
        ctx = ModelDefinitionContext(Part)
        attr = ctx.attribute("mass", unit="kg")
        port = ctx.port("out", direction="out")
        with pytest.raises(ModelDefinitionError, match="PortRef"):
            ctx.connect(attr, port)  # type: ignore[arg-type]


class TestAllocations:
    def test_allocate_records_edge(self) -> None:
        ctx = ModelDefinitionContext(System)
        req = ctx.composed_of("req1", DummyRequirement)
        part = ctx.composed_of("motor", DummyPart)
        ctx.allocate(req, part)
        assert len(ctx.edges) == 1
        assert ctx.edges[0]["kind"] == "allocate"

    def test_owner_part_ref_has_empty_path(self) -> None:
        ctx = ModelDefinitionContext(System)
        self_ref = ctx.owner_part()
        assert isinstance(self_ref, PartRef)
        assert self_ref.path == ()
        assert self_ref.target_type is System
        assert self_ref.owner_type is System

    def test_root_block_matches_owner_part(self) -> None:
        ctx = ModelDefinitionContext(System)
        assert ctx.root_block().path == ctx.owner_part().path == ()

    def test_allocate_to_system_target_matches_allocate_root_block(self) -> None:
        ctx = ModelDefinitionContext(System)
        req = ctx.composed_of("req1", DummyRequirement)
        ctx.allocate_to_system(req)
        assert len(ctx.edges) == 1
        assert ctx.edges[0]["kind"] == "allocate"
        ctx2 = ModelDefinitionContext(System)
        req2 = ctx2.composed_of("req1", DummyRequirement)
        ctx2.allocate(req2, ctx2.root_block())
        assert ctx.edges[0]["target"].path == ctx2.edges[0]["target"].path

    def test_allocate_to_root_alias_matches_allocate_to_system(self) -> None:
        ctx = ModelDefinitionContext(System)
        req = ctx.composed_of("req1", DummyRequirement)
        ctx.allocate_to_root(req)
        assert len(ctx.edges) == 1
        assert ctx.edges[0]["kind"] == "allocate"
        ctx2 = ModelDefinitionContext(System)
        req2 = ctx2.composed_of("req1", DummyRequirement)
        ctx2.allocate_to_system(req2)
        assert ctx.edges[0]["target"].path == ctx2.edges[0]["target"].path


class TestFreezing:
    def test_frozen_context_rejects_mutations(self) -> None:
        ctx = ModelDefinitionContext(Part)
        ctx.freeze()
        with pytest.raises(ModelDefinitionError, match="Cannot mutate"):
            ctx.port("out", direction="out")

    def test_frozen_context_rejects_connect(self) -> None:
        ctx = ModelDefinitionContext(System)
        src = ctx.port("src", direction="out")
        tgt = ctx.port("tgt", direction="in")
        ctx.freeze()
        with pytest.raises(ModelDefinitionError, match="Cannot mutate"):
            ctx.connect(src, tgt)
