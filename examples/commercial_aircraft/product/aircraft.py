"""Top-level vehicle product block for the notional Atlas-400F."""

from __future__ import annotations

from typing import Any

from commercial_aircraft.integrations.bindings import make_mission_range_margin_binding
from unitflow.catalogs.si import kg, m

from tg_model.model.definition_context import parameter_ref
from commercial_aircraft.product.major_assemblies.parts import (
    AircraftSystemsPart,
    EmpennageAssembly,
    FuselageAssembly,
    LandingGearAssembly,
    PropulsionInstallation,
    WingAssembly,
)
from tg_model.model.elements import Part
from tg_model.model.expr import sum_attributes


class Aircraft(Part):
    """Wide-body freighter configuration root: assembly tree, mass roll-up, thesis-style constraints.

    ``modeled_max_payload_kg`` is **derived** (MZFW − operating empty mass) and feeds L1 mission-closure
    acceptance via ``allocate(..., inputs=…)``. Aircraft-owned **mission desk** external compute
    (``mission_range_margin_m`` on this part)
    complements the structural range parameter ``modeled_max_design_range_m``.
    """

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("aircraft")
        from commercial_aircraft.program.cargo_jet_program import CargoJetProgram

        modeled_max_design_range_m = model.parameter("modeled_max_design_range_m", unit=m)
        notional_mzfw_kg = model.parameter("notional_mzfw_kg", unit=kg)
        notional_mtow_kg = model.parameter("notional_mtow_kg", unit=kg)
        notional_trip_fuel_kg = model.parameter("notional_trip_fuel_kg", unit=kg)
        scenario_payload = model.parameter("scenario_payload_mass_kg", unit=kg)
        scenario_range = model.parameter("scenario_design_range_m", unit=m)

        fuselage = model.composed_of("fuselage", FuselageAssembly)
        wing = model.composed_of("wing", WingAssembly)
        empennage = model.composed_of("empennage", EmpennageAssembly)
        landing_gear = model.composed_of("landing_gear", LandingGearAssembly)
        propulsion_installation = model.composed_of("propulsion_installation", PropulsionInstallation)
        aircraft_systems = model.composed_of("aircraft_systems", AircraftSystemsPart)

        operating_empty_mass_kg = model.attribute(
            "operating_empty_mass_kg",
            unit=kg,
            expr=sum_attributes(
                fuselage.dry_mass_kg,
                wing.dry_mass_kg,
                empennage.dry_mass_kg,
                landing_gear.dry_mass_kg,
                propulsion_installation.dry_mass_kg,
                aircraft_systems.dry_mass_kg,
            ),
        )

        modeled_max_payload_kg = model.attribute(
            "modeled_max_payload_kg",
            unit=kg,
            expr=notional_mzfw_kg - operating_empty_mass_kg,
        )
        mission_range_margin_m = model.attribute(
            "mission_range_margin_m",
            unit=m,
            computed_by=make_mission_range_margin_binding(
                root_block_type=CargoJetProgram,
                baseline_max_range_m=parameter_ref(CargoJetProgram, "mission_desk_baseline_max_range_m"),
            ),
        )

        model.constraint(
            "mzfw_covers_operating_empty",
            expr=notional_mzfw_kg >= operating_empty_mass_kg,
        )
        model.constraint(
            "mtow_covers_mzfw",
            expr=notional_mtow_kg >= notional_mzfw_kg,
        )
        model.constraint(
            "mission_range_margin_non_negative",
            expr=mission_range_margin_m >= 0 * m,
        )
        model.constraint(
            "notional_takeoff_mass_closure",
            expr=notional_mtow_kg
            >= sum_attributes(
                operating_empty_mass_kg,
                scenario_payload,
                notional_trip_fuel_kg,
            ),
        )
        model.constraint(
            "design_mission_payload_within_structural_envelope",
            expr=scenario_payload <= modeled_max_payload_kg,
        )
        model.constraint(
            "design_mission_range_within_modeled_envelope",
            expr=scenario_range <= modeled_max_design_range_m,
        )
