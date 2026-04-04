"""Notional Mars heavy-lift nuclear thermal tug — illustrative tg_model program.

All numeric policy limits are **pedagogical placeholders**, not design baselines.
"""

from __future__ import annotations

from typing import Any

from unitflow import Quantity
from unitflow.catalogs.si import MW, kg, kN, m, s
from unitflow.core.units import Unit

from examples.mars_ntp_tug.integrations.bindings import make_mars_transfer_napkin_binding
from tg_model.integrations.external_compute import link_external_routes
from tg_model.model.definition_context import parameter_ref
from tg_model.model.elements import Part, Requirement, System

DIMLESS = Unit.dimensionless()
kg_per_s = kg / s
m_per_s = m / s
m_per_s2 = m / s**2


def _root_napkin_binding(root_block_type: type, *output_names: str) -> Any:
    return make_mars_transfer_napkin_binding(
        dry_mass_kg=parameter_ref(root_block_type, "napkin_dry_mass_incl_payload_kg"),
        delta_v_m_s=parameter_ref(root_block_type, "napkin_transfer_delta_v"),
        isp_s=parameter_ref(root_block_type, "napkin_specific_impulse_vacuum_s"),
        g0_m_s2=parameter_ref(root_block_type, "napkin_reference_gravity"),
        min_thrust_to_weight=parameter_ref(root_block_type, "napkin_thrust_to_weight_start"),
        thermal_to_jet_efficiency=parameter_ref(root_block_type, "napkin_thermal_to_jet_efficiency"),
        propellant_loadout_margin=parameter_ref(root_block_type, "napkin_propellant_loadout_margin"),
        jet_kinetic_fraction=parameter_ref(root_block_type, "napkin_jet_kinetic_fraction"),
        output_names=output_names or None,
    )


class NtpCorePart(Part):
    """TRISO-in-matrix region: thermal power, hydrogen flow, enrichment, temperature ratio."""

    @classmethod
    def define(cls, model: Any) -> None:
        rated_thermal_power = model.parameter("rated_thermal_power", unit=MW)
        mdot = model.parameter("hydrogen_mass_flow", unit=kg_per_s)
        enrich = model.parameter("u235_mass_fraction", unit=DIMLESS)
        triso_ok = model.parameter("triso_intact_fraction", unit=DIMLESS)
        temp_ratio = model.parameter("peak_fuel_matrix_temp_ratio", unit=DIMLESS)
        drum = model.parameter("control_drum_safety_margin", unit=DIMLESS)
        model.parameter("core_dry_mass", unit=kg)
        napkin_b = _root_napkin_binding(
            MarsNuclearTug,
            "hydrogen_mass_flow_kg_s",
            "thermal_power_mw",
        )
        mission_mdot = model.attribute(
            "mission_required_hydrogen_mass_flow",
            unit=kg_per_s,
            computed_by=napkin_b,
        )
        mission_pth = model.attribute(
            "mission_required_thermal_power",
            unit=MW,
            computed_by=napkin_b,
        )
        link_external_routes(
            napkin_b,
            {
                "hydrogen_mass_flow_kg_s": mission_mdot,
                "thermal_power_mw": mission_pth,
            },
        )
        model.constraint("core_flow_positive", expr=mdot > 0 * kg_per_s)
        model.constraint("core_enrichment_heu_floor", expr=enrich >= Quantity(0.95, DIMLESS))
        model.constraint("core_triso_integrity_floor", expr=triso_ok >= Quantity(0.999, DIMLESS))
        model.constraint("core_matrix_temp_ratio_le_one", expr=temp_ratio <= Quantity(1.0, DIMLESS))
        model.constraint("core_shutdown_margin_positive", expr=drum > 0 * DIMLESS)
        model.constraint(
            "core_thermal_covers_mission_desk",
            expr=rated_thermal_power >= mission_pth * Quantity(0.90, DIMLESS),
        )
        model.constraint(
            "core_flow_covers_mission_desk",
            expr=mdot >= mission_mdot * Quantity(0.90, DIMLESS),
        )


