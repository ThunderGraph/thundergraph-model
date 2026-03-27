# Repository map

Orientation for contributors: where code and docs live in **thundergraph-model** (this package root).

## Layout

| Path | Purpose |
|------|---------|
| `tg_model/` | Installable library — **only** this tree ships in the wheel. |
| `tests/unit/`, `tests/integration/` | Pytest suites (see {doc}`testing`). |
| `examples/` | Domain examples (e.g. commercial aircraft); not on `PYTHONPATH` unless you add them. |
| `notebooks/` | Jupyter walkthroughs; dev dependency in `uv` optional groups. |
| `docs/user_docs/` | Sphinx site sources — **this** manual (`conf.py`, `user/`, `developer/`, `api/`, `drafts/`). |
| `docs/generation_docs/` | Internal design / agent context — not the default end-user manual. |

A longer file-level breakdown (Phase 2) lives in {doc}`../drafts/repository_map`.

## Suggested reading order (new contributor)

1. {doc}`../user/quickstart` — default **`evaluate`** path vs explicit pipeline (read this before diving into compiler details).
2. {doc}`../drafts/what_is_thundergraph_model`
3. {doc}`../drafts/execution_pipeline`
4. {doc}`architecture` and {doc}`extension_playbook`
5. Source: `tg_model/model/definition_context.py` → `tg_model/execution/configured_model.py` → `graph_compiler.py` → `evaluator.py`
