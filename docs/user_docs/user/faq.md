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

## When should I use `Requirement` (composable requirement package)?

Use **`Requirement`** when requirements need **structure**, **ownership**, and **local** acceptance logic—same idea as using **`Part`** for structure, but for requirement namespaces.

Register packages with **`model.requirement_package(name, type)`**.

> **Default:** Inside `Requirement.define()`, use **`model.parameter`**, **`model.attribute`**, and **`model.constraint`** at package scope — the same surface you use on `Part` / `System`. **This is the standard, recommended pattern for all new requirement packages.** Use `model.requirement(id, text)` for leaf traceability statements, and `model.allocate` / `model.references` for structural edges and citations.
>
> **Advanced (rare):** `requirement_input`, `requirement_attribute`, and `requirement_accept_expr` are low-level helpers for **INCOSE-style leaf acceptance rows** only. Use them when you need `summarize_requirement_satisfaction` per-requirement pass/fail rows wired through `allocate(..., inputs=...)`. **Do not use them as the default pattern.** If your check can be a package-level `constraint`, use that instead. See {doc}`concepts_requirements`.

### Upgrading from thundergraph-model before 0.2.0

**0.2.0** removed the temporary compatibility names **`RequirementBlock`**, **`RequirementBlockRef`**, and **`ModelDefinitionContext.requirement_block(...)`**. Use **`Requirement`**, **`RequirementRef`**, and **`requirement_package`** instead. **Internal** compiled node **`kind`** is still the string **`"requirement_block"`** — that is not a Python API and did not change.

## What is the difference between `requirement_input` and `requirement_attribute`?

> **Note:** These are **advanced, rare helpers** for leaf-level INCOSE acceptance rows.  For new requirement packages, **use package-level `parameter` / `attribute` / `constraint` instead** — see {doc}`concepts_requirements`.

**`requirement_input`** declares **slots that you map** from the design at allocation time (`allocate(..., inputs={name: AttributeRef, ...})`).

**`requirement_attribute`** declares **values computed on the requirement** from an `expr=` (and `unit=`). Names must not overlap with inputs on the same requirement; declare attributes **before** `requirement_accept_expr`. If you use **`requirement_attribute`**, that requirement may only have **one** `allocate(...)` edge.

## Where do I start if I am new?

- {doc}`quickstart`
- {doc}`mental_model`
- {doc}`../api/index`

## The graph compiled but `evaluate` failed or results look wrong

Compilation only builds topology; it does not prove inputs, units, or external bindings are coherent. With the **explicit** pipeline, call `validate_graph(graph, configured_model=cm)` after `compile_graph` and inspect `ValidationResult.failures` before evaluating. With **`ConfiguredModel.evaluate`**, validation runs automatically unless you pass `validate=False`.

For requirement-heavy models, use `summarize_requirement_satisfaction(result)` to see which acceptance rows failed rather than relying on a single boolean.

If validation passes but evaluation still fails, check missing required parameters, wrong keys in the `inputs` map, and external `compute` exceptions — the same `RunResult` constraint rows usually point to the failing check name.
