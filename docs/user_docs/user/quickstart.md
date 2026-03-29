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

## Composable requirements next to `Part`

Systems are mostly **`Part`** trees with values on the root or parts. **Composable requirement packages** sit beside that structure: you define a subclass of **`Requirement`**, register it with **`model.requirement_package(name, YourRequirementType)`**, and bind leaf requirements to a part with **`model.allocate(...)`**. **`RequirementRef`** dot access (e.g. `reqs.power_budget`) matches how you navigate **`PartRef`**s.

The example below adds a **package-level parameter** (`max_output_w`) that behaves like a root/part parameter but lives under the package namespace on the configured model (`cm.root.electrical.max_output_w`). Evaluation uses the same recommended path: **`instantiate`** → **`evaluate`** with **`ValueSlot`** keys.

```python
from unitflow import W
from tg_model import Requirement, System
from tg_model.execution import instantiate


class PowerReqs(Requirement):
    @classmethod
    def define(cls, model):
        threshold = model.parameter("max_output_w", unit=W, required=True)
        r = model.requirement("power_budget", "Draw shall not exceed outlet budget.")
        draw = model.requirement_input(r, "draw_w", unit=W)
        model.requirement_accept_expr(r, expr=(draw <= threshold))


class Rack(System):
    @classmethod
    def define(cls, model):
        root = model.part()
        outlet = model.attribute("outlet_w", unit=W, expr=1500 * W)
        reqs = model.requirement_package("electrical", PowerReqs)
        model.allocate(reqs.power_budget, root, inputs={"draw_w": outlet})


cm = instantiate(Rack)
threshold_slot = cm.root.electrical.max_output_w
result = cm.evaluate(inputs={threshold_slot: 2000 * W})
print("Passed:", result.passed)
```

**Sidebar: leaf `model.requirement(...)` vs composable `Requirement`**

- **`model.requirement("id", "text")`** (only valid inside **`Requirement.define()`**) declares a **single** requirement node: you attach **`requirement_input`** / **`requirement_attribute`** and **`requirement_accept_expr`** to that ref. It is **not** a subclassable package by itself.
- **`class MyPackage(Requirement)`** defines a **composable package** type (namespace for parameters, attributes, constraints, nested **`requirement_package`** entries, and leaf **`requirement`** declarations). You **mount** it on a **`System`** / **`Part`** with **`requirement_package`**.

Details: {doc}`concepts_requirements`, {doc}`faq`.

## What happened (both paths)

1. `define()` declared symbols (parameter, attribute, constraint).
2. `instantiate()` (or `System.instantiate()`) created one frozen configuration.
3. **Recommended path:** `evaluate()` compiles the graph on first use, optionally runs `validate_graph`, then runs the evaluator.
4. **Explicit path:** `compile_graph()` created dependency nodes and handlers; `validate_graph(..., configured_model=cm)` ran static checks; `evaluate()` ran one execution with a fresh `RunContext`.

## Next examples

- {doc}`concepts_requirements`
- {doc}`concepts_external_compute`
- {doc}`../api/api_execution`
