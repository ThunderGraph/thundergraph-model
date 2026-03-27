"""Requirement satisfaction reporting (Phase 7).

Acceptance criteria are compiled as dependency-graph constraint checks; results appear in
:class:`~tg_model.execution.run_context.RunContext` / :class:`~tg_model.execution.evaluator.RunResult`
alongside part-owned constraints, tagged with ``requirement_path`` when applicable.
"""

from __future__ import annotations

from dataclasses import dataclass

from tg_model.execution.evaluator import RunResult
from tg_model.execution.run_context import RunContext


@dataclass(frozen=True)
class RequirementSatisfactionResult:
    """Outcome of one requirement acceptance check (one allocation x one compiled check)."""

    requirement_path: str
    allocation_target_path: str
    passed: bool
    evidence: str
    check_name: str


@dataclass(frozen=True)
class RequirementSatisfactionSummary:
    """Aggregated requirement acceptance outcomes for one run.

    Use :attr:`check_count` to detect the case where **no** acceptance checks ran (no ``expr=``
    requirements compiled into the graph for this configuration). :attr:`all_passed` is **False**
    when ``check_count == 0`` so callers do not treat "nothing to verify" as green compliance.
    """

    results: tuple[RequirementSatisfactionResult, ...]

    @property
    def check_count(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        """True only when there is at least one acceptance check and every check passed."""
        return len(self.results) > 0 and all(r.passed for r in self.results)


def iter_requirement_satisfaction(
    ctx: RunContext | RunResult,
) -> list[RequirementSatisfactionResult]:
    """Filter constraint rows that carry ``requirement_path`` (acceptance checks).

    Parameters
    ----------
    ctx : RunContext or RunResult
        Object exposing ``constraint_results`` (same ordering as evaluation).

    Returns
    -------
    list of RequirementSatisfactionResult
        One row per tagged constraint result.
    """
    out: list[RequirementSatisfactionResult] = []
    for cr in ctx.constraint_results:
        if cr.requirement_path is None:
            continue
        out.append(
            RequirementSatisfactionResult(
                requirement_path=cr.requirement_path,
                allocation_target_path=cr.allocation_target_path or "",
                passed=cr.passed,
                evidence=cr.evidence,
                check_name=cr.name,
            )
        )
    return out


def summarize_requirement_satisfaction(
    ctx: RunContext | RunResult,
) -> RequirementSatisfactionSummary:
    """Aggregate :func:`iter_requirement_satisfaction` into a summary tuple.

    Returns
    -------
    RequirementSatisfactionSummary
        Includes :attr:`RequirementSatisfactionSummary.all_passed` semantics for zero checks.
    """
    return RequirementSatisfactionSummary(tuple(iter_requirement_satisfaction(ctx)))


def all_requirements_satisfied(ctx: RunContext | RunResult) -> bool:
    """Return :attr:`RequirementSatisfactionSummary.all_passed` for ``ctx``.

    Returns
    -------
    bool
        **False** when there are **zero** requirement acceptance checks (not vacuously true).

    See Also
    --------
    summarize_requirement_satisfaction
    """
    return summarize_requirement_satisfaction(ctx).all_passed
