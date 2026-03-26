# Mental Model

ThunderGraph has three layers:

1. Type time (`define` + compile)
2. Configuration time (`instantiate`)
3. Run time (`Evaluator` + `RunContext`)

## Mini walkthrough (same symbol, three layers)

Take a parameter declared on a `System` subclass:

- **Type time:** `model.parameter("mass_kg", ...)` inside `define()` fixes the *kind* of slot and its unit for every instance of that system type.
- **Configuration time:** `instantiate(MySystem)` materializes a `ConfiguredModel`: concrete parts, stable ids, and frozen wiring (what connects to what).
- **Run time:** You pass **inputs** keyed by stable id (`cm.root.mass_kg.stable_id`) into `Evaluator.evaluate`; `RunContext` holds the numbers for that run only.

Between configuration and run, `compile_graph` builds the dependency graph, and `validate_graph(..., configured_model=cm)` is the cheap sanity check before you spend time evaluating.

For **requirements**, remember the two value roles: **`requirement_input`** values are **wired** from the allocated design via `allocate(..., inputs=...)`, while **`requirement_attribute`** values are **derived on the requirement** from expressions (and appear among `cm.requirement_value_slots` after `instantiate`). Both participate in the same graph as constraints.

See {doc}`../drafts/execution_pipeline` for the canonical flow.
