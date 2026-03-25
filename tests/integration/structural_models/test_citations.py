"""Phase 8: citation nodes and ``references`` edges — compile + instantiate + export shape."""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.core.units import Unit

from tg_model.execution.configured_model import instantiate
from tg_model.model.definition_context import ModelDefinitionError
from tg_model.model.elements import Part, System
from tg_model.model.identity import qualified_name
from tg_model.model.refs import Ref

DIMLESS = Unit.dimensionless()


class CitedPart(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        x = model.parameter("x", unit=DIMLESS)
        cite_a = model.citation("handbook_a", title="Example handbook", revision="2024")
        cite_b = model.citation("paper_b", doi="10.1000/182")
        req = model.requirement("local_req", "Subsystem shall be bounded.")
        cons = model.constraint("x_nonneg", expr=x >= Quantity(0, DIMLESS))
        model.references(x, cite_a)
        model.references(cons, cite_b)
        model.references(req, cite_a)


class CitedPlant(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        lic = model.citation("reg_basis", title="Illustrative regulatory pointer", url="https://example.invalid/rule")
        sub = model.part("subsystem", CitedPart)
        model.references(sub, lic)


def test_citations_in_compiled_edges_and_instantiate() -> None:
    CitedPlant._reset_compilation()
    compiled = CitedPlant.compile()
    assert "reg_basis" in compiled["nodes"]
    assert compiled["nodes"]["reg_basis"]["kind"] == "citation"
    sub_compiled = compiled["child_types"][qualified_name(CitedPart)]
    assert "handbook_a" in sub_compiled["nodes"]
    assert sub_compiled["nodes"]["handbook_a"]["kind"] == "citation"

    ref_edges = [e for e in compiled["edges"] if e["kind"] == "references"]
    ref_edges_sub = [e for e in sub_compiled["edges"] if e["kind"] == "references"]
    assert len(ref_edges) + len(ref_edges_sub) == 4
    kinds = {e["kind"] for e in compiled["edges"]}
    assert "references" in kinds

    cm = instantiate(CitedPlant)
    assert len(cm.references) == 4
    paths = {(r.source.path_string, r.citation.path_string) for r in cm.references}
    assert ("CitedPlant.subsystem", "CitedPlant.reg_basis") in paths
    assert ("CitedPlant.subsystem.x", "CitedPlant.subsystem.handbook_a") in paths


def test_references_requires_citation_target() -> None:
    class Bad(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            x = model.parameter("x", unit=DIMLESS)
            model.references(x, x)

    Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="citation"):
        Bad.compile()


def test_references_resolves_unknown_source() -> None:
    class Bad(System):
        @classmethod
        def define(cls, model):  # type: ignore[override]
            c = model.citation("c1", title="only")
            fake = Ref(
                owner_type=Bad,
                path=("not_declared",),
                kind="parameter",
                metadata={"unit": DIMLESS},
            )
            model.references(fake, c)

    Bad._reset_compilation()
    with pytest.raises(ModelDefinitionError, match="does not resolve"):
        Bad.compile()
