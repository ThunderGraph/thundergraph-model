# Contributing

## Before you open a PR

- **Scope:** Prefer **small, reviewable** changes—one concern per PR when possible.
- **Tests:** Add or update tests for behavior that users rely on (see {doc}`testing`).
- **Public API:** If you change or add **user-visible** symbols, follow the NumPy docstring contract in {doc}`/docstring_style` (summary, Parameters, Returns, **Raises** where applicable, Notes for lifecycle).

## Checklist (public behavior changes)

- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check tg_model tests` passes (or only pre-existing issues outside your diff).
- [ ] `uv run mypy tg_model` passes if your change touched typed surfaces.
- [ ] Docstrings updated for any new or changed **public** function, method, or module export.
- [ ] If user-facing behavior changed, **user docs** or examples are updated in the same change or a follow-up is tracked.

## Docs build

After editing narrative or API-adjacent docs:

```bash
cd thundergraph-model
uv run --group docs sphinx-build -W -b html docs/user_docs docs/user_docs/_build/html
```

Fix broken **internal** links reported by Sphinx before merging.

## References

- Extension boundaries: {doc}`extension_playbook`
- Releasing: {doc}`releasing`
