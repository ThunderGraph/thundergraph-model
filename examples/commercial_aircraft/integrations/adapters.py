"""Fake external tools for the cargo jet example (structured, synchronous, auditable provenance)."""

from __future__ import annotations

from math import pow

from unitflow import Quantity
from unitflow.catalogs.si import kg

from tg_model.integrations.external_compute import ExternalComputeResult


class AtlasMissionDesk:
    """Notional range–payload desk: synthetic still-air range vs requested design range (margin output).

    Uses a simple payload scaling exponent on a **baseline** max-range parameter — not a real mission
    model. Provenance carries the internal scale factor for reporting.
    """

    name = "atlas_mission_desk_v0"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        payload = inputs["payload_kg"]
        requested = inputs["design_range_m"]
        baseline = inputs["baseline_max_range_m"]
        ref_payload = Quantity(100_000, kg)
        ratio = float((ref_payload / payload).magnitude)
        scale = pow(ratio, 0.15)
        synthetic_max = baseline * scale
        margin = synthetic_max - requested
        return ExternalComputeResult(
            value=margin,
            provenance={
                "tool": self.name,
                "payload_scale": scale,
                "synthetic_max_range_m": float(synthetic_max.magnitude),
            },
        )


class WingStructuralCaeSnapshot:
    """Notional wing CAE snapshot: mass-per-span intensity scaled by a program payload proxy.

    Consumes **wing-local** parameters plus ``scenario_payload_mass_kg`` from the program root via the
    binding (no globals).
    """

    name = "wing_structural_cae_snapshot_v0"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        dry = inputs["dry_mass_kg"]
        span = inputs["wing_span_m"]
        payload_proxy = inputs["payload_proxy_kg"]
        ref_payload = Quantity(100_000, kg)
        load_factor = 1.0 + float((payload_proxy / ref_payload).magnitude)
        intensity = (dry / span) * load_factor
        return ExternalComputeResult(
            value=intensity,
            provenance={
                "tool": self.name,
                "load_factor": load_factor,
            },
        )
