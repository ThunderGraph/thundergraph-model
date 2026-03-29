"""External-compute binding factory for :class:`MarsTransferNapkinDesk`."""

from __future__ import annotations

from examples.mars_ntp_tug.integrations.adapters import MarsTransferNapkinDesk
from tg_model.integrations.external_compute import ExternalComputeBinding
from tg_model.model.refs import AttributeRef


def make_mars_transfer_napkin_binding(
    *,
    dry_mass_kg: AttributeRef,
    delta_v_m_s: AttributeRef,
    isp_s: AttributeRef,
    g0_m_s2: AttributeRef,
    min_thrust_to_weight: AttributeRef,
    thermal_to_jet_efficiency: AttributeRef,
    propellant_loadout_margin: AttributeRef,
    jet_kinetic_fraction: AttributeRef,
) -> ExternalComputeBinding:
    """Inputs are napkin **parameters** on the program root (``AttributeRef`` from ``model.parameter``)."""
    return ExternalComputeBinding(
        MarsTransferNapkinDesk(),
        inputs={
            "dry_mass_kg": dry_mass_kg,
            "delta_v_m_s": delta_v_m_s,
            "isp_s": isp_s,
            "g0_m_s2": g0_m_s2,
            "min_thrust_to_weight": min_thrust_to_weight,
            "thermal_to_jet_efficiency": thermal_to_jet_efficiency,
            "propellant_loadout_margin": propellant_loadout_margin,
            "jet_kinetic_fraction": jet_kinetic_fraction,
        },
    )
