# Install

## Requirements

- Python 3.11+
- `uv` (recommended)

## Install for development (repo workflow)

From `thundergraph-model/`:

```bash
uv sync --all-groups
```

## Install as a library

The project name is `thundergraph-model` (see `pyproject.toml`). If a release is published to PyPI under that name, you can install with:

```bash
pip install thundergraph-model
```

If that package is not available in your environment (for example you are on a pre-release checkout or using a private index), install from the repository root instead:

```bash
cd thundergraph-model
uv sync
# or: pip install -e .
```

## Verify install

```bash
python -c "import tg_model; print('ok')"
```
