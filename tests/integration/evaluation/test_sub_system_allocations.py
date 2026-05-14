"""Integration test: ``model.allocate(...)`` calls authored inside a composed
sub-System (not the top-level program) are collected into the root
``ConfiguredModel.allocations`` and wire correctly end-to-end.

Background
----------
Historically, ``_instantiate_allocations`` only inspected the root type's
compile artifact, so allocate edges declared inside a sub-System's
``define()`` were silently dropped. This violated the design intent that
each ``System`` class be self-contained — composable into larger programs
without requiring its allocations to be hoisted to the program root.

The walk now mirrors ``_instantiate_all_connections`` and
``_instantiate_all_references``: every ``PartInstance`` in the tree
contributes its own allocate edges, with paths re-rooted via
``part.instance_path``.

Coverage in this file
---------------------
1. Allocations declared in an inner System are present in
   ``cm.allocations`` after instantiating the outer System.
2. The constraint declared on the inner Requirement evaluates correctly
   end-to-end (inputs wired via the inner allocation).
3. Two inner Systems composed into the same outer System get distinct
   stable IDs even when their relative allocate paths are identical
   (no stable-id collisions across sub-System scopes).
4. Root-level allocations alongside sub-System allocations both work
   (no regression in the previously-working pattern).
"""

from __future__ import annotations

from unitflow import Quantity
from unitflow.catalogs.si import kN

from tg_model.execution.configured_model import instantiate
from tg_model.model.elements import Part, Requirement, System


# ──────────────────────────────────────────────────────────────────────────
# Shared declarations
# ──────────────────────────────────────────────────────────────────────────


