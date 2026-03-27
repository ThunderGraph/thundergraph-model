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

For **requirements**, remember the two value roles: **`requirement_input`** values are **wired** from the allocated design via `allocate(..., inputs=...)`, while **`requirement_attribute`** values are **derived on the requirement** from expressions (and appear among `cm.requirement_value_slots` after `instantiate`). Both participate in the same graph as constraints.

See {doc}`../drafts/execution_pipeline` for the full pipeline (including the explicit steps). See {doc}`faq` for when to use `evaluate` vs `compile_graph` + `Evaluator`.

**Contributors and extension authors:** {doc}`../developer/architecture` and {doc}`../developer/extension_playbook` describe the same split from a library and tooling perspective.
