"""Multi-run orchestration: sweeps, variant comparison, value-graph propagation (Phase 5).

``impact`` / :func:`dependency_impact` report **dependency reachability on the value graph**
only — not program-wide “engineering impact” (see :mod:`tg_model.analysis.impact`).
"""

from tg_model.analysis.compare_variants import (
    CapturedSlotOutput,
    CompareVariantsValidationError,
    VariantComparisonRow,
    VariantScenario,
    compare_variants,
    compare_variants_async,
)
from tg_model.analysis.impact import (
    ImpactReport,
    dependency_impact,
    value_graph_propagation,
)
from tg_model.analysis.sweep import SweepRecord, sweep, sweep_async

impact = dependency_impact

__all__ = [
    "CapturedSlotOutput",
    "CompareVariantsValidationError",
    "ImpactReport",
    "SweepRecord",
    "VariantComparisonRow",
    "VariantScenario",
    "compare_variants",
    "compare_variants_async",
    "dependency_impact",
    "impact",
    "sweep",
    "sweep_async",
    "value_graph_propagation",
]
