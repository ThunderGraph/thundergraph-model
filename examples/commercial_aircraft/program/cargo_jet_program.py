"""Program-level :class:`~tg_model.model.elements.System` for the Atlas-400F notional cargo jet."""

from __future__ import annotations

from typing import Any

from unitflow import Quantity

from commercial_aircraft.integrations.bindings import make_mission_range_margin_binding
from commercial_aircraft.product.aircraft import Aircraft
from commercial_aircraft.program.l1_requirement_blocks import L1RequirementsRoot
from commercial_aircraft.program.l1_specs import L1RequirementSpec, iter_l1_requirements
from commercial_aircraft.program.mission_context import CITATION_RETRIEVED_ISO
from unitflow.catalogs.si import kg, m

from tg_model.model.definition_context import parameter_ref
from tg_model.model.elements import System
from tg_model.model.expr import sum_attributes
from tg_model.model.refs import Ref, RequirementBlockRef


def _l1_requirement_ref(l1: RequirementBlockRef, spec: L1RequirementSpec) -> Ref:
    """Resolve ``spec`` to a requirement ref under ``l1`` (nested block + leaf name)."""
    if spec.block == "mission":
        branch = l1.mission
    elif spec.block == "airworthiness":
        branch = l1.airworthiness
    elif spec.block == "product":
        branch = l1.product
    else:
        raise ValueError(f"unknown L1 block {spec.block!r}")
    return getattr(branch, spec.node_name)


class CargoJetProgram(System):
    """Configured root: scenario parameters, citations, nested L1 requirements, and composed ``aircraft`` part."""

    @classmethod
    def define(cls, model: Any) -> None:
        # Scenario parameters first (nested parts may use parameter_ref(CargoJetProgram, ...) in later phases).
        model.parameter("scenario_payload_mass_kg", unit=kg)
        model.parameter("scenario_design_range_m", unit=m)

        mission_binding = make_mission_range_margin_binding(model, CargoJetProgram)
        mission_range_margin_m = model.attribute(
            "mission_range_margin_m",
            unit=m,
            computed_by=mission_binding,
        )
        model.constraint(
            "mission_range_margin_non_negative",
            expr=mission_range_margin_m >= Quantity(0, m),
        )

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

        l1 = model.requirement_block("l1", L1RequirementsRoot)
        aircraft = model.part("aircraft", Aircraft)
        # Anonymous configured root part: allocation target for regulatory/context L1 items that are
        # not evidenced on the named ``aircraft`` subtree (citations + trace only — see ``l1_specs``).
        root = model.part()

        scenario_payload = parameter_ref(CargoJetProgram, "scenario_payload_mass_kg")
        scenario_range = parameter_ref(CargoJetProgram, "scenario_design_range_m")
        model.constraint(
            "notional_takeoff_mass_closure",
            expr=aircraft.notional_mtow_kg
            >= sum_attributes(
                aircraft.operating_empty_mass_kg,
                scenario_payload,
                aircraft.notional_trip_fuel_kg,
            ),
        )
        model.constraint(
            "design_mission_payload_within_structural_envelope",
            expr=scenario_payload <= aircraft.modeled_max_payload_kg,
        )
        model.constraint(
            "design_mission_range_within_modeled_envelope",
            expr=scenario_range <= aircraft.modeled_max_design_range_m,
        )

        for spec in iter_l1_requirements():
            req_ref = _l1_requirement_ref(l1, spec)
            for cid in spec.citation_ids:
                if cid not in citations:
                    raise KeyError(f"Unknown citation id {cid!r} in requirement {spec.node_name}")
                model.references(req_ref, citations[cid])
            if spec.allocate_to == "program_root":
                model.allocate(req_ref, root)
            elif spec.mission_closure_acceptance:
                model.allocate(
                    req_ref,
                    aircraft,
                    inputs={
                        "scenario_payload": parameter_ref(CargoJetProgram, "scenario_payload_mass_kg"),
                        "scenario_range": parameter_ref(CargoJetProgram, "scenario_design_range_m"),
                        "envelope_payload": aircraft.modeled_max_payload_kg,
                        "envelope_range": aircraft.modeled_max_design_range_m,
                    },
                )
            else:
                model.allocate(req_ref, aircraft)
