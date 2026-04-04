# Concept: Requirements — parameter / attribute / constraint (DEFAULT)

> **TL;DR — When writing a new `Requirement` package, use `model.parameter`, `model.attribute`, and `model.constraint`.  That is the default, recommended, current API.**
>
> `requirement_input`, `requirement_attribute`, and `requirement_accept_expr` exist **only** for a rare, advanced leaf-reqcheck pattern (INCOSE-style acceptance rows wired through `allocate(..., inputs=...)`).  **Do not reach for them first.**  If you are not sure whether you need them, **you don't**.

---

## The default pattern: package-level `parameter` / `attribute` / `constraint`

A composable **`Requirement`** package uses the same value/check authoring surface as a `Part`. Unlike a `System`, it may own `attribute(...)` and `constraint(...)` declarations directly:

```python
from unitflow.catalogs.si import kN
from unitflow.core.units import Unit
from tg_model import Requirement

DIMLESS = Unit.dimensionless()


class PropulsionReqs(Requirement):
    @classmethod
    def define(cls, model):
        required = model.parameter("required_vacuum_thrust", unit=kN)
        declared = model.parameter("declared_vacuum_thrust", unit=kN)
        margin = model.attribute(
            "vacuum_thrust_margin", unit=kN, expr=declared - required,
        )
        model.constraint("thrust_margin_non_negative", expr=margin >= 0 * kN)

        model.requirement(
            "req_vacuum_thrust_capability",
            "The propulsion subsystem shall deliver vacuum thrust no less than "
            "the mission floor (verification by test / analysis).",
        )
```

**That's it.**  `parameter`, `attribute`, `constraint` on the package, plus `model.requirement` for the formal "shall" text.  The constraint enforces the executable check; the requirement node carries the traceability text and can be `allocate`d and `references`d for citations.

After `instantiate`, the slots live at `cm.requirements.propulsion.required_vacuum_thrust` etc., and constraints appear in `RunResult.constraint_results` alongside part constraints.

### When to use this pattern

**Always.**  For every new requirement package, start here.  This is the primary modeling surface for requirements.

---

## Leaf `model.requirement(...)` vs composable `Requirement`

- **`Requirement`** (the class) is a **composable package type**.  You subclass it, implement `define(cls, model)`, and register it with `model.requirement_package(name, YourType)`.  Navigate with `RequirementRef` dot access (e.g. `reqs.mission.req_delta_v_closure`).
- **`model.requirement(id, text)`** declares **one leaf** requirement statement inside a package.  It returns a `Ref` for `allocate`, `references`, and (in the rare advanced case) `requirement_input` / `requirement_accept_expr`.

Keeping those two straight avoids confusion with the class name.

---

## Package-level value surface

Inside `Requirement.define()`:

| Method | What it does | Same as on `Part`? |
|--------|-------------|-------------------|
| `model.parameter(name, unit=...)` | Externally bound input slot | Yes |
| `model.attribute(name, unit=..., expr=...)` | Derived value from expression | Yes |
| `model.constraint(name, expr=...)` | Pass/fail check on the expression | Yes |
| `model.requirement(id, text)` | Leaf "shall" statement (traceability) | Requirement-only |
| `model.requirement_package(name, Type)` | Nested composable sub-package | Requirement-only |
| `model.citation(name, ...)` | External provenance node | Yes |
| `model.references(req, citation)` | Traceability edge | Requirement-only |

**Limitations (today):** package-level slots do not support `computed_by=` or rollups in graph compilation; every package `constraint` must supply `expr=`.

---

## Advanced (rare): leaf-level `requirement_input` / `requirement_attribute` / `requirement_accept_expr`

> **⚠️  Stop.  You almost certainly do not need this section for new code.**
>
> These three helpers exist for **one specific pattern**: encoding an INCOSE-style executable acceptance test on a **single leaf** `model.requirement(...)`, where:
>
> 1. You declare `requirement_input` slots on the leaf requirement.
> 2. You wire those inputs from the design via `allocate(..., inputs={name: part_ref.slot})`.
> 3. You optionally compute a `requirement_attribute` margin.
> 4. You set a `requirement_accept_expr` boolean check.
> 5. `summarize_requirement_satisfaction` then reports per-requirement pass/fail rows.
>
> **If your check can be expressed as a package-level `constraint`, use that instead.**  It is simpler, more readable, and produces the same pass/fail result in `RunResult.constraint_results`.

### When the leaf reqcheck pattern is appropriate

- You have a **formal Level-1 "shall" statement** with its own acceptance criterion.
- You want `summarize_requirement_satisfaction` to print a **per-requirement row** (tagged with `requirement_path`).
- The acceptance wiring needs **`allocate(..., inputs=...)`** to map scenario values and design envelope values into requirement-local input slots.

### Example (mission closure — the rare case)

```python
from unitflow.catalogs.si import m

m_per_s = m / s


class MissionClosure(Requirement):
    @classmethod
    def define(cls, model):
        r_dv = model.requirement(
            "req_delta_v_closure",
            "Design shall close scenario delta-v within declared envelope.",
        )
        scenario_dv = model.requirement_input(r_dv, "scenario_delta_v", unit=m_per_s)
        envelope_dv = model.requirement_input(r_dv, "envelope_delta_v", unit=m_per_s)
        dv_margin = model.requirement_attribute(
            r_dv, "delta_v_margin", expr=envelope_dv - scenario_dv, unit=m_per_s,
        )
        model.requirement_accept_expr(r_dv, expr=dv_margin >= 0 * m_per_s)
```

Then on the `System`:

```python
model.allocate(
    rq.mission.req_delta_v_closure,
    design_envelope,
    inputs={
        "scenario_delta_v": scenario_dv_param,
        "envelope_delta_v": design_envelope.design_delta_v_capability,
    },
)
```

### Rules and limitations (leaf reqcheck)

- Names — An input name and an attribute name on the **same** requirement cannot collide.
- Order — Declare all `requirement_input` and `requirement_attribute` calls **before** `requirement_accept_expr`.
- Allocations — If a requirement declares `requirement_attribute`, it must have **at most one** `allocate(...)` edge.

---

## Summary: which pattern to use

| Situation | Pattern |
|-----------|---------|
| **New requirement package** (99% of cases) | `parameter` + `attribute` + `constraint` on the package |
| **Formal leaf acceptance test** (rare, INCOSE-style) | `requirement_input` + `requirement_attribute` + `requirement_accept_expr` on a leaf `model.requirement(...)` |
| **Traceability text** | `model.requirement(id, text)` + `model.allocate(req, part)` + `model.references(req, citation)` |

**Default to the first row.  Always.**
