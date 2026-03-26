# Extension playbook

Where ThunderGraph Model is designed to be extended safely—and where you should **not** hook in without treating the change as a library contribution.

## Supported extension surfaces

### Authoring types (`tg_model.model`)

- **`System`**, **`Part`**, **`RequirementBlock`** — override `define(cls, model)` (and `compile()` only where the framework’s contract requires it). This is the primary **domain** extension point: new parts, parameters, constraints, requirement blocks, **`requirement_input`** / **`requirement_attribute`** / **`requirement_accept_expr`**, and allocation wiring.
- **`ModelDefinitionContext`** — you do not subclass this; you call its methods **from** `define` on your element types. Public methods are the vocabulary for declarations.
- **Refs** (`AttributeRef`, `PartRef`, …) — returned by `model` APIs; you **use** them in expressions and `allocate`, not subclass them.

### Execution boundaries (`tg_model.execution`)

- **`instantiate`**, **`compile_graph`**, **`validate_graph`**, **`Evaluator`** — call these; do not fork the evaluator unless you are fixing a bug in the library.
- **`RunContext`** — per-run mutable state; safe to use for multiple evaluations with fresh instances per run.

### External compute (`tg_model.integrations`)

- Implement **`ExternalCompute`** (sync) or **`AsyncExternalCompute`** (async with `evaluate_async`).
- Optionally implement **`ValidatableExternalCompute.validate_binding`** so `validate_graph(..., configured_model=cm)` can check units before evaluation.
- Wire with **`ExternalComputeBinding`** and **`attribute(..., computed_by=...)`**; use **`link_external_routes`** when returning multiple outputs.

### Analysis (`tg_model.analysis`)

- Use **`sweep`**, **`compare_variants`**, **`dependency_impact`** as **tools** over existing `ConfiguredModel` / `DependencyGraph` / `RunResult` instances. New analysis is usually **new functions** in this package or in your product code, not a plugin API.

## What is not a stable extension API

- **Internal graph construction** (`graph_compiler`, dependency node kinds) — treat as library internals unless you are contributing to `tg_model`.
- **Private helpers** (`_*` modules, ad hoc compiler passes) — may change without notice.
- **Subclassing** `Evaluator`, `ConfiguredModel`, or `DependencyGraph` — not supported; open an issue or PR if you need a seam.

## Practical workflow

1. Model your domain with **`System` / `Part` / `RequirementBlock`** and `define`.
2. For tool-backed values, **`ExternalComputeBinding`** + **`validate_graph`** when possible.
3. Add **tests** under `tests/unit/` or `tests/integration/` that mirror your usage (see {doc}`testing`).
4. If you need behavior that cannot be expressed with declarations and external compute, **document the gap** and consider a focused PR to `tg_model` rather than monkey-patching.

## References

- {doc}`architecture`
- {doc}`../drafts/execution_pipeline`
- API: {doc}`../api/index`
