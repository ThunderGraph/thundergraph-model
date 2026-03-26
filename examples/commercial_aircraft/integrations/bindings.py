"""Factories for :class:`~tg_model.integrations.external_compute.ExternalComputeBinding` (no module globals).

Call from ``define()`` with the **configured root** type and the active ``model`` context. Nested parts
use :func:`~tg_model.model.definition_context.parameter_ref` for scenario inputs.
"""

from __future__ import annotations

from typing import Any

from unitflow.catalogs.si import m

from commercial_aircraft.integrations.adapters import AtlasMissionDesk, WingStructuralCaeSnapshot
from tg_model.integrations.external_compute import ExternalComputeBinding
from tg_model.model.definition_context import parameter_ref
from tg_model.model.refs import AttributeRef


def make_mission_range_margin_binding(model: Any, root_block_type: type) -> ExternalComputeBinding:
    """Program-root mission desk: margin in metres (synthetic max range minus requested design range)."""
    baseline = model.parameter("mission_desk_baseline_max_range_m", unit=m)
    return ExternalComputeBinding(
        AtlasMissionDesk(),
        inputs={
            "payload_kg": parameter_ref(root_block_type, "scenario_payload_mass_kg"),
            "design_range_m": parameter_ref(root_block_type, "scenario_design_range_m"),
            "baseline_max_range_m": baseline,
        },
    )


def make_wing_structural_intensity_binding(
    *,
    root_block_type: type,
    wing_dry_mass_kg: AttributeRef,
    wing_span_m: AttributeRef,
) -> ExternalComputeBinding:
    """Wing-local CAE snapshot binding (owner is ``WingAssembly``)."""
    return ExternalComputeBinding(
        WingStructuralCaeSnapshot(),
        inputs={
            "dry_mass_kg": wing_dry_mass_kg,
            "wing_span_m": wing_span_m,
            "payload_proxy_kg": parameter_ref(root_block_type, "scenario_payload_mass_kg"),
        },
    )
