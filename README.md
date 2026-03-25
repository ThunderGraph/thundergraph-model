<div align="center">

<img src="logo.png" alt="ThunderGraph Model" width="220">

# thundergraph-model

**Executable systems modeling in Python** — architecture, constraints, behavior, and traceability in one library engineers can actually run.

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Tests](https://img.shields.io/badge/tests-200%20passed-success)](./tests/)
[![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)](#development)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![mypy](https://img.shields.io/badge/types-mypy--strict-2d50a5?logo=python&logoColor=white)](https://mypy-lang.org/)
[![Hatch](https://img.shields.io/badge/build-hatch-0077B5)](https://hatch.pypa.io/)
[![uv](https://img.shields.io/badge/uv-project-0A0A0A?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)

[Quick start](#quick-start) · [Why this exists](#why-this-exists) · [Docs](#documentation) · [Development](#development)

</div>

---

## Why this exists

Most “architecture” tools stop at diagrams. **ThunderGraph Model** is a **small, strict Python library** for modeling **systems** the way engineers think: **parts**, **interfaces**, **constraints**, **requirements with acceptance**, **discrete behavior**, and **provenance** — all tied together so you can **compile**, **evaluate**, and **validate** a configuration, not just draw it.

It is built for **MBSE**-style workflows, **digital twin** sketches, and **executable specs** where **units matter** (`unitflow`), **requirements are the locus of acceptance**, and **citations** attach to real design elements for traceability.

If you want a library that feels **honest** (fail-fast validation, explicit graphs) and **hackable** (plain Python, no proprietary runtime), you’re in the right place.

---

## What you get

| Capability | What it means for engineering |
|------------|--------------------------------|
| **Structured authoring** | `System` / `Part` with `define(cls, model)` — one place to declare ports, parameters, attributes, constraints, behavior. |
| **Unit-aware expressions** | Parameters and attributes use **unitflow**; constraints and requirement acceptance are evaluated on real quantities. |
| **Requirements + allocation** | Requirements live at the **system** level; `allocate` links them to **parts**; optional `expr` drives automated acceptance checks. |
| **Citations & references** | `citation` nodes and `references` edges bind standards, reports, or clauses to **any** declared element — provenance without pretending to be a bibliography manager. |
| **Discrete behavior** | States, events, guards, sequences, fork/join, item flow across ports — **scenarios** for trace validation. |
| **Execution** | `instantiate` → `compile_graph` → `Evaluator` on a `RunContext` — one pipeline for constraints and requirement checks. |

---

## Quick start

This directory is its **own [uv](https://docs.astral.sh/uv/) project** (separate from the monorepo root venv).

```bash
cd thundergraph-model
uv sync --all-groups   # dev + notebook tooling
uv run pytest
uv run ruff check tg_model tests
uv run mypy tg_model
```

**Notebook demos** (interactive walkthroughs):

```bash
uv run jupyter lab notebooks/aev_thundergraph_demo.ipynb
uv run jupyter lab notebooks/sodium_fast_reactor_demo.ipynb
```

Headless execution:

```bash
uv run jupyter nbconvert --to notebook --execute notebooks/aev_thundergraph_demo.ipynb --output-dir notebooks
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [`docs/v0_api.md`](docs/v0_api.md) | Public API shape, authoring patterns, execution contract. |
| [`docs/implementation_plan.md`](docs/implementation_plan.md) | Phased roadmap (requirements, behavior, citations, …). |
| [`docs/logical_architecture.md`](docs/logical_architecture.md) | Conceptual architecture. |

---

## Development

| Tool | Role |
|------|------|
| **pytest** + **pytest-cov** | Tests; default run includes `--cov=tg_model` (see `pyproject.toml`). |
| **Ruff** | Lint + import sort (`E`, `F`, `I`, `UP`, `RUF`). |
| **mypy** | **Strict** typing on `tg_model`. |

Typical loop:

```bash
uv run pytest
uv run ruff check tg_model tests && uv run ruff format tg_model tests
uv run mypy tg_model
```

**Coverage** badge (88%) reflects `pytest --cov=tg_model` on the current tree; re-run tests to refresh.

---

## License

Licensed under the **Apache License 2.0** — see [`LICENSE`](./LICENSE).

---

## Contributing

Issues and PRs are welcome. Keep changes focused, match existing style (`ruff` / `mypy`), and extend **tests** when you touch behavior or contracts.

If you want to **talk engineering** about MBSE, nuclear, automotive, or digital twins — this library is meant to be **used**, not just read.
