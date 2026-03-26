# User-facing documentation

The **implementation plan** for NumPy docstrings **first**, then library explanation, then Sphinx HTML, is:

**[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)**

**Order of work:** docstring standard (Phase 0) → docstrings across `tg_model` (Phase 1) → prose “what the library does” (Phase 2) → Sphinx (Phase 3+). Sphinx `conf.py` and builds start in Phase 3, not at the beginning.

**Phase 0 checklist:** [docstring_style.md](./docstring_style.md)

**Phase 2 drafts (library explanation):** [drafts/README.md](./drafts/README.md)

## Build (Phase 3 scaffold)

From `thundergraph-model/`:

```bash
uv sync --group docs
uv run sphinx-build -b html docs/user_docs docs/user_docs/_build/html
```
