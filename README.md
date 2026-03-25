# thundergraph-model
ThunderGraph DSL for MBSE and digital twins

## Environment
This directory is its **own uv project** (not a member of the repo-root workspace). From here:

```bash
uv sync --all-groups   # creates/uses thundergraph-model/.venv
uv run pytest
uv run jupyter lab notebooks/aev_thundergraph_demo.ipynb
```

The monorepo root `.venv` is for `backend-monorepo` only.
