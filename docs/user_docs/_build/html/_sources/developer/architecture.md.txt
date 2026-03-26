# Developer architecture

## Subsystems

The core engine lives in:

- `tg_model.model` — authoring and compile-time types (`define`, `ModelDefinitionContext`, refs, compile cache).
- `tg_model.execution` — `ConfiguredModel`, dependency graph, validation, evaluation, behavior dispatch, requirements reporting.
- `tg_model.integrations` — external compute protocols and bindings.
- `tg_model.analysis` — sweeps, variant comparison, value-graph impact (multi-run tooling on top of execution outputs).

Canonical narrative flow (with more detail): {doc}`../drafts/execution_pipeline`.

## Pipeline sequences

1. **Compile types** — `Element.compile()` / `define` fills a `ModelDefinitionContext`; output is a **class-level** compiled artifact (not a runnable graph).
2. **Instantiate** — `instantiate(SomeSystem)` → `ConfiguredModel`: **frozen** topology, stable ids, registries.
3. **Compile graph** — `compile_graph(cm)` → `DependencyGraph` + handlers (evaluation order, compute nodes).
4. **Validate (recommended)** — `validate_graph(graph, configured_model=cm)` before expensive or remote evaluation.
5. **Evaluate** — fresh `RunContext` per run; `Evaluator.evaluate` / `evaluate_async` fills values and constraint rows.

Behavior APIs (`dispatch_event`, …) read/write **run** state and traces; they do **not** change `ConfiguredModel` topology.

## Invariants (mental checklist for contributors)

- **Topology is frozen** after `instantiate`; graphs are built **from** that topology, not mutated structurally during evaluation.
- **Stable ids** identify value slots across compile and run; inputs to `evaluate` are keyed by those ids.
- **`RunContext` is per run** — do not reuse across parallel evaluations without a clear concurrency story.
- **Requirement acceptance** is part of the same constraint/evaluation pass when requirements are allocated and wired with inputs.

## Extension points

See {doc}`extension_playbook` for supported seams (authoring types, external compute, analysis usage) versus internals.
