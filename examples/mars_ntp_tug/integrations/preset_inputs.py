"""Merge napkin desk outputs with declared hardware into a :meth:`ConfiguredModel.evaluate` map.

The graph still runs the same :class:`MarsTransferNapkinDesk` via ``computed_by``; calling the desk
here **once** lets notebooks fill requirement-package mirrors and the reactor/nozzle operating
point without hand-copying five separate numbers from the napkin snapshot.
"""

from __future__ import annotations

from typing import Any

from unitflow import Quantity
from unitflow.catalogs.si import kg, kN, m, s
from unitflow.core.units import Unit

from examples.mars_ntp_tug.integrations.adapters import MarsTransferNapkinDesk
from tg_model.execution.configured_model import ConfiguredModel

DIMLESS = Unit.dimensionless()
m_per_s = m / s
m_per_s2 = m / s**2


def run_mars_transfer_napkin_desk(napkin: dict[str, Quantity]) -> dict[str, Quantity]:
    """Run the desk once; ``napkin`` keys must match :meth:`MarsTransferNapkinDesk.compute` inputs."""
    res = MarsTransferNapkinDesk().compute(napkin)
    if not isinstance(res.value, dict):
        raise TypeError("expected multi-output desk result")
    return dict(res.value)


def merge_mars_ntp_eval_inputs(
    cm: ConfiguredModel,
    *,
    napkin: dict[str, Quantity],
    hardware: dict[str, Quantity],
) -> dict[Any, Quantity]:
    """Build ``evaluate`` inputs: napkin parameters, desk snapshot, hardware, mirrored req packages.

    Parameters
    ----------
    napkin
        Desk inputs: ``dry_mass_kg``, ``delta_v_m_s``, ``isp_s``, ``g0_m_s2``, ``min_thrust_to_weight``,
        ``thermal_to_jet_efficiency``, ``propellant_loadout_margin``, ``jet_kinetic_fraction``.
    hardware
        Part / policy slots not produced by the desk. Required keys::

            ``tank_propellant_mass_kg``, ``ullage_fraction``, ``feed_pressure_margin``,
            ``nozzle_vacuum_thrust_kn``, ``nozzle_area_ratio``, ``shadow_dose_proxy``, ``shadow_dose_limit``,
            ``guidance_string_count``, ``max_berthing_load_kn``, ``design_delta_v_m_s``,
            ``design_propellant_capacity_kg``, ``reactor_u235_mass_fraction``,
            ``reactor_triso_intact_fraction``, ``reactor_peak_fuel_matrix_temp_ratio``,
            ``reactor_control_drum_margin``, ``reactor_core_dry_mass_kg``, ``hot_side_temp_ratio``,
            ``declared_vacuum_thrust_kn``, ``thermal_power_margin`` (dimensionless, e.g. 1.02),
            ``mass_flow_margin`` (dimensionless), ``thrust_nameplate_margin`` (dimensionless, vs desk floor).
    """
    sim = run_mars_transfer_napkin_desk(napkin)
    th_mult = hardware["thermal_power_margin"]
    mdot_mult = hardware["mass_flow_margin"]
    thrust_mult = hardware["thrust_nameplate_margin"]

    p_th = sim["thermal_power_mw"] * th_mult
    mdot = sim["hydrogen_mass_flow_kg_s"] * mdot_mult
    f_des = sim["vacuum_thrust_kn"] * thrust_mult

    return {
        cm.napkin_dry_mass_incl_payload_kg: napkin["dry_mass_kg"],
        cm.napkin_transfer_delta_v: napkin["delta_v_m_s"],
        cm.napkin_specific_impulse_vacuum_s: napkin["isp_s"],
        cm.napkin_reference_gravity: napkin["g0_m_s2"],
        cm.napkin_thrust_to_weight_start: napkin["min_thrust_to_weight"],
        cm.napkin_thermal_to_jet_efficiency: napkin["thermal_to_jet_efficiency"],
        cm.napkin_propellant_loadout_margin: napkin["propellant_loadout_margin"],
        cm.napkin_jet_kinetic_fraction: napkin["jet_kinetic_fraction"],
        cm.reactor_core.rated_thermal_power: p_th,
        cm.reactor_core.hydrogen_mass_flow: mdot,
        cm.reactor_core.u235_mass_fraction: hardware["reactor_u235_mass_fraction"],
        cm.reactor_core.triso_intact_fraction: hardware["reactor_triso_intact_fraction"],
        cm.reactor_core.peak_fuel_matrix_temp_ratio: hardware["reactor_peak_fuel_matrix_temp_ratio"],
        cm.reactor_core.control_drum_safety_margin: hardware["reactor_control_drum_margin"],
        cm.reactor_core.core_dry_mass: hardware["reactor_core_dry_mass_kg"],
        cm.propellant_feed.tank_propellant_mass: hardware["tank_propellant_mass_kg"],
        cm.propellant_feed.ullage_fraction: hardware["ullage_fraction"],
        cm.propellant_feed.feed_pressure_margin: hardware["feed_pressure_margin"],
        cm.nozzle.vacuum_thrust: f_des,
        cm.nozzle.nozzle_area_ratio: hardware["nozzle_area_ratio"],
        cm.shadow_shield.dose_proxy_at_cargo: hardware["shadow_dose_proxy"],
        cm.shadow_shield.dose_limit_proxy: hardware["shadow_dose_limit"],
        cm.avionics_gnc.guidance_string_count: hardware["guidance_string_count"],
        cm.cargo_berthing.max_berthing_load: hardware["max_berthing_load_kn"],
        cm.design_envelope.design_delta_v_capability: hardware["design_delta_v_m_s"],
        cm.design_envelope.design_propellant_capacity: hardware["design_propellant_capacity_kg"],
        cm.requirements.reactor_fuel.u235_mass_fraction: hardware["reactor_u235_mass_fraction"],
        cm.requirements.reactor_fuel.triso_intact_fraction: hardware["reactor_triso_intact_fraction"],
        cm.requirements.reactor_fuel.peak_fuel_matrix_temp_ratio: hardware[
            "reactor_peak_fuel_matrix_temp_ratio"
        ],
        cm.requirements.thermal_hydraulic.thermal_power: p_th,
        cm.requirements.thermal_hydraulic.hydrogen_mass_flow: mdot,
        cm.requirements.thermal_hydraulic.hot_side_temp_ratio: hardware["hot_side_temp_ratio"],
        cm.requirements.propulsion.required_vacuum_thrust: sim["vacuum_thrust_kn"],
        cm.requirements.propulsion.declared_vacuum_thrust: f_des,
        cm.requirements.shielding.dose_proxy_at_cargo: hardware["shadow_dose_proxy"],
        cm.requirements.shielding.dose_limit_proxy: hardware["shadow_dose_limit"],
    }


