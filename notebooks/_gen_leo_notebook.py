"""Regenerate leo_launch_vehicle_deep_stack.ipynb (run from thundergraph-model/)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "leo_launch_vehicle_deep_stack.ipynb"


def cell_md(lines: list[str]) -> dict:
    return {"cell_type": "markdown", "id": str(uuid.uuid4())[:8], "metadata": {}, "source": [ln + "\n" for ln in lines]}


def cell_code(src: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": str(uuid.uuid4())[:8],
        "metadata": {},
        "outputs": [],
        "source": [src.rstrip() + "\n"],
    }


CODE1 = r'''# LEO mission + launch rocket: composition, mass roll-ups, Δv, liftoff T/W
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path


def _thundergraph_pkg_root(start: Path) -> Path:
    p = start.resolve()
    for _ in range(24):
        if (p / "tg_model" / "__init__.py").is_file():
            return p
        nested = p / "thundergraph-model"
        if (nested / "tg_model" / "__init__.py").is_file():
            return nested
        if p.parent == p:
            break
        p = p.parent
    return start.resolve()


_cwd = Path.cwd().resolve()
_pkg_root = _thundergraph_pkg_root(_cwd)
_root_s = str(_pkg_root)
if _root_s in sys.path:
    sys.path.remove(_root_s)
sys.path.insert(0, _root_s)
for _k in list(sys.modules):
    if _k == "tg_model" or _k.startswith("tg_model."):
        del sys.modules[_k]
_spec = importlib.util.find_spec("tg_model")
if _spec is None or not getattr(_spec, "origin", None):
    raise RuntimeError(
        f"Could not locate tg_model under {_pkg_root} (cwd={_cwd}). "
        "Use thundergraph-model/.venv or run from the package root."
    )

from unitflow import Quantity
from unitflow.catalogs.si import N, kg, m, s
from unitflow.core.units import Unit
from unitflow.expr.expressions import Expr, QuantityExpr
from tg_model.integrations.external_compute import (
    ExternalComputeBinding,
    ExternalComputeResult,
    link_external_routes,
)
from tg_model import parameter_ref
from tg_model.model.elements import Part, System
from tg_model.execution.configured_model import instantiate
from tg_model.execution.evaluator import Evaluator
from tg_model.execution.graph_compiler import compile_graph
from tg_model.execution.requirements import summarize_requirement_satisfaction
from tg_model.execution.run_context import RunContext
from tg_model.execution.validation import validate_graph

G0 = Quantity(9.80665, m / (s * s))
DIMLESS = Unit.dimensionless(symbol="1")
# subtree_cumulative_delta_v rolls up as: (burn Δv attributed *here*) + Σ(children).
# Fairing, tanks, engine mounts, etc. do not get a Tsiolkovsky term in this demo—only the two
# stage assemblies do—so their *local* ideal burn increment is 0 m/s. (Mass still flows through
# dry/wet attributes; this slot is only the ideal ΣΔv accounting.)
NO_MODELED_STAGE_BURN_DV = QuantityExpr(Quantity(0, m / s))

def _leo_scenario_inputs() -> dict[str, object]:
    """Mission scenario parameters as refs for ExternalComputeBinding.inputs (no module globals)."""
    return {
        "orbit_m": parameter_ref(LeoLaunchMission, "scenario_target_orbit_altitude_m"),
        "payload_kg": parameter_ref(LeoLaunchMission, "scenario_payload_mass_kg"),
    }


def _leaf_mass_adapter(adapter_name: str, dry_base: float, prop_base: float):
    """Tiny fake CAE/weights export: (orbit, payload) -> dry + prop for one tank/section part."""

    class _LeafMassAdapter:
        name = adapter_name

        def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
            orbit_m = float(inputs["orbit_m"].to(m).magnitude)
            payload_kg = float(inputs["payload_kg"].to(kg).magnitude)
            s = 1.0 + (payload_kg - 5_200.0) / 500_000.0 + (orbit_m - 400_000.0) / 5_000_000.0
            return ExternalComputeResult(
                value={
                    "local_dry_mass_kg": Quantity(dry_base * s, kg),
                    "local_propellant_mass_kg": Quantity(prop_base * s, kg),
                },
                provenance={"adapter": self.name, "orbit_m": orbit_m},
            )

    return _LeafMassAdapter()


class _NotionalRocketThrustStudio:
    """Fake **propulsion/engine-deck** output only: sea-level thrust (not a mass rollup).

    Vehicle **mass** on `LaunchRocket` comes from **composition** — rolling up child part subtree masses.
    Thrust is a separate physics/product output (engine model, test data, MDAO thrust level).
    """

    name = "notional_rocket_thrust_studio"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        orbit_m = float(inputs["orbit_m"].to(m).magnitude)
        payload_kg = float(inputs["payload_kg"].to(kg).magnitude)
        alt_400 = max(0.5, orbit_m / 400_000.0)
        pay_scale = 1.0 + (payload_kg - 5_200.0) / 200_000.0
        thrust = 7_600_000.0 * (0.97 + 0.03 * alt_400) * pay_scale
        return ExternalComputeResult(
            value=Quantity(thrust, N),
            provenance={"adapter": self.name, "orbit_m": orbit_m, "payload_kg": payload_kg},
        )


class _NotionalFairingMassStudio:
    """Fake fairing / PLF loads–mass sketch from trajectory + payload."""

    name = "notional_fairing_mass_studio"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        orbit_m = float(inputs["orbit_m"].to(m).magnitude)
        payload_kg = float(inputs["payload_kg"].to(kg).magnitude)
        dry = 5_200.0 + 0.12 * (payload_kg - 5_200.0) + 2e-6 * max(0.0, orbit_m - 400_000.0) * payload_kg
        return ExternalComputeResult(
            value={
                "fairing_local_dry_mass_kg": Quantity(dry, kg),
                "fairing_local_propellant_mass_kg": Quantity(0, kg),
            },
            provenance={"adapter": self.name, "orbit_m": orbit_m},
        )


class _NotionalUpperStageTrajectorySnapshot:
    """Fake upper-stage mass / burn snapshot (e.g. exported from a trajectory tool)."""

    name = "notional_upper_stage_trajectory_snapshot"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        orbit_m = float(inputs["orbit_m"].to(m).magnitude)
        payload_kg = float(inputs["payload_kg"].to(kg).magnitude)
        pay = (payload_kg - 5_200.0) / 50_000.0
        alt = (orbit_m - 400_000.0) / 1_000_000.0
        return ExternalComputeResult(
            value={
                "upper_stage_structure_dry_mass_kg": Quantity(1_100.0 * (1.0 + 0.02 * pay), kg),
                "upper_stage_structure_propellant_mass_kg": Quantity(0, kg),
                "upper_stage_burn_initial_mass_kg": Quantity(168_000.0 * (1.0 + 0.03 * pay + 0.01 * alt), kg),
                "upper_stage_burn_final_mass_kg": Quantity(52_000.0 * (1.0 + 0.02 * pay), kg),
                "upper_stage_isp_seconds": Quantity(340.0 * (1.0 - 0.01 * alt), s),
            },
            provenance={"adapter": self.name, "orbit_m": orbit_m, "payload_kg": payload_kg},
        )


class _NotionalFirstStageTrajectorySnapshot:
    """Fake booster mass / burn snapshot (e.g. from staging analysis export)."""

    name = "notional_first_stage_trajectory_snapshot"

    def compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult:
        orbit_m = float(inputs["orbit_m"].to(m).magnitude)
        payload_kg = float(inputs["payload_kg"].to(kg).magnitude)
        pay = (payload_kg - 5_200.0) / 50_000.0
        alt = (orbit_m - 400_000.0) / 1_000_000.0
        # Isp stays ≥ ~318 s at defaults so ΣΔv requirement still closes (same role as prior hand input).
        isp = max(318.0, 318.0 * (1.0 - 0.008 * alt) * (1.0 - 0.01 * pay))
        return ExternalComputeResult(
            value={
                "first_stage_structure_dry_mass_kg": Quantity(920.0 * (1.0 + 0.015 * pay), kg),
                "first_stage_structure_propellant_mass_kg": Quantity(0, kg),
                "first_stage_burn_initial_mass_kg": Quantity(195_000.0 * (1.0 + 0.025 * pay + 0.008 * alt), kg),
                "first_stage_burn_final_mass_kg": Quantity(38_000.0 * (1.0 + 0.02 * pay), kg),
                "first_stage_isp_seconds": Quantity(isp, s),
            },
            provenance={"adapter": self.name, "orbit_m": orbit_m, "payload_kg": payload_kg},
        )


class TsiolkovskyDeltaVExpr(Expr):
    """Δv = I_sp * g0 * ln(m_wet / m_dry) — custom Expr because unitflow has no ln()."""

    __slots__ = ("_g0", "_isp", "_md", "_mw")

    def __init__(self, isp_ref, m_wet_ref, m_dry_ref, g0: Quantity) -> None:
        self._isp = isp_ref
        self._mw = m_wet_ref
        self._md = m_dry_ref
        self._g0 = g0

    @property
    def dimension(self):
        return (m / s).dimension

    @property
    def free_symbols(self):
        return frozenset({self._isp.sym, self._mw.sym, self._md.sym})

    def evaluate(self, context):
        isp_q = context[self._isp.sym]
        mw_q = context[self._mw.sym]
        md_q = context[self._md.sym]
        ratio = mw_q.to(kg).magnitude / md_q.to(kg).magnitude
        if ratio <= 1.0:
            raise ValueError("stage burn requires m_wet > m_dry for positive Δv")
        ve = isp_q.to(s).magnitude * float(self._g0.to(m / (s * s)).magnitude)
        return Quantity(ve * math.log(ratio), m / s)


# --- Passive leaves (mass only; no rocket-equation Δv on these nodes) ---


class FairingAndPayloadInterface(Part):
    """Composite part block: fairing + payload interface / attach (notional lump). Owned by `LaunchRocket`."""

    @classmethod
    def define(cls, model):  # type: ignore[override]
        b_fairing = ExternalComputeBinding(_NotionalFairingMassStudio(), inputs=_leo_scenario_inputs())
        dry = model.attribute("local_dry_mass_kg", unit=kg, computed_by=b_fairing)
        prop = model.attribute("local_propellant_mass_kg", unit=kg, computed_by=b_fairing)
        link_external_routes(
            b_fairing,
            {
                "fairing_local_dry_mass_kg": dry,
                "fairing_local_propellant_mass_kg": prop,
            },
        )
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class UpperStageOxidizerTank(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        b = ExternalComputeBinding(
            _leaf_mass_adapter("notional_upper_ox_tank_mass_export", 380.0, 118_000.0),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("local_dry_mass_kg", unit=kg, computed_by=b)
        prop = model.attribute("local_propellant_mass_kg", unit=kg, computed_by=b)
        link_external_routes(
            b,
            {"local_dry_mass_kg": dry, "local_propellant_mass_kg": prop},
        )
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class UpperStageFuelTank(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        b = ExternalComputeBinding(
            _leaf_mass_adapter("notional_upper_fuel_tank_mass_export", 290.0, 48_000.0),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("local_dry_mass_kg", unit=kg, computed_by=b)
        prop = model.attribute("local_propellant_mass_kg", unit=kg, computed_by=b)
        link_external_routes(
            b,
            {"local_dry_mass_kg": dry, "local_propellant_mass_kg": prop},
        )
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class UpperStageEngineInstallation(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        b = ExternalComputeBinding(
            _leaf_mass_adapter("notional_upper_engine_install_mass_export", 650.0, 800.0),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("local_dry_mass_kg", unit=kg, computed_by=b)
        prop = model.attribute("local_propellant_mass_kg", unit=kg, computed_by=b)
        link_external_routes(
            b,
            {"local_dry_mass_kg": dry, "local_propellant_mass_kg": prop},
        )
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class UpperStageAssembly(Part):
    """Composite assembly block: **composed of** oxidizer tank, fuel tank, engine installation (sibling parts).

    One ideal Tsiolkovsky burn is attributed at this assembly (MBSE: propulsion / stage behavior here).
    """

    @classmethod
    def define(cls, model):  # type: ignore[override]
        ox = model.part("oxidizer_tank", UpperStageOxidizerTank)
        ft = model.part("fuel_tank", UpperStageFuelTank)
        ei = model.part("engine_installation", UpperStageEngineInstallation)

        b_upper = ExternalComputeBinding(
            _NotionalUpperStageTrajectorySnapshot(),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("stage_structure_dry_mass_kg", unit=kg, computed_by=b_upper)
        prop = model.attribute("stage_structure_propellant_mass_kg", unit=kg, computed_by=b_upper)
        wet_local = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)

        mw = model.attribute("stage_burn_initial_mass_kg", unit=kg, computed_by=b_upper)
        md = model.attribute("stage_burn_final_mass_kg", unit=kg, computed_by=b_upper)
        isp = model.attribute("stage_isp_seconds", unit=s, computed_by=b_upper)
        link_external_routes(
            b_upper,
            {
                "upper_stage_structure_dry_mass_kg": dry,
                "upper_stage_structure_propellant_mass_kg": prop,
                "upper_stage_burn_initial_mass_kg": mw,
                "upper_stage_burn_final_mass_kg": md,
                "upper_stage_isp_seconds": isp,
            },
        )
        local_dv = model.attribute(
            "local_stage_delta_v",
            unit=m / s,
            expr=TsiolkovskyDeltaVExpr(isp, mw, md, G0),
        )

        r_dry = model.attribute(
            "rolled_children_dry_mass_kg",
            unit=kg,
            expr=ox.subtree_dry_mass_kg + (ft.subtree_dry_mass_kg + ei.subtree_dry_mass_kg),
        )
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym + r_dry.sym)

        r_wet = model.attribute(
            "rolled_children_wet_mass_kg",
            unit=kg,
            expr=ox.subtree_wet_mass_kg + (ft.subtree_wet_mass_kg + ei.subtree_wet_mass_kg),
        )
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet_local.sym + r_wet.sym)

        r_dv = model.attribute(
            "rolled_children_delta_v_sum",
            unit=m / s,
            expr=ox.subtree_cumulative_delta_v + (ft.subtree_cumulative_delta_v + ei.subtree_cumulative_delta_v),
        )
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=local_dv.sym + r_dv.sym)


class FirstStagePropellantSection(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        b = ExternalComputeBinding(
            _leaf_mass_adapter("notional_first_propellant_section_mass_export", 480.0, 185_000.0),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("local_dry_mass_kg", unit=kg, computed_by=b)
        prop = model.attribute("local_propellant_mass_kg", unit=kg, computed_by=b)
        link_external_routes(
            b,
            {"local_dry_mass_kg": dry, "local_propellant_mass_kg": prop},
        )
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class FirstStageEngineCluster(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        b = ExternalComputeBinding(
            _leaf_mass_adapter("notional_first_engine_cluster_mass_export", 5_200.0, 0.0),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("local_dry_mass_kg", unit=kg, computed_by=b)
        prop = model.attribute("local_propellant_mass_kg", unit=kg, computed_by=b)
        link_external_routes(
            b,
            {"local_dry_mass_kg": dry, "local_propellant_mass_kg": prop},
        )
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class FirstStageThrustStructure(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        b = ExternalComputeBinding(
            _leaf_mass_adapter("notional_first_thrust_structure_mass_export", 520.0, 1_200.0),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("local_dry_mass_kg", unit=kg, computed_by=b)
        prop = model.attribute("local_propellant_mass_kg", unit=kg, computed_by=b)
        link_external_routes(
            b,
            {"local_dry_mass_kg": dry, "local_propellant_mass_kg": prop},
        )
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class FirstStageAssembly(Part):
    """Composite assembly block: **composed of** propellant section, engine cluster, thrust structure.

    One ideal Tsiolkovsky burn is attributed at this assembly.
    """

    @classmethod
    def define(cls, model):  # type: ignore[override]
        ps = model.part("propellant_section", FirstStagePropellantSection)
        ec = model.part("engine_cluster", FirstStageEngineCluster)
        ts = model.part("thrust_structure", FirstStageThrustStructure)

        b_first = ExternalComputeBinding(
            _NotionalFirstStageTrajectorySnapshot(),
            inputs=_leo_scenario_inputs(),
        )
        dry = model.attribute("stage_structure_dry_mass_kg", unit=kg, computed_by=b_first)
        prop = model.attribute("stage_structure_propellant_mass_kg", unit=kg, computed_by=b_first)
        wet_local = model.attribute("local_wet_mass_kg", unit=kg, expr=dry.sym + prop.sym)

        mw = model.attribute("stage_burn_initial_mass_kg", unit=kg, computed_by=b_first)
        md = model.attribute("stage_burn_final_mass_kg", unit=kg, computed_by=b_first)
        isp = model.attribute("stage_isp_seconds", unit=s, computed_by=b_first)
        link_external_routes(
            b_first,
            {
                "first_stage_structure_dry_mass_kg": dry,
                "first_stage_structure_propellant_mass_kg": prop,
                "first_stage_burn_initial_mass_kg": mw,
                "first_stage_burn_final_mass_kg": md,
                "first_stage_isp_seconds": isp,
            },
        )
        local_dv = model.attribute(
            "local_stage_delta_v",
            unit=m / s,
            expr=TsiolkovskyDeltaVExpr(isp, mw, md, G0),
        )

        r_dry = model.attribute(
            "rolled_children_dry_mass_kg",
            unit=kg,
            expr=ps.subtree_dry_mass_kg + (ec.subtree_dry_mass_kg + ts.subtree_dry_mass_kg),
        )
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym + r_dry.sym)

        r_wet = model.attribute(
            "rolled_children_wet_mass_kg",
            unit=kg,
            expr=ps.subtree_wet_mass_kg + (ec.subtree_wet_mass_kg + ts.subtree_wet_mass_kg),
        )
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet_local.sym + r_wet.sym)

        r_dv = model.attribute(
            "rolled_children_delta_v_sum",
            unit=m / s,
            expr=ps.subtree_cumulative_delta_v + (ec.subtree_cumulative_delta_v + ts.subtree_cumulative_delta_v),
        )
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=local_dv.sym + r_dv.sym)


class LaunchRocket(Part):
    """**Rocket** block (BDD: the vehicle product): **composed of** fairing, upper stage, first stage.

    **Mass / Δv:** `subtree_*` and roll-up attributes are **derived from child parts** (SysML composition).
    Optional ``vehicle_misc_*`` would be mass **not** allocated to a named child in this model; **this demo
    fixes them to 0 kg** with constant expressions so **vehicle mass is entirely the sum of composed
    assemblies** — not a second parallel “simulator” at the root.

    **Thrust:** `sea_level_thrust_n` is a **propulsion-side** output (`ExternalCompute`), not a sum of masses.

    A **mission** system composes this block as ``part rocket`` and holds mission requirements.
    """

    @classmethod
    def define(cls, model):  # type: ignore[override]
        # --- Composition (SysML part properties on the rocket block) ---
        fairing = model.part("fairing_and_payload_interface", FairingAndPayloadInterface)
        upper = model.part("upper_stage", UpperStageAssembly)
        first = model.part("first_stage", FirstStageAssembly)

        b_thrust = ExternalComputeBinding(
            _NotionalRocketThrustStudio(),
            inputs=_leo_scenario_inputs(),
        )
        thrust = model.attribute("sea_level_thrust_n", unit=N, computed_by=b_thrust)
        # Mass rollup is explicit composition: misc = 0 here (no mass invented at root by a “simulator”).
        _zero_kg = QuantityExpr(Quantity(0, kg))
        misc_dry = model.attribute("vehicle_misc_dry_mass_kg", unit=kg, expr=_zero_kg)
        misc_prop = model.attribute("vehicle_misc_propellant_mass_kg", unit=kg, expr=_zero_kg)
        misc_wet = model.attribute("vehicle_misc_wet_mass_kg", unit=kg, expr=misc_dry.sym + misc_prop.sym)

        r_dry = model.attribute(
            "rolled_major_assemblies_dry_mass_kg",
            unit=kg,
            expr=fairing.subtree_dry_mass_kg
            + (upper.subtree_dry_mass_kg + first.subtree_dry_mass_kg),
        )
        sub_dry = model.attribute("subtree_dry_mass_kg", unit=kg, expr=misc_dry.sym + r_dry.sym)

        r_wet = model.attribute(
            "rolled_major_assemblies_wet_mass_kg",
            unit=kg,
            expr=fairing.subtree_wet_mass_kg
            + (upper.subtree_wet_mass_kg + first.subtree_wet_mass_kg),
        )
        sub_wet = model.attribute("subtree_wet_mass_kg", unit=kg, expr=misc_wet.sym + r_wet.sym)

        r_dv = model.attribute(
            "rolled_major_assemblies_delta_v_sum",
            unit=m / s,
            expr=fairing.subtree_cumulative_delta_v
            + (upper.subtree_cumulative_delta_v + first.subtree_cumulative_delta_v),
        )
        sub_dv = model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=r_dv.sym)

        twr = model.attribute(
            "liftoff_thrust_to_weight",
            unit=DIMLESS,
            expr=thrust.sym / (sub_wet.sym * G0),
        )
        model.constraint("min_liftoff_twr", expr=twr >= Quantity(1.12, DIMLESS))
        model.constraint("vehicle_dry_under_cap", expr=sub_dry <= Quantity(28_000, kg))


class LeoLaunchMission(System):
    """**Mission / analysis context** (BDD root): **composed of** the launch vehicle as a single part.

    Requirements at this level allocate to ``rocket`` — the same pattern as allocating to any other
    composed subsystem: ``rocket = model.part(\"rocket\", LaunchRocket)`` then ``model.allocate(req, rocket)``.

    **Simulation integration (showcase):** scenario parameters live on the mission block. Nested
    parts use ``parameter_ref(LeoLaunchMission, ...)`` so ``ExternalComputeBinding.inputs`` point
    at those parameters (no globals). Each block builds its own binding + ``link_external_routes``
    next to the attributes it hydrates (one binding per owning part — compiler rule).
    """

    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("scenario_target_orbit_altitude_m", unit=m)
        model.parameter("scenario_payload_mass_kg", unit=kg)
        rocket = model.part("rocket", LaunchRocket)
        req = model.requirement(
            "req_leo_delta_v_budget",
            "Sum of ideal stage Δv (Tsiolkovsky on each burning stage) meets a notional LEO budget.",
            expr=rocket.subtree_cumulative_delta_v >= Quantity(9_000, m / s),
        )
        model.allocate(req, rocket)


_ALL_TYPES = (
    FairingAndPayloadInterface,
    UpperStageOxidizerTank,
    UpperStageFuelTank,
    UpperStageEngineInstallation,
    UpperStageAssembly,
    FirstStagePropellantSection,
    FirstStageEngineCluster,
    FirstStageThrustStructure,
    FirstStageAssembly,
    LaunchRocket,
    LeoLaunchMission,
)


def reset_vehicle_types() -> None:
    for cls in _ALL_TYPES:
        cls._reset_compilation()


reset_vehicle_types()
'''

CODE2 = r'''reset_vehicle_types()
cm = instantiate(LeoLaunchMission)
rocket = cm.rocket

# **Only** mission scenario knobs. Mass roll-ups on the rocket are **sums of composed parts**; external
# compute supplies thrust + discipline exports (tanks, burns, …), not a fake parallel root mass.
inputs = {
    cm.scenario_target_orbit_altitude_m.stable_id: Quantity(400_000, m),
    cm.scenario_payload_mass_kg.stable_id: Quantity(5_200, kg),
}

graph, handlers = compile_graph(cm)
val = validate_graph(graph)
assert val.passed, val.failures

ctx = RunContext()
result = Evaluator(graph, compute_handlers=handlers).evaluate(ctx, inputs=inputs)
assert not result.failures, result.failures

_W = 78


def _qmag(q) -> float:
    return float(q.magnitude)


def _hr(ch: str = "─", w: int = _W) -> None:
    print(ch * w)


def _title(label: str) -> None:
    print()
    _hr("═")
    print(f"  {label}")
    _hr("═")


def _subtitle(label: str) -> None:
    print()
    print(f"  ▸ {label}")
    print("  " + "─" * 52)


def _kv(key: str, val: str, klen: int = 40) -> None:
    print(f"  {key:.<{klen}} {val}")


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]], col_widths: tuple[int, ...]) -> None:
    def row(cells: tuple[str, ...]) -> str:
        parts = [str(c).ljust(col_widths[i]) for i, c in enumerate(cells)]
        return " │ ".join(parts)

    sep_w = sum(col_widths) + 3 * (len(headers) - 1)
    print("  " + row(headers))
    print("  " + "─" * sep_w)
    for r in rows:
        print("  " + row(r))


def _fmt_km_from_m(q) -> str:
    return f"{_qmag(q) / 1000.0:,.0f} km"


def _fmt_kg(q) -> str:
    return f"{_qmag(q):,.1f} kg"


def _fmt_ms(q) -> str:
    return f"{_qmag(q):,.2f} m/s"


def _fmt_dimless(q) -> str:
    return f"{_qmag(q):.3f}"


def _fmt_n(q) -> str:
    v = _qmag(q)
    if v >= 1e6:
        return f"{v / 1e6:.3f} MN"
    return f"{v:,.0f} N"


def _fmt_prov(p: dict) -> str:
    if not p:
        return "—"
    ad = p.get("adapter", "—")
    bits = [ad]
    if "orbit_m" in p:
        bits.append(f"orbit {float(p['orbit_m']) / 1000.0:,.0f} km")
    if "payload_kg" in p:
        bits.append(f"payload {float(p['payload_kg']):,.0f} kg")
    return "  ·  ".join(bits)


# ─── Report body ───────────────────────────────────────────────────────────
orbit_q = inputs[cm.scenario_target_orbit_altitude_m.stable_id]
payload_q = inputs[cm.scenario_payload_mass_kg.stable_id]

print()
_hr("═")
print(
    "  THUNDERGRAPH  ·  LEO MISSION SNAPSHOT  ·  NOTIONAL VEHICLE (IDEAL STAGE Δv, NO LOSSES)".ljust(
        _W - 2
    )
)
_hr("═")
_kv("Configured root", "LeoLaunchMission")
_kv("Composition chain", f"{rocket.path_string}  (LaunchRocket)")
_kv("Scenario — target altitude", _fmt_km_from_m(orbit_q))
_kv("Scenario — payload mass", _fmt_kg(payload_q))
_kv(
    "Evaluate() binding surface",
    "two scenario parameters only; masses / thrust / burns from graph + external compute",
)

_title("EXTERNAL COMPUTE — SAMPLE HYDRATION + PROVENANCE")
for slot_label, sid in [
    ("Sea-level thrust (vehicle)", rocket.sea_level_thrust_n.stable_id),
    ("Upper oxidizer tank — dry mass", rocket.upper_stage.oxidizer_tank.local_dry_mass_kg.stable_id),
]:
    rec = ctx.get_or_create_record(sid)
    v = ctx.get_value(sid)
    if "thrust" in slot_label.lower():
        vstr = _fmt_n(v)
    else:
        vstr = _fmt_kg(v)
    print(f"  {slot_label}")
    print(f"      Value . . . . . . . .  {vstr}")
    print(f"      Provenance . . . . . .  {_fmt_prov(dict(rec.provenance))}")
    print()

_subtitle("Vehicle roll-up (LaunchRocket subtree)")
_kv("Wet mass m_wet", _fmt_kg(ctx.get_value(rocket.subtree_wet_mass_kg.stable_id)))
_kv("Dry mass m_dry", _fmt_kg(ctx.get_value(rocket.subtree_dry_mass_kg.stable_id)))
_kv("Ideal ΣΔv (2 burning assemblies)", _fmt_ms(ctx.get_value(rocket.subtree_cumulative_delta_v.stable_id)))
_twr = ctx.get_value(rocket.liftoff_thrust_to_weight.stable_id)
_kv("Liftoff thrust-to-weight", _fmt_dimless(_twr))

_title("COMPOSITION — MAJOR ASSEMBLIES (BDD-STYLE)")
_table(
    ("Block", "m_dry", "m_wet", "ΣΔv contrib."),
    [
        (
            "Fairing + payload I/F",
            _fmt_kg(ctx.get_value(rocket.fairing_and_payload_interface.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.fairing_and_payload_interface.subtree_wet_mass_kg.stable_id)),
            _fmt_ms(ctx.get_value(rocket.fairing_and_payload_interface.subtree_cumulative_delta_v.stable_id)),
        ),
        (
            "Upper stage assembly",
            _fmt_kg(ctx.get_value(rocket.upper_stage.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.upper_stage.subtree_wet_mass_kg.stable_id)),
            _fmt_ms(ctx.get_value(rocket.upper_stage.subtree_cumulative_delta_v.stable_id)),
        ),
        (
            "First stage assembly",
            _fmt_kg(ctx.get_value(rocket.first_stage.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.first_stage.subtree_wet_mass_kg.stable_id)),
            _fmt_ms(ctx.get_value(rocket.first_stage.subtree_cumulative_delta_v.stable_id)),
        ),
    ],
    (26, 14, 14, 18),
)

_subtitle("Upper stage — sibling parts")
_table(
    ("Part property", "m_dry", "m_wet"),
    [
        (
            "oxidizer_tank",
            _fmt_kg(ctx.get_value(rocket.upper_stage.oxidizer_tank.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.upper_stage.oxidizer_tank.subtree_wet_mass_kg.stable_id)),
        ),
        (
            "fuel_tank",
            _fmt_kg(ctx.get_value(rocket.upper_stage.fuel_tank.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.upper_stage.fuel_tank.subtree_wet_mass_kg.stable_id)),
        ),
        (
            "engine_installation",
            _fmt_kg(ctx.get_value(rocket.upper_stage.engine_installation.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.upper_stage.engine_installation.subtree_wet_mass_kg.stable_id)),
        ),
    ],
    (22, 14, 14),
)

_subtitle("First stage — sibling parts")
_table(
    ("Part property", "m_dry", "m_wet"),
    [
        (
            "propellant_section",
            _fmt_kg(ctx.get_value(rocket.first_stage.propellant_section.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.first_stage.propellant_section.subtree_wet_mass_kg.stable_id)),
        ),
        (
            "engine_cluster",
            _fmt_kg(ctx.get_value(rocket.first_stage.engine_cluster.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.first_stage.engine_cluster.subtree_wet_mass_kg.stable_id)),
        ),
        (
            "thrust_structure",
            _fmt_kg(ctx.get_value(rocket.first_stage.thrust_structure.subtree_dry_mass_kg.stable_id)),
            _fmt_kg(ctx.get_value(rocket.first_stage.thrust_structure.subtree_wet_mass_kg.stable_id)),
        ),
    ],
    (22, 14, 14),
)

_subtitle("Stage ideal Δv (Tsiolkovsky attributed at assembly only)")
_kv("Upper — local_stage_delta_v", _fmt_ms(ctx.get_value(rocket.upper_stage.local_stage_delta_v.stable_id)))
_kv("First — local_stage_delta_v", _fmt_ms(ctx.get_value(rocket.first_stage.local_stage_delta_v.stable_id)))

_subtitle("Δv budget evidence (per-stage equation inputs and reconstruction)")
upper_isp = ctx.get_value(rocket.upper_stage.stage_isp_seconds.stable_id)
upper_mw = ctx.get_value(rocket.upper_stage.stage_burn_initial_mass_kg.stable_id)
upper_md = ctx.get_value(rocket.upper_stage.stage_burn_final_mass_kg.stable_id)
upper_dv_model = ctx.get_value(rocket.upper_stage.local_stage_delta_v.stable_id)
upper_dv_reconstructed = Quantity(
    _qmag(upper_isp.to(s)) * _qmag(G0.to(m / (s * s))) * math.log(_qmag(upper_mw.to(kg)) / _qmag(upper_md.to(kg))),
    m / s,
)

first_isp = ctx.get_value(rocket.first_stage.stage_isp_seconds.stable_id)
first_mw = ctx.get_value(rocket.first_stage.stage_burn_initial_mass_kg.stable_id)
first_md = ctx.get_value(rocket.first_stage.stage_burn_final_mass_kg.stable_id)
first_dv_model = ctx.get_value(rocket.first_stage.local_stage_delta_v.stable_id)
first_dv_reconstructed = Quantity(
    _qmag(first_isp.to(s)) * _qmag(G0.to(m / (s * s))) * math.log(_qmag(first_mw.to(kg)) / _qmag(first_md.to(kg))),
    m / s,
)

_table(
    ("Stage", "Isp", "m0", "mf", "Δv(model)", "Δv(reconstructed)"),
    [
        (
            "Upper",
            f"{_qmag(upper_isp.to(s)):.2f} s",
            _fmt_kg(upper_mw),
            _fmt_kg(upper_md),
            _fmt_ms(upper_dv_model),
            _fmt_ms(upper_dv_reconstructed),
        ),
        (
            "First",
            f"{_qmag(first_isp.to(s)):.2f} s",
            _fmt_kg(first_mw),
            _fmt_kg(first_md),
            _fmt_ms(first_dv_model),
            _fmt_ms(first_dv_reconstructed),
        ),
    ],
    (10, 10, 14, 14, 16, 20),
)

total_dv = ctx.get_value(rocket.subtree_cumulative_delta_v.stable_id)
dv_target = Quantity(9_000, m / s)
dv_margin = total_dv - dv_target
_kv("ΣΔv total (vehicle)", _fmt_ms(total_dv))
_kv("Mission requirement threshold", _fmt_ms(dv_target))
_kv("Δv margin vs threshold", _fmt_ms(dv_margin))

summary = summarize_requirement_satisfaction(result)
_title("REQUIREMENTS & CONSTRAINTS — VERIFICATION")
pass_sym = "✓ SAT"
fail_sym = "✗ UNSAT"
_kv("Requirement acceptance checks", str(summary.check_count))
_kv("All requirements satisfied", "YES" if summary.all_passed else "NO")
print()
for row in summary.results:
    st = pass_sym if row.passed else fail_sym
    print(f"  {st}  {row.requirement_path}")
    print(f"         allocated to  {row.allocation_target_path}")
    print(
        "         acceptance    "
        f"ΣΔv(vehicle) {'>=' if row.passed else '<'} 9,000 m/s  "
        f"({ _fmt_ms(total_dv) } vs { _fmt_ms(dv_target) })"
    )
    if row.evidence:
        print(f"         evidence      {row.evidence[:64]}{'…' if len(row.evidence) > 64 else ''}")

print()
print("  Local constraints (design rules on LaunchRocket)")
_table(
    ("Constraint", "Status"),
    [
        (
            cr.name.split(".")[-1] if "." in cr.name else cr.name,
            pass_sym if cr.passed else fail_sym,
        )
        for cr in result.constraint_results
        if cr.requirement_path is None
    ],
    (48, 12),
)

print()
_hr("═")
print("  END SNAPSHOT — values traceable to composed blocks + external-compute provenance".ljust(_W - 2))
_hr("═")
'''

nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    },
    "cells": [],
}

nb["cells"].append(
    cell_md(
        [
            "# LEO mission — **SysML-style composition**, mass roll-ups, ideal Δv, liftoff T/W",
            "",
            "This notebook is a **customer-readable** example: two BDD layers an MBSE engineer expects — a **mission / context** block that **owns** the vehicle product, and a **rocket** block whose **`define()`** lists fairing, upper stage, and first stage as **part properties**.",
            "",
            "**Pattern:** **`LeoLaunchMission`** (configured root `System`) declares **`rocket = model.part(\"rocket\", LaunchRocket)`**, then a mission requirement and **`model.allocate(req, rocket)`**. The name **`rocket`** is a real composed child: after `instantiate(LeoLaunchMission)`, **`cm.rocket`** is the vehicle **`PartInstance`** that **owns** `fairing_and_payload_interface`, `upper_stage`, and `first_stage`. Vehicle physics and design constraints live on **`LaunchRocket`**; the **LEO Δv budget** requirement lives on the mission block and **allocates to** the rocket part.",
            "",
            "**Simulation vs composition:** **Mass** totals on `LaunchRocket` **roll up from child parts** (fairing, stages, tanks…). **External compute** fills **discipline outputs** — e.g. CAE mass exports on leaves, **propulsion thrust** on the vehicle, trajectory-linked burn snapshots — not a duplicate “root mass simulator.” Mission **`scenario_*`** parameters are the only **`evaluate()` inputs**. **`parameter_ref`** wires nested **`ExternalComputeBinding.inputs`** to those root parameters (no hidden global state).",
            "",
            "**ThunderGraph ↔ SysML:** each **`model.part(\"name\", BlockType)`** is **composition** (the parent **owns** that child). `model.part()` with **no** args remains available as a ref to the block you are defining (`root_block`); this demo does not need it because allocation targets the named **`rocket`** part.",
            "",
            "**What it is not:** trajectory, losses, staging time, or engine-out. Δv is **ideal Tsiolkovsky once per burning stage** (upper assembly and first-stage assembly). Tank/fairing **leaves** use `NO_MODELED_STAGE_BURN_DV`: they add **no burn term** to the ΣΔv roll-up (mass is in dry/wet; this slot is burn accounting only).",
            "",
            "**How to read the code:** every subsystem is a **`Part` / `System` class** with **`define()`**. Roll-ups use **named sums** so accountability matches the tree. **Passthrough attributes** use **`.sym`** (e.g. `expr=wet.sym`), not bare refs — otherwise the graph never binds realized numbers.",
            "",
            "**Imports:** load `tg_model` **after** the `sys.path` fix and any `sys.modules` purge.",
            "",
            "**Run:** `uv run jupyter nbconvert --to notebook --execute notebooks/leo_launch_vehicle_deep_stack.ipynb --inplace`",
            "",
            "**Kernel:** after updating `tg_model`, **restart the Jupyter kernel** and run the notebook from the top so `parameter_ref` and other API changes load (stale `ModelDefinitionContext` is a common cause of `AttributeError`).",
        ]
    )
)

nb["cells"].append(
    cell_md(
        [
            "## Review corner (adversarial advisor)",
            "",
            "*Persona: `reviewer_architype.md` — directed at the **previous** draft of this demo.*",
            "",
            "You shipped a **linked list** down the vehicle and called it architecture. A fairing is not the **parent** of a core interstage in any program that flies. You **meta-programmed** stack segments so nobody could trace accountability to a named subsystem. You front-loaded import-order archaeology before you explained scope. **Customer-facing** means PDR nouns, honest idealizations, and a topology a propulsion lead can draw on a whiteboard in sixty seconds. Fix the ontology; keep the rocket equation.",
        ]
    )
)

nb["cells"].append(
    cell_md(
        [
            "## MBSE: composition (BDD-style)",
            "",
            "| Parent block | Part property (role) | Child block type |",
            "|--------------|----------------------|------------------|",
            "| **`LeoLaunchMission`** | `scenario_target_orbit_altitude_m`, `scenario_payload_mass_kg` | scenario inputs (feed external compute) |",
            "| **`LeoLaunchMission`** | `rocket` | `LaunchRocket` |",
            "| **`LaunchRocket`** | `fairing_and_payload_interface` | `FairingAndPayloadInterface` |",
            "| **`LaunchRocket`** | `upper_stage` | `UpperStageAssembly` |",
            "| **`LaunchRocket`** | `first_stage` | `FirstStageAssembly` |",
            "| **`UpperStageAssembly`** | `oxidizer_tank` / `fuel_tank` / `engine_installation` | tank / installation parts |",
            "| **`FirstStageAssembly`** | `propellant_section` / `engine_cluster` / `thrust_structure` | section parts |",
            "",
            "Row 1 is the **mission owns vehicle** edge. Rows 2–4 are **the rocket is composed of** fairing, upper stage, and first stage — **siblings** under the vehicle boundary. Lower rows repeat the same idea inside each stage assembly.",
        ]
    )
)

nb["cells"].append(
    cell_md(
        [
            "## Topology diagram",
            "",
            "```mermaid",
            "flowchart TB",
            "  M[\"LeoLaunchMission (system / context)\"]",
            "  M --> R[\"part: rocket → LaunchRocket\"]",
            "  R --> F[\"fairing_and_payload_interface\"]",
            "  R --> U[\"upper_stage\"]",
            "  R --> FS[\"first_stage\"]",
            "  U --> UO[oxidizer_tank]",
            "  U --> UF[fuel_tank]",
            "  U --> UE[engine_installation]",
            "  FS --> FP[propellant_section]",
            "  FS --> FE[engine_cluster]",
            "  FS --> FTS[thrust_structure]",
            "```",
        ]
    )
)

nb["cells"].append(cell_code(CODE1))
nb["cells"].append(
    cell_md(
        [
            "## Parameters vs tool / simulation outputs",
            "",
            "| Mechanism | Meaning in ThunderGraph |",
            "|-----------|-------------------------|",
            "| **`model.parameter`** | You supply a value in the **`inputs`** map at `evaluate()` (or from a file/DB elsewhere). The **dependency graph does not compute it**.",
            "| **`model.attribute(..., expr=...)`** | **Derived** in-graph from other slots (e.g. **sum of child part masses**, constraints on expressions).",
            "| **`model.attribute(..., computed_by=ExternalComputeBinding)`** | Filled by **`ExternalCompute.compute()`** — use for **discipline / tool outputs** (propulsion thrust, CAE mass on a leaf, trajectory export), **not** for a duplicate root mass that should be a rollup.",
            "",
            "So: **\"sum the parts\"** → **expression / rollup**. **\"a tool produced this number\"** → **external**. **\"scenario knob for this run\"** → **parameter**.",
            "",
            "This demo uses **two mission parameters** (orbit + payload). **Vehicle-level mass** is the **composition sum** of child assemblies (optional `vehicle_misc_*` fixed at 0 kg). **Thrust and leaf/assembly tool outputs** are **externally hydrated** — each owning **`Part.define`** creates its **`ExternalComputeBinding`** and calls **`link_external_routes`** beside the attributes it fills (**one binding per owning part**, compiler rule). Nested parts use **`parameter_ref(LeoLaunchMission, \"…\")`** (import from **`tg_model`**) so tool inputs reference mission parameters **without module globals**.",
        ]
    )
)

nb["cells"].append(
    cell_md(
        [
            "## Instantiate, bind inputs, evaluate",
            "",
            "Bind **only** `scenario_target_orbit_altitude_m` and `scenario_payload_mass_kg`. After `evaluate()`, the cell prints a **column-aligned snapshot**: scenario summary, external-compute samples with provenance, composition tables (major assemblies + sibling parts), stage Δv, and requirement / constraint verification (✓ SAT / ✗ UNSAT).",
        ]
    )
)
nb["cells"].append(cell_code(CODE2))

NB.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("Wrote", NB)
