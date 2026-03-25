"""Unit tests for ModelDefinitionContext."""

from __future__ import annotations

import pytest

from tg_model.model.definition_context import ModelDefinitionContext, ModelDefinitionError
from tg_model.model.elements import Part, System
from tg_model.model.refs import AttributeRef, PartRef, PortRef, Ref


class DummyPart(Part):
    pass


class TestDeclarations:
    def test_part_declaration(self) -> None:
        ctx = ModelDefinitionContext(System)
        ref = ctx.part("battery", DummyPart)
        assert isinstance(ref, PartRef)
        assert ref.path == ("battery",)
        assert ref.kind == "part"
        assert ref.target_type is DummyPart
        assert "battery" in ctx.nodes

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

    def test_requirement_declaration(self) -> None:
        ctx = ModelDefinitionContext(System)
        ref = ctx.requirement("req1", "The system shall do X.")
        assert isinstance(ref, Ref)
        assert ref.kind == "requirement"
        assert ref.metadata["text"] == "The system shall do X."


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
        ctx = ModelDefinitionContext(System)
        attr = ctx.attribute("mass", unit="kg")
        port = ctx.port("out", direction="out")
        with pytest.raises(ModelDefinitionError, match="PortRef"):
            ctx.connect(attr, port)  # type: ignore[arg-type]


class TestAllocations:
    def test_allocate_records_edge(self) -> None:
        ctx = ModelDefinitionContext(System)
        req = ctx.requirement("req1", "Shall do X.")
        part = ctx.part("motor", DummyPart)
        ctx.allocate(req, part)
        assert len(ctx.edges) == 1
        assert ctx.edges[0]["kind"] == "allocate"


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
