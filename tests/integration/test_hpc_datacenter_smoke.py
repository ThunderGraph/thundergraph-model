"""Smoke: hpc_datacenter example compiles, evaluates, and supports sweep-style evaluate(validate=False)."""

from __future__ import annotations

import sys
from pathlib import Path

from unitflow import Quantity
from unitflow.catalogs.si import kW

_THUNDERGRAPH_MODEL = Path(__file__).resolve().parents[2]
_EXAMPLES_ROOT = _THUNDERGRAPH_MODEL / "examples"
if str(_EXAMPLES_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_ROOT))

from hpc_datacenter import HpcDatacenterProgram, reset_hpc_datacenter_types  # noqa: E402


def setup_function() -> None:
    reset_hpc_datacenter_types()


def test_hpc_datacenter_compiles_requirement_package_subtree() -> None:
    """Composable Requirement tree is wired under internal kind ``requirement_block`` on the root artifact."""
    art = HpcDatacenterProgram.compile()
    assert art["nodes"]["l1"]["kind"] == "requirement_block"
    l1_key = next(k for k in art["child_types"] if k.endswith("L1HpcRoot"))
    l1_nodes = art["child_types"][l1_key]["nodes"]
    assert l1_nodes["hpc"]["kind"] == "requirement_block"
    hpc_key = next(k for k in art["child_types"][l1_key]["child_types"] if k.endswith("L1HpcRequirements"))
    hpc_nodes = art["child_types"][l1_key]["child_types"][hpc_key]["nodes"]
    assert "req_grid_import_capacity" in hpc_nodes
    assert hpc_nodes["req_grid_import_capacity"]["kind"] == "requirement"


def test_hpc_datacenter_instantiate_and_evaluate() -> None:
    cm = HpcDatacenterProgram.instantiate()
    fac = cm.facility
    inputs = {
        cm.equipment_electrical_load_kw: Quantity(30.0, kW),
        cm.auxiliary_cooling_load_kw: Quantity(8.0, kW),
        fac.equipment_electrical_load_kw: Quantity(30.0, kW),
        fac.auxiliary_cooling_load_kw: Quantity(8.0, kW),
        fac.grid_import_capacity_kw: Quantity(50.0, kW),
        fac.max_cooling_kw: Quantity(12.0, kW),
    }
    result = cm.evaluate(inputs=inputs)
    assert result.passed
    assert result.outputs[fac.total_facility_kw.stable_id] == Quantity(38.0, kW)


def test_hpc_datacenter_sweep_uses_validate_false_after_first_pass() -> None:
    """Second and later points skip static validation (facade contract for tight loops)."""
    cm = HpcDatacenterProgram.instantiate()
    fac = cm.facility
    cm.evaluate(
        inputs={
            cm.equipment_electrical_load_kw: Quantity(10.0, kW),
            cm.auxiliary_cooling_load_kw: Quantity(4.0, kW),
            fac.equipment_electrical_load_kw: Quantity(10.0, kW),
            fac.auxiliary_cooling_load_kw: Quantity(4.0, kW),
            fac.grid_import_capacity_kw: Quantity(100.0, kW),
            fac.max_cooling_kw: Quantity(20.0, kW),
        },
        validate=True,
    )
    r2 = cm.evaluate(
        inputs={
            cm.equipment_electrical_load_kw: Quantity(90.0, kW),
            cm.auxiliary_cooling_load_kw: Quantity(25.0, kW),
            fac.equipment_electrical_load_kw: Quantity(90.0, kW),
            fac.auxiliary_cooling_load_kw: Quantity(25.0, kW),
            fac.grid_import_capacity_kw: Quantity(100.0, kW),
            fac.max_cooling_kw: Quantity(20.0, kW),
        },
        validate=False,
    )
    assert not r2.passed
