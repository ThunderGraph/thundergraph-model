"""Unit tests for graph_compiler — requirement package owner resolution.

Covers the System-in-System pattern: a Requirement lives inside a child System,
not directly under the root. This is the topology that triggered:

    GraphCompilationError: Symbol 'l1_energy_capacity.usable_battery_capacity_kj'
    has registered path (...) but could not be resolved under 'AutonomousEvProgram'

Every test in this file would have failed (or could not have caught a future
regression) before the owner_part fix in _compile_requirement_package_tree and
_compile_requirement_package_constraint.
"""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kJ

from tg_model.execution.configured_model import instantiate
from tg_model.execution.dependency_graph import NodeKind
from tg_model.execution.graph_compiler import GraphCompilationError, compile_graph
from tg_model.execution.validation import validate_graph
from tg_model.model.elements import Part, Requirement, System


# ---------------------------------------------------------------------------
# Model topology
#
#   RootProgram
#   └── energy  (EnergySubsystem — child System)
#       ├── battery  (BatteryModule — Part)
#       └── energy_req  (EnergyCapacityReq — Requirement)
#           ├── parameter: mission_energy_kj
#           ├── parameter: usable_capacity_kj
#           ├── attribute: energy_margin_kj  (expr = usable - mission)
#           └── constraint: margin_non_negative  (margin >= 0)
# ---------------------------------------------------------------------------

