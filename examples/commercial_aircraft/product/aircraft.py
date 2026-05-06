"""Top-level vehicle product block for the notional Atlas-400F."""

from __future__ import annotations

from typing import Any

from commercial_aircraft.integrations.bindings import make_mission_range_margin_binding
from commercial_aircraft.product.major_assemblies.parts import (
    AircraftSystemsPart,
    EmpennageAssembly,
    FuselageAssembly,
    LandingGearAssembly,
    PropulsionInstallation,
    WingAssembly,
)
from unitflow.catalogs.si import kg, m

from tg_model.model.definition_context import parameter_ref
from tg_model.model.elements import Part
from tg_model.model.expr import sum_attributes

# ---------------------------------------------------------------------------
# Flight-phase state machine events (referenced outside the class for use in
# dispatch calls and scenario declarations from test code or notebooks).
# The Ref objects are set on the class after first compile; access via
# Aircraft.compile()["nodes"]["<name>"] or pass the event name directly to
# dispatch_event().
# ---------------------------------------------------------------------------
FLIGHT_EVENTS = [
    "clearance_received",       # ATC / turnaround complete — ready to depart
    "takeoff_cleared",          # Cleared onto runway and authorised to roll
    "cruise_altitude_reached",  # Transition from climb to level-off
    "top_of_descent",           # Cruise complete; begin arrival sequence
    "runway_vacated",           # Aircraft off runway; mission complete
    "diversion_declared",       # Emergency diversion from en-route or approach
]