class _Thruster(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("thruster")
        model.parameter("vacuum_thrust", unit=kN)


class _ThrustFloorReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("thrust_floor")
        model.doc("Thruster shall deliver at least the declared minimum vacuum thrust.")
        required = model.parameter("required_thrust", unit=kN)
        declared = model.parameter("declared_thrust", unit=kN)
        margin = model.attribute("thrust_margin", unit=kN, expr=declared - required)
        model.constraint("thrust_margin_non_negative", expr=margin >= Quantity(0, kN))


class _PropulsionSubsystem(System):
    """Inner System: composes Part + Requirement and wires the allocation locally."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("propulsion_subsystem")
        floor = model.parameter("mission_thrust_floor", unit=kN)
        thruster = model.composed_of("thruster", _Thruster)
        req = model.composed_of("thrust_req", _ThrustFloorReq)
        # This is the case that previously dropped silently: an allocate
        # authored inside a sub-System's define().
        model.allocate(
            req,
            thruster,
            inputs={
                "required_thrust": floor,
                "declared_thrust": thruster.vacuum_thrust,
            },
        )


class _ProgramWithOneSubSystem(System):
    """Outer program composing exactly one sub-System."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("program_with_one_subsystem")
        model.composed_of("prop", _PropulsionSubsystem)


class _ProgramWithTwoSubSystems(System):
    """Outer program composing two structurally-identical sub-Systems under
    different slot names. Exercises stable-id uniqueness."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("program_with_two_subsystems")
        model.composed_of("prop_a", _PropulsionSubsystem)
        model.composed_of("prop_b", _PropulsionSubsystem)


class _RootLevelOnlyProgram(System):
    """Regression check: allocation declared at the root, no sub-Systems involved."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("root_level_only_program")
        floor = model.parameter("mission_thrust_floor", unit=kN)
        thruster = model.composed_of("thruster", _Thruster)
        req = model.composed_of("thrust_req", _ThrustFloorReq)
        model.allocate(
            req,
            thruster,
            inputs={
                "required_thrust": floor,
                "declared_thrust": thruster.vacuum_thrust,
            },
        )


def setup_function() -> None:
    _Thruster._reset_compilation()
    _ThrustFloorReq._reset_compilation()
    _PropulsionSubsystem._reset_compilation()
    _ProgramWithOneSubSystem._reset_compilation()
    _ProgramWithTwoSubSystems._reset_compilation()
    _RootLevelOnlyProgram._reset_compilation()


# ──────────────────────────────────────────────────────────────────────────
# 1) Sub-System allocations are collected
# ──────────────────────────────────────────────────────────────────────────


def test_sub_system_allocation_collected_on_root() -> None:
    """An allocate declared inside _PropulsionSubsystem.define() should appear
    in the outer program's cm.allocations after instantiate()."""
    cm = instantiate(_ProgramWithOneSubSystem)
    assert len(cm.allocations) == 1, (
        "Allocation declared inside sub-System.define() was not collected"
    )
    alloc = cm.allocations[0]
    # Paths are re-rooted via the sub-System's instance_path.
    assert alloc.requirement.path_string == (
        "_ProgramWithOneSubSystem.prop.thrust_req"
    )
    assert alloc.target.path_string == "_ProgramWithOneSubSystem.prop.thruster"


def test_sub_system_allocation_parameter_overrides_resolve() -> None:
    """The inputs dict on a sub-System allocate must resolve against the
    sub-System's path_string (not the root's), because the relative paths
    in the edge are scoped to the declaring System."""
    cm = instantiate(_ProgramWithOneSubSystem)
    alloc = cm.allocations[0]
    overrides = alloc.parameter_overrides
    assert set(overrides.keys()) == {"required_thrust", "declared_thrust"}
    assert overrides["required_thrust"].path_string == (
        "_ProgramWithOneSubSystem.prop.mission_thrust_floor"
    )
    assert overrides["declared_thrust"].path_string == (
        "_ProgramWithOneSubSystem.prop.thruster.vacuum_thrust"
    )


# ──────────────────────────────────────────────────────────────────────────
# 2) End-to-end evaluation through a sub-System allocation
# ──────────────────────────────────────────────────────────────────────────


def test_sub_system_allocation_evaluates_pass() -> None:
    cm = instantiate(_ProgramWithOneSubSystem)
    result = cm.evaluate(
        inputs={
            cm.prop.mission_thrust_floor.stable_id: Quantity(50, kN),
            cm.prop.thruster.vacuum_thrust.stable_id: Quantity(80, kN),
        },
    )
    assert result.passed, result.failures


def test_sub_system_allocation_evaluates_fail() -> None:
    cm = instantiate(_ProgramWithOneSubSystem)
    result = cm.evaluate(
        inputs={
            cm.prop.mission_thrust_floor.stable_id: Quantity(100, kN),
            cm.prop.thruster.vacuum_thrust.stable_id: Quantity(60, kN),
        },
    )
    assert not result.passed


# ──────────────────────────────────────────────────────────────────────────
# 3) Stable-id uniqueness across sub-System scopes
# ──────────────────────────────────────────────────────────────────────────


def test_two_sub_systems_produce_two_distinct_allocations() -> None:
    """Two structurally identical sub-Systems composed under different slot
    names should produce TWO allocations with DISTINCT stable IDs."""
    cm = instantiate(_ProgramWithTwoSubSystems)
    assert len(cm.allocations) == 2

    sids = {a.stable_id for a in cm.allocations}
    assert len(sids) == 2, (
        "Allocations from two sub-System instances must have distinct stable_ids; "
        "collisions indicate the part.instance_path is not included in the stable_id"
    )

    # Endpoints should resolve into the two different subtrees.
    targets = {a.target.path_string for a in cm.allocations}
    assert targets == {
        "_ProgramWithTwoSubSystems.prop_a.thruster",
        "_ProgramWithTwoSubSystems.prop_b.thruster",
    }


def test_two_sub_systems_both_evaluate_independently() -> None:
    cm = instantiate(_ProgramWithTwoSubSystems)
    result = cm.evaluate(
        inputs={
            cm.prop_a.mission_thrust_floor.stable_id: Quantity(50, kN),
            cm.prop_a.thruster.vacuum_thrust.stable_id: Quantity(80, kN),
            cm.prop_b.mission_thrust_floor.stable_id: Quantity(50, kN),
            cm.prop_b.thruster.vacuum_thrust.stable_id: Quantity(40, kN),
        },
    )
    # prop_a passes (80 >= 50), prop_b fails (40 < 50) — overall fails but
    # both constraints were actually evaluated.
    assert not result.passed
    constraint_names = {cr.name for cr in result.constraint_results}
    assert any("prop_a" in n for n in constraint_names)
    assert any("prop_b" in n for n in constraint_names)


# ──────────────────────────────────────────────────────────────────────────
# 4) Root-level allocations still work (no regression)
# ──────────────────────────────────────────────────────────────────────────


def test_root_level_allocation_still_works() -> None:
    """The previously-supported pattern (allocate at root) must remain intact."""
    cm = instantiate(_RootLevelOnlyProgram)
    assert len(cm.allocations) == 1
    alloc = cm.allocations[0]
    assert alloc.requirement.path_string == "_RootLevelOnlyProgram.thrust_req"
    assert alloc.target.path_string == "_RootLevelOnlyProgram.thruster"


def test_root_level_allocation_evaluates_pass() -> None:
    cm = instantiate(_RootLevelOnlyProgram)
    result = cm.evaluate(
        inputs={
            cm.mission_thrust_floor.stable_id: Quantity(50, kN),
            cm.thruster.vacuum_thrust.stable_id: Quantity(80, kN),
        },
    )
    assert result.passed, result.failures