class BatteryModule(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("battery_module")
        model.parameter("usable_capacity_kj", unit=kJ)


class EnergyCapacityReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("energy_capacity")
        model.doc("Usable battery energy must cover mission demand.")
        mission = model.parameter("mission_energy_kj", unit=kJ)
        usable = model.parameter("usable_capacity_kj", unit=kJ)
        margin = model.attribute("energy_margin_kj", unit=kJ, expr=usable - mission)
        model.constraint("margin_non_negative", expr=margin >= Quantity(0, kJ))


class EnergySubsystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("energy_subsystem")
        model.parameter("mission_energy_kj", unit=kJ)
        model.composed_of("battery", BatteryModule)
        model.composed_of("energy_req", EnergyCapacityReq)


class RootProgram(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("root_program")
        model.composed_of("energy", EnergySubsystem)


_ALL_TYPES = (BatteryModule, EnergyCapacityReq, EnergySubsystem, RootProgram)


def setup_function() -> None:
    for t in _ALL_TYPES:
        t._reset_compilation()


# ---------------------------------------------------------------------------
# Primary regression: compile_graph must not raise
# ---------------------------------------------------------------------------

class TestSystemInSystemCompileDoesNotRaise:
    def test_compile_graph_succeeds(self) -> None:
        """Primary regression guard: compile_graph must not raise GraphCompilationError
        when a Requirement with attribute(expr=...) lives inside a child System."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        assert graph is not None

    def test_graph_validates_after_compile(self) -> None:
        """Graph produced for the System-in-System topology must pass static validation."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        result = validate_graph(graph)
        assert result.passed, result.failures


# ---------------------------------------------------------------------------
# Graph structure: attribute expression nodes
# ---------------------------------------------------------------------------

class TestSystemInSystemAttributeExprNodes:
    def test_derived_attribute_has_attribute_value_node(self) -> None:
        """The derived energy_margin_kj slot must compile to an ATTRIBUTE_VALUE node."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        node_id = f"val:{cm.energy.energy_req.energy_margin_kj.path_string}"
        node = graph.nodes.get(node_id)
        assert node is not None, f"Missing graph node {node_id!r}"
        assert node.kind == NodeKind.ATTRIBUTE_VALUE

    def test_expression_compute_node_is_local_expression(self) -> None:
        """The expression compute node for energy_margin_kj must be LOCAL_EXPRESSION."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        expr_node_id = f"expr:{cm.energy.energy_req.energy_margin_kj.path_string}"
        node = graph.nodes.get(expr_node_id)
        assert node is not None, f"Missing expression node {expr_node_id!r}"
        assert node.kind == NodeKind.LOCAL_EXPRESSION

    def test_expression_node_depends_on_both_parameter_slots(self) -> None:
        """The margin expression must have inbound edges from both parameter value nodes."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        expr_node_id = f"expr:{cm.energy.energy_req.energy_margin_kj.path_string}"
        deps = graph.dependencies_of(expr_node_id)

        mission_node = f"val:{cm.energy.energy_req.mission_energy_kj.path_string}"
        usable_node = f"val:{cm.energy.energy_req.usable_capacity_kj.path_string}"
        assert mission_node in deps, f"Expected edge from {mission_node!r}; got deps={deps}"
        assert usable_node in deps, f"Expected edge from {usable_node!r}; got deps={deps}"

    def test_expression_node_feeds_into_attribute_value_node(self) -> None:
        """The expression compute node must have an outbound edge to the value node."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        expr_node_id = f"expr:{cm.energy.energy_req.energy_margin_kj.path_string}"
        val_node_id = f"val:{cm.energy.energy_req.energy_margin_kj.path_string}"
        dependents = graph.dependents_of(expr_node_id)
        assert val_node_id in dependents, (
            f"Expected {expr_node_id!r} → {val_node_id!r}; dependents={dependents}"
        )


# ---------------------------------------------------------------------------
# Graph structure: constraint nodes
# ---------------------------------------------------------------------------

class TestSystemInSystemConstraintNodes:
    def test_constraint_has_constraint_check_node(self) -> None:
        """The margin_non_negative constraint must be compiled as a CONSTRAINT_CHECK node."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        constraint_id = f"check:{cm.energy.energy_req.path_string}.margin_non_negative"
        node = graph.nodes.get(constraint_id)
        assert node is not None, f"Missing constraint node {constraint_id!r}"
        assert node.kind == NodeKind.CONSTRAINT_CHECK

    def test_constraint_depends_on_derived_attribute_value(self) -> None:
        """The constraint check must be downstream of the derived attribute value node.
        This verifies the constraint handler has the correct owner scope after the fix."""
        cm = instantiate(RootProgram)
        graph, _ = compile_graph(cm)
        constraint_id = f"check:{cm.energy.energy_req.path_string}.margin_non_negative"
        margin_val_id = f"val:{cm.energy.energy_req.energy_margin_kj.path_string}"
        deps = graph.dependencies_of(constraint_id)
        assert margin_val_id in deps, (
            f"Constraint must depend on margin value node.\n"
            f"  expected: {margin_val_id!r}\n"
            f"  got deps: {deps}"
        )


# ---------------------------------------------------------------------------
# Deeper nesting: Requirement inside a Requirement inside a child System
# ---------------------------------------------------------------------------

class InnerReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("inner_req")
        model.doc("Inner requirement with its own derived attribute.")
        a = model.parameter("param_a_kj", unit=kJ)
        b = model.parameter("param_b_kj", unit=kJ)
        delta = model.attribute("delta_kj", unit=kJ, expr=a - b)
        model.constraint("delta_positive", expr=delta >= Quantity(0, kJ))


class OuterReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("outer_req")
        model.doc("Outer requirement that composes an inner requirement.")
        model.composed_of("inner", InnerReq)


class NestedSubsystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("nested_subsystem")
        model.composed_of("req", OuterReq)


class NestedRoot(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("nested_root")
        model.composed_of("sub", NestedSubsystem)


_NESTED_TYPES = (InnerReq, OuterReq, NestedSubsystem, NestedRoot)


class TestDeepNestedRequirementCompiles:
    def setup_method(self) -> None:
        for t in _NESTED_TYPES:
            t._reset_compilation()

    def test_compile_graph_succeeds_for_doubly_nested_requirement(self) -> None:
        """owner_part must propagate through recursive _compile_requirement_package_tree calls."""
        cm = instantiate(NestedRoot)
        graph, _ = compile_graph(cm)
        assert graph is not None

    def test_inner_requirement_attribute_node_exists(self) -> None:
        """The inner Requirement's derived attribute must compile correctly two levels deep."""
        cm = instantiate(NestedRoot)
        graph, _ = compile_graph(cm)
        delta_node_id = f"val:{cm.sub.req.inner.delta_kj.path_string}"
        node = graph.nodes.get(delta_node_id)
        assert node is not None, f"Missing graph node {delta_node_id!r}"
        assert node.kind == NodeKind.ATTRIBUTE_VALUE

    def test_inner_requirement_constraint_node_exists(self) -> None:
        """The inner Requirement's constraint must compile two levels deep."""
        cm = instantiate(NestedRoot)
        graph, _ = compile_graph(cm)
        constraint_id = f"check:{cm.sub.req.inner.path_string}.delta_positive"
        node = graph.nodes.get(constraint_id)
        assert node is not None, f"Missing constraint node {constraint_id!r}"
        assert node.kind == NodeKind.CONSTRAINT_CHECK
