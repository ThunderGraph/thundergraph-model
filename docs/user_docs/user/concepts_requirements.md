# Concept: Requirements (inputs, derived attributes, acceptance)

This page covers **executable** requirement acceptance: symbols stay scoped to a composable **`Requirement`** package, and the graph evaluates acceptance like any other constraint.

## Leaf `model.requirement(...)` vs composable `Requirement`

- **`Requirement`** is the **type** of a composable requirements **package**. You implement **`define(cls, model)`** on a subclass, register it from a **`System`** or **`Part`** with **`model.requirement_package(name, YourType)`**, and navigate with **`RequirementRef`** dot access (e.g. **`reqs.mission_range`**).
- **`model.requirement(id, text)`** is a **declaration** that creates one **leaf** requirement inside such a package. It returns a ref used with **`requirement_input`**, **`requirement_attribute`**, and **`requirement_accept_expr`**. It is not an alternative to subclassing **`Requirement`** for a reusable package.

Keeping those two straight avoids confusion with the class name **`Requirement`**.

## Package-level parameters, attributes, and constraints

Inside **`Requirement.define()`**, you may declare **`parameter`**, **`attribute`**, and **`constraint`** at **package** scope (not only on leaf requirements). They compile and instantiate like other value nodes, with symbols resolved under the package’s path prefix. After **`instantiate`**, access them from the configured **`PartInstance`** (typically the root) via the package name, e.g. **`cm.root.my_pkg.my_param`**.

**Limitations (today):** package-level slots do not support **`computed_by=`** or rollups in graph compilation; every package **`constraint`** must supply **`expr=`** (constant expressions are allowed). See the **`Requirement`** class docstring in the API reference for the authoritative list.

**Product alignment:** package-scoped values are a good match for models where **requirements own parameters and derived quantities** as first-class nodes (the same mental model as “attributes as nodes” in graph databases). This library does not ship a Neo4j schema change; it only exposes the authoring and execution shape.

## Values on a leaf requirement

There are two complementary ways to introduce **values** on a **leaf** requirement (the ref returned by **`model.requirement`**):

- **`requirement_input`** — slots you **wire from the design** with `allocate(..., inputs={...})` (scenario parameters, part attributes, and so on).
- **`requirement_attribute`** — **requirement-owned derived values** with an `expr=` (sums, margins, normalized quantities, intermediate checks) that may depend on inputs, earlier attributes on the same requirement, and root/part symbols.

Use **`requirement_accept_expr`** (or inline `requirement(..., expr=)` where appropriate) for the boolean acceptance check.

## Wired inputs (`requirement_input`)

This is the simplest pattern when acceptance only needs values **mapped from** the allocated subtree.

```python
from unitflow import km
from tg_model import Requirement, System
from tg_model.execution import (
    Evaluator,
    RunContext,
    compile_graph,
    instantiate,
    summarize_requirement_satisfaction,
    validate_graph,
)


class RangeReqs(Requirement):
    @classmethod
    def define(cls, model):
        r = model.requirement("mission_range", "Aircraft shall support mission range.")
        achieved = model.requirement_input(r, "achieved_range_km", unit=km)
        required = model.requirement_input(r, "required_range_km", unit=km)
        model.requirement_accept_expr(r, expr=(achieved >= required))


class Aircraft(System):
    @classmethod
    def define(cls, model):
        root = model.part()
        mission_km = model.parameter("mission_required_km", unit=km, required=True)
        achieved_km = model.attribute("achieved_km", unit=km, expr=9000 * km)

        reqs = model.requirement_package("reqs", RangeReqs)
        model.allocate(
            reqs.mission_range,
            root,
            inputs={
                "achieved_range_km": root.achieved_km,
                "required_range_km": root.mission_required_km,
            },
        )


cm = instantiate(Aircraft)
graph, handlers = compile_graph(cm)
vr = validate_graph(graph, configured_model=cm)
assert vr.passed, vr.failures

result = Evaluator(graph, compute_handlers=handlers).evaluate(
    RunContext(),
    inputs={cm.root.mission_required_km.stable_id: 8000 * km},
)
req = summarize_requirement_satisfaction(result)
print("Overall run passed:", result.passed)
print("Requirement checks:", req.check_count, "all_passed:", req.all_passed)
for row in req.results:
    print(row.requirement_path, "passed" if row.passed else "failed", row.evidence)
```

### Why this pattern

- Requirement expression is local to the `Requirement` package.
- Part values are explicitly mapped by `allocate(..., inputs=...)`.
- Acceptance runs in normal graph evaluation (same pass as constraints).

Use `summarize_requirement_satisfaction(result)` (or `iter_requirement_satisfaction`) to read **per-requirement** outcomes. `result.passed` aggregates every constraint in the run; requirement rows are the ones tagged with a `requirement_path` in the evaluator output.

## Derived values on the requirement (`requirement_attribute`)

When acceptance (or another derived value) should use **intermediate math** that belongs to the requirement itself—not to a part—declare **`requirement_attribute(requirement, name, *, expr=..., unit=...)`**. Expressions may use:

- **`requirement_input`** symbols on the same requirement,
- **`requirement_attribute`** symbols declared **earlier** in the same `define()` (declaration order matters),
- parameters and attributes on the configured root and allocated parts (same symbol rules as elsewhere).

Derived attributes are materialized as value slots on the configured root; **`ConfiguredModel.requirement_value_slots`** lists them for inspection and tooling.

**Example (sum of two wired inputs, then acceptance on the sum):**

```python
from unitflow import Quantity, QuantityExpr
from unitflow.catalogs.si import m
from tg_model import Requirement, System
from tg_model.execution import Evaluator, RunContext, compile_graph, instantiate, validate_graph


class SumReqs(Requirement):
    @classmethod
    def define(cls, model):
        r = model.requirement("positive_span", "Span sum shall be positive.")
        a = model.requirement_input(r, "a_m", unit=m)
        b = model.requirement_input(r, "b_m", unit=m)
        total = model.requirement_attribute(r, "total_m", expr=a + b, unit=m)
        model.requirement_accept_expr(r, expr=total > QuantityExpr(Quantity(0, m)))


class Demo(System):
    @classmethod
    def define(cls, model):
        root = model.part()
        la = model.parameter("len_a_m", unit=m)
        lb = model.parameter("len_b_m", unit=m)
        blk = model.requirement_package("reqs", SumReqs)
        model.allocate(
            blk.positive_span,
            root,
            inputs={"a_m": la, "b_m": lb},
        )


cm = instantiate(Demo)
graph, handlers = compile_graph(cm)
assert validate_graph(graph, configured_model=cm).passed
result = Evaluator(graph, compute_handlers=handlers).evaluate(
    RunContext(),
    inputs={
        cm.root.len_a_m.stable_id: Quantity(1, m),
        cm.root.len_b_m.stable_id: Quantity(2, m),
    },
)
assert result.passed
```

### Rules and limitations

- **Names** — An input name and an attribute name on the **same** requirement cannot collide.
- **Order** — Declare all **`requirement_input`** and **`requirement_attribute`** calls **before** **`requirement_accept_expr`** for that requirement.
- **Allocations** — If a requirement declares any **`requirement_attribute`**, it must have **at most one** `allocate(...)` edge in the configured model. Multiple allocations would make a single derived slot ambiguous; split the model or duplicate requirement structure if you truly need multiple targets.

This split matches common MBSE practice: **inputs** are where the design feeds the requirement, and **attributes** are properties or derived quantities **owned by** the requirement for acceptance and reporting.
