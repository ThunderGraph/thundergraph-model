"""Notional Mars-transfer napkin physics (structured external compute, same pattern as cargo jet).

These are **illustrative** algebraic sketches (Tsiolkovsky + vacuum thrust floor + jet-power napkin),
not trajectory or reactor codes. Provenance is attached for reporting and audit trails.
"""

from __future__ import annotations

from math import exp

from unitflow import Quantity
from unitflow.catalogs.si import MW, N, kg, kN, m, s
from unitflow.core.units import Unit

from tg_model.integrations.external_compute import ExternalComputeResult

m_per_s = m / s
m_per_s2 = m / s**2
kg_per_s = kg / s
DIMLESS = Unit.dimensionless()


class MarsTransferNapkinDesk:
    """Back-of-napkin Mars tug sizing snapshot (single evaluate, multi-output).

    Outputs
    -------
    * ``propellant_kg`` — Tsiolkovsky mass on *dry* stack (cargo + dry tug, excluding propellant).
    * ``wet_start_kg`` — dry + propellant * loadout margin (tank policy / ullage narrative).
    * ``vacuum_thrust_kn`` — start-of-burn vacuum thrust from thrust/weight * wet weight.
    * ``hydrogen_mass_flow_kg_s`` — ``F / (Isp * g0)`` vacuum idealization.
    * ``thermal_power_mw`` — jet kinetic power ~ (1/2) F v_e, divided by thermal-to-jet efficiency.
    """

    name = "mars_transfer_napkin_desk_v0"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        dry = inputs["dry_mass_kg"]
        delta_v = inputs["delta_v_m_s"]
        isp = inputs["isp_s"]
        g0 = inputs["g0_m_s2"]
        twr = inputs["min_thrust_to_weight"]
        eta = inputs["thermal_to_jet_efficiency"]
        loadout = inputs["propellant_loadout_margin"]
        jet_frac = inputs["jet_kinetic_fraction"]

        ve = isp * g0
        dv_over_ve = float((delta_v / ve).magnitude)
        mass_ratio = exp(dv_over_ve)
        m_prop = dry * Quantity(mass_ratio - 1.0, DIMLESS)
        m_wet = dry + m_prop * loadout

        f_n = twr * m_wet * g0
        mdot = f_n / ve
        # ``jet_kinetic_fraction`` folds ideal ½ṁv² vs bookkeeping (nozzle / cycle) into one knob.
        p_jet = jet_frac * f_n * ve
        p_th = p_jet / eta

        return ExternalComputeResult(
            value={
                "propellant_kg": m_prop,
                "wet_start_kg": m_wet,
                "vacuum_thrust_kn": f_n.to(kN),
                "hydrogen_mass_flow_kg_s": mdot.to(kg_per_s),
                "thermal_power_mw": p_th.to(MW),
            },
            provenance={
                "tool": self.name,
                "mass_ratio": mass_ratio,
                "effective_exhaust_velocity_m_s": float(ve.to(m_per_s).magnitude),
                "vacuum_thrust_n": float(f_n.to(N).magnitude),
                "jet_power_mw": float(p_jet.to(MW).magnitude),
            },
        )
