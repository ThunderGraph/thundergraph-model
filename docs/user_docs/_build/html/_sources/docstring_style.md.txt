# NumPy-style docstrings for `tg_model` (Phase 0 contract)

This file is the **checklist** for public API documentation in ThunderGraph Model. It implements **Phase 0** of `docs/user_docs/IMPLEMENTATION_PLAN.md`: authors and reviewers use it so docstrings stay consistent before Sphinx renders them.

## Standard

We follow the [numpydoc](https://numpydoc.readthedocs.io/en/latest/format.html) sections. Sphinx will consume these via Napoleon (NumPy) in Phase 3.

## What counts as “public”

- Any name listed in `__all__` of `tg_model`, `tg_model.model`, `tg_model.execution`, `tg_model.integrations`, or `tg_model.analysis`.
- Any subclass hook or method users override in normal use (e.g. `Element.define`, `Element.compile`).
- Module docstrings for packages users import.

**Private** helpers (leading `_`, internal compilers): minimal docstrings unless the logic is non-obvious.

## Required sections by symbol kind

### Module

| Section | Required |
|---------|----------|
| Summary (first line) | Yes |
| Extended summary | If the module is non-obvious |
| **Notes** | Optional: lifecycle (type vs configure vs run), links to related modules |

### Class

| Section | Required |
|---------|----------|
| Summary | Yes |
| **Attributes** or **Parameters** (for `dataclass` fields) | When instance state is user-facing |
| **Notes** | For lifecycle, threading, or scope rules (e.g. `RunContext` behavior scope) |
| **Examples** | Primary authoring types (`System`, `ModelDefinitionContext` patterns) when a short example fits |

### Function / method

| Section | Required |
|---------|----------|
| Summary | Yes |
| **Parameters** | If there are parameters (use clear semantics; do not duplicate type hints verbatim only) |
| **Returns** | If not `None` or obvious |
| **Raises** | **Whenever** the callable raises documented exceptions (`ModelDefinitionError`, `KeyError`, `ValueError`, `TypeError`, `RuntimeError`, etc.) |
| **Notes** | Ordering, resolution rules, preconditions, interaction with compile/instantiate/evaluate |
| **Examples** | Primary entrypoints (`instantiate`, `compile_graph`, `Evaluator.evaluate`, `parameter_ref` + `allocate`) where copy-paste helps |
| **See Also** | Tight cross-links (`allocate` ↔ `requirement_input`, sync vs async evaluator) |

### Properties

Treat like methods: summary + **Returns** + **Raises** if applicable.

## Style rules

1. **Honesty:** Docstrings must not contradict tests. If code and doc disagree, fix code or doc in the same change.
2. **Raises is not optional** for APIs that fail in normal misuse paths (missing declarations, wrong ref kind, async/sync mismatch).
3. **Prefer “Notes” for pipelines** (e.g. “Resolution order: compiled artifact, then active definition context”).
4. **Avoid redundant noise:** Do not restate the entire implementation; state the contract.
5. **Unitflow:** When symbols or quantities matter, name the dependency (`unitflow`) in **Notes** or **Parameters**, not vague “expression” only.

## PR checklist (touched public API)

- [ ] Summary line under 72 characters when possible.
- [ ] Parameters / Returns / Raises filled in **as applicable**.
- [ ] Primary entrypoint: **Examples** or a pointer to tests/notebooks.
- [ ] Cross-type references use Sphinx-friendly roles where we will build HTML: `` :class:`~tg_model....` `` (optional in code; consistent naming regardless).
- [ ] No new public symbol without meeting this bar.

## Pilot reference

The first full application of this standard is `tg_model/model/definition_context.py` (and the rest of Phase 1 modules per the implementation plan).
