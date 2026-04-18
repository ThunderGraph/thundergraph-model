"""Smoke: mars_ntp_tug example compiles, evaluates, and reports cleanly."""

from __future__ import annotations

import sys
from pathlib import Path

_THUNDERGRAPH_MODEL = Path(__file__).resolve().parents[2]
_EXAMPLES_ROOT = _THUNDERGRAPH_MODEL / "examples"
if str(_EXAMPLES_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_ROOT))

from mars_ntp_tug.integrations.preset_inputs import (  # noqa: E402
    merge_mars_ntp_eval_inputs,
    reference_hardware_overrides,
    reference_napkin_assumptions,
)
from mars_ntp_tug.reporting.extract import extract_mars_ntp_evaluation_report  # noqa: E402
from mars_ntp_tug.reporting.snapshot import format_mars_ntp_report  # noqa: E402
from mars_ntp_tug.tug_model import MarsNuclearTug, reset_ntp_types  # noqa: E402

from tg_model.execution.configured_model import instantiate  # noqa: E402


def setup_function() -> None:
    reset_ntp_types()


def test_mars_ntp_tug_compiles() -> None:
    art = MarsNuclearTug.compile()
    assert "napkin_transfer_delta_v" in art["nodes"]
    assert art["nodes"]["requirements"]["kind"] == "requirement_block"
    assert art["nodes"]["mission_sizing"]["kind"] == "part"
    ms_key = next(k for k in art["child_types"] if k.endswith("MissionSizingPart"))
    ms_nodes = art["child_types"][ms_key]["nodes"]
    assert ms_nodes["sim_propellant_required_kg"]["kind"] == "attribute"
    assert ms_nodes["mission_propellant_required"]["kind"] == "attribute"
    assert ms_nodes["napkin_propellant_loadout_margin_ge_one"]["kind"] == "constraint"


def test_mars_ntp_tug_instantiate_and_evaluate() -> None:
    cm = instantiate(MarsNuclearTug)
    inputs = merge_mars_ntp_eval_inputs(
        cm,
        napkin=reference_napkin_assumptions(),
        hardware=reference_hardware_overrides(),
    )
    result = cm.evaluate(inputs=inputs)
    assert result.passed, result.failures

    ms = cm.mission_sizing
    assert result.outputs[ms.sim_propellant_required_kg.stable_id].magnitude > 0
    assert result.outputs[ms.mission_min_vacuum_thrust.stable_id].magnitude > 0


def test_mars_ntp_report_extract_and_snapshot() -> None:
    cm = instantiate(MarsNuclearTug)
    inputs = merge_mars_ntp_eval_inputs(
        cm,
        napkin=reference_napkin_assumptions(),
        hardware=reference_hardware_overrides(),
    )
    result = cm.evaluate(inputs=inputs)
    assert result.passed, result.failures

    data = extract_mars_ntp_evaluation_report(cm, result)
    assert data["evaluation_passed"]
    assert data["reqcheck_all_passed"]
    assert data["reqcheck_count"] == 10
    assert data["mission_desk_outputs"]["sim_propellant_required_kg"]

    text = format_mars_ntp_report(data)
    assert "Verdict" in text
    assert "Mission desk outputs" in text
    assert "Formal requirements" in text
