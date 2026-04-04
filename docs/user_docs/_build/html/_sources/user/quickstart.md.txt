# Quickstart (Concrete Example)

## Install

Use the published library in a normal project:

```bash
uv add thundergraph-model
# or
pip install thundergraph-model
```

If you are working on the library itself from this repository, use the development setup:

```bash
cd thundergraph-model
uv sync --all-groups
```

## Recommended: `instantiate` → `evaluate`

For most scripts and notebooks, configure a model, pass **slot handles** (`ValueSlot`) and **unitflow** quantities, and call **`ConfiguredModel.evaluate`**. The dependency graph **compiles lazily** on first use (cached on the `ConfiguredModel`), and each call uses a **fresh** `RunContext` unless you pass `run_context=` explicitly.

```python
from unitflow import kg
from tg_model import Part, System
from tg_model.execution import instantiate


class PayloadAnalysis(Part):
    @classmethod
    def define(cls, model):
        payload = model.parameter_ref(PayloadSystem, "payload_kg")
        model.attribute("payload_with_margin_kg", unit=kg, expr=payload * 1.1)
        model.constraint("payload_limit", expr=(payload <= 1000 * kg))


class PayloadSystem(System):
    @classmethod
    def define(cls, model):
        model.parameter("payload_kg", unit=kg, required=True)
        model.part("analysis", PayloadAnalysis)


cm = instantiate(PayloadSystem)
# Equivalent: cm = PayloadSystem.instantiate()

payload_slot = cm.root.payload_kg
result = cm.evaluate(inputs={payload_slot: 800 * kg})

print("Passed:", result.passed)
print("Margin payload:", result.outputs[cm.root.analysis.payload_with_margin_kg.stable_id])
```

`System.define()` should stay structural: compose parts and declare top-level input parameters there, but put derived values and executable checks on owned `Part` instances or requirement packages.

Static validation runs before each evaluation by default (`validate=True`). For tight loops after you have validated once, pass `validate=False` (see {doc}`faq`).

API details: {doc}`../api/api_execution` (`ConfiguredModel`, `instantiate`).

## Advanced: explicit `compile_graph` + `Evaluator`

Use the explicit pipeline when you need **async** externals (`Evaluator.evaluate_async`), custom wiring, or to step through compile/validate/evaluate separately (tools, tests, debugging). Behavior matches the façade when **inputs** are the same (keys as `stable_id` strings).

```python
from unitflow import kg
from tg_model import Part, System
from tg_model.execution import Evaluator, RunContext, compile_graph, instantiate, validate_graph


class PayloadAnalysis(Part):
    @classmethod
    def define(cls, model):
        payload = model.parameter_ref(PayloadSystem, "payload_kg")
        model.attribute("payload_with_margin_kg", unit=kg, expr=payload * 1.1)
        model.constraint("payload_limit", expr=(payload <= 1000 * kg))


class PayloadSystem(System):
    @classmethod
    def define(cls, model):
        model.parameter("payload_kg", unit=kg, required=True)
        model.part("analysis", PayloadAnalysis)


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
    cm.root.analysis.payload_with_margin_kg.stable_id,
    ctx.get_value(cm.root.analysis.payload_with_margin_kg.stable_id),
)
```

## Composable requirements next to `Part`

Systems are mostly **`Part`** trees with top-level inputs on the root and executable value/check logic on owned parts. **Composable requirement packages** sit beside that structure: subclass **`Requirement`**, register with **`model.requirement_package(name, Type)`**, and navigate with **`RequirementRef`** dot access.

> **Default pattern: use `parameter` / `attribute` / `constraint` on the package** — exactly like a `Part`.  This is the recommended, current API for executable checks on requirements.  See {doc}`concepts_requirements` for the full explanation.

```python
from unitflow import W
from tg_model import Requirement, System
from tg_model.execution import instantiate


class PowerReqs(Requirement):
    @classmethod
    def define(cls, model):
        max_draw = model.parameter("max_draw_w", unit=W, required=True)
        actual_draw = model.parameter("actual_draw_w", unit=W, required=True)
        headroom = model.attribute("headroom_w", unit=W, expr=max_draw - actual_draw)
        model.constraint("draw_within_budget", expr=headroom >= 0 * W)

        model.requirement(
            "power_budget",
            "Draw shall not exceed outlet budget (verification by analysis).",
        )


class Rack(System):
    @classmethod
    def define(cls, model):
        reqs = model.requirement_package("electrical", PowerReqs)
        model.allocate_to_system(reqs.power_budget)


cm = instantiate(Rack)
result = cm.evaluate(inputs={
    cm.root.electrical.max_draw_w: 2000 * W,
    cm.root.electrical.actual_draw_w: 1500 * W,
})
print("Passed:", result.passed)
```

**Sidebar: leaf `model.requirement(...)` vs composable `Requirement`**

- **`class MyPackage(Requirement)`** defines a **composable package** type (namespace for `parameter`, `attribute`, `constraint`, nested `requirement_package`, and leaf `requirement` declarations). Mount it with `requirement_package`.
- **`model.requirement("id", "text")`** declares a **single** requirement statement (traceability text). Use `allocate` and `references` for structural edges.
- **Root-scope traceability:** use **`model.allocate_to_system(requirement)`** when a requirement applies to the structural root rather than a named child part.
- **Advanced (rare):** `requirement_input`, `requirement_attribute`, and `requirement_accept_expr` are low-level helpers for leaf-level INCOSE acceptance rows — **do not use them as the default pattern**. See {doc}`concepts_requirements` for when they are appropriate.

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
