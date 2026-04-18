# Concept: Parts

A `Part` is the building block of structural composition in `tg_model`. It declares
parameters (inputs), attributes (derived values), constraints (checks), and can own
child Parts. After instantiation, Parts form a navigable tree under `cm.root`.

---

## Minimal Part

Every `Part` subclass must call `model.name(...)` exactly once. After that, it can
declare any combination of parameters, attributes, and constraints:

```python
from unitflow.catalogs.si import kg, m
from tg_model import Part


class FuelTank(Part):
    @classmethod
    def define(cls, model):
        model.name("fuel_tank")
        capacity = model.parameter("capacity_kg", unit=kg)
        loaded   = model.parameter("loaded_mass_kg", unit=kg)
        margin   = model.attribute("mass_margin_kg", unit=kg, expr=capacity - loaded)
        model.constraint("within_capacity", expr=margin >= 0 * kg)
```

The compiler raises `ModelDefinitionError` if `model.name(...)` is missing or called twice.

---

## Parameters

`model.parameter(name, unit=...)` declares a **bindable input slot**. Its value is supplied
at evaluation time in the `inputs=` map:

```python
cm = instantiate(MySystem)
result = cm.evaluate(inputs={cm.root.fuel_tank.capacity_kg: 5000 * kg})
```

Parameters are free inputs — they have no expression and must be bound before evaluation.

---

## Attributes

`model.attribute(name, unit=..., expr=...)` declares a **derived value** computed from
an expression over other slots. The expression uses the `AttributeRef` objects returned
by earlier `model.parameter` / `model.attribute` calls:

```python
capacity = model.parameter("capacity_kg", unit=kg)
loaded   = model.parameter("loaded_mass_kg", unit=kg)
margin   = model.attribute("mass_margin_kg", unit=kg, expr=capacity - loaded)
```

For values that come from external tools or simulations, use `computed_by=` instead of
`expr=`. See {doc}`concepts_external_compute`.

---

## Constraints

`model.constraint(name, expr=...)` declares a **boolean pass/fail check**. The `expr=`
must be a comparison expression over slot refs:

```python
model.constraint("within_capacity", expr=margin >= 0 * kg)
model.constraint("loaded_positive", expr=loaded > 0 * kg)
```

Constraint results appear in `RunResult.constraint_results`.
`result.passed` is `True` only when all constraints pass.

---

## Composing Parts

Use `model.composed_of(name, ChildPartType)` to declare a child `Part`.
This replaces the old `model.part(name, Type)` call (which no longer exists).

```python
from unitflow.catalogs.si import kg
from tg_model import Part


class Engine(Part):
    @classmethod
    def define(cls, model):
        model.name("engine")
        model.parameter("dry_mass_kg", unit=kg)
        model.parameter("thrust_kn", unit=kN)


class Wing(Part):
    @classmethod
    def define(cls, model):
        model.name("wing")
        model.parameter("structural_mass_kg", unit=kg)


class Airframe(Part):
    @classmethod
    def define(cls, model):
        model.name("airframe")
        model.composed_of("engine", Engine)
        model.composed_of("wing",   Wing)
```

`model.composed_of` returns a `PartRef` you can use in expressions and allocations:

```python
engine = model.composed_of("engine", Engine)
# engine.dry_mass_kg is an AttributeRef to the child's slot
```

After `instantiate`, navigate the tree: `cm.root.airframe.engine.dry_mass_kg`.

---

## Roll-ups

A **roll-up** aggregates a slot across all direct child Parts. Use the `rollup` helper:

```python
from tg_model import Part, rollup
from unitflow.catalogs.si import kg


class StructurePart(Part):
    @classmethod
    def define(cls, model):
        model.name("structure_part")
        model.parameter("mass_kg", unit=kg)


class Assembly(Part):
    @classmethod
    def define(cls, model):
        model.name("assembly")
        model.composed_of("frame",   StructurePart)
        model.composed_of("bracket", StructurePart)
        model.composed_of("cover",   StructurePart)

        total_mass = model.attribute(
            "total_mass_kg",
            unit=kg,
            expr=rollup(model.parts(), "mass_kg"),
        )
        model.constraint("mass_positive", expr=total_mass > 0 * kg)
```

`model.parts()` returns a sentinel representing all direct child Parts declared on this
type. `rollup(model.parts(), "slot_name")` sums the named slot across those children.

---

## Ports and connections

For interface-level wiring between Parts, declare **ports** and **connections**:

```python
from tg_model import Part
from unitflow.catalogs.si import W


class PowerSource(Part):
    @classmethod
    def define(cls, model):
        model.name("power_source")
        model.parameter("output_power_w", unit=W)
        model.port("power_out", direction="out")


class PowerLoad(Part):
    @classmethod
    def define(cls, model):
        model.name("power_load")
        model.parameter("required_power_w", unit=W)
        model.port("power_in", direction="in")


class PowerSubsystem(Part):
    @classmethod
    def define(cls, model):
        model.name("power_subsystem")
        src  = model.composed_of("source", PowerSource)
        load = model.composed_of("load",   PowerLoad)
        model.connect(src.power_out, load.power_in)
```

Ports and connections are structural — they model interfaces and flow, not value transfer.
Value flow between Parts uses expressions referencing child slot refs directly.

---

## Reference: Part methods

| Method | Returns | Description |
|--------|---------|-------------|
| `model.name(str)` | `None` | Required once. Snake_case identifier. |
| `model.parameter(name, unit=...)` | `AttributeRef` | Bindable input slot. |
| `model.attribute(name, unit=..., expr=...)` | `AttributeRef` | Derived or computed value. |
| `model.constraint(name, expr=...)` | `Ref` | Boolean pass/fail check. |
| `model.composed_of(name, ChildPartType)` | `PartRef` | Declare a child Part. |
| `model.port(name, direction, ...)` | `PortRef` | Structural interface port. |
| `model.connect(source, target, ...)` | `None` | Port-to-port connection. |
| `model.parts()` | sentinel | All direct child Parts (for roll-up expressions). |
| `model.citation(name, ...)` | `Ref` | External provenance reference. |
