# Concept: Requirements

Requirements in `tg_model` are **executable packages** — not just text. Each `Requirement`
subclass owns parameters, attributes, and constraints using the same surface as a `Part`.
The difference is that a `Requirement` also carries a `model.doc(...)` "shall" statement
and participates in allocation wiring.

---

## The authoring pattern

Every `Requirement` class follows this shape, no exceptions:

```python
from unitflow.catalogs.si import kN
from tg_model import Requirement


class ThrustReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("thrust_req")                          # required once
        model.doc(                                         # required once, Requirement only
            "The propulsion subsystem shall deliver vacuum thrust "
            "no less than the mission floor."
        )

        required = model.parameter("required_thrust", unit=kN)
        declared = model.parameter("declared_thrust", unit=kN)
        margin = model.attribute("thrust_margin", unit=kN, expr=declared - required)
        model.constraint("thrust_margin_non_negative", expr=margin >= 0 * kN)
```

| Rule | Detail |
|------|--------|
| `model.name(str)` | Required exactly once. Identifies the package. |
| `model.doc(str)` | Required exactly once. The "shall" statement. Requirement-only. |
| `model.parameter(name, unit=...)` | Bindable input slot. Wired at allocation time. |
| `model.attribute(name, unit=..., expr=...)` | Derived value from an expression. |
| `model.constraint(name, expr=...)` | Boolean pass/fail check. |
| `model.composed_of(name, ChildRequirementType)` | Nest a child requirement package. |

The compiler rejects any `Requirement` class missing `model.name()` or `model.doc()`.
Both must be called exactly once — a second call raises `ModelDefinitionError`.

---

## Composing requirement packages

Use `model.composed_of(name, ChildType)` to build a hierarchy:

```python
from unitflow.catalogs.si import kg, m
from tg_model import Requirement


class PayloadReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("payload_req")
        model.doc("Design payload mass shall not exceed structural envelope.")
        scenario = model.parameter("scenario_payload_kg", unit=kg)
        envelope = model.parameter("envelope_payload_kg", unit=kg)
        margin = model.attribute("payload_margin_kg", unit=kg, expr=envelope - scenario)
        model.constraint("payload_margin_non_negative", expr=margin >= 0 * kg)


class RangeReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("range_req")
        model.doc("Design mission range shall not exceed modeled envelope.")
        scenario = model.parameter("scenario_range_m", unit=m)
        envelope = model.parameter("envelope_range_m", unit=m)
        margin = model.attribute("range_margin_m", unit=m, expr=envelope - scenario)
        model.constraint("range_margin_non_negative", expr=margin >= 0 * m)


class L1MissionReqs(Requirement):
    @classmethod
    def define(cls, model):
        model.name("l1_mission_reqs")
        model.doc("Level-1 mission closure requirements.")
        model.composed_of("payload", PayloadReq)
        model.composed_of("range", RangeReq)
```

`L1MissionReqs` owns both children. After `instantiate`, slots are accessible at
`cm.root.reqs.payload.scenario_payload_kg` etc.

---

## Mounting requirements on a System

Use `model.composed_of(name, RequirementType)` on a `System` to mount the requirement tree,
then `model.allocate(req_ref, part_ref, inputs={...})` to wire values in:

```python
from unitflow.catalogs.si import kg, m
from tg_model import Part, System


class Aircraft(Part):
    @classmethod
    def define(cls, model):
        model.name("aircraft")
        model.parameter("max_payload_kg", unit=kg)
        model.parameter("max_range_m", unit=m)


class MissionProgram(System):
    @classmethod
    def define(cls, model):
        model.name("mission_program")
        scenario_payload = model.parameter("scenario_payload_kg", unit=kg)
        scenario_range = model.parameter("scenario_range_m", unit=m)

        aircraft = model.composed_of("aircraft", Aircraft)
        reqs = model.composed_of("reqs", L1MissionReqs)

        model.allocate(reqs.payload, aircraft, inputs={
            "scenario_payload_kg": scenario_payload,
            "envelope_payload_kg": aircraft.max_payload_kg,
        })
        model.allocate(reqs.range, aircraft, inputs={
            "scenario_range_m":   scenario_range,
            "envelope_range_m":   aircraft.max_range_m,
        })
```

`model.allocate(req_ref, target_ref, inputs={...})` takes:

- `req_ref` — a `RequirementRef` pointing to the package to satisfy (obtained from `model.composed_of` or dot-navigation into a composed tree)
- `target_ref` — a `PartRef` or similar ref to the design element being allocated to
- `inputs` — a `dict[str, AttributeRef]` mapping each `parameter` name declared in the requirement class to the Part slot that provides the value

---

## Reading constraint results

After `evaluate`, requirement constraints appear in `RunResult.constraint_results`
tagged with `requirement_path` and `allocation_target_path`:

```python
cm = instantiate(MissionProgram)
result = cm.evaluate(inputs={
    cm.root.scenario_payload_kg: 45_000 * kg,
    cm.root.aircraft.max_payload_kg: 50_000 * kg,
    cm.root.scenario_range_m: 8_000_000 * m,
    cm.root.aircraft.max_range_m: 9_000_000 * m,
})

print("Overall passed:", result.passed)

for cr in result.constraint_results:
    print(
        f"{cr.name}: {'PASS' if cr.passed else 'FAIL'}"
        f"  requirement={cr.requirement_path}"
        f"  target={cr.allocation_target_path}"
    )
```

Filter by requirement path to get per-package results:

```python
payload_results = [
    cr for cr in result.constraint_results
    if cr.requirement_path and "payload" in cr.requirement_path
]
```

---

## Available methods inside `Requirement.define()`

| Method | Description |
|--------|-------------|
| `model.name(str)` | Human-readable identifier. Required once. |
| `model.doc(str)` | "Shall" statement. Required once. Requirement-only. |
| `model.parameter(name, unit=...)` | Bindable input slot. Wired via `allocate(..., inputs=...)`. |
| `model.attribute(name, unit=..., expr=...)` | Derived value. |
| `model.constraint(name, expr=...)` | Pass/fail check. |
| `model.composed_of(name, ChildRequirementType)` | Nested child requirement package. |
| `model.solve_group(name, equations, unknowns, givens)` | Coupled equation group solved numerically at evaluation time. |
| `model.citation(name, ...)` | External provenance (standard, clause, URI). |
| `model.references(node, citation)` | Traceability edge from a node to a citation. |
