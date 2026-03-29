"""External napkin simulations (``ExternalComputeBinding``) for the Mars NTP tug example."""

from examples.mars_ntp_tug.integrations.adapters import MarsTransferNapkinDesk
from examples.mars_ntp_tug.integrations.bindings import make_mars_transfer_napkin_binding
from examples.mars_ntp_tug.integrations.preset_inputs import (
    merge_mars_ntp_eval_inputs,
    reference_hardware_overrides,
    reference_napkin_assumptions,
    run_mars_transfer_napkin_desk,
)

__all__ = [
    "MarsTransferNapkinDesk",
    "make_mars_transfer_napkin_binding",
    "merge_mars_ntp_eval_inputs",
    "reference_hardware_overrides",
    "reference_napkin_assumptions",
    "run_mars_transfer_napkin_desk",
]
