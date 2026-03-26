"""Shim: L1 specs moved to :mod:`commercial_aircraft.program.l1_specs`."""

from commercial_aircraft.program.l1_specs import (
    L1_REQUIREMENTS,
    L1RequirementSpec,
    L1VerificationKind,
    iter_l1_requirements,
)

__all__ = ["L1_REQUIREMENTS", "L1RequirementSpec", "L1VerificationKind", "iter_l1_requirements"]
