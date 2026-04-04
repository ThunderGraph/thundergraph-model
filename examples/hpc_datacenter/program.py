"""Notional datacenter program: facility roll-up + two atomic Level-1 power requirements."""

from __future__ import annotations

from typing import Any

from unitflow.catalogs.si import kW

from tg_model.model.elements import Part, Requirement, System
from tg_model.model.expr import sum_attributes


class L1HpcRequirements(Requirement):
    """Executable Level-1 checks on the facility block (grid import + cooling envelope)."""

    @classmethod
    def define(cls, model: Any) -> None:
        r_grid = model.requirement(
            "req_grid_import_capacity",
            (
                "The aggregate facility electrical load (equipment electrical load plus auxiliary cooling) shall "
                "remain within the "
                "declared grid import capacity for the notional site interconnection (verification by analysis)."
            ),
            rationale=(
                "Atomic capacity obligation; executable acceptance compares scenario peak load to the "
                "declared import envelope on the allocated facility block."
            ),
        )
        scenario_peak = model.requirement_input(r_grid, "scenario_peak_kw", unit=kW)
        envelope_cap = model.requirement_input(r_grid, "envelope_capacity_kw", unit=kW)
        grid_headroom_kw = model.requirement_attribute(
            r_grid,
            "grid_headroom_kw",
            expr=envelope_cap - scenario_peak,
            unit=kW,
        )
        model.requirement_accept_expr(r_grid, expr=grid_headroom_kw >= 0 * kW)

        r_cool = model.requirement(
            "req_auxiliary_cooling_envelope",
            (
                "The auxiliary cooling electrical load shall remain within the declared cooling subsystem "
                "envelope for the notional facility (verification by analysis)."
            ),
            rationale=(
                "Atomic cooling-side obligation; compares scenario auxiliary cooling to a declared design "
                "maximum on the allocated facility block."
            ),
        )
        scenario_cooling = model.requirement_input(r_cool, "scenario_cooling_kw", unit=kW)
        envelope_cooling = model.requirement_input(r_cool, "envelope_cooling_kw", unit=kW)
        cooling_headroom_kw = model.requirement_attribute(
            r_cool,
            "cooling_headroom_kw",
            expr=envelope_cooling - scenario_cooling,
            unit=kW,
        )
        model.requirement_accept_expr(r_cool, expr=cooling_headroom_kw >= 0 * kW)


class L1HpcRoot(Requirement):
    """Top-level Level-1 grouping for the datacenter example."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.requirement_package("hpc", L1HpcRequirements)


class HpcColoFacility(Part):
    """Colocation hall: holds declared grid import and auxiliary cooling envelopes."""

    @classmethod
    def define(cls, model: Any) -> None:
        equipment_kw = model.parameter("equipment_electrical_load_kw", unit=kW)
        cooling_kw = model.parameter("auxiliary_cooling_load_kw", unit=kW)
        model.parameter("grid_import_capacity_kw", unit=kW)
        model.parameter("max_cooling_kw", unit=kW)
        model.attribute(
            "total_facility_kw",
            unit=kW,
            expr=sum_attributes(equipment_kw, cooling_kw),
        )
        model.constraint("positive_equipment_load_kw", expr=equipment_kw > 0 * kW)


class HpcDatacenterProgram(System):
    """Scenario parameters (equipment and auxiliary cooling load), Level-1 requirements, one facility part."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.parameter("equipment_electrical_load_kw", unit=kW)
        model.parameter("auxiliary_cooling_load_kw", unit=kW)

        l1 = model.requirement_package("l1", L1HpcRoot)
        facility = model.part("facility", HpcColoFacility)

        r_grid = l1.hpc.req_grid_import_capacity
        r_cool = l1.hpc.req_auxiliary_cooling_envelope
        model.allocate(
            r_grid,
            facility,
            inputs={
                "scenario_peak_kw": facility.total_facility_kw,
                "envelope_capacity_kw": facility.grid_import_capacity_kw,
            },
        )
        model.allocate(
            r_cool,
            facility,
            inputs={
                "scenario_cooling_kw": facility.auxiliary_cooling_load_kw,
                "envelope_cooling_kw": facility.max_cooling_kw,
            },
        )


def reset_hpc_datacenter_types() -> None:
    """Clear cached ``compile()`` artifacts (tests / notebook re-runs)."""
    for t in (HpcDatacenterProgram, HpcColoFacility, L1HpcRoot, L1HpcRequirements):
        t._reset_compilation()
