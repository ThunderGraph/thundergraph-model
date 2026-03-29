# Mental Model

ThunderGraph has three layers:

1. Type time (`define` + compile)
2. Configuration time (`instantiate` / `System.instantiate()`)
3. Run time (evaluation — façade or explicit pipeline)

## Mini walkthrough (same symbol, three layers)

Take a parameter declared on a `System` subclass:

- **Type time:** `model.parameter("mass_kg", ...)` inside `define()` fixes the *kind* of slot and its unit for every instance of that system type.
- **Configuration time:** `instantiate(MySystem)` (or `MySystem.instantiate()`) materializes a `ConfiguredModel`: concrete parts, stable ids, and frozen wiring (what connects to what).
- **Run time:** You supply **inputs** for one scenario. The **default** path is **`ConfiguredModel.evaluate`** with keys that are **handles** (`ValueSlot`) on that model (or, for interop, the slot’s `stable_id` string). The **advanced** path binds the same values with `Evaluator.evaluate(..., inputs={stable_id: Quantity, ...})` and a `RunContext` you create yourself.

Between configuration and run, `compile_graph` builds the dependency graph (called explicitly in the advanced path, or **lazily inside** `ConfiguredModel.evaluate` on the default path). `validate_graph(..., configured_model=cm)` is the cheap sanity check before evaluation — invoked automatically by `evaluate` by default, or by you after `compile_graph` in the explicit pipeline.

For **requirements**, treat each registered **`requirement_package`** as its **own namespace**: besides leaf **`requirement`** declarations, the package may own **package-level** **`parameter`**, **`attribute`**, and **`constraint`** declarations (same authoring methods as on **`System`** / **`Part`**, scoped to the package). After **`instantiate`**, those slots show up under the configured part as dot paths (for example **`cm.root.<package>.<slot>`**), next to **`requirement_input`** / **`requirement_attribute`** wiring and acceptance. **`requirement_input`** values are **wired** from the allocated design via **`allocate(..., inputs=...)`**; **`requirement_attribute`** values are **derived on the leaf requirement** from expressions and appear among **`cm.requirement_value_slots`** where applicable. All of these participate in the same evaluation graph as ordinary constraints.

That layout lines up with a **graph-shaped product model** where values are first-class nodes (for example Neo4j-style “attributes as nodes”) without implying any particular persistence schema in this library.

See {doc}`../drafts/execution_pipeline` for the full pipeline (including the explicit steps). See {doc}`faq` for when to use `evaluate` vs `compile_graph` + `Evaluator`.

**Contributors and extension authors:** {doc}`../developer/architecture` and {doc}`../developer/extension_playbook` describe the same split from a library and tooling perspective.
