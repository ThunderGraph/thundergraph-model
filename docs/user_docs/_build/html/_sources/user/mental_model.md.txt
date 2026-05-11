# Mental Model

ThunderGraph has three layers:

1. Type time (`define` + compile)
2. Configuration time (`instantiate` / `System.instantiate()`)
3. Run time (evaluation — façade or explicit pipeline)

## Mini walkthrough (same symbol, three layers)

Take a parameter declared on a `System` subclass:

- **Type time:** `model.parameter("mass_kg", ...)` inside `define()` fixes the *kind* of slot and its unit for every instance of that system type.
- **Configuration time:** `instantiate(MySystem)` (or `MySystem.instantiate()`) materializes a `ConfiguredModel`: concrete parts, stable ids, and frozen wiring (what connects to what).
- **Run time:** You supply **inputs** for one scenario. The **default** path is **`ConfiguredModel.evaluate`** with keys that are **handles** (`ValueSlot`) on that model (or, for interop, the slot's `stable_id` string). The **advanced** path binds the same values with `Evaluator.evaluate(..., inputs={stable_id: Quantity, ...})` and a `RunContext` you create yourself.

Between configuration and run, `compile_graph` builds the dependency graph (called explicitly in the advanced path, or **lazily inside** `ConfiguredModel.evaluate` on the default path). `validate_graph(..., configured_model=cm)` is the cheap sanity check before evaluation — invoked automatically by `evaluate` by default, or by you after `compile_graph` in the explicit pipeline.

For **requirements**, each `Requirement` subclass is its **own namespace**: it owns **`parameter`**, **`attribute`**, and **`constraint`** declarations — the same authoring surface as `Part`, plus a required `model.doc(...)` "shall" statement. Mount requirement trees on a `System` with `model.composed_of(name, RequirementType)` and wire values in with `model.allocate(req_ref, part_ref, inputs={...})`. After `instantiate`, those slots are accessible as dot paths (e.g. `cm.root.<package>.<slot>`) and constraints appear in `RunResult.constraint_results`. Use `model.citation` and `model.references` for traceability to external standards.

For **coupled equations** (e.g. solving for an unknown given a set of equations and knowns), use `model.solve_group(name, equations=[...], unknowns=[...], givens=[...])` inside any `Part.define()`. See {doc}`concepts_parts`.

That layout lines up with a **graph-shaped product model** where values are first-class nodes (for example Neo4j-style "attributes as nodes") without implying any particular persistence schema in this library.

See {doc}`faq` for when to use `evaluate` vs `compile_graph` + `Evaluator`.

**Contributors and extension authors:** {doc}`../developer/architecture` and {doc}`../developer/extension_playbook` describe the same split from a library and tooling perspective.