class PropellantFeedPart(Part):
    """Cryogenic hydrogen tankage and feed path (lumped)."""

    @classmethod
    def define(cls, model: Any) -> None:
        tank = model.parameter("tank_propellant_mass", unit=kg)
        ull = model.parameter("ullage_fraction", unit=DIMLESS)
        p = model.parameter("feed_pressure_margin", unit=DIMLESS)
        model.constraint("propellant_mass_positive", expr=tank > 0 * kg)
        model.constraint("ullage_bounded", expr=ull <= Quantity(0.15, DIMLESS))
        model.constraint("feed_pressure_margin_ok", expr=p > 0 * DIMLESS)


class NozzleAssemblyPart(Part):
    """Regeneratively cooled nozzle segment (lumped vacuum thrust)."""

    @classmethod
    def define(cls, model: Any) -> None:
        f = model.parameter("vacuum_thrust", unit=kN)
        model.parameter("nozzle_area_ratio", unit=DIMLESS)
        napkin_b = _root_napkin_binding(MarsNuclearTug, "vacuum_thrust_kn")
        mission_thrust = model.attribute(
            "mission_min_vacuum_thrust",
            unit=kN,
            computed_by=napkin_b,
        )
        link_external_routes(napkin_b, {"vacuum_thrust_kn": mission_thrust})
        model.constraint("vacuum_thrust_positive", expr=f > 0 * kN)
        model.constraint(
            "nozzle_thrust_covers_mission_desk",
            expr=f >= mission_thrust * Quantity(0.95, DIMLESS),
        )


class ShadowShieldPart(Part):
    """Payload-side attenuation (dose proxy vs limit, dimensionless scale)."""

    @classmethod
    def define(cls, model: Any) -> None:
        d = model.parameter("dose_proxy_at_cargo", unit=DIMLESS)
        lim = model.parameter("dose_limit_proxy", unit=DIMLESS)
        model.constraint("dose_below_limit", expr=d <= lim)


class AvionicsGncPart(Part):
    """Navigation, guidance, fault management (redundancy as a count)."""

    @classmethod
    def define(cls, model: Any) -> None:
        n = model.parameter("guidance_string_count", unit=DIMLESS)
        model.constraint("dual_string_gnc", expr=n >= Quantity(2.0, DIMLESS))


class CargoBerthingPart(Part):
    """Heavy cargo interface loads."""

    @classmethod
    def define(cls, model: Any) -> None:
        f = model.parameter("max_berthing_load", unit=kN)
        model.constraint("berthing_load_positive", expr=f > 0 * kN)


class TugDesignEnvelopePart(Part):
    """Declared mission envelope (Δv capability, propellant capacity) for closure checks."""

    @classmethod
    def define(cls, model: Any) -> None:
        dv = model.parameter("design_delta_v_capability", unit=m_per_s)
        model.parameter("design_propellant_capacity", unit=kg)
        model.constraint("delta_v_cap_positive", expr=dv > 0 * m_per_s)