class Aircraft(Part):
    """Wide-body freighter configuration root: assembly tree, mass roll-up, thesis-style constraints.

    ``modeled_max_payload_kg`` is **derived** (MZFW − operating empty mass) and feeds L1 mission-closure
    acceptance via ``allocate(..., inputs=…)``. Aircraft-owned **mission desk** external compute
    (``mission_range_margin_m`` on this part)
    complements the structural range parameter ``modeled_max_design_range_m``.
    """

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("aircraft")
        from commercial_aircraft.program.cargo_jet_program import CargoJetProgram

        modeled_max_design_range_m = model.parameter("modeled_max_design_range_m", unit=m)
        notional_mzfw_kg = model.parameter("notional_mzfw_kg", unit=kg)
        notional_mtow_kg = model.parameter("notional_mtow_kg", unit=kg)
        notional_trip_fuel_kg = model.parameter("notional_trip_fuel_kg", unit=kg)
        scenario_payload = model.parameter("scenario_payload_mass_kg", unit=kg)
        scenario_range = model.parameter("scenario_design_range_m", unit=m)

        fuselage = model.composed_of("fuselage", FuselageAssembly)
        wing = model.composed_of("wing", WingAssembly)
        empennage = model.composed_of("empennage", EmpennageAssembly)
        landing_gear = model.composed_of("landing_gear", LandingGearAssembly)
        propulsion_installation = model.composed_of("propulsion_installation", PropulsionInstallation)
        aircraft_systems = model.composed_of("aircraft_systems", AircraftSystemsPart)

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
        mission_range_margin_m = model.attribute(
            "mission_range_margin_m",
            unit=m,
            computed_by=make_mission_range_margin_binding(
                root_block_type=CargoJetProgram,
                baseline_max_range_m=parameter_ref(CargoJetProgram, "mission_desk_baseline_max_range_m"),
            ),
        )

        model.constraint(
            "mzfw_covers_operating_empty",
            expr=notional_mzfw_kg >= operating_empty_mass_kg,
        )
        model.constraint(
            "mtow_covers_mzfw",
            expr=notional_mtow_kg >= notional_mzfw_kg,
        )
        model.constraint(
            "mission_range_margin_non_negative",
            expr=mission_range_margin_m >= 0 * m,
        )
        model.constraint(
            "notional_takeoff_mass_closure",
            expr=notional_mtow_kg
            >= sum_attributes(
                operating_empty_mass_kg,
                scenario_payload,
                notional_trip_fuel_kg,
            ),
        )
        model.constraint(
            "design_mission_payload_within_structural_envelope",
            expr=scenario_payload <= modeled_max_payload_kg,
        )
        model.constraint(
            "design_mission_range_within_modeled_envelope",
            expr=scenario_range <= modeled_max_design_range_m,
        )

        # ------------------------------------------------------------------ #
        # Flight-phase state machine                                          #
        # ------------------------------------------------------------------ #
        # Five high-level flight phases; mirrors an FAA-style phase-of-flight
        # taxonomy used in accident investigation and FMS design.
        parked      = model.state("parked",      initial=True)
        pre_dep     = model.state("pre_departure")
        airborne    = model.state("airborne")
        en_route    = model.state("en_route")
        approach    = model.state("approach")

        # Events
        clearance_received   = model.event("clearance_received")
        takeoff_cleared      = model.event("takeoff_cleared")
        cruise_alt_reached   = model.event("cruise_altitude_reached")
        top_of_descent       = model.event("top_of_descent")
        runway_vacated       = model.event("runway_vacated")
        diversion_declared   = model.event("diversion_declared")

        # Guards
        # Reads payload mass from RunContext (bound via ctx.bind_input before dispatch).
        # Returns False conservatively if the slot has no ready value.
        def _weight_ok(ctx, part):  # type: ignore[no-untyped-def]
            from tg_model.execution.run_context import SlotState
            sid = part.scenario_payload_mass_kg.stable_id
            if ctx.get_state(sid) not in (SlotState.BOUND_INPUT, SlotState.REALIZED):
                return False  # not yet evaluated — refuse takeoff clearance
            val = ctx.get_value(sid)
            # Accept raw numeric or a unitflow Quantity (has .magnitude attribute)
            mag = float(val.magnitude) if hasattr(val, "magnitude") else float(val)
            return mag > 0.0

        weight_within_limits = model.guard("weight_within_limits", predicate=_weight_ok)

        # Effect-only actions — fire on specific state transitions.
        # No then= because they are not part of a functional flow sequence.
        model.action("record_dispatch_clearance")   # log ATC clearance timestamp
        model.action("execute_go_around")           # initiate missed approach

        # ------------------------------------------------------------------ #
        # State transitions                                                   #
        # ------------------------------------------------------------------ #
        model.transition(
            parked, pre_dep, clearance_received,
            effect="record_dispatch_clearance",
        )
        model.transition(
            pre_dep, airborne, takeoff_cleared,
            guard=weight_within_limits,
        )
        model.transition(airborne, en_route,  cruise_alt_reached)
        model.transition(en_route, approach,  top_of_descent)
        model.transition(approach, parked,    runway_vacated)
        # Diversion: return to parked (simplified — real model would add a
        # divert_destination state) from any airborne phase.
        model.transition(airborne,  parked, diversion_declared, effect="execute_go_around")
        model.transition(en_route,  parked, diversion_declared, effect="execute_go_around")
        model.transition(approach,  parked, diversion_declared, effect="execute_go_around")

        # ------------------------------------------------------------------ #
        # Activity flow (then= chains)                                        #
        # ------------------------------------------------------------------ #
        # Pre-departure sequence: ground checks → engine start → taxi out.
        model.action("run_pre_flight_checks",   then="start_engines")
        model.action("start_engines",           then="complete_taxi_out")
        model.action("complete_taxi_out")

        # Flight execution sequence: rotation → cruise → arrival.
        model.action("rotate_and_climb",        then="retract_landing_gear")
        model.action("retract_landing_gear",    then="establish_cruise")
        model.action("establish_cruise",        then="initiate_descent")
        model.action("initiate_descent",        then="configure_for_approach")
        model.action("configure_for_approach",  then="touchdown_and_rollout")
        model.action("touchdown_and_rollout")

        # Scenario: nominal round-trip departure and arrival.
        model.scenario(
            "nominal_departure_arrival",
            expected_event_order=[
                clearance_received,
                takeoff_cleared,
                cruise_alt_reached,
                top_of_descent,
                runway_vacated,
            ],
            initial_behavior_state="parked",
            expected_final_behavior_state="parked",
        )

