"""Notional major assemblies for Atlas-400F — each carries a dry-mass parameter and a sanity constraint.

Phase 2 mass stubs; ``WingAssembly`` adds a Phase 3 external-compute intensity attribute; other assemblies may gain tools in later phases.
"""

from __future__ import annotations

from typing import Any

from unitflow import Quantity
from unitflow.catalogs.si import kg, m

from tg_model.model.elements import Part


def _non_negative_dry_mass(model: Any, dry: Any) -> None:
    model.constraint(
        "dry_mass_non_negative",
        expr=dry >= Quantity(0, kg),
    )


class FuselageAssembly(Part):
    """Primary structure / cabin shell (mass lump)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("fuselage_assembly")
        dry = model.parameter("dry_mass_kg", unit=kg)
        _non_negative_dry_mass(model, dry)


class WingAssembly(Part):
    """Lifting surface assembly (mass lump)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("wing_assembly")
        from commercial_aircraft.integrations.bindings import make_wing_structural_intensity_binding
        from commercial_aircraft.program.cargo_jet_program import CargoJetProgram

        dry = model.parameter("dry_mass_kg", unit=kg)
        _non_negative_dry_mass(model, dry)
        span = model.parameter("notional_wing_span_m", unit=m)
        model.constraint("wing_span_positive", expr=span > Quantity(0, m))

        wing_cae_binding = make_wing_structural_intensity_binding(
            root_block_type=CargoJetProgram,
            wing_dry_mass_kg=dry,
            wing_span_m=span,
        )
        model.attribute(
            "wing_structural_intensity_kg_per_m",
            unit=kg / m,
            computed_by=wing_cae_binding,
        )


class EmpennageAssembly(Part):
    """Tail surfaces (mass lump)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("empennage_assembly")
        dry = model.parameter("dry_mass_kg", unit=kg)
        _non_negative_dry_mass(model, dry)


class LandingGearAssembly(Part):
    """Undercarriage (mass lump)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("landing_gear_assembly")
        dry = model.parameter("dry_mass_kg", unit=kg)
        _non_negative_dry_mass(model, dry)


class PropulsionInstallation(Part):
    """Engines, nacelles, mounts (mass lump)."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("propulsion_installation")
        dry = model.parameter("dry_mass_kg", unit=kg)
        _non_negative_dry_mass(model, dry)


class AircraftSystemsPart(Part):
    """Avionics, electrical, hydraulic, environmental — single lump for Phase 2."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("aircraft_systems")
        dry = model.parameter("dry_mass_kg", unit=kg)
        _non_negative_dry_mass(model, dry)
