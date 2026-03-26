# Quickstart (Concrete Example)

This example creates a tiny model with one parameter, one derived attribute,
one constraint, then runs evaluation.

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

# Bind by stable slot id.
payload_slot = cm.root.payload_kg
result = evaluator.evaluate(ctx, inputs={payload_slot.stable_id: 800 * kg})

print("Passed:", result.passed)
print("Payload with margin:", cm.root.payload_with_margin_kg.stable_id, ctx.get_value(cm.root.payload_with_margin_kg.stable_id))
```

## What happened

1. `define()` declared symbols (parameter, attribute, constraint).
2. `instantiate()` created one frozen configuration.
3. `compile_graph()` created dependency nodes and handlers.
4. `validate_graph(..., configured_model=cm)` ran static checks (cycles, orphans, external bindings when applicable) before any evaluation.
5. `evaluate()` ran one execution with a fresh `RunContext`.

## Next examples

- {doc}`concepts_requirements`
- {doc}`concepts_external_compute`
- {doc}`../api/api_execution`
