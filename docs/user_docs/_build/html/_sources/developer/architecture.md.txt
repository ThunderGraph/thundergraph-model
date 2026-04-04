# Developer architecture

## Subsystems

The core engine lives in:

- `tg_model.model` — authoring and compile-time types (`define`, `ModelDefinitionContext`, refs, compile cache).
- `tg_model.execution` — `ConfiguredModel`, dependency graph, validation, evaluation, behavior dispatch, requirements reporting.
- `tg_model.integrations` — external compute protocols and bindings.
- `tg_model.analysis` — sweeps, variant comparison, value-graph impact (multi-run tooling on top of execution outputs).

Canonical narrative flow (with more detail): {doc}`../drafts/execution_pipeline`. Application-oriented summary: {doc}`../user/quickstart`.

## Pipeline sequences

1. **Compile types** — `Element.compile()` / `define` fills a `ModelDefinitionContext`; output is a **class-level** compiled artifact (not a runnable graph).
2. **Instantiate** — `instantiate(SomeSystem)` or `SomeSystem.instantiate()` → `ConfiguredModel`: **frozen** topology, stable ids, registries.

**Authoring rule:** the configured root `System` is structural composition plus top-level inputs. Derived values, constraints, roll-ups, solve groups, and external-compute bindings belong on owned `Part` instances or requirement packages.

**Default path (application authors):**

3. **`ConfiguredModel.evaluate`** — On first call, **compiles** the graph (lazy, cached on the instance — same cache as explicit `compile_graph`), optionally runs **`validate_graph`**, then **`Evaluator.evaluate`** with a **fresh** `RunContext`. Inputs are keyed by **`ValueSlot`** handles (or slot **`stable_id`** strings).

**Explicit path (extensions, tooling, async, debugging):**

3. **Compile graph** — `compile_graph(cm)` → `DependencyGraph` + handlers (evaluation order, compute nodes); populates the same instance cache as step 3 above when used on the same `ConfiguredModel`.
4. **Validate (recommended)** — `validate_graph(graph, configured_model=cm)` before expensive or remote evaluation.
5. **Evaluate** — fresh `RunContext` per run; `Evaluator.evaluate` / `evaluate_async`; `inputs` keyed by **`stable_id`** strings.

Behavior APIs (`dispatch_event`, …) read/write **run** state and traces; they do **not** change `ConfiguredModel` topology.

## Invariants (mental checklist for contributors)

- **Topology is frozen** after `instantiate`; graphs are built **from** that topology, not mutated structurally during evaluation.
- **Stable ids** identify value slots across compile and run. The **facade** accepts **`ValueSlot`** keys (normalized internally); the **explicit** `Evaluator` API uses **`stable_id`** strings in the `inputs` mapping.
- **One compiled graph per `ConfiguredModel`** — lazy **`evaluate`** and explicit **`compile_graph`** share the same cached `(DependencyGraph, handlers)` after the first successful compile on that instance.
- **`RunContext` is per run** — the façade creates a new context each **`evaluate`** unless **`run_context=`** is passed; do not reuse contexts across parallel evaluations without a clear concurrency story (see **`ConfiguredModel`** docstring on threading).
- **Requirement acceptance** is part of the same constraint/evaluation pass when requirements are allocated and wired with inputs.

## Composable requirement packages

**Authoring:** A subclass of **`Requirement`** is a **namespace** mounted with **`requirement_package`** (see {doc}`extension_playbook`). **Leaf** statements use **`model.requirement`** inside that **`define()`**; package-level **`parameter`** / **`attribute`** / **`constraint`** live alongside them and participate in the same compile → instantiate → graph pipeline as part values.

**Runtime:** After **`instantiate`**, **`RequirementPackageInstance`** hangs under the owning **`PartInstance`** (usually the configured root). **`ConfiguredModel.evaluate`** and **`compile_graph`** share one graph cache; **package** value slots are valid **`ValueSlot`** keys for the façade the same way as root parameters.

**Artifacts:** The compiler still labels composable requirement nodes with internal **`kind`** **`"requirement_block"`**; tests and tooling should not couple user-facing names to that string without reason.

End-user concepts: {doc}`../user/concepts_requirements`.

## Extension points

See {doc}`extension_playbook` for supported seams (authoring types, external compute, analysis usage) versus internals.
