# Quickstart (Concrete Example)

## Recommended: `instantiate` → `evaluate`

For most scripts and notebooks, configure a model, pass **slot handles** (`ValueSlot`) and **unitflow** quantities, and call **`ConfiguredModel.evaluate`**. The dependency graph **compiles lazily** on first use (cached on the `ConfiguredModel`), and each call uses a **fresh** `RunContext` unless you pass `run_context=` explicitly.

```python
from unitflow import kg
from tg_model import System
from tg_model.execution import instantiate


class PayloadSystem(System):
    @classmethod
    def define(cls, model):
        p = model.parameter("payload_kg", unit=kg, required=True)
        model.attribute("payload_with_margin_kg", unit=kg, expr=p * 1.1)
        model.constraint("payload_limit", expr=(p <= 1000 * kg))


cm = instantiate(PayloadSystem)
# Equivalent: cm = PayloadSystem.instantiate()

payload_slot = cm.root.payload_kg
result = cm.evaluate(inputs={payload_slot: 800 * kg})

print("Passed:", result.passed)
```

Static validation runs before each evaluation by default (`validate=True`). For tight loops after you have validated once, pass `validate=False` (see {doc}`faq`).

API details: {doc}`../api/api_execution` (`ConfiguredModel`, `instantiate`).

## Advanced: explicit `compile_graph` + `Evaluator`

Use the explicit pipeline when you need **async** externals (`Evaluator.evaluate_async`), custom wiring, or to step through compile/validate/evaluate separately (tools, tests, debugging). Behavior matches the façade when **inputs** are the same (keys as `stable_id` strings).

```python
from unitflow import kg
from tg_model import System
from tg_model.execution import Evaluator, RunContext, compile_graph, instantiate, validate_graph


class PayloadSystem(System):
    @classmethod
    def define(cls, model):
        p = model.parameter("payload_kg", unit=kg, required=True)
        model.attribute("payload_with_margin_kg", unit=kg, expr=p * 1.1)
        model.constraint("payload_limit", expr=(p <= 1000 * kg))


cm = instantiate(PayloadSystem)
graph, handlers = compile_graph(cm)

vr = validate_graph(graph, configured_model=cm)
assert vr.passed, vr.failures

ctx = RunContext()
evaluator = Evaluator(graph, compute_handlers=handlers)

payload_slot = cm.root.payload_kg
result = evaluator.evaluate(ctx, inputs={payload_slot.stable_id: 800 * kg})

print("Passed:", result.passed)
print(
    "Payload with margin:",
    cm.root.payload_with_margin_kg.stable_id,
    ctx.get_value(cm.root.payload_with_margin_kg.stable_id),
)
```

## What happened (both paths)

1. `define()` declared symbols (parameter, attribute, constraint).
2. `instantiate()` (or `System.instantiate()`) created one frozen configuration.
3. **Recommended path:** `evaluate()` compiles the graph on first use, optionally runs `validate_graph`, then runs the evaluator.
4. **Explicit path:** `compile_graph()` created dependency nodes and handlers; `validate_graph(..., configured_model=cm)` ran static checks; `evaluate()` ran one execution with a fresh `RunContext`.

## Next examples

- {doc}`concepts_requirements`
- {doc}`concepts_external_compute`
- {doc}`../api/api_execution`
