# End-to-End Guide: Building a Complete System

This guide walks through building a complete executable model from scratch —
from defining leaf Parts all the way to evaluating constraints and reading results.

The running example is a colocation data center that must stay within power and cooling
budgets. It is small enough to fit on one page but exercises every major feature:
Parts, Requirement packages, a System that wires them together, and evaluation.

---

## What we are building

```
HpcDatacenterProgram (System)
├── facility (HpcColoFacility — Part)
│   ├── equipment_electrical_load_kw   (parameter)
│   ├── auxiliary_cooling_load_kw      (parameter)
│   ├── grid_import_capacity_kw        (parameter)
│   ├── max_cooling_kw                 (parameter)
│   └── total_facility_kw              (attribute = electrical + cooling)
└── reqs (L1HpcRoot — Requirement)
    └── hpc (L1HpcRequirements — Requirement)
        ├── grid_capacity (GridImportCapacityReq — Requirement)
        │   ├── scenario_peak_kw       (parameter, wired from facility.total_facility_kw)
        │   ├── envelope_capacity_kw   (parameter, wired from facility.grid_import_capacity_kw)
        │   ├── grid_headroom_kw       (attribute = envelope - scenario)
        │   └── constraint: grid_headroom_non_negative
        └── cooling_envelope (AuxiliaryCoolingEnvelopeReq — Requirement)
            ├── scenario_cooling_kw    (parameter, wired from facility.auxiliary_cooling_load_kw)
            ├── envelope_cooling_kw    (parameter, wired from facility.max_cooling_kw)
            ├── cooling_headroom_kw    (attribute = envelope - scenario)
            └── constraint: cooling_headroom_non_negative
```

---

## Step 1: Define leaf Parts

Start from the bottom. A `Part` subclass must call `model.name(...)` exactly once.
Declare parameters (inputs you supply at evaluation time) and attributes (derived values).

```python
from unitflow.catalogs.si import kW
from tg_model import Part, rollup


class HpcColoFacility(Part):
    @classmethod
    def define(cls, model):
        model.name("hpc_colo_facility")

        equipment_load = model.parameter("equipment_electrical_load_kw", unit=kW)
        aux_cooling    = model.parameter("auxiliary_cooling_load_kw",     unit=kW)
        grid_capacity  = model.parameter("grid_import_capacity_kw",       unit=kW)
        max_cooling    = model.parameter("max_cooling_kw",                unit=kW)

        model.attribute(
            "total_facility_kw",
            unit=kW,
            expr=equipment_load + aux_cooling,
        )
        model.constraint(
            "equipment_load_positive",
            expr=equipment_load > 0 * kW,
        )
```

Key rules:
- `model.parameter(name, unit=...)` — each becomes a required input at evaluation time.
- `model.attribute(name, unit=..., expr=...)` — computed from an expression over declared slots.
- `model.constraint(name, expr=...)` — boolean pass/fail; appears in `RunResult.constraint_results`.

---

## Step 2: Define Requirement packages

Each `Requirement` subclass must call `model.name(...)` and `model.doc(...)` exactly once.
Its executable checks use the same `parameter` / `attribute` / `constraint` surface as a `Part`.

```python
from unitflow.catalogs.si import kW
from tg_model import Requirement


class GridImportCapacityReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("grid_capacity")
        model.doc(
            "Total facility power draw shall not exceed the contracted "
            "grid import capacity."
        )

        scenario  = model.parameter("scenario_peak_kw",      unit=kW)
        envelope  = model.parameter("envelope_capacity_kw",  unit=kW)
        headroom  = model.attribute("grid_headroom_kw", unit=kW, expr=envelope - scenario)
        model.constraint("grid_headroom_non_negative", expr=headroom >= 0 * kW)


class AuxiliaryCoolingEnvelopeReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("cooling_envelope")
        model.doc(
            "Auxiliary cooling load shall not exceed the mechanical plant "
            "design envelope."
        )

        scenario  = model.parameter("scenario_cooling_kw",   unit=kW)
        envelope  = model.parameter("envelope_cooling_kw",   unit=kW)
        headroom  = model.attribute("cooling_headroom_kw", unit=kW, expr=envelope - scenario)
        model.constraint("cooling_headroom_non_negative", expr=headroom >= 0 * kW)
```

The `parameter` slots on a `Requirement` are **not** supplied directly in `inputs=`.
They get their values through `model.allocate(..., inputs={...})` on the System.
This decoupling is intentional: the requirement defines what values it needs;
the System declares where those values come from.

---

## Step 3: Compose Requirements into a tree

Use `model.composed_of(name, ChildRequirementType)` to build hierarchy:

