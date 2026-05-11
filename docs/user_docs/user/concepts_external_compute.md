# Concept: External Compute (Concrete Binding)

Use external compute when a value comes from another tool or model.

## Example

```python
from unitflow import Quantity
from unitflow.catalogs.si import kg
from tg_model import Part, System
from tg_model.execution import Evaluator, RunContext, compile_graph, instantiate
from tg_model.integrations import ExternalComputeBinding, ExternalComputeResult


class MassTool:
    @property
    def name(self):
        return "mass_tool"

    def compute(self, inputs):
        # inputs values are unitflow Quantity objects
        dry = inputs["dry"]
        payload = inputs["payload"]
        return ExternalComputeResult(value=dry + payload, provenance={"tool": self.name})


class VehicleMassAnalysis(Part):
    @classmethod
    def define(cls, model):
        model.name("vehicle_mass_analysis")
        dry = model.parameter_ref(Vehicle, "dry_kg")
        payload = model.parameter_ref(Vehicle, "payload_kg")

        total = model.attribute(
            "total_kg",
            unit=kg,
            computed_by=ExternalComputeBinding(
                external=MassTool(),
                inputs={"dry": dry, "payload": payload},
            ),
        )
        model.constraint("non_negative", expr=(total >= Quantity(0, kg)))


class Vehicle(System):
    @classmethod
    def define(cls, model):
        model.name("vehicle")
        model.parameter("dry_kg", unit=kg)
        model.parameter("payload_kg", unit=kg)
        model.composed_of("mass_analysis", VehicleMassAnalysis)


cm = instantiate(Vehicle)
graph, handlers = compile_graph(cm)
ctx = RunContext()
result = Evaluator(graph, compute_handlers=handlers).evaluate(
    ctx,
    inputs={
        cm.root.dry_kg.stable_id: Quantity(10000, kg),
        cm.root.payload_kg.stable_id: Quantity(5000, kg),
    },
)
print(result.passed)
print(ctx.get_value(cm.root.mass_analysis.total_kg.stable_id))
```

### Same run with `evaluate` (recommended)

After `instantiate`, you can skip manual `compile_graph` / `Evaluator` and pass **slot handles**:

```python
result = cm.evaluate(
    inputs={
        cm.root.dry_kg: Quantity(10000, kg),
        cm.root.payload_kg: Quantity(5000, kg),
    },
)
print(result.passed)
```

See {doc}`quickstart` and {doc}`faq`.

## Input and output contract

- **Binding keys:** The string keys in `ExternalComputeBinding(..., inputs={"dry": ..., "payload": ...})` are the names your `compute(self, inputs)` receives. Values are `unitflow.Quantity` instances with compatible units for the linked slots.
- **Single output:** Return `ExternalComputeResult(value=...)` with one quantity; the compiler wires it to the attribute that uses `computed_by=`.
- **Multiple outputs:** Return `ExternalComputeResult(value={"route_a": q1, "route_b": q2})` and supply matching `output_routes` on the binding so each name maps to an attribute ref (see API docs for `link_external_routes`).
- **Static checks:** If the external object implements `validate_binding`, pass `configured_model=` into `validate_graph` so units and routes can be checked before `evaluate`.
- **Ownership rule:** keep root `System` types structural and put `computed_by=` attributes and related constraints on the owning `Part` or requirement package.

## Rule of thumb

- If logic is simple and local, keep it as expression math.
- If logic depends on external tools/data, bind external compute explicitly.
