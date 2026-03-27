# Extension playbook

Where ThunderGraph Model is designed to be extended safely—and where you should **not** hook in without treating the change as a library contribution.

## Supported extension surfaces

### Authoring types (`tg_model.model`)

- **`System`**, **`Part`**, **`RequirementBlock`** — override `define(cls, model)` (and `compile()` only where the framework’s contract requires it). This is the primary **domain** extension point: new parts, parameters, constraints, requirement blocks, **`requirement_input`** / **`requirement_attribute`** / **`requirement_accept_expr`**, and allocation wiring.
- **`ModelDefinitionContext`** — you do not subclass this; you call its methods **from** `define` on your element types. Public methods are the vocabulary for declarations.
- **Refs** (`AttributeRef`, `PartRef`, …) — returned by `model` APIs; you **use** them in expressions and `allocate`, not subclass them.

### Execution (`tg_model.execution`)

**Application code (default):** Prefer **`instantiate(SomeSystem)`** or **`SomeSystem.instantiate()`** to get a **`ConfiguredModel`**, then **`ConfiguredModel.evaluate(inputs={slot: Quantity, …})`**. Compilation is **lazy** (cached on the model), validation runs per the **`evaluate`** policy (default: on), and each call uses a **fresh** **`RunContext`** unless you pass **`run_context=`** for tests or custom runners. Input keys should be **`ValueSlot`** handles from **that** model (or the slot’s **`stable_id`** string for scripts).

**Extensions, tools, async, and debugging (explicit pipeline):** Call **`compile_graph`**, **`validate_graph`**, **`Evaluator`**, and **`RunContext`** directly when you need **`Evaluator.evaluate_async`**, to **reuse** one context across steps, to **inspect** the graph or handlers, or to mirror low-level behavior in tests. Do **not** fork the evaluator unless you are fixing a bug in the library.

**`RunContext`** remains the per-run mutable state carrier; the façade builds one for you on each **`evaluate`** by default.

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
2. Run scenarios with **`ConfiguredModel.evaluate`** in product code and notebooks unless you need the explicit pipeline (see **Execution** above).
3. For tool-backed values, **`ExternalComputeBinding`** + **`validate_graph`** when possible (the façade runs validation before evaluation by default; explicit callers run **`validate_graph`** after **`compile_graph`**).
4. Add **tests** under `tests/unit/` or `tests/integration/` that mirror your usage (see {doc}`testing`).
5. If you need behavior that cannot be expressed with declarations and external compute, **document the gap** and consider a focused PR to `tg_model` rather than monkey-patching.

## References

- End-user narrative: {doc}`../user/quickstart` (recommended **`evaluate`** path vs explicit pipeline).
- {doc}`architecture`
- {doc}`../drafts/execution_pipeline`
- API: {doc}`../api/index`
