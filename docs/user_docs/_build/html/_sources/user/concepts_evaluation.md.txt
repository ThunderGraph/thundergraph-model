# Concept: Evaluation

`tg_model` separates **topology** (what things exist and how they relate) from
**evaluation** (running the math and checks with real quantities). Evaluation always
starts from a `ConfiguredModel` — a frozen snapshot of the instantiated topology.

---

## The two evaluation paths

```
instantiate(SystemType)
       │
       ▼
 ConfiguredModel
       │
       ├── Recommended ──► cm.evaluate(inputs={slot: qty})
       │                          │
       │                          ▼
       │                      RunResult
       │
       └── Explicit ──► compile_graph(cm) → validate_graph(...) → Evaluator.evaluate(...)
                                                                         │
                                                                         ▼
                                                                     RunResult
```

Both paths produce the same `RunResult` for the same inputs.
Use the recommended path for most work; use the explicit path when you need
async backends, direct graph inspection, or fine-grained validation control.

---

## Step 1: Instantiate

`instantiate(SystemType)` (or `SystemType.instantiate()`) compiles all declared types,
builds the instance graph, and returns a frozen `ConfiguredModel`:

```python
from tg_model.execution import instantiate

cm = instantiate(MySystem)
```

`ConfiguredModel` is **immutable** after creation. It holds:
- `.root` — the root `PartInstance`, the entry point for navigating slots
- A path registry mapping every slot to a `ValueSlot` with a stable id
- A lazy compiled graph cache (populated on first `evaluate`)

---

## Step 2 (recommended): `cm.evaluate`

Pass a dict of `{ValueSlot: unitflow.Quantity}` and receive a `RunResult`:

```python
from unitflow.catalogs.si import kg

result = cm.evaluate(inputs={
    cm.root.tank.capacity_kg: 5000 * kg,
    cm.root.tank.loaded_mass_kg: 3200 * kg,
})
```

Use slot handles (e.g. `cm.root.tank.capacity_kg`) as keys — not strings.
The facade compiles the graph on first use, validates by default, and creates
a fresh `RunContext` per call.

To skip validation after the first confirmed-valid call:

```python
result = cm.evaluate(inputs={...}, validate=False)
```

---

## Step 2 (explicit): `compile_graph` + `Evaluator`

Use the explicit pipeline for async backends, tooling integration, or custom evaluation flow:

```python
from tg_model.execution import Evaluator, RunContext, compile_graph, validate_graph

graph, handlers = compile_graph(cm)

vr = validate_graph(graph, configured_model=cm)
if not vr.passed:
    raise RuntimeError(f"Graph invalid: {vr.failures}")

ctx = RunContext()
evaluator = Evaluator(graph, compute_handlers=handlers)
result = evaluator.evaluate(ctx, inputs={
    cm.root.tank.capacity_kg.stable_id: 5000 * kg,
    cm.root.tank.loaded_mass_kg.stable_id: 3200 * kg,
})
```

In the explicit path, input keys are **stable id strings** (`.stable_id` on a `ValueSlot`).

**Async evaluation** — if you have async external compute backends:

```python
import asyncio

result = asyncio.run(evaluator.evaluate_async(ctx, inputs={...}))
```

---

## Reading RunResult

`RunResult` has three main fields:

| Field | Type | Description |
|-------|------|-------------|
| `result.passed` | `bool` | `True` iff every constraint passed. |
| `result.constraint_results` | `list[ConstraintResult]` | One row per constraint. |
| `result.outputs` | `dict[str, Quantity]` | Map of stable id → realized value. |

### Inspecting constraints

```python
for cr in result.constraint_results:
    status = "PASS" if cr.passed else "FAIL"
    print(f"[{status}] {cr.name}")
    if cr.requirement_path:
        print(f"         requirement: {cr.requirement_path}")
        print(f"         target:      {cr.allocation_target_path}")
```

`ConstraintResult` fields:

| Field | Description |
|-------|-------------|
| `cr.name` | Constraint name as declared with `model.constraint(name, ...)`. |
| `cr.passed` | Boolean result. |
| `cr.requirement_path` | Dot-path of the owning `Requirement` package, or `None` for Part constraints. |
| `cr.allocation_target_path` | Dot-path of the allocated Part, or `None`. |

### Reading output values

```python
# Via slot handle (recommended)
margin_value = result.outputs[cm.root.tank.mass_margin_kg.stable_id]

# Or directly from RunContext (explicit path only)
margin_value = ctx.get_value(cm.root.tank.mass_margin_kg.stable_id)
```

### Filtering by requirement

```python
# All failing constraint results under a specific requirement package
payload_failures = [
    cr for cr in result.constraint_results
    if not cr.passed and cr.requirement_path and "payload" in cr.requirement_path
]
```

---

## Validation

`validate_graph` runs static checks before evaluation:
- All required parameters have sources
- External compute binding routes are consistent (if the external implements `validate_binding`)
- Cycle detection in the dependency graph

With `cm.evaluate`, validation runs automatically on the first call.
Pass `validate=False` to skip it on subsequent calls in a tight loop.

---

## Multiple evaluations on one ConfiguredModel

`ConfiguredModel` is immutable and can be evaluated many times with different inputs:

```python
for payload in [1000 * kg, 2000 * kg, 3000 * kg]:
    result = cm.evaluate(inputs={cm.root.tank.loaded_mass_kg: payload}, validate=False)
    print(payload, result.passed)
```

Each call gets a fresh `RunContext`. The compiled graph is cached after the first call.

---

## Analysis utilities

For systematic multi-value evaluation, use the analysis module:

```python
from tg_model.analysis import sweep, compare_variants

# Sweep one parameter across a range of values
results = sweep(
    cm,
    param_slot=cm.root.tank.loaded_mass_kg,
    values=[1000 * kg, 2000 * kg, 3000 * kg, 4000 * kg],
)
for r in results:
    print(r.passed, r.outputs[cm.root.tank.mass_margin_kg.stable_id])
```

See {doc}`../api/api_analysis` for `sweep`, `compare_variants`, and `dependency_impact`.