```python
class L1HpcRequirements(Requirement):
    @classmethod
    def define(cls, model):
        model.name("l1_hpc_requirements")
        model.doc("Level-1 infrastructure requirements for the HPC facility.")
        model.composed_of("grid_capacity",    GridImportCapacityReq)
        model.composed_of("cooling_envelope", AuxiliaryCoolingEnvelopeReq)


class L1HpcRoot(Requirement):
    @classmethod
    def define(cls, model):
        model.name("l1_hpc_root")
        model.doc("Root requirement package for the HPC program.")
        model.composed_of("hpc", L1HpcRequirements)
```

This is entirely optional — you can allocate leaf packages directly without intermediate
containers. The hierarchy is for organization and traceability.

---

## Step 4: Define the System

The `System` composes the Part tree and Requirement tree, then wires them together.

```python
from unitflow.catalogs.si import kW
from tg_model import System


class HpcDatacenterProgram(System):
    @classmethod
    def define(cls, model):
        model.name("hpc_datacenter_program")

        # 1. Compose Parts
        facility = model.composed_of("facility", HpcColoFacility)

        # 2. Compose Requirements
        reqs = model.composed_of("reqs", L1HpcRoot)

        # 3. Allocate: wire requirement parameters to facility slots
        model.allocate(reqs.hpc.grid_capacity, facility, inputs={
            "scenario_peak_kw":     facility.total_facility_kw,
            "envelope_capacity_kw": facility.grid_import_capacity_kw,
        })
        model.allocate(reqs.hpc.cooling_envelope, facility, inputs={
            "scenario_cooling_kw":  facility.auxiliary_cooling_load_kw,
            "envelope_cooling_kw":  facility.max_cooling_kw,
        })
```

`model.allocate(req_ref, target_ref, inputs={...})`:
- `req_ref` — navigate the composed tree with dot-access: `reqs.hpc.grid_capacity`
- `target_ref` — the Part receiving the allocation (appears in constraint result rows)
- `inputs` — dict mapping each `parameter` name in the Requirement to an `AttributeRef`
  from the target Part (or a System-level parameter)

---

## Step 5: Instantiate

```python
from tg_model.execution import instantiate

cm = instantiate(HpcDatacenterProgram)
```

`instantiate` compiles all declared types, builds the instance graph, and returns a
frozen `ConfiguredModel`. This is cheap to call and can be done once at module load.

Navigate the topology via `cm.root`:

```python
# ValueSlot objects — use as keys in evaluate(inputs={...})
cm.root.facility.equipment_electrical_load_kw
cm.root.facility.total_facility_kw
cm.root.reqs.hpc.grid_capacity.grid_headroom_kw
```

---

## Step 6: Evaluate

Pass a dict of `{ValueSlot: Quantity}` for every unbound parameter:

```python
from unitflow.catalogs.si import kW

result = cm.evaluate(inputs={
    cm.root.facility.equipment_electrical_load_kw: 850 * kW,
    cm.root.facility.auxiliary_cooling_load_kw:    320 * kW,
    cm.root.facility.grid_import_capacity_kw:     1500 * kW,
    cm.root.facility.max_cooling_kw:               400 * kW,
})
```

---

## Step 7: Read results

```python
print("All constraints passed:", result.passed)
```

### Inspect every constraint

```python
for cr in result.constraint_results:
    status = "PASS" if cr.passed else "FAIL"
    print(f"[{status}] {cr.name}")
    if cr.requirement_path:
        print(f"         req    = {cr.requirement_path}")
        print(f"         target = {cr.allocation_target_path}")
```

Example output:

```
[PASS] equipment_load_positive
[PASS] grid_headroom_non_negative
         req    = hpc_datacenter_program.reqs.l1_hpc_root.hpc.l1_hpc_requirements.grid_capacity
         target = hpc_datacenter_program.facility
[PASS] cooling_headroom_non_negative
         req    = hpc_datacenter_program.reqs.l1_hpc_root.hpc.l1_hpc_requirements.cooling_envelope
         target = hpc_datacenter_program.facility
```

### Read computed attribute values

```python
total_kw       = result.outputs[cm.root.facility.total_facility_kw.stable_id]
grid_headroom  = result.outputs[cm.root.reqs.hpc.grid_capacity.grid_headroom_kw.stable_id]
cool_headroom  = result.outputs[cm.root.reqs.hpc.cooling_envelope.cooling_headroom_kw.stable_id]

print(f"Total facility draw:  {total_kw}")
print(f"Grid headroom:        {grid_headroom}")
print(f"Cooling headroom:     {cool_headroom}")
```

### Failing scenario

Change the electrical load to exceed the grid capacity:

```python
result_fail = cm.evaluate(inputs={
    cm.root.facility.equipment_electrical_load_kw: 1300 * kW,   # over budget
    cm.root.facility.auxiliary_cooling_load_kw:     320 * kW,
    cm.root.facility.grid_import_capacity_kw:       1500 * kW,
    cm.root.facility.max_cooling_kw:                 400 * kW,
})

print("Passed:", result_fail.passed)   # False

failures = [cr for cr in result_fail.constraint_results if not cr.passed]
for cr in failures:
    print(f"FAIL: {cr.name}  ({cr.requirement_path})")
```