class MissionSizingPart(Part):
    """Mission desk snapshot and input sanity checks for the notional transfer scenario."""

    @classmethod
    def define(cls, model: Any) -> None:
        p_dv = model.parameter("mission_delta_v_required", unit=m_per_s)
        p_eta = model.parameter("thermal_to_jet_efficiency", unit=DIMLESS)
        p_loadout = model.parameter("propellant_loadout_margin", unit=DIMLESS)
        p_jet_frac = model.parameter("jet_kinetic_fraction", unit=DIMLESS)
        napkin_b = _root_napkin_binding(MarsNuclearTug)
        sim_prop = model.attribute("sim_propellant_required_kg", unit=kg, computed_by=napkin_b)
        sim_wet = model.attribute("sim_wet_mass_start_kg", unit=kg, computed_by=napkin_b)
        sim_thrust = model.attribute("sim_min_vacuum_thrust_kn", unit=kN, computed_by=napkin_b)
        sim_mdot = model.attribute("sim_hydrogen_mass_flow_kg_s", unit=kg_per_s, computed_by=napkin_b)
        sim_pth = model.attribute("sim_rated_thermal_power_mw", unit=MW, computed_by=napkin_b)
        link_external_routes(
            napkin_b,
            {
                "propellant_kg": sim_prop,
                "wet_start_kg": sim_wet,
                "vacuum_thrust_kn": sim_thrust,
                "hydrogen_mass_flow_kg_s": sim_mdot,
                "thermal_power_mw": sim_pth,
            },
        )
        model.attribute("mission_propellant_required", unit=kg, expr=sim_prop)
        model.attribute("mission_min_vacuum_thrust", unit=kN, expr=sim_thrust)
        model.constraint("napkin_propellant_loadout_margin_ge_one", expr=p_loadout >= Quantity(1.0, DIMLESS))
        model.constraint("napkin_jet_kinetic_fraction_positive", expr=p_jet_frac > 0 * DIMLESS)
        model.constraint("napkin_thermal_efficiency_gt_floor", expr=p_eta > Quantity(0.05, DIMLESS))
        model.constraint("napkin_thermal_efficiency_lt_ceiling", expr=p_eta < Quantity(0.99, DIMLESS))


class ReqReactorFuelTRISO(Requirement):
    """HEU fraction, TRISO integrity, matrix temperature ratio (package + leaf text)."""

    @classmethod
    def define(cls, model: Any) -> None:
        enrich = model.parameter("u235_mass_fraction", unit=DIMLESS)
        triso_ok = model.parameter("triso_intact_fraction", unit=DIMLESS)
        temp_ratio = model.parameter("peak_fuel_matrix_temp_ratio", unit=DIMLESS)
        model.constraint("pkg_enrichment_ge_95pct", expr=enrich >= Quantity(0.95, DIMLESS))
        model.constraint("pkg_triso_intact_ge_999", expr=triso_ok >= Quantity(0.999, DIMLESS))
        model.constraint("pkg_matrix_temp_ratio_le_one", expr=temp_ratio <= Quantity(1.0, DIMLESS))

        model.requirement(
            "req_heu_fuel_specification",
            (
                "The loaded fuel shall meet the program HEU mass-fraction floor for this notional tug "
                "(verification by analysis / assay records)."
            ),
            rationale="Separates policy text from the package-level executable constraints.",
        )
        r_triso = model.requirement(
            "req_triso_barrier_function",
            (
                "TRISO particle coatings shall preserve a bounded fraction of intact particles under "
                "declared thermal cycling for this concept (verification by qualification test data)."
            ),
            rationale="Ties formal requirement language to the TRISO integrity parameter.",
        )
        cite = model.citation(
            "cite_triso_illustrative",
            title="Illustrative TRISO fuel description (notional)",
            standard_id="DEMO-TRISO-NTP-001",
        )
        model.references(r_triso, cite)


class ReqThermalHydraulic(Requirement):
    """Power, flow, and hot-side temperature ratio (mirrors core operating point)."""

    @classmethod
    def define(cls, model: Any) -> None:
        p_th = model.parameter("thermal_power", unit=MW)
        mdot = model.parameter("hydrogen_mass_flow", unit=kg_per_s)
        t_ratio = model.parameter("hot_side_temp_ratio", unit=DIMLESS)
        model.constraint("pkg_thermal_power_positive", expr=p_th > 0 * MW)
        model.constraint("pkg_mass_flow_positive", expr=mdot > 0 * kg_per_s)
        model.constraint("pkg_temp_ratio_le_one", expr=t_ratio <= Quantity(1.0, DIMLESS))
        model.requirement(
            "req_channel_cooling_envelope",
            (
                "Core thermal-hydraulic operation shall remain within the declared hot-side temperature ratio "
                "and positive-flow envelope for the operating scenario (verification by analysis)."
            ),
        )


