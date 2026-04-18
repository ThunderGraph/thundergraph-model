"""Notional datacenter program: facility roll-up + two atomic Level-1 power requirements."""

from __future__ import annotations

from typing import Any

from unitflow.catalogs.si import kW

from tg_model.model.elements import Part, Requirement, System
from tg_model.model.expr import sum_attributes


class GridImportCapacityRequirement(Requirement):
    """Aggregate facility load vs declared grid import capacity."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("grid_import_capacity")
        model.doc(
            "The aggregate facility electrical load (equipment electrical load plus auxiliary "
            "cooling) shall remain within the declared grid import capacity for the notional site "
            "interconnection (verification by analysis)."
        )
        scenario_peak = model.parameter("scenario_peak_kw", unit=kW)
        envelope_cap = model.parameter("envelope_capacity_kw", unit=kW)
        headroom = model.attribute("grid_headroom_kw", unit=kW, expr=envelope_cap - scenario_peak)
        model.constraint("grid_headroom_non_negative", expr=headroom >= 0 * kW)


class AuxiliaryCoolingEnvelopeRequirement(Requirement):
    """Auxiliary cooling load vs declared cooling subsystem envelope."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("auxiliary_cooling_envelope")
        model.doc(
            "The auxiliary cooling electrical load shall remain within the declared cooling "
            "subsystem envelope for the notional facility (verification by analysis)."
        )
        scenario_cooling = model.parameter("scenario_cooling_kw", unit=kW)
        envelope_cooling = model.parameter("envelope_cooling_kw", unit=kW)
        headroom = model.attribute(
            "cooling_headroom_kw", unit=kW, expr=envelope_cooling - scenario_cooling
        )
        model.constraint("cooling_headroom_non_negative", expr=headroom >= 0 * kW)


class L1HpcRequirements(Requirement):
    """Executable Level-1 checks on the facility block (grid import + cooling envelope)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("l1_hpc_requirements")
        model.doc("Level-1 power and cooling obligations for the notional HPC facility.")
        model.composed_of("grid_capacity", GridImportCapacityRequirement)
        model.composed_of("cooling_envelope", AuxiliaryCoolingEnvelopeRequirement)


class L1HpcRoot(Requirement):
    """Top-level Level-1 grouping for the datacenter example."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("l1_hpc_root")
        model.doc("Top-level Level-1 requirement tree for the HPC datacenter program.")
        model.composed_of("hpc", L1HpcRequirements)


class HpcColoFacility(Part):
    """Colocation hall: holds declared grid import and auxiliary cooling envelopes."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("hpc_colo_facility")
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
        model.name("hpc_datacenter_program")
        model.parameter("equipment_electrical_load_kw", unit=kW)
        model.parameter("auxiliary_cooling_load_kw", unit=kW)

        l1 = model.composed_of("l1", L1HpcRoot)
        facility = model.composed_of("facility", HpcColoFacility)

        r_grid = l1.hpc.grid_capacity
        r_cool = l1.hpc.cooling_envelope
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
    for t in (
        HpcDatacenterProgram,
        HpcColoFacility,
        L1HpcRoot,
        L1HpcRequirements,
        GridImportCapacityRequirement,
        AuxiliaryCoolingEnvelopeRequirement,
    ):
        t._reset_compilation()
