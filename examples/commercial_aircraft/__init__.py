"""Commercial cargo jet program example — see README.md and IMPLEMENTATION_PLAN.md."""

from __future__ import annotations

from commercial_aircraft.program.cargo_jet_program import CargoJetProgram


def reset_commercial_aircraft_types() -> None:
    """Clear cached ``compile()`` artifacts on example element types (tests / notebook re-runs)."""
    from commercial_aircraft.program.l1_requirement_blocks import (
        L1AirworthinessRequirements,
        L1MissionRequirements,
        L1ProductRequirements,
        L1RequirementsRoot,
    )
    from commercial_aircraft.product.aircraft import Aircraft
    from commercial_aircraft.product.major_assemblies.parts import (
        AircraftSystemsPart,
        EmpennageAssembly,
        FuselageAssembly,
        LandingGearAssembly,
        PropulsionInstallation,
        WingAssembly,
    )

    for t in (
        CargoJetProgram,
        Aircraft,
        FuselageAssembly,
        WingAssembly,
        EmpennageAssembly,
        LandingGearAssembly,
        PropulsionInstallation,
        AircraftSystemsPart,
        L1RequirementsRoot,
        L1MissionRequirements,
        L1AirworthinessRequirements,
        L1ProductRequirements,
    ):
        t._reset_compilation()


__all__ = ["CargoJetProgram", "reset_commercial_aircraft_types"]