class ReqPropulsionNtp(Requirement):
    """Vacuum thrust margin vs mission floor (mirrors nozzle + scenario)."""

    @classmethod
    def define(cls, model: Any) -> None:
        f_req = model.parameter("required_vacuum_thrust", unit=kN)
        f_des = model.parameter("declared_vacuum_thrust", unit=kN)
        margin = model.attribute("vacuum_thrust_margin", unit=kN, expr=f_des - f_req)
        model.constraint("pkg_thrust_margin_non_negative", expr=margin >= 0 * kN)
        model.requirement(
            "req_ntp_vacuum_thrust_capability",
            (
                "The propulsion subsystem shall deliver vacuum thrust no less than the declared mission floor "
                "for Earth-Mars cargo transfer burns (verification by test / analysis)."
            ),
        )


class ReqShielding(Requirement):
    """Dose proxy at cargo plane vs limit."""

    @classmethod
    def define(cls, model: Any) -> None:
        d = model.parameter("dose_proxy_at_cargo", unit=DIMLESS)
        lim = model.parameter("dose_limit_proxy", unit=DIMLESS)
        headroom = model.attribute("dose_headroom", unit=DIMLESS, expr=lim - d)
        model.constraint("pkg_dose_headroom_non_negative", expr=headroom >= 0 * DIMLESS)
        model.requirement(
            "req_payload_dose_bound",
            (
                "Ionizing dose at the cargo interface shall not exceed the declared limit proxy "
                "(verification by analysis)."
            ),
        )


class ReqMissionMarsTransfer(Requirement):
    """Executable closure: scenario Δv and propellant vs design envelope."""

    @classmethod
    def define(cls, model: Any) -> None:
        r_dv = model.requirement(
            "req_delta_v_closure",
            (
                "The design shall close the scenario Earth-Mars transfer delta-v within the declared "
                "capability envelope (verification by mission analysis)."
            ),
        )
        scenario_dv = model.requirement_input(r_dv, "scenario_delta_v", unit=m_per_s)
        envelope_dv = model.requirement_input(r_dv, "envelope_delta_v", unit=m_per_s)
        dv_margin = model.requirement_attribute(
            r_dv,
            "delta_v_margin",
            expr=envelope_dv - scenario_dv,
            unit=m_per_s,
        )
        model.requirement_accept_expr(r_dv, expr=dv_margin >= 0 * m_per_s)

        r_mp = model.requirement(
            "req_propellant_mass_closure",
            (
                "Loaded propellant mass shall meet or exceed the scenario-required hydrogen mass for the reference "
                "transfer (verification by mass accounting)."
            ),
        )
        scenario_mp = model.requirement_input(r_mp, "scenario_propellant_kg", unit=kg)
        available_mp = model.requirement_input(r_mp, "available_propellant_kg", unit=kg)
        mp_margin = model.requirement_attribute(
            r_mp,
            "propellant_margin_kg",
            expr=available_mp - scenario_mp,
            unit=kg,
        )
        model.requirement_accept_expr(r_mp, expr=mp_margin >= 0 * kg)


class ReqSafetyPolicy(Requirement):
    """Handling / subcritical assembly policy (text + citation only in this slice)."""

    @classmethod
    def define(cls, model: Any) -> None:
        r = model.requirement(
            "req_subcritical_assembly_rules",
            (
                "Ground and launch-site handling shall maintain subcritical configurations per the program safety "
                "basis (verification by procedure / criticality safety analysis)."
            ),
        )
        cite = model.citation(
            "cite_handling_illustrative",
            title="Illustrative criticality safety basis (notional)",
            standard_id="DEMO-CRIT-SAFE-001",
        )
        model.references(r, cite)


