# Quickstart

## Install

Use the published library in a normal project:

```bash
uv add thundergraph-model
# or
pip install thundergraph-model
```

If you are working on the library itself from this repository:

```bash
cd thundergraph-model
uv sync --all-groups
```

## Recommended path: `instantiate` → `evaluate`

The recommended path for applications, scripts, and notebooks is:
`instantiate(SystemType)` → `cm.evaluate(inputs={slot: quantity})` → inspect `RunResult`.

The dependency graph compiles lazily on first use (cached on the `ConfiguredModel`).
Each `evaluate` call uses a fresh `RunContext` unless you pass `run_context=` explicitly.

```python
from unitflow.catalogs.si import kg
from tg_model import Part, System
from tg_model.execution import instantiate


class PayloadAnalysis(Part):
    @classmethod
    def define(cls, model):
        model.name("payload_analysis")
        payload = model.parameter("payload_kg", unit=kg)
        model.attribute("payload_with_margin_kg", unit=kg, expr=payload * 1.1)
        model.constraint("payload_within_limit", expr=payload <= 1000 * kg)


class PayloadSystem(System):
    @classmethod
    def define(cls, model):
        model.name("payload_system")
        model.composed_of("analysis", PayloadAnalysis)


cm = instantiate(PayloadSystem)

result = cm.evaluate(inputs={
    cm.root.analysis.payload_kg: 800 * kg,
})

print("Passed:", result.passed)
print("Margin value:", result.outputs[cm.root.analysis.payload_with_margin_kg.stable_id])
```

Every `define()` body must call `model.name(...)` exactly once — the compiler rejects any
class that omits it.

---

## Advanced path: explicit `compile_graph` + `Evaluator`

Use the explicit pipeline when you need async external backends
(`Evaluator.evaluate_async`), want to inspect the `DependencyGraph` directly,
or need fine-grained control over validation timing.

Behavior is identical to the facade when inputs are the same.
In the explicit path, input keys are **stable id strings** instead of slot handles.

```python
from unitflow.catalogs.si import kg
from tg_model import Part, System
from tg_model.execution import Evaluator, RunContext, compile_graph, instantiate, validate_graph


class PayloadAnalysis(Part):
    @classmethod
    def define(cls, model):
        model.name("payload_analysis")
        payload = model.parameter("payload_kg", unit=kg)
        model.attribute("payload_with_margin_kg", unit=kg, expr=payload * 1.1)
        model.constraint("payload_within_limit", expr=payload <= 1000 * kg)


class PayloadSystem(System):
    @classmethod
    def define(cls, model):
        model.name("payload_system")
        model.composed_of("analysis", PayloadAnalysis)


cm = instantiate(PayloadSystem)
graph, handlers = compile_graph(cm)

vr = validate_graph(graph, configured_model=cm)
assert vr.passed, vr.failures

ctx = RunContext()
evaluator = Evaluator(graph, compute_handlers=handlers)

result = evaluator.evaluate(ctx, inputs={
    cm.root.analysis.payload_kg.stable_id: 800 * kg,
})

print("Passed:", result.passed)
print(
    "Payload with margin:",
    ctx.get_value(cm.root.analysis.payload_with_margin_kg.stable_id),
)
```

---

## Requirements alongside a Part tree

**`Requirement`** subclasses declare executable checks just like `Part` — the same
`model.parameter` / `model.attribute` / `model.constraint` surface.
Use `model.composed_of(name, RequirementType)` to mount a requirement tree on a `System`,
then `model.allocate(req_ref, part_ref, inputs={...})` to wire scenario values in.

Each `Requirement.define()` must also call `model.doc(...)` exactly once
to declare its "shall" statement.

```python
from unitflow.catalogs.si import W
from tg_model import Part, Requirement, System
from tg_model.execution import instantiate


class PowerSupply(Part):
    @classmethod
    def define(cls, model):
        model.name("power_supply")
        model.parameter("rated_output_w", unit=W)
        model.parameter("actual_draw_w", unit=W)


class PowerBudgetReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("power_budget")
        model.doc("Actual draw shall not exceed rated outlet capacity.")
        rated = model.parameter("rated_output_w", unit=W)
        actual = model.parameter("actual_draw_w", unit=W)
        headroom = model.attribute("headroom_w", unit=W, expr=rated - actual)
        model.constraint("draw_within_budget", expr=headroom >= 0 * W)


class Rack(System):
    @classmethod
    def define(cls, model):
        model.name("rack")
        psu = model.composed_of("supply", PowerSupply)
        reqs = model.composed_of("electrical", PowerBudgetReq)
        model.allocate(reqs, psu, inputs={
            "rated_output_w": psu.rated_output_w,
            "actual_draw_w":  psu.actual_draw_w,
        })


cm = instantiate(Rack)
result = cm.evaluate(inputs={
    cm.root.supply.rated_output_w: 2000 * W,
    cm.root.supply.actual_draw_w:  1500 * W,
})
print("Passed:", result.passed)
for cr in result.constraint_results:
    print(cr.name, cr.passed, "| req:", cr.requirement_path)
```

`allocate(..., inputs={...})` maps requirement `parameter` names to Part slot refs.
The constraint result rows carry `requirement_path` and `allocation_target_path` so you
can filter results by requirement without a separate summary call.

---

## What happened (both paths)

1. `define()` declared symbols (name, parameters, attributes, constraints, composition).
2. `instantiate()` created one frozen configuration with a full path registry.
3. **Recommended path:** `evaluate()` compiles the graph on first use, validates, and returns a `RunResult`.
4. **Explicit path:** `compile_graph()` built dependency nodes and handlers; `validate_graph()` ran static checks; `Evaluator.evaluate()` ran one execution with a fresh `RunContext`.

---

## Next steps

- {doc}`end_to_end_guide` — step-by-step walkthrough building a complete system
- {doc}`concepts_parts` — Parts, composition, roll-ups
- {doc}`concepts_system` — Systems, scenario parameters, allocation wiring
- {doc}`concepts_requirements` — Requirements deep dive
- {doc}`concepts_evaluation` — Evaluation paths, RunResult, constraint filtering
- {doc}`concepts_external_compute` — External compute bindings
