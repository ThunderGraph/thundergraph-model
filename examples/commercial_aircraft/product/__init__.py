"""Physical product (Parts) for the cargo jet example."""

from commercial_aircraft.product.aircraft import Aircraft
from commercial_aircraft.product.major_assemblies import (
    AircraftSystemsPart,
    EmpennageAssembly,
    FuselageAssembly,
    LandingGearAssembly,
    PropulsionInstallation,
    WingAssembly,
)

__all__ = [
    "Aircraft",
    "AircraftSystemsPart",
    "EmpennageAssembly",
    "FuselageAssembly",
    "LandingGearAssembly",
    "PropulsionInstallation",
    "WingAssembly",
]