class NtpRequirementsRoot(Requirement):
    """Top-level requirement tree for the tug."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.requirement_package("reactor_fuel", ReqReactorFuelTRISO)
        model.requirement_package("thermal_hydraulic", ReqThermalHydraulic)
        model.requirement_package("propulsion", ReqPropulsionNtp)
        model.requirement_package("shielding", ReqShielding)
        model.requirement_package("mission", ReqMissionMarsTransfer)
        model.requirement_package("safety_policy", ReqSafetyPolicy)


class MarsNuclearTug(System):
    """NTP Mars cargo tug: hardware parts + composable requirements + mission scenario parameters."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.parameter("napkin_dry_mass_incl_payload_kg", unit=kg)
        p_dv = model.parameter("napkin_transfer_delta_v", unit=m_per_s)
        model.parameter("napkin_specific_impulse_vacuum_s", unit=s)
        model.parameter("napkin_reference_gravity", unit=m_per_s2)
        model.parameter("napkin_thrust_to_weight_start", unit=DIMLESS)
        model.parameter("napkin_thermal_to_jet_efficiency", unit=DIMLESS)
        model.parameter("napkin_propellant_loadout_margin", unit=DIMLESS)
        model.parameter("napkin_jet_kinetic_fraction", unit=DIMLESS)

        reactor_core = model.part("reactor_core", NtpCorePart)
        propellant_feed = model.part("propellant_feed", PropellantFeedPart)
        nozzle = model.part("nozzle", NozzleAssemblyPart)
        shadow_shield = model.part("shadow_shield", ShadowShieldPart)
        model.part("avionics_gnc", AvionicsGncPart)
        model.part("cargo_berthing", CargoBerthingPart)
        design_envelope = model.part("design_envelope", TugDesignEnvelopePart)
        mission_sizing = model.part("mission_sizing", MissionSizingPart)

        rq = model.requirement_package("requirements", NtpRequirementsRoot)

        model.allocate(rq.reactor_fuel.req_heu_fuel_specification, reactor_core)
        model.allocate(rq.reactor_fuel.req_triso_barrier_function, reactor_core)

        model.allocate(rq.thermal_hydraulic.req_channel_cooling_envelope, reactor_core)

        model.allocate(rq.propulsion.req_ntp_vacuum_thrust_capability, nozzle)

        model.allocate(rq.shielding.req_payload_dose_bound, shadow_shield)

        model.allocate(
            rq.mission.req_delta_v_closure,
            design_envelope,
            inputs={
                "scenario_delta_v": p_dv,
                "envelope_delta_v": design_envelope.design_delta_v_capability,
            },
        )
        model.allocate(
            rq.mission.req_propellant_mass_closure,
            design_envelope,
            inputs={
                "scenario_propellant_kg": mission_sizing.mission_propellant_required,
                "available_propellant_kg": propellant_feed.tank_propellant_mass,
            },
        )

        model.allocate(rq.safety_policy.req_subcritical_assembly_rules, reactor_core)

        cite_mission = model.citation(
            "cite_mars_transfer_illustrative",
            title="Illustrative Mars cargo transfer Δv accounting (notional)",
            standard_id="DEMO-MARS-TUG-001",
        )
        model.references(rq.mission.req_delta_v_closure, cite_mission)
        model.references(rq.mission.req_propellant_mass_closure, cite_mission)


def reset_ntp_types() -> None:
    for t in (
        NtpCorePart,
        PropellantFeedPart,
        NozzleAssemblyPart,
        ShadowShieldPart,
        AvionicsGncPart,
        CargoBerthingPart,
        TugDesignEnvelopePart,
        MissionSizingPart,
        ReqReactorFuelTRISO,
        ReqThermalHydraulic,
        ReqPropulsionNtp,
        ReqShielding,
        ReqMissionMarsTransfer,
        ReqSafetyPolicy,
        NtpRequirementsRoot,
        MarsNuclearTug,
    ):
        t._reset_compilation()
