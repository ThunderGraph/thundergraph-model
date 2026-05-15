"""Integration tests for Requirement class-identity deduplication.

A Requirement class is a specification statement. When the same Requirement
subclass is composed in multiple places from DIFFERENT defining classes (e.g.
inside a domain System AND inside a top-level rollup package), tg-model treats
them as ONE shared RequirementPackageInstance with multiple navigation paths.

When the SAME defining class introduces the same Requirement multiple times
(because that class is instantiated more than once), each instance gets its own
independent RequirementPackageInstance. This is the multi-instantiation case
and must NOT be deduped.

Parts and Systems are unaffected — they always retain distinct-instance semantics.
"""

from __future__ import annotations

import pytest
from unitflow import Quantity
from unitflow.catalogs.si import kN

from tg_model.execution.configured_model import instantiate
from tg_model.model.elements import Part, Requirement, System


# ── Shared leaf declarations ─────────────────────────────────────────────────

class _Thruster(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("thruster")
        model.parameter("thrust", unit=kN)


class _ThrustReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("thrust_req")
        model.doc("Thrust shall meet the floor.")
        declared = model.parameter("declared", unit=kN)
        floor    = model.parameter("floor",    unit=kN)
        margin   = model.attribute("margin", unit=kN, expr=declared - floor)
        model.constraint("margin_non_negative", expr=margin >= Quantity(0, kN))


class _CapacityReq(Requirement):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("capacity_req")
        model.doc("Capacity shall meet the minimum.")
        capacity = model.parameter("capacity", unit=kN)
        minimum  = model.parameter("minimum",  unit=kN)
        headroom = model.attribute("headroom", unit=kN, expr=capacity - minimum)
        model.constraint("headroom_non_negative", expr=headroom >= Quantity(0, kN))


# ── Programs for dedupe scenarios ────────────────────────────────────────────

class _RollupReqs(Requirement):
    """Top-level rollup that re-composes _ThrustReq — should alias the domain System's instance."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("rollup")
        model.doc("Top-level rollup view.")
        model.composed_of("thrust", _ThrustReq)


class _DomainSystem(System):
    """Domain System that owns _ThrustReq and allocates it to the thruster."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("domain")
        floor = model.parameter("floor_kN", unit=kN)
        thr   = model.composed_of("thruster", _Thruster)
        req   = model.composed_of("thrust_req", _ThrustReq)
        model.allocate(req, thr, inputs={
            "declared": thr.thrust,
            "floor":    floor,
        })


class _ProgramWithRollup(System):
    """Top-level program: domain System + rollup that also composes the same Requirement."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("program_with_rollup")
        model.composed_of("domain",   _DomainSystem)
        model.composed_of("rollup",   _RollupReqs)


# ── Programs for multi-instantiation (no-dedupe) scenario ────────────────────

class _SubSystem(System):
    """Sub-system that composes _ThrustReq internally."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("subsystem")
        floor = model.parameter("floor_kN", unit=kN)
        thr   = model.composed_of("thruster", _Thruster)
        req   = model.composed_of("thrust_req", _ThrustReq)
        model.allocate(req, thr, inputs={
            "declared": thr.thrust,
            "floor":    floor,
        })


class _ProgramWithTwoSubSystems(System):
    """Two instances of the same sub-System class — each should get its own Requirement instance."""
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("program_two_subsystems")
        model.composed_of("sub_a", _SubSystem)
        model.composed_of("sub_b", _SubSystem)


# ── Programs for regression tests ───────────────────────────────────────────

class _Motor(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("motor")
        model.parameter("torque", unit=kN)


class _ProgramTwoDistinctParts(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("program_two_parts")
        model.composed_of("motor_a", _Motor)
        model.composed_of("motor_b", _Motor)


class _InnerSystem(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("inner")
        model.parameter("p", unit=kN)


class _ProgramTwoDistinctSystems(System):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.name("program_two_systems")
        model.composed_of("inner_a", _InnerSystem)
        model.composed_of("inner_b", _InnerSystem)


def setup_function() -> None:
    for cls in (
        _Thruster, _ThrustReq, _CapacityReq, _RollupReqs, _DomainSystem,
        _ProgramWithRollup, _SubSystem, _ProgramWithTwoSubSystems,
        _Motor, _ProgramTwoDistinctParts, _InnerSystem, _ProgramTwoDistinctSystems,
    ):
        cls._reset_compilation()


# ── 1) Dedupe: same Requirement class composed by two DIFFERENT classes ──────

def test_same_req_class_two_parents_is_one_instance() -> None:
    """DomainSystem and RollupReqs both compose _ThrustReq — only one instance."""
    cm = instantiate(_ProgramWithRollup)
    domain_req  = cm.handle("_ProgramWithRollup.domain.thrust_req")
    rollup_req  = cm.handle("_ProgramWithRollup.rollup.thrust")
    assert domain_req is rollup_req, "Both paths must resolve to the SAME RequirementPackageInstance"


def test_alias_path_resolves_to_canonical_slots() -> None:
    """Both navigation paths point to the same ValueSlot objects."""
    cm = instantiate(_ProgramWithRollup)
    canonical_declared = cm.handle("_ProgramWithRollup.domain.thrust_req.declared")
    alias_declared     = cm.handle("_ProgramWithRollup.rollup.thrust.declared")
    assert canonical_declared is alias_declared


def test_id_registry_has_one_entry_per_req_instance() -> None:
    """id_registry dedupe: only one stable_id entry for _ThrustReq."""
    cm = instantiate(_ProgramWithRollup)
    thrust_req_entries = [
        (sid, obj) for sid, obj in cm.id_registry.items()
        if hasattr(obj, "package_type") and obj.package_type is _ThrustReq
    ]
    assert len(thrust_req_entries) == 1, (
        f"Expected exactly one id_registry entry for _ThrustReq, got {len(thrust_req_entries)}"
    )


def test_allocation_wires_shared_instance() -> None:
    """Allocation declared in DomainSystem uses the shared instance and correct source slots."""
    cm = instantiate(_ProgramWithRollup)
    assert len(cm.allocations) == 1
    alloc = cm.allocations[0]
    # Requirement points at the shared (canonical) instance
    assert alloc.requirement.path_string == "_ProgramWithRollup.domain.thrust_req"
    # parameter_overrides maps req-param-name → SOURCE slot (the Part side of the wiring)
    assert set(alloc.parameter_overrides.keys()) == {"declared", "floor"}
    assert alloc.parameter_overrides["declared"].path_string == "_ProgramWithRollup.domain.thruster.thrust"
    assert alloc.parameter_overrides["floor"].path_string == "_ProgramWithRollup.domain.floor_kN"


def test_end_to_end_evaluates_constraint_once() -> None:
    """Only one constraint result — not two copies of the same constraint."""
    cm = instantiate(_ProgramWithRollup)
    result = cm.evaluate(inputs={
        cm.domain.floor_kN.stable_id:        Quantity(50, kN),
        cm.domain.thruster.thrust.stable_id: Quantity(80, kN),
    })
    assert result.passed
    assert len(result.constraint_results) == 1, (
        f"Expected 1 constraint result (not duplicated), got {len(result.constraint_results)}"
    )


# ── 2) No-dedupe: same class instantiated multiple times ─────────────────────

def test_multi_instantiation_produces_distinct_req_instances() -> None:
    """sub_a and sub_b each get their OWN _ThrustReq instance (different subsystem instances)."""
    cm = instantiate(_ProgramWithTwoSubSystems)
    req_a = cm.handle("_ProgramWithTwoSubSystems.sub_a.thrust_req")
    req_b = cm.handle("_ProgramWithTwoSubSystems.sub_b.thrust_req")
    assert req_a is not req_b, "_SubSystem instances must each own their own _ThrustReq"


def test_multi_instantiation_distinct_slots() -> None:
    slot_a = cm_two = instantiate(_ProgramWithTwoSubSystems)
    slot_a_declared = cm_two.handle("_ProgramWithTwoSubSystems.sub_a.thrust_req.declared")
    slot_b_declared = cm_two.handle("_ProgramWithTwoSubSystems.sub_b.thrust_req.declared")
    assert slot_a_declared is not slot_b_declared


def test_multi_instantiation_two_allocations() -> None:
    cm = instantiate(_ProgramWithTwoSubSystems)
    assert len(cm.allocations) == 2
    targets = {a.target.path_string for a in cm.allocations}
    assert targets == {
        "_ProgramWithTwoSubSystems.sub_a.thruster",
        "_ProgramWithTwoSubSystems.sub_b.thruster",
    }


def test_multi_instantiation_evaluates_each_subsystem() -> None:
    cm = instantiate(_ProgramWithTwoSubSystems)
    result = cm.evaluate(inputs={
        cm.sub_a.floor_kN.stable_id:        Quantity(50, kN),
        cm.sub_a.thruster.thrust.stable_id: Quantity(80, kN),  # passes
        cm.sub_b.floor_kN.stable_id:        Quantity(50, kN),
        cm.sub_b.thruster.thrust.stable_id: Quantity(30, kN),  # fails
    })
    assert not result.passed
    assert len(result.constraint_results) == 2
    states = {cr.state for cr in result.constraint_results}
    assert "passed" in states and "failed" in states


# ── 3) Regression: Parts and Systems always produce distinct instances ────────

def test_part_composed_twice_distinct_instances() -> None:
    cm = instantiate(_ProgramTwoDistinctParts)
    motor_a = cm.handle("_ProgramTwoDistinctParts.motor_a")
    motor_b = cm.handle("_ProgramTwoDistinctParts.motor_b")
    assert motor_a is not motor_b
    assert motor_a.stable_id != motor_b.stable_id


def test_system_composed_twice_distinct_instances() -> None:
    cm = instantiate(_ProgramTwoDistinctSystems)
    inner_a = cm.handle("_ProgramTwoDistinctSystems.inner_a")
    inner_b = cm.handle("_ProgramTwoDistinctSystems.inner_b")
    assert inner_a is not inner_b
    assert inner_a.stable_id != inner_b.stable_id
