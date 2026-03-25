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
        dry = model.parameter("local_dry_mass_kg", unit=kg)
        prop = model.parameter("local_propellant_mass_kg", unit=kg)
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class UpperStageOxidizerTank(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        dry = model.parameter("local_dry_mass_kg", unit=kg)
        prop = model.parameter("local_propellant_mass_kg", unit=kg)
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class UpperStageFuelTank(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        dry = model.parameter("local_dry_mass_kg", unit=kg)
        prop = model.parameter("local_propellant_mass_kg", unit=kg)
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class UpperStageEngineInstallation(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        dry = model.parameter("local_dry_mass_kg", unit=kg)
        prop = model.parameter("local_propellant_mass_kg", unit=kg)
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)
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

        dry = model.parameter("stage_structure_dry_mass_kg", unit=kg)
        prop = model.parameter("stage_structure_propellant_mass_kg", unit=kg)
        wet_local = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)

        mw = model.parameter("stage_burn_initial_mass_kg", unit=kg)
        md = model.parameter("stage_burn_final_mass_kg", unit=kg)
        isp = model.parameter("stage_isp_seconds", unit=s)
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
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry + r_dry)

        r_wet = model.attribute(
            "rolled_children_wet_mass_kg",
            unit=kg,
            expr=ox.subtree_wet_mass_kg + (ft.subtree_wet_mass_kg + ei.subtree_wet_mass_kg),
        )
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet_local + r_wet)

        r_dv = model.attribute(
            "rolled_children_delta_v_sum",
            unit=m / s,
            expr=ox.subtree_cumulative_delta_v + (ft.subtree_cumulative_delta_v + ei.subtree_cumulative_delta_v),
        )
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=local_dv + r_dv)


class FirstStagePropellantSection(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        dry = model.parameter("local_dry_mass_kg", unit=kg)
        prop = model.parameter("local_propellant_mass_kg", unit=kg)
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class FirstStageEngineCluster(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        dry = model.parameter("local_dry_mass_kg", unit=kg)
        prop = model.parameter("local_propellant_mass_kg", unit=kg)
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry.sym)
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet.sym)
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=NO_MODELED_STAGE_BURN_DV)


class FirstStageThrustStructure(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        dry = model.parameter("local_dry_mass_kg", unit=kg)
        prop = model.parameter("local_propellant_mass_kg", unit=kg)
        wet = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)
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

        dry = model.parameter("stage_structure_dry_mass_kg", unit=kg)
        prop = model.parameter("stage_structure_propellant_mass_kg", unit=kg)
        wet_local = model.attribute("local_wet_mass_kg", unit=kg, expr=dry + prop)

        mw = model.parameter("stage_burn_initial_mass_kg", unit=kg)
        md = model.parameter("stage_burn_final_mass_kg", unit=kg)
        isp = model.parameter("stage_isp_seconds", unit=s)
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
        model.attribute("subtree_dry_mass_kg", unit=kg, expr=dry + r_dry)

        r_wet = model.attribute(
            "rolled_children_wet_mass_kg",
            unit=kg,
            expr=ps.subtree_wet_mass_kg + (ec.subtree_wet_mass_kg + ts.subtree_wet_mass_kg),
        )
        model.attribute("subtree_wet_mass_kg", unit=kg, expr=wet_local + r_wet)

        r_dv = model.attribute(
            "rolled_children_delta_v_sum",
            unit=m / s,
            expr=ps.subtree_cumulative_delta_v + (ec.subtree_cumulative_delta_v + ts.subtree_cumulative_delta_v),
        )
        model.attribute("subtree_cumulative_delta_v", unit=m / s, expr=local_dv + r_dv)