def reference_napkin_assumptions() -> dict[str, Quantity]:
    """Default assumptions for the notebook (illustrative Mars cargo tug scenario)."""
    return {
        "dry_mass_kg": Quantity(98_000, kg),
        "delta_v_m_s": Quantity(5800, m_per_s),
        "isp_s": Quantity(900, s),
        "g0_m_s2": Quantity(9.80665, m_per_s2),
        "min_thrust_to_weight": Quantity(0.205, DIMLESS),
        "thermal_to_jet_efficiency": Quantity(0.38, DIMLESS),
        "propellant_loadout_margin": Quantity(1.08, DIMLESS),
        "jet_kinetic_fraction": Quantity(0.055, DIMLESS),
    }


def reference_hardware_overrides() -> dict[str, Quantity]:
    """Structural / envelope / policy inputs that the napkin desk does not synthesize."""
    return {
        "tank_propellant_mass_kg": Quantity(102_000, kg),
        "ullage_fraction": Quantity(0.06, DIMLESS),
        "feed_pressure_margin": Quantity(0.12, DIMLESS),
        "nozzle_area_ratio": Quantity(200, DIMLESS),
        "shadow_dose_proxy": Quantity(0.35, DIMLESS),
        "shadow_dose_limit": Quantity(1.0, DIMLESS),
        "guidance_string_count": Quantity(3, DIMLESS),
        "max_berthing_load_kn": Quantity(450, kN),
        "design_delta_v_m_s": Quantity(6500, m_per_s),
        "design_propellant_capacity_kg": Quantity(240_000, kg),
        "reactor_u235_mass_fraction": Quantity(0.965, DIMLESS),
        "reactor_triso_intact_fraction": Quantity(0.9992, DIMLESS),
        "reactor_peak_fuel_matrix_temp_ratio": Quantity(0.97, DIMLESS),
        "reactor_control_drum_margin": Quantity(0.08, DIMLESS),
        "reactor_core_dry_mass_kg": Quantity(2800, kg),
        "hot_side_temp_ratio": Quantity(0.97, DIMLESS),
        "thermal_power_margin": Quantity(1.04, DIMLESS),
        "mass_flow_margin": Quantity(1.05, DIMLESS),
        "thrust_nameplate_margin": Quantity(1.06, DIMLESS),
    }
