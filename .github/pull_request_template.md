## What I did

<!-- Describe the work: problem solved, approach, main files or areas touched. Use bullets if it helps. -->



## Why

<!-- Motivation, context, or link to issue / discussion. e.g. Fixes #123 -->



## How to verify

<!-- How a reviewer can validate this change (commands, UI steps, scenarios). Omit or write “see checklist” if obvious. -->



## Scope

<!-- Which part(s) of the monorepo: e.g. thundergraph-model, api_server, infra, docs only. -->



---

## Checklist

### Tests and lint (ThunderGraph Model)

When your change is under **`thundergraph-model/`** (run commands from that directory):

- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check tg_model tests` passes (or only pre-existing issues outside your diff).
- [ ] `uv run mypy tg_model` passes if your change touched typed surfaces.

### Public API and docs

- [ ] Docstrings updated for any new or changed public function, method, or module export (NumPy-style; see `thundergraph-model/docs/user_docs/docstring_style.md`).
- [ ] If user-facing behavior changed, user docs or examples are updated in the same change or a follow-up is tracked.

### Sphinx (if you edited `thundergraph-model/docs/` or API-adjacent narratives)

- [ ] `uv run sphinx-build -b html docs/user_docs docs/user_docs/_build/html` succeeds (use `-W` for warnings-as-errors if you are touching the docs build in CI).

### Monorepo / other packages

<!-- Add package-specific checks if this PR is not only thundergraph-model, e.g. pytest in `api_server/`, CDK synth, etc. -->

- [ ] _(optional)_ Additional validation performed:



---

## Screenshots / sample output

<!-- Paste snippets, API responses, or screenshots if the change is visible. Write N/A if not applicable. -->



## Risk and rollback

<!-- Blast radius, feature flags, migration notes, or how to revert. Write N/A if low risk. -->