class LaunchRocket(Part):
    """**Rocket** block (BDD: the vehicle product): **composed of** fairing, upper stage, first stage.

    All vehicle-level parameters, mass/Δv roll-ups, and design constraints live **here**. A separate
    **mission / context** system composes this block as ``part rocket`` and holds mission-level
    requirements plus allocation to ``rocket``.
    """

    @classmethod
    def define(cls, model):  # type: ignore[override]
        # --- Composition (SysML part properties on the rocket block) ---
        fairing = model.part("fairing_and_payload_interface", FairingAndPayloadInterface)
        upper = model.part("upper_stage", UpperStageAssembly)
        first = model.part("first_stage", FirstStageAssembly)

        thrust = model.parameter("sea_level_thrust_n", unit=N)

        misc_dry = model.parameter("vehicle_misc_dry_mass_kg", unit=kg)
        misc_prop = model.parameter("vehicle_misc_propellant_mass_kg", unit=kg)
        misc_wet = model.attribute("vehicle_misc_wet_mass_kg", unit=kg, expr=misc_dry + misc_prop)

        r_dry = model.attribute(
            "rolled_major_assemblies_dry_mass_kg",
            unit=kg,
            expr=fairing.subtree_dry_mass_kg
            + (upper.subtree_dry_mass_kg + first.subtree_dry_mass_kg),
        )
        sub_dry = model.attribute("subtree_dry_mass_kg", unit=kg, expr=misc_dry + r_dry)

        r_wet = model.attribute(
            "rolled_major_assemblies_wet_mass_kg",
            unit=kg,
            expr=fairing.subtree_wet_mass_kg
            + (upper.subtree_wet_mass_kg + first.subtree_wet_mass_kg),
        )
        sub_wet = model.attribute("subtree_wet_mass_kg", unit=kg, expr=misc_wet + r_wet)

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
            expr=thrust / (sub_wet * G0),
        )
        model.constraint("min_liftoff_twr", expr=twr >= Quantity(1.12, DIMLESS))
        model.constraint("vehicle_dry_under_cap", expr=sub_dry <= Quantity(28_000, kg))


class LeoLaunchMission(System):
    """**Mission / analysis context** (BDD root): **composed of** the launch vehicle as a single part.

    Requirements at this level allocate to ``rocket`` — the same pattern as allocating to any other
    composed subsystem: ``rocket = model.part(\"rocket\", LaunchRocket)`` then ``model.allocate(req, rocket)``.
    """

    @classmethod
    def define(cls, model):  # type: ignore[override]
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

inputs = {
    rocket.sea_level_thrust_n.stable_id: Quantity(7_600_000, N),
    rocket.vehicle_misc_dry_mass_kg.stable_id: Quantity(0, kg),
    rocket.vehicle_misc_propellant_mass_kg.stable_id: Quantity(0, kg),
    rocket.fairing_and_payload_interface.local_dry_mass_kg.stable_id: Quantity(5_200, kg),
    rocket.fairing_and_payload_interface.local_propellant_mass_kg.stable_id: Quantity(0, kg),
    rocket.upper_stage.stage_structure_dry_mass_kg.stable_id: Quantity(1_100, kg),
    rocket.upper_stage.stage_structure_propellant_mass_kg.stable_id: Quantity(0, kg),
    rocket.upper_stage.oxidizer_tank.local_dry_mass_kg.stable_id: Quantity(380, kg),
    rocket.upper_stage.oxidizer_tank.local_propellant_mass_kg.stable_id: Quantity(118_000, kg),
    rocket.upper_stage.fuel_tank.local_dry_mass_kg.stable_id: Quantity(290, kg),
    rocket.upper_stage.fuel_tank.local_propellant_mass_kg.stable_id: Quantity(48_000, kg),
    rocket.upper_stage.engine_installation.local_dry_mass_kg.stable_id: Quantity(650, kg),
    rocket.upper_stage.engine_installation.local_propellant_mass_kg.stable_id: Quantity(800, kg),
    rocket.upper_stage.stage_burn_initial_mass_kg.stable_id: Quantity(168_000, kg),
    rocket.upper_stage.stage_burn_final_mass_kg.stable_id: Quantity(52_000, kg),
    rocket.upper_stage.stage_isp_seconds.stable_id: Quantity(340, s),
    rocket.first_stage.stage_structure_dry_mass_kg.stable_id: Quantity(920, kg),
    rocket.first_stage.stage_structure_propellant_mass_kg.stable_id: Quantity(0, kg),
    rocket.first_stage.propellant_section.local_dry_mass_kg.stable_id: Quantity(480, kg),
    rocket.first_stage.propellant_section.local_propellant_mass_kg.stable_id: Quantity(185_000, kg),
    rocket.first_stage.engine_cluster.local_dry_mass_kg.stable_id: Quantity(5_200, kg),
    rocket.first_stage.engine_cluster.local_propellant_mass_kg.stable_id: Quantity(0, kg),
    rocket.first_stage.thrust_structure.local_dry_mass_kg.stable_id: Quantity(520, kg),
    rocket.first_stage.thrust_structure.local_propellant_mass_kg.stable_id: Quantity(1_200, kg),
    rocket.first_stage.stage_burn_initial_mass_kg.stable_id: Quantity(195_000, kg),
    rocket.first_stage.stage_burn_final_mass_kg.stable_id: Quantity(38_000, kg),
    # ~318 s: with fixed masses, first-stage ideal Δv scales ~linearly with Isp; nudges ΣΔv past 9 km/s vs 290 s.
    rocket.first_stage.stage_isp_seconds.stable_id: Quantity(318, s),
}