---

## Complete listing

```python
from unitflow.catalogs.si import kW
from tg_model import Part, Requirement, System
from tg_model.execution import instantiate


# --- Parts ---

class HpcColoFacility(Part):
    @classmethod
    def define(cls, model):
        model.name("hpc_colo_facility")
        equipment_load = model.parameter("equipment_electrical_load_kw", unit=kW)
        aux_cooling    = model.parameter("auxiliary_cooling_load_kw",     unit=kW)
        grid_capacity  = model.parameter("grid_import_capacity_kw",       unit=kW)
        max_cooling    = model.parameter("max_cooling_kw",                unit=kW)
        model.attribute("total_facility_kw", unit=kW, expr=equipment_load + aux_cooling)
        model.constraint("equipment_load_positive", expr=equipment_load > 0 * kW)


# --- Requirements ---

class GridImportCapacityReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("grid_capacity")
        model.doc("Total facility draw shall not exceed grid import capacity.")
        scenario = model.parameter("scenario_peak_kw",     unit=kW)
        envelope = model.parameter("envelope_capacity_kw", unit=kW)
        headroom = model.attribute("grid_headroom_kw", unit=kW, expr=envelope - scenario)
        model.constraint("grid_headroom_non_negative", expr=headroom >= 0 * kW)


class AuxiliaryCoolingEnvelopeReq(Requirement):
    @classmethod
    def define(cls, model):
        model.name("cooling_envelope")
        model.doc("Auxiliary cooling load shall not exceed the plant design envelope.")
        scenario = model.parameter("scenario_cooling_kw",  unit=kW)
        envelope = model.parameter("envelope_cooling_kw",  unit=kW)
        headroom = model.attribute("cooling_headroom_kw", unit=kW, expr=envelope - scenario)
        model.constraint("cooling_headroom_non_negative", expr=headroom >= 0 * kW)


class L1HpcRequirements(Requirement):
    @classmethod
    def define(cls, model):
        model.name("l1_hpc_requirements")
        model.doc("Level-1 infrastructure requirements.")
        model.composed_of("grid_capacity",    GridImportCapacityReq)
        model.composed_of("cooling_envelope", AuxiliaryCoolingEnvelopeReq)


class L1HpcRoot(Requirement):
    @classmethod
    def define(cls, model):
        model.name("l1_hpc_root")
        model.doc("Root requirement package.")
        model.composed_of("hpc", L1HpcRequirements)


# --- System ---

class HpcDatacenterProgram(System):
    @classmethod
    def define(cls, model):
        model.name("hpc_datacenter_program")
        facility = model.composed_of("facility", HpcColoFacility)
        reqs     = model.composed_of("reqs",     L1HpcRoot)

        model.allocate(reqs.hpc.grid_capacity, facility, inputs={
            "scenario_peak_kw":     facility.total_facility_kw,
            "envelope_capacity_kw": facility.grid_import_capacity_kw,
        })
        model.allocate(reqs.hpc.cooling_envelope, facility, inputs={
            "scenario_cooling_kw":  facility.auxiliary_cooling_load_kw,
            "envelope_cooling_kw":  facility.max_cooling_kw,
        })


# --- Evaluate ---

cm = instantiate(HpcDatacenterProgram)

result = cm.evaluate(inputs={
    cm.root.facility.equipment_electrical_load_kw: 850 * kW,
    cm.root.facility.auxiliary_cooling_load_kw:    320 * kW,
    cm.root.facility.grid_import_capacity_kw:     1500 * kW,
    cm.root.facility.max_cooling_kw:               400 * kW,
})

print("Passed:", result.passed)
for cr in result.constraint_results:
    status = "PASS" if cr.passed else "FAIL"
    print(f"  [{status}] {cr.name}")
```

---

## Summary: the authoring loop

Every tg_model program follows the same structure:

1. **Parts** — declare structural elements with parameters, attributes, constraints.
2. **Requirements** — declare executable checks with `model.name`, `model.doc`, parameters, attributes, constraints.
3. **Requirement trees** — compose leaf Requirements into a hierarchy using `model.composed_of`.
4. **System** — compose the Part tree and Requirement tree; wire them with `model.allocate`.
5. **`instantiate`** — freeze topology into a `ConfiguredModel`.
6. **`evaluate`** — supply parameter values, get back a `RunResult`.

---

## Where to go next

- {doc}`concepts_parts` — Part deep dive: roll-ups, ports, external compute
- {doc}`concepts_requirements` — Requirement deep dive: nesting, citations, traceability
- {doc}`concepts_system` — System deep dive: scenario parameters, multiple allocations
- {doc}`concepts_evaluation` — Evaluation paths, reading RunResult, analysis utilities
- {doc}`concepts_external_compute` — Binding external tools and simulations
