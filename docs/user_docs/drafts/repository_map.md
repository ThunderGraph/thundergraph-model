# Repository Map (thundergraph-model)

This is the Phase 2 map for readers who need orientation before Sphinx pages exist.

## Core package

- `tg_model/`
  - `__init__.py`: primary exports
  - `model/`: authoring-time API and compile pipeline
    - `definition_context.py`: declarations and edges
    - `elements.py`: `Element`, `System`, `Part`, `Requirement`
    - `refs.py`: symbolic references
    - `compile_types.py`: compile engine and validation
    - `expr.py`: expression helpers
    - `declarations/`: behavior and rollup declaration helpers
  - `execution/`: configured topology and run pipeline
    - `configured_model.py`: instantiate frozen topology
    - `graph_compiler.py`: build dependency graph + handlers
    - `validation.py`: static checks before evaluation
    - `evaluator.py`: sync/async evaluation
    - `run_context.py`: per-run mutable state
    - `behavior.py`: state/decision/fork-join/item flow dispatch + trace
    - `requirements.py`: requirement satisfaction summary helpers
    - `instances.py`, `value_slots.py`, `dependency_graph.py`: runtime data structures
    - `external_ops.py`, `rollups.py`, `solve_groups.py`: compute helpers
  - `integrations/`
    - `external_compute.py`: external compute protocols and bindings
  - `analysis/`
    - `sweep.py`: parameter sweeps
    - `compare_variants.py`: multi-scenario evaluation comparison
    - `impact.py`: value-graph reachability impact
  - `export/`: reserved export namespace (currently minimal)

## Documentation

- `docs/generation_docs/`: internal design/agent-oriented docs
- `docs/user_docs/`: user-facing docs workstream
  - `IMPLEMENTATION_PLAN.md`: phased roadmap
  - `docstring_style.md`: NumPy docstring contract
  - `drafts/`: Phase 2 canonical prose (this folder)

## Examples and notebooks

- `examples/`: runnable domain examples (including commercial aircraft)
- `notebooks/`: interactive demos

## Tests

- `tests/unit/`: fast focused API/behavior tests
- `tests/integration/`: broader cross-module flows and example smoke tests

## Practical navigation order

If you are new, read in this order:

1. `docs/user_docs/drafts/what_is_thundergraph_model.md`
2. `docs/user_docs/drafts/execution_pipeline.md`
3. `tg_model/model/definition_context.py`
4. `tg_model/execution/configured_model.py`
5. `tg_model/execution/graph_compiler.py`
6. `tg_model/execution/evaluator.py`