graph, handlers = compile_graph(cm)
val = validate_graph(graph)
assert val.passed, val.failures

ctx = RunContext()
result = Evaluator(graph, compute_handlers=handlers).evaluate(ctx, inputs=inputs)
assert not result.failures, result.failures


def qmag(q):
    return float(q.magnitude)


print("=== LeoLaunchMission (configured root) ===")
print("  part: rocket ->", rocket.path_string)

print("\n=== LaunchRocket (vehicle block) ===")
print("Wet mass (kg):", qmag(ctx.get_value(rocket.subtree_wet_mass_kg.stable_id)))
print("Dry mass (kg):", qmag(ctx.get_value(rocket.subtree_dry_mass_kg.stable_id)))
print("Ideal ΣΔv (m/s):", qmag(ctx.get_value(rocket.subtree_cumulative_delta_v.stable_id)))
_twr = ctx.get_value(rocket.liftoff_thrust_to_weight.stable_id)
print("Liftoff T/W (—):", _twr.magnitude)

print("\n=== Major assemblies (composition under LaunchRocket) ===")
for label, handle in [
    ("Fairing + payload interface", rocket.fairing_and_payload_interface),
    ("Upper stage", rocket.upper_stage),
    ("First stage", rocket.first_stage),
]:
    dry = ctx.get_value(handle.subtree_dry_mass_kg.stable_id)
    wet = ctx.get_value(handle.subtree_wet_mass_kg.stable_id)
    dv = ctx.get_value(handle.subtree_cumulative_delta_v.stable_id)
    print(f"  {label}: dry={dry}  wet={wet}  ΣΔv={dv}")

print("\n=== Upper stage — sibling tanks / engines ===")
for name in ("oxidizer_tank", "fuel_tank", "engine_installation"):
    h = getattr(rocket.upper_stage, name)
    print(f"  {name}: dry={ctx.get_value(h.subtree_dry_mass_kg.stable_id)}  wet={ctx.get_value(h.subtree_wet_mass_kg.stable_id)}")

print("\n=== First stage — sibling sections ===")
for name in ("propellant_section", "engine_cluster", "thrust_structure"):
    h = getattr(rocket.first_stage, name)
    print(f"  {name}: dry={ctx.get_value(h.subtree_dry_mass_kg.stable_id)}  wet={ctx.get_value(h.subtree_wet_mass_kg.stable_id)}")

print("\n=== Stage burns (Tsiolkovsky at assembly only) ===")
print("  Upper local_stage_delta_v:", ctx.get_value(rocket.upper_stage.local_stage_delta_v.stable_id))
print("  First  local_stage_delta_v:", ctx.get_value(rocket.first_stage.local_stage_delta_v.stable_id))

summary = summarize_requirement_satisfaction(result)
print("\nRequirement checks:", summary.check_count, "| all_passed:", summary.all_passed)
for row in summary.results:
    print(" ", row.requirement_path, "|", "PASS" if row.passed else "FAIL")

print("\nConstraints:", len(result.constraint_results))
for cr in result.constraint_results:
    print(" ", cr)
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
            "**ThunderGraph ↔ SysML:** each **`model.part(\"name\", BlockType)`** is **composition** (the parent **owns** that child). `model.part()` with **no** args remains available as a ref to the block you are defining (`root_block`); this demo does not need it because allocation targets the named **`rocket`** part.",
            "",
            "**What it is not:** trajectory, losses, staging time, or engine-out. Δv is **ideal Tsiolkovsky once per burning stage** (upper assembly and first-stage assembly). Tank/fairing **leaves** use `NO_MODELED_STAGE_BURN_DV`: they add **no burn term** to the ΣΔv roll-up (mass is in dry/wet; this slot is burn accounting only).",
            "",
            "**How to read the code:** every subsystem is a **`Part` / `System` class** with **`define()`**. Roll-ups use **named sums** so accountability matches the tree. **Passthrough attributes** use **`.sym`** (e.g. `expr=wet.sym`), not bare refs — otherwise the graph never binds realized numbers.",
            "",
            "**Imports:** load `tg_model` **after** the `sys.path` fix and any `sys.modules` purge.",
            "",
            "**Run:** `uv run jupyter nbconvert --to notebook --execute notebooks/leo_launch_vehicle_deep_stack.ipynb --inplace`",
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
            "## Instantiate, bind inputs, evaluate",
            "",
            "Illustrative masses and stage burn parameters — chosen so **ΣΔv** and **T/W** constraints pass.",
        ]
    )
)
nb["cells"].append(cell_code(CODE2))

NB.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("Wrote", NB)
