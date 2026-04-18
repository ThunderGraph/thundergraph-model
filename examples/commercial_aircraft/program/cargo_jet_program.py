"""Program-level :class:`~tg_model.model.elements.System` for the Atlas-400F notional cargo jet."""

from __future__ import annotations

from typing import Any

from commercial_aircraft.product.aircraft import Aircraft
from commercial_aircraft.program.l1_requirement_packages import L1RequirementsRoot
from commercial_aircraft.program.mission_context import CITATION_RETRIEVED_ISO
from unitflow.catalogs.si import kg, m

from tg_model.model.definition_context import parameter_ref
from tg_model.model.elements import System


class CargoJetProgram(System):
    """Configured root: scenario parameters, citations, nested Level-1 requirements, and composed ``aircraft`` part."""

    @classmethod
    def define(cls, model: Any) -> None:
        model.name("cargo_jet_program")
        model.parameter("scenario_payload_mass_kg", unit=kg)
        model.parameter("scenario_design_range_m", unit=m)
        model.parameter("mission_desk_baseline_max_range_m", unit=m)

        citations = {
            "c_acaps": model.citation(
                "c_acaps",
                title="Airplane Characteristics for Airport Planning (777 family — illustrative)",
                uri="https://www.boeing.com/commercial/airports/",
                publisher="The Boeing Company",
                retrieved=CITATION_RETRIEVED_ISO,
            ),
            "c_far25": model.citation(
                "c_far25",
                title="14 CFR Part 25 — Airworthiness Standards: Transport Category Airplanes",
                uri="https://www.ecfr.gov/current/title-14/chapter-I/subchapter-C/part-25",
                publisher="U.S. eCFR (National Archives)",
                retrieved=CITATION_RETRIEVED_ISO,
            ),
            "c_ac25_7c": model.citation(
                "c_ac25_7c",
                title="AC 25-7C — Flight Test Guide for Certification of Transport Category Airplanes",
                uri="https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentID/1030235",
                publisher="Federal Aviation Administration",
                retrieved=CITATION_RETRIEVED_ISO,
            ),
        }

        l1 = model.composed_of("l1", L1RequirementsRoot)
        aircraft = model.composed_of("aircraft", Aircraft)

        # --- Citations and allocation for each Level-1 requirement ---

        r_payload = l1.mission.payload_closure
        r_range = l1.mission.range_closure
        for r_mission in (r_payload, r_range):
            model.references(r_mission, citations["c_far25"])
            model.references(r_mission, citations["c_ac25_7c"])
        model.allocate(
            r_payload,
            aircraft,
            inputs={
                "scenario_payload": parameter_ref(CargoJetProgram, "scenario_payload_mass_kg"),
                "envelope_payload": aircraft.modeled_max_payload_kg,
            },
        )
        model.allocate(
            r_range,
            aircraft,
            inputs={
                "scenario_range": parameter_ref(CargoJetProgram, "scenario_design_range_m"),
                "envelope_range": aircraft.modeled_max_design_range_m,
            },
        )

        r_part25 = l1.airworthiness.part25
        model.references(r_part25, citations["c_far25"])
        model.allocate_to_system(r_part25)

        r_airport = l1.product.airport_planning
        model.references(r_airport, citations["c_acaps"])
        model.references(r_airport, citations["c_far25"])
        model.allocate(r_airport, aircraft)

        r_trace = l1.product.verification_traceability
        model.references(r_trace, citations["c_far25"])
        model.references(r_trace, citations["c_ac25_7c"])
        model.allocate(r_trace, aircraft)

        r_ft = l1.airworthiness.flight_test
        model.references(r_ft, citations["c_ac25_7c"])
        model.allocate_to_system(r_ft)
