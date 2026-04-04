"""External-compute binding factory for :class:`MarsTransferNapkinDesk`."""

from __future__ import annotations

from collections.abc import Sequence

from examples.mars_ntp_tug.integrations.adapters import MarsTransferNapkinDesk
from tg_model.integrations.external_compute import ExternalComputeBinding, ExternalComputeResult
from tg_model.model.refs import AttributeRef


class _ProjectedMarsTransferNapkinDesk:
    """Project a subset of desk outputs so binding routes match exactly."""

    def __init__(self, output_names: Sequence[str]) -> None:
        self._output_names = tuple(output_names)
        self._desk = MarsTransferNapkinDesk()
        joined = ",".join(self._output_names)
        self.name = f"{self._desk.name}[{joined}]"

    def compute(self, inputs):
        res = self._desk.compute(inputs)
        value = res.value
        if not isinstance(value, dict):
            raise TypeError("expected MarsTransferNapkinDesk to return a mapping")
        return ExternalComputeResult(
            value={name: value[name] for name in self._output_names},
            provenance=res.provenance,
        )


def make_mars_transfer_napkin_binding(
    *,
    dry_mass_kg: AttributeRef,
    delta_v_m_s: AttributeRef,
    isp_s: AttributeRef,
    g0_m_s2: AttributeRef,
    min_thrust_to_weight: AttributeRef,
    thermal_to_jet_efficiency: AttributeRef,
    propellant_loadout_margin: AttributeRef,
    jet_kinetic_fraction: AttributeRef,
    output_names: Sequence[str] | None = None,
) -> ExternalComputeBinding:
    """Inputs are napkin **parameters** on the program root (``AttributeRef`` from ``model.parameter``)."""
    external = MarsTransferNapkinDesk()
    if output_names is not None:
        external = _ProjectedMarsTransferNapkinDesk(output_names)
    return ExternalComputeBinding(
        external,
        inputs={
            "dry_mass_kg": dry_mass_kg,
            "delta_v_m_s": delta_v_m_s,
            "isp_s": isp_s,
            "g0_m_s2": g0_m_s2,
            "min_thrust_to_weight": min_thrust_to_weight,
            "thermal_to_jet_efficiency": thermal_to_jet_efficiency,
            "propellant_loadout_margin": propellant_loadout_margin,
            "jet_kinetic_fraction": jet_kinetic_fraction,
        },
    )
