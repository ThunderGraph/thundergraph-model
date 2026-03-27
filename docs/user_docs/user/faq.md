# FAQ

## When should I use `ConfiguredModel.evaluate` vs `compile_graph` + `Evaluator`?

**Default:** Call **`ConfiguredModel.evaluate`** on the configured model after `instantiate`. You pass **handles** (`ValueSlot`) and quantities; the library compiles the graph on first use, validates by default, and returns a **`RunResult`**. That is the path we recommend for applications, notebooks, and most scripts.

**Use the explicit pipeline** (`compile_graph` → `validate_graph` → `Evaluator` + `RunContext`) when you need:

- `Evaluator.evaluate_async` (async external backends)
- to **inspect or reuse** the `DependencyGraph` or handler map
- to **control validation timing** (e.g. validate once, then many evaluations with `evaluate(..., validate=False)` is also available on the façade)
- to integrate with tooling that already assembles `Evaluator` and `RunContext`

Both paths share the **same** compiled graph cache on the `ConfiguredModel` when you mix them on one instance.

See {doc}`quickstart` and {doc}`../api/api_execution`.

## Why do I need `RunContext`?

`ConfiguredModel` is frozen topology. `RunContext` stores per-run mutable values and results.

- **Default `evaluate()` path:** you usually **do not** create a `RunContext`; the method uses a fresh one per call unless you pass `run_context=` for advanced testing.
- **Explicit `Evaluator` path:** you create `RunContext()` and pass it to `Evaluator.evaluate` / `evaluate_async`.

## Why are inputs bound by stable id in the explicit pipeline?

The evaluator’s wire format is keyed by **stable slot ids** (strings). Stable ids are deterministic and unambiguous for a configured topology.

On the **facade**, prefer **slot handles** as keys (`cm.root.some_param`) instead of raw strings — same binding, less error-prone. String keys are allowed when they refer to a **parameter/attribute** slot’s `stable_id` (not arbitrary part ids).

## I changed code in a notebook and behavior is weird.

If declarations changed, restart kernel and re-run compile/instantiate cells.
Old class artifacts may still be cached.

## When should I use `RequirementBlock`?

Use it when requirements need structure, ownership, and local acceptance logic.
Then bind model values via `allocate(..., inputs=...)` for **`requirement_input`** slots, and use **`requirement_attribute`** when the requirement needs its **own** derived quantities (sums, margins, intermediate checks) before acceptance. See {doc}`concepts_requirements`.

## What is the difference between `requirement_input` and `requirement_attribute`?

**`requirement_input`** declares **slots that you map** from the design at allocation time (`allocate(..., inputs={name: AttributeRef, ...})`). They are the usual way to feed scenario or part values into a requirement expression without globals.

**`requirement_attribute`** declares **values computed on the requirement** from an `expr=` (and `unit=`). Use them when acceptance depends on **intermediate math** that should live on the requirement, not on a part. Names must not overlap with inputs on the same requirement; declare attributes **before** `requirement_accept_expr`. If you use **`requirement_attribute`**, that requirement may only have **one** `allocate(...)` edge in the configured model (see {doc}`concepts_requirements`).

## Where do I start if I am new?

- {doc}`quickstart`
- {doc}`mental_model`
- {doc}`../api/index`

## The graph compiled but `evaluate` failed or results look wrong

Compilation only builds topology; it does not prove inputs, units, or external bindings are coherent. With the **explicit** pipeline, call `validate_graph(graph, configured_model=cm)` after `compile_graph` and inspect `ValidationResult.failures` before evaluating. With **`ConfiguredModel.evaluate`**, validation runs automatically unless you pass `validate=False`.

For requirement-heavy models, use `summarize_requirement_satisfaction(result)` to see which acceptance rows failed rather than relying on a single boolean.

If validation passes but evaluation still fails, check missing required parameters, wrong keys in the `inputs` map, and external `compute` exceptions — the same `RunResult` constraint rows usually point to the failing check name.
