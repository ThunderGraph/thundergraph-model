# FAQ

## Where do I start if I am new?

- {doc}`end_to_end_guide` — the recommended starting point, a full walkthrough
- {doc}`quickstart` — shorter examples for each major path
- {doc}`mental_model` — the three-layer execution model
- {doc}`../api/index` — API reference

---

## When should I use `ConfiguredModel.evaluate` vs `compile_graph` + `Evaluator`?

**Default:** call `ConfiguredModel.evaluate` after `instantiate`. Pass **slot handles**
(`ValueSlot` objects like `cm.root.some_param`) and unitflow quantities. The library
compiles the graph on first use, validates by default, and returns a `RunResult`.

**Use the explicit pipeline** when you need:

- `Evaluator.evaluate_async` (async external compute backends)
- direct inspection or reuse of the `DependencyGraph`
- control over validation timing (e.g. validate once, then loop with `evaluate(..., validate=False)`)
- integration with tooling that constructs `Evaluator` and `RunContext` externally

Both paths share the same compiled graph cache on the `ConfiguredModel` when you mix them.

See {doc}`quickstart` and {doc}`concepts_evaluation`.

---

## Why do I need `RunContext`?

`ConfiguredModel` is frozen topology. `RunContext` stores per-run mutable values and results.

- **Default `evaluate()` path:** you do not create a `RunContext`; the method creates a
  fresh one per call unless you pass `run_context=` explicitly.
- **Explicit `Evaluator` path:** create `RunContext()` and pass it to `Evaluator.evaluate`
  or `evaluate_async`.

---

## Why are inputs bound by stable id in the explicit pipeline?

The evaluator's wire format is keyed by **stable slot ids** (strings). Stable ids are
deterministic and unambiguous for a configured topology.

On the **facade**, prefer **slot handles** as keys (`cm.root.some_param`) — same binding,
less error-prone. String keys are allowed when they refer to a parameter/attribute slot's
`stable_id`.

---

## I changed code in a notebook and behavior is weird.

If declarations changed, restart the kernel and re-run compile/instantiate cells.
Old class artifacts may still be cached.

---

## When should I use `Requirement`?

Use `Requirement` whenever requirements need **structure**, **local acceptance logic**,
and **traceability** to a "shall" statement.

Every `Requirement` class must call `model.name(...)` and `model.doc(...)` exactly once.
Inside `define()`, use the same authoring surface as `Part`:
`model.parameter`, `model.attribute`, `model.constraint`, and `model.composed_of`.

Mount the requirement tree on a `System` with `model.composed_of(name, RequirementType)`,
then wire values in with `model.allocate(req_ref, part_ref, inputs={...})`.

See {doc}`concepts_requirements` for the full pattern.

---

## How do I split requirements into a hierarchy?

Create a separate `Requirement` subclass for each coherent group of checks, then compose
them with `model.composed_of`:

```python
class ThermalReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("thermal_req")
        model.doc("Thermal envelope shall not be exceeded.")
        temp = model.parameter("peak_temp_c", unit=degC)
        limit = model.parameter("temp_limit_c", unit=degC)
        model.constraint("temp_within_limit", expr=temp <= limit)


class L1SafetyReqs(Requirement):
    @classmethod
    def define(cls, model):
        model.name("l1_safety_reqs")
        model.doc("Level-1 safety requirements.")
        model.composed_of("thermal", ThermalReq)
        # ...more children...
```

There is no limit to nesting depth.

---

## When does `model.composed_of` return a `PartRef` vs `RequirementRef`?

`model.composed_of(name, ChildType)` dispatches on the type of `ChildType`:

- If `ChildType` is a `Part` subclass → returns a `PartRef`
- If `ChildType` is a `Requirement` subclass → returns a `RequirementRef`
- Anything else → `ModelDefinitionError`

Use the returned ref to navigate children in `allocate` calls:
`model.allocate(reqs.child_name, part_ref, inputs={...})`.

---

## The graph compiled but `evaluate` failed or results look wrong.

Compilation only builds topology; it does not prove inputs, units, or external bindings
are coherent. With the explicit pipeline, call `validate_graph(graph, configured_model=cm)`
after `compile_graph` and inspect `ValidationResult.failures` before evaluating.
With `ConfiguredModel.evaluate`, validation runs automatically unless you pass `validate=False`.

If validation passes but evaluation still fails, check:

- missing required parameters (not bound in `inputs=`)
- wrong keys in the `inputs` map (use slot handles on the facade, stable id strings on the explicit path)
- external `compute` exceptions — the failing check name in `RunResult.constraint_results` usually points to the cause

---

## How do I filter constraint results by requirement?

`ConstraintResult` rows carry `requirement_path` (dot-separated path string of the
requirement package) and `allocation_target_path` (path of the allocated Part) when
the constraint belongs to an allocated requirement package.

```python
# All failing constraints from a specific requirement subtree
failures = [
    cr for cr in result.constraint_results
    if not cr.passed and cr.requirement_path and "l1_safety" in cr.requirement_path
]
```

---

## The graph compiled but `evaluate` is very slow.

For tight evaluation loops after you have validated once, pass `validate=False` to skip
the static checks:

```python
result = cm.evaluate(inputs={...}, validate=False)
```

---

## How do I run a parameter sweep?

Use `tg_model.analysis.sweep`. All arguments are keyword-only; compile the graph
first and access results via `SweepRecord.result`:

```python
from tg_model.analysis import sweep
from tg_model.execution import compile_graph

graph, handlers = compile_graph(cm)

records = sweep(
    graph=graph,
    handlers=handlers,
    parameter_values={
        cm.root.analysis.payload_kg: [500 * kg, 750 * kg, 1000 * kg],
    },
    configured_model=cm,
)
for rec in records:
    print(rec.result.passed, rec.result.outputs[...])
```

See {doc}`../api/api_analysis` for the full signature including `prune_to_slots`, `collect`, and `sink`.
