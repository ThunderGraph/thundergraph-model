"""Top-level vehicle product block for the notional Atlas-400F."""

from __future__ import annotations

from typing import Any

from unitflow.catalogs.si import kg, m

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
    acceptance via ``allocate(..., inputs=…)``. Program-level **mission desk** external compute
    (``mission_range_margin_m`` on :class:`~commercial_aircraft.program.cargo_jet_program.CargoJetProgram`)
    complements the structural range parameter ``modeled_max_design_range_m``.
    """

    @classmethod
    def define(cls, model: Any) -> None:
        modeled_max_design_range_m = model.parameter("modeled_max_design_range_m", unit=m)
        notional_mzfw_kg = model.parameter("notional_mzfw_kg", unit=kg)
        notional_mtow_kg = model.parameter("notional_mtow_kg", unit=kg)
        notional_trip_fuel_kg = model.parameter("notional_trip_fuel_kg", unit=kg)

        fuselage = model.part("fuselage", FuselageAssembly)
        wing = model.part("wing", WingAssembly)
        empennage = model.part("empennage", EmpennageAssembly)
        landing_gear = model.part("landing_gear", LandingGearAssembly)
        propulsion_installation = model.part("propulsion_installation", PropulsionInstallation)
        aircraft_systems = model.part("aircraft_systems", AircraftSystemsPart)

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

        model.constraint(
            "mzfw_covers_operating_empty",
            expr=notional_mzfw_kg >= operating_empty_mass_kg,
        )
        model.constraint(
            "mtow_covers_mzfw",
            expr=notional_mtow_kg >= notional_mzfw_kg,
        )
