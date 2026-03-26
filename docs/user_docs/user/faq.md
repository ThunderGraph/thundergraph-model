# FAQ

## Why do I need `RunContext` for each evaluation?

`ConfiguredModel` is frozen topology. `RunContext` stores per-run mutable values and results.
Use a fresh context per run.

## Why are inputs bound by stable id?

Stable ids are deterministic and unambiguous for a configured topology.
You can resolve them from slots (for example `cm.root.some_param.stable_id`).

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

Compilation only builds topology; it does not prove inputs, units, or external bindings are coherent. Call `validate_graph(graph, configured_model=cm)` after `compile_graph` and inspect `ValidationResult.failures` before evaluating. For requirement-heavy models, use `summarize_requirement_satisfaction(result)` to see which acceptance rows failed rather than relying on a single boolean.

If validation passes but evaluation still fails, check missing required parameters, wrong stable ids in the `inputs` map, and external `compute` exceptions — the same `RunContext` / `RunResult` constraint rows usually point to the failing check name.
