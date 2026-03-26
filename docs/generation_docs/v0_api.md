# tg-model v0 API Design

## Purpose

This document proposes the first concrete public API shape for `tg-model`.

It is a v0 API proposal, not a final specification.

**Authoring status (major v0 direction):** the preferred structural authoring path is a framework-managed `@classmethod def define(cls, model)` hook and a `ModelDefinitionContext` (`model`) that records declarations and returns typed reference objects. That direction is **validated** (for typed part/port/attribute declaration and `connect` capture) by the early prototype in [`model_prototype_sketch.py`](model_prototype_sketch.py). **Configured instance graphs** and **library execution** (`instantiate`, `compile_graph`, `Evaluator`, Phase 5 analysis, Phase 6 discrete behavior including activity control-flow and inter-part **`emit_item`**) are **implemented** in `tg_model`; **product-shaped** instance APIs (`DriveSystem()`, `execute_scenario` on a system handle) remain directional. Parts of this document still show **class-body** illustrations for constructs not yet on `model`.

Its purpose is to:

- test the architectural decisions already captured in the requirements and logical architecture
- provide a concrete authoring surface for review
- identify awkward or ambiguous parts of the design early
- keep the API aligned with `tg-model`'s mission as a standalone executable systems modeling library

## Table of Contents

- [Scope](#scope)
- [API Design Goals](#api-design-goals)
- [Guiding Decisions](#guiding-decisions)
- [Public API Surfaces](#public-api-surfaces)
- [Model Authoring API](#model-authoring-api)
- [Framework authoring hook (`define` and `model`)](#framework-authoring-hook-define-and-model)
- [Behavioral Modeling](#behavioral-modeling)
- [Execution API](#execution-api)
- [Execution engine methodology (separate doc)](execution_methodology.md)
- [Analysis API](#analysis-api)
- [Integration API](#integration-api)
- [Export API](#export-api)
- [End-to-End Examples](#end-to-end-examples)
- [Contract Freeze: Value Authoring And Handle Mapping](#contract-freeze-value-authoring-and-handle-mapping)
- [Remaining Open Questions](#remaining-open-questions)

## Scope

This document covers the public API surface for:

- model authoring
- model instantiation
- evaluation
- compliance checking
- studies
- external analysis binding
- graph export entry points

This document does not finalize:

- internal implementation details
- final package layout
- export schema details
- optional future behavioral extensions (e.g. general looping activity nodes) beyond the current Phase 6 library
- how compiled type definitions become **configured instances** (the “`DriveSystem()` / `configure(...)`” shapes below are directional, not locked)

**Frozen in this document:** value authoring (items 1–3), minimum synchronous execution API (item 4), and **external computation binding** (item 5, Phase 4 gate). See [Contract Freeze](#contract-freeze-value-authoring-and-handle-mapping).

**Phase 5 library alignment:** multi-run **analysis** entry points (`sweep`, `compare_variants`, value-graph propagation) are described below to match the implemented `tg_model.analysis` package; treat this as the canonical v0 shape unless a later freeze revises it.

**Phase 6 library alignment:** full **methodology-aligned** discrete behavior on `RunContext` — state machines, guards, **`sequence` / `decision` / `merge` / `fork_join`**, item flow via **`emit_item`**, scenario validation, and structural boundary enforcement in effects — matches `tg_model.execution.behavior` and `ModelDefinitionContext` as documented under [Behavioral Modeling](#behavioral-modeling) and [Execution API](#execution-api).

## API Design Goals

The v0 API should:

- be declarative enough for reliable LLM generation
- be readable and editable by power users
- use one obvious way to express the main concepts
- reflect the conceptual requirements and use cases directly
- preserve explicit system semantics rather than hiding them in generic graphs
- work naturally with `unitflow`
- support strict completeness and fail-fast evaluation
- separate model definition from execution

## Guiding Decisions

These API choices are assumed from the current architecture:

- structural declarations are recorded through a framework-managed `define(cls, model)` hook (see [Framework authoring hook](#framework-authoring-hook-define-and-model))
- `unitflow` is foundational
- stable identity supports explicit IDs with deterministic fallback
- the model owns a precompiled dependency graph
- constraints operate synchronously over realized values
- async work belongs in computed attribute realization and execution internals
- roll-ups are core model semantics, not analysis-only helpers
- variants are independent instantiated configurations
- analysis coordinates multi-run workflows, but execution performs single runs

## Public API Surfaces

The proposed public API is split into five conceptual surfaces:

- modeling surface
- execution surface
- analysis surface
- integration surface
- export surface

These surfaces may map to packages or may be re-exported from the top-level package for ergonomics.

High-level direction:

- **Types** (`System`, `Part`, `Requirement`, …) are imported as classes users subclass.
- **Structural declarations** in v0 are made through methods on the `model` object passed into `define(cls, model)` (see below), not by assigning descriptors in the class body. The exact re-export story (`from tg_model import …` vs `model.port(...)`) may evolve; the invariant is “declarations go through the definition context during `define`.”
- **Execution, analysis, and export** remain separate surfaces that operate on compiled definitions and (eventually) configured instances.

Illustrative imports (names are indicative):

```python
from tg_model import (
    System,
    Part,
    Requirement,
    Interface,
    Action,
    Decision,
    Merge,
    Fork,
    Join,
    State,
    Transition,
    Guard,
    Event,
    Item,
    Scenario,
    constraint,
    action,
    decision,
    merge,
    fork,
    join,
    state,
    transition,
    guard,
    event,
    item,
    scenario,
    sequence,
    solve_group,
    choice,
    configure,
    computed_by,
)
```

Analysis workflows import from the analysis subpackage, e.g. `from tg_model.analysis import sweep, compare_variants, dependency_impact` (see [Analysis API](#analysis-api)).

## Model Authoring API

Model authoring is centered on **element types** (Python subclasses of `Element`) and a single **definition entry point** per type: `define(cls, model)`. The framework calls `define` when a type needs to be compiled; the `model` object records nodes and edges and returns typed **`Ref`** objects for use in relationships (e.g. `connect`).

Longer examples in this document sometimes still use a **class-body** style for behavior, constraints, or roll-ups. Treat those as **target semantics** until they are re-expressed through `define` (or companion hooks) in a later revision.

## Framework authoring hook (`define` and `model`)

This section captures the **preferred v0 direction** for structural modeling, validated by prototype, and the **explicit limits** of what that prototype proves.

- The preferred v0 direction is a **framework-managed** `define(cls, model)` authoring hook.
- That direction has been **validated by an early prototype** for typed part/port/attribute declaration and relationship capture (`connect` with structured `Ref` endpoints).
- **Configured instance graphs**, **behavioral compilation**, and **execution semantics** remain under active design.

Reference implementation (sketch, not the final library API): [`model_prototype_sketch.py`](model_prototype_sketch.py).

### `ModelDefinitionContext` (`model`)

During `define`, the framework provides a `model: ModelDefinitionContext` bound to the owner type being defined. It:

- registers named declarations (parts, ports, attributes, …)
- returns **`Ref` subclasses** (`PartRef`, `PortRef`, `AttributeRef`, …) — symbolic handles, **not** runtime part instances
- accepts relationship calls such as `connect(source: PortRef, target: PortRef, carrying=...)`
- on compile, validates references (e.g. nested `battery.power_out` resolves against the child type’s compiled definition), recursively compiles referenced part types, and emits a canonical structure

### Typed references (`Ref`) and nested member access

Cross-part references avoid the “metaclass / descriptor trap” (class body has no live instances, so naive `battery.power_out` attributes do not work). The preferred pattern:

- `battery = model.part("battery", Battery)` returns a **`PartRef`**
- `battery.power_out` is resolved by the framework via **`PartRef.__getattr__`**, using **`Battery`’s compiled definition** to produce a **`PortRef`** with path `("battery", "power_out")` (and similarly for nested parts)

So the authoring surface stays **Pythonic and typed**, without pretending declarations are already materialized objects.

### Illustrative structural definition

```python
class Battery(Part):
    @classmethod
    def define(cls, model):
        model.attribute("charge", unit="%")
        model.port("power_out", direction="out")


class Motor(Part):
    @classmethod
    def define(cls, model):
        model.port("power_in", direction="in")
        model.attribute("torque", unit="N*m")


class DriveSystem(System):
    @classmethod
    def define(cls, model):
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)
        model.connect(
            source=battery.power_out,
            target=motor.power_in,
            carrying="electrical_power",
        )
```

Compilation is triggered by the framework (e.g. `DriveSystem._compile_once()` in the sketch) and is idempotent per process for a given type under the current prototype’s rules.

### What is not settled by the prototype

The sketch does **not** yet demonstrate everything the **library** now covers. Relative to the sketch:

- **Configured instances** — implemented via `instantiate(root_type)` → `ConfiguredModel` in `tg_model` (not the sketch’s ad hoc materializer).
- **Behavioral nodes through `model`** — **Phase 6:** `state`, `event`, `action`, `guard`, `transition`, `scenario`, `sequence`, `decision`, `merge`, `fork_join`, `item_kind`, plus inter-part **`emit_item`** over `connect`, are implemented in `tg_model`.
- **Constraints, `computed_by`, roll-ups** — wired in the real `compile_graph` / `Evaluator` pipeline (see contract freeze), not the sketch alone.
- **Execution** — synchronous value evaluation and Phase 6 `dispatch_event` / scenario trace validation run on live `RunContext`; product-shaped `system.evaluate(...)` / `execute_scenario(...)` sugar remains directional.

Remaining gaps stay aligned with [logical architecture](logical_architecture.md), [execution methodology](execution_methodology.md), and [behavior methodology](behavior_methodology.md).

## Core Element Types

Proposed top-level authoring types:

- `Element`
- `System`
- `Part`
- `Requirement`
- `Interface`
- `Port`
- `Action`
- `Decision`
- `Merge`
- `Fork`
- `Join`
- `State`
- `Transition`
- `Guard`
- `Event`
- `Item`
- `Scenario`

The intent is:

- `Element` is the abstract base
- `System` and `Part` are the main structural authoring types
- `Action`, `State`, `Event`, and `Item` are first-class behavioral node types
- the rest are specialized semantic types

## Core Declaration Functions

**Structural v0 direction:** the primary declaration surface is **`model.<verb>(...)`** on `ModelDefinitionContext` inside `define(cls, model)` — e.g. `model.part(...)`, `model.port(...)`, `model.connect(...)`. Optional top-level functions (if any) would be thin conveniences; the authoritative recording point is `model`.

Proposed verbs / decorators (final names may differ):

**On `model` (definition time), validated for parts/ports/attributes/connect in the prototype:**

- `model.part()` (no args: **PartRef** to this root block, no child declared) / `model.part(name, part_type, ...)` (child part)
- `model.port(name, ...)`
- `model.attribute(name, ...)`
- `model.connect(source_port_ref, target_port_ref, carrying=...)`

**On `model` (value + behavior subset implemented in `tg_model`):**

- `model.parameter(...)` / `model.attribute(...)` / `model.constraint(...)` / `model.solve_group(...)` / `model.allocate(...)` / `model.requirement(...)` / `model.choice(...)` (as implemented in the package; some names remain directional in docs)
- **Phase 6 (discrete behavior):** `model.state` / `event` / `action` / `guard` / `transition` / `scenario` / `sequence` / `decision` / `merge` / `fork_join` / `item_kind` — see [Behavioral Modeling](#behavioral-modeling)

**Companion / future (not yet `model.*` in the library):**

- separate first-class **`Fork`** / **`Join`** nodes distinct from the bundled **`fork_join`** block (if ever split for notation)

**Execution and studies (not part of `define`):**

- `configure(...)` / `instantiate(...)` (configured topology; exact product spelling may vary)
- `sweep(...)` and related analysis APIs live under **`tg_model.analysis`** (see [Analysis API](#analysis-api))
- `constraint` / `computed_by(...)` (may attach at definition time via `model` or decorators — TBD)
- `solve_group(...)` (may attach through `model`, a declaration object, or companion hook — TBD)

These declarations should be enough to cover the primary use cases without forcing users into imperative graph construction.

For v0, **`connect`** (whether spelled `model.connect` or re-exported) is the preferred authoring primitive for structural linkage. If carried flow semantics are needed, they should be expressed through the connection declaration rather than requiring a second top-level `flow(...)` verb in the common path.

## Identity API

Direction:

- every declaration supports optional **stable identity** metadata (explicit id and/or deterministic derivation)
- if no explicit id is provided, identity is derived deterministically from the **definition path** and configuration context (exact algorithm TBD; must stay stable across regenerations for ThunderGraph-style citation continuity)

Illustrative shape inside `define`:

```python
class DriveSystem(System):
    @classmethod
    def define(cls, model):
        main_battery = model.part("main_battery", Battery, id="main_battery")  # illustrative kw
```

Type-level identity (if needed) might remain a class attribute or metaclass concern separate from instance identity:

```python
class Battery(Part):
    __type_id__ = "battery_type"  # illustrative
```

If no explicit ID is supplied for a nested part, fallback identity would still be traceable via paths such as:

- `DriveSystem.main_battery` (definition scope)
- plus configuration discriminator when variants exist (instance scope — **under design**)

This document does not finalize the exact syntax for explicit IDs. It only establishes that the API must support them and that **`Ref` paths and declaration names** are inputs to deterministic identity.

## Structural Authoring

**Preferred v0 shape** (aligned with [`model_prototype_sketch.py`](model_prototype_sketch.py)):

```python
class PowerInterface(Interface):
    @classmethod
    def define(cls, model):
        model.attribute("voltage", unit=V)
        model.attribute("current", unit=A)


class Battery(Part):
    @classmethod
    def define(cls, model):
        model.attribute("charge", unit=percent)
        model.port("power_out", direction="out")  # interface typing TBD


class Motor(Part):
    @classmethod
    def define(cls, model):
        model.port("power_in", direction="in")
        model.attribute("torque", unit=N * m, quantity_kind="torque")


class DriveSystem(System):
    @classmethod
    def define(cls, model):
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)
        model.connect(
            source=battery.power_out,
            target=motor.power_in,
            carrying="electrical_power",
        )
```

Why this shape:

- it is declarative and runs inside one obvious hook (`define`)
- it is readable and maps cleanly to a compiled graph
- it gives LLMs one obvious place to emit declarations
- nested references (`battery.power_out`) work via **`PartRef` + compiled child definition**, not via class-body descriptors

## Typed references vs “stringly” or class-body wiring

Cross-element references should use **`Ref` objects** returned from `model` (and chained from `PartRef`), not ad hoc strings and not pretend instance attributes on the class.

This direction:

- avoids the metaclass/descriptor trap for structural wiring
- keeps connections inspectable as structured objects (owner type, path, kind, metadata)
- preserves enough information for export, validation, and (later) instance binding

## Requirements And Allocation

Requirements are first-class nodes. **`model.allocate(requirement, target)`** records traceability from a requirement to a model element (typically a part).

When the requirement’s **`expr=`** only references attributes on the **configured root** type, use **`rocket = model.part()`** (no arguments — does not declare a child) then **`model.allocate(requirement, rocket)`**, same pattern as **`model.part("name", Type)`** for children. That ref has an **empty path**; **`instantiate`** resolves it to the **root** **`PartInstance`**. Shortcut: **`model.allocate_to_root(requirement)`**. **`root_block()`** / **`owner_part()`** are aliases of the same ref as **`model.part()`**.

### Acceptance expression (Phase 7)

Optional **`expr=`** on **`model.requirement(...)`** attaches an executable acceptance criterion (same expression family as **`model.constraint(expr=...)`**). Symbols in **`expr`** must be **`parameter` / `attribute` refs** from **`model`**. Resolution rules:

- Refs authored on the **same type** as the `allocate()` call site use paths from that type’s root (e.g. `motor.shaft_power` on a system). The compiler strips the allocate target’s path under the configured root and evaluates the remainder on the **allocated** `PartInstance`.
- Refs owned by the **allocate target’s part type** use paths relative to that part (e.g. `shaft_power` inside `Motor.define`) and resolve directly from the allocate target.

A requirement **with** **`expr=`** must have **at least one** **`model.allocate(...)`** from that requirement. **`compile_graph`** emits dependency nodes (same evaluator path as part constraints). After **`Evaluator.evaluate`**, use **`summarize_requirement_satisfaction(run_result)`** for **`check_count`** and **`all_passed`**, or **`iter_requirement_satisfaction`** for the list. **`all_requirements_satisfied(run_result)`** is **`False`** when **no** acceptance checks ran (so “nothing compiled to verify” is not mistaken for success). **`ConstraintResult`** entries from acceptance checks set **`requirement_path`** / **`allocation_target_path`**.

Allocate target for acceptance must be a **`PartInstance`** (not a port-only handle).

Symbol owner matching for acceptance resolution uses the same **type object identity** as definition-time refs (`is`); duplicate or reloaded model classes can break resolution — treat models as stable within a process.

```python
class DriveSystem(System):
    @classmethod
    def define(cls, model):
        motor = model.part("motor", Motor)
        shall_positive_power = model.requirement(
            "shall_positive_power",
            "Motor shall deliver positive shaft power.",
            expr=motor.shaft_power > Quantity(0, N * m / s),
        )
        model.allocate(shall_positive_power, motor)
```

## Citations And References (Phase 8)

**Citations** are first-class definition nodes: **`model.citation(name, **metadata)`** returns a **`Ref`** with **`kind="citation"`**. Store optional well-known keys in metadata (e.g. **`title`**, **`doi`**, **`url`**, **`standard_id`**, **`clause`**, **`revision`**, free-text **`notes`**) — v0 does not enforce a fixed schema beyond **JSON-serializable** metadata on compile.

**`model.references(source, citation)`** records a **`references`** edge from any **declared** element on the same type (**`source`** `Ref`) to a **citation** `Ref`. The target must be **`kind="citation"`**. Multiple **`references`** edges from the same owner are allowed.

- **Compile:** **`citation`** appears in **`nodes`**; each **`references`** edge appears in **`edges`** with **`kind: "references"`**, **`source`/`target`** as **`to_dict()`** payloads (same pattern as **`allocate`**).
- **Instantiation:** **`instantiate`** builds **`ElementInstance`** rows for **`citation`** (and **`constraint`**, for reference sources) and attaches **`ConfiguredModel.references`**: a list of **`ReferenceBinding`** (**`source`**, **`citation`**) with resolved instance paths.
- **Execution:** citations do **not** participate in **`compile_graph` / `Evaluator`** in v0.

Orthogonal to Phase 7: a **requirement** may have both **`expr=`** (acceptance) and **`references(...)`** (provenance).

```python
std = model.citation("asme_v", title="ASME Section V", standard_id="BPVC-V-2023")
req = model.requirement("weld_inspect", "Welds shall be inspected per code.", expr=...)
model.references(req, std)
```

## Parameters And Attributes

Direction:

- `parameter(...)` represents externally supplied, sweepable, unit-aware inputs
- `attribute(...)` represents stateful or derived model properties

Illustrative shape inside `define`:

```python
class Motor(Part):
    @classmethod
    def define(cls, model):
        model.parameter("shaft_speed", unit=rpm)
        model.attribute("shaft_torque", unit=N * m, quantity_kind="torque")
        model.attribute("shaft_power", unit=W)
```

(Class-body `Motor.shaft_speed = …` remains a readable **semantic** illustration elsewhere in this doc until those sections are migrated.)

This distinction supports:

- strict input control
- sweep definition
- clearer dependency planning
- cleaner modeling semantics

## Constraints

Constraints should remain synchronous and operate over realized values.

**Attachment to definitions** (decorator on a method, registration on `model`, or separate constraint object) is not fixed yet. Illustrative class-body style:

```python
class Motor(Part):
    shaft_speed = parameter(unit=rpm)
    shaft_torque = attribute(unit=N * m, quantity_kind="torque")
    shaft_power = attribute(unit=W)

    @constraint
    def power_balance(self):
        return self.shaft_power == self.shaft_torque * self.shaft_speed.to(rad / s)
```

The authoring rule is simple:

- constraints do not perform async work
- constraints do not launch external jobs
- constraints do not tolerate unresolved required values
- constraints validate designs; they are not the engine's general equation-solving mechanism

## Computed Attributes

Computed attributes are where external or async realization enters the model. **Binding** this to `define` / `model` is still open; the example below shows intended semantics.

Illustrative direction:

```python
class Motor(Part):
    max_temp = parameter(unit=degC)
    ambient_temp = parameter(unit=degC)
    power_in = attribute(unit=W)
    operating_temp = attribute(
        unit=degC,
        computed_by=computed_by(
            backend="openfoam",
            job="steady_state_thermal",
            inputs={
                "power": power_in,
                "ambient": ambient_temp,
            },
        ),
    )

    @constraint
    def thermal_check(self):
        return self.operating_temp < self.max_temp
```

This keeps the authoring DSL declarative while allowing the execution subsystem to orchestrate external realization.

## Solve Groups

Some engineering relationships are not just directed computations. They are equation sets where one or more variables must be solved from declared givens.

Preferred v0 direction:

- keep **directed derived attributes** as the default path
- keep **roll-ups** as first-class structural computations
- support **explicit solve groups** for coupled or implicit relationships
- do **not** treat every equality-like constraint as an automatic solve request

Illustrative direction:

```python
class Motor(Part):
    shaft_power = attribute(unit=W)
    shaft_speed = attribute(unit=rpm)
    shaft_torque = attribute(unit=N * m, quantity_kind="torque")

    power_balance = solve_group(
        equations=[
            shaft_power == shaft_torque * shaft_speed.to(rad / s),
        ],
        unknowns=[shaft_torque],
        givens=[shaft_power, shaft_speed],
    )
```

This document does not lock the final syntax. It does lock the execution distinction:

- directed expressions compute declared outputs from known inputs
- roll-ups aggregate configured child values
- solve groups solve explicit equation sets for explicit unknowns
- constraints validate realized results

## Roll-Ups

Roll-ups are core semantics, not analysis-only helpers.

**Instance and selector binding:** expressions like `self.parts()` or `children_of(Aircraft)` assume a **configured instance** or a well-defined structural scope at evaluation time. That scope is **not** specified by the current structural prototype; treat roll-up examples as **semantic targets** for how roll-ups should behave once instance realization exists.

Authoring should feel recursive over the structural tree and should avoid both fragile string paths and manually maintained giant addition expressions wherever possible.

```python
class Aircraft(Part):
    fuselage = part(Fuselage)
    left_wing = part(Wing)
    right_wing = part(Wing)
    left_tail_fin = part(TailFin)
    right_tail_fin = part(TailFin)
    total_mass = attribute(unit=kg)

    @computed_by
    def total_mass(self):
        return rollup.sum(
            self.parts(),
            value=lambda child: child.mass,
        )
```

This direction is preferred over manually listing every child in the equation because:

- it follows the actual structural hierarchy
- it automatically includes newly added children that match the selection scope
- it reduces the risk of silent under-counting when the structure changes

If a dedicated helper is preferred at class declaration time, it should still be structural and non-stringly-typed.

```python
class Aircraft(Part):
    fuselage = part(Fuselage)
    left_wing = part(Wing)
    right_wing = part(Wing)
    left_tail_fin = part(TailFin)
    right_tail_fin = part(TailFin)

    total_mass = attribute(
        unit=kg,
        computed_by=rollup.sum(
            children_of(Aircraft),
            value=lambda child: child.mass,
        ),
    )
```

This document does not lock the final syntax.

It does lock the expectation that:

- roll-ups are modeled explicitly
- missing required children cause failure
- roll-ups compile into explicit execution dependencies
- roll-ups should prefer structural selectors or explicit object references over fragile string selectors
- structural roll-up declarations should compile into an explicit dependency set for the instantiated configuration being evaluated

## Variants

Variants must be configuration-aware and independent.

The API should distinguish between:

- declaring a variation point
- instantiating a concrete configuration that selects an option

Preferred direction (likely expressed on `model` in `define`; spelling TBD):

```python
class DriveSystem(System):
    @classmethod
    def define(cls, model):
        model.choice(
            "propulsion",
            battery=BatteryDriveSystem,
            fuel_cell=FuelCellDriveSystem,
        )
```

Earlier class-body style for the same idea:

```python
class DriveSystem(System):
    propulsion = choice(
        battery=part(BatteryDriveSystem),
        fuel_cell=part(FuelCellDriveSystem),
    )
```

Then instantiate concrete configurations explicitly:

```python
battery_variant = configure(DriveSystem, propulsion="battery")
fuel_cell_variant = configure(DriveSystem, propulsion="fuel_cell")
```

These configurations are independent instantiated model configurations.

That matters because:

- each configuration may compile its own dependency graph
- variant comparison is an analysis concern, not a single-run execution concern
- allocations and roll-ups may differ by configuration

Illustrative multi-variant comparison (library shape: **labeled scenarios**, not a product `variants=` list):

```python
from tg_model.analysis import compare_variants, compare_variants_async

# cm_battery / cm_fuel are independent ConfiguredModel instances (how you obtain them is product/configuration-specific).
rows = compare_variants(
    scenarios=[
        ("battery", cm_battery, {cm_battery.motor.torque.stable_id: ..., ...}),  # inputs: stable_id -> value
        ("fuel_cell", cm_fuel, {cm_fuel.motor.torque.stable_id: ..., ...}),
    ],
    output_paths=["DriveSystem.motor.shaft_power"],  # path strings via ConfiguredModel.handle
    validate_before_run=True,
    require_same_root_definition_type=True,  # optional: reject mixed root definition types
)
# rows[i].outputs[path] is CapturedSlotOutput: .value, .present_in_run_outputs, .result (RunResult)
```

This document does not yet finalize whether the declaration primitive should be named `choice(...)`, `variant(...)`, or something else. The key point is that variation must be declared in the model and resolved into independent configurations before execution.

## Behavioral Modeling

Behavior is not deferred. It is a core part of the v0 API problem space.

**Authoring status:** the **executable v0** path for discrete **state machines** is **`define(cls, model)`** only — see **Phase 6 (implemented)** below. Deeper examples in this section that use **class-body** `state()` / `transition()` / `sequence()` / `fork()` are **illustrative** for methodology and future control-flow APIs; they are **not** the current library surface unless noted.

### Phase 6 (implemented): discrete behavior on `RunContext`

Authoring uses **`ModelDefinitionContext`** during `define(cls, model)`:

| Concept | Verb | Notes |
|--------|------|--------|
| State | `model.state(name, initial=False)` | Exactly **one** `initial=True` when any states exist on the type |
| Event | `model.event(name)` | Discrete trigger label |
| Action | `model.action(name, effect=callable \| None)` | Optional `effect(run_context, part_instance) -> None` |
| Guard | `model.guard(name, predicate=callable)` | First-class guard; use on **`transition(..., guard=)`** or in **`decision`** branches |
| Transition | `model.transition(..., when= \| guard=, effect=)` | `when` XOR `guard`; `effect` is action **name** |
| Sequence | `model.sequence(name, steps=[...])` | Linear action names; **`dispatch_sequence`** |
| Decision / Merge | `model.decision(..., merge_point=)` / `model.merge(..., then_action=)` | Exclusive branches; optional compile-time merge pairing |
| Fork / Join | `model.fork_join(name, branches=[...], then_action=)` | Deterministic v0 branch order; **`dispatch_fork_join`** |
| Item kind | `model.item_kind(name)` | Declared kinds for **`emit_item`** |
| Scenario | `model.scenario(..., expected_interaction_order=, expected_item_kind_order=, ...)` | See **`validate_scenario_trace`** |

**Compile-time rules (v0):**

- At most **one** transition per **(from_state, event)** pair (deterministic dispatch).
- Any `effect="action_name"` on a transition must match a declared `model.action("action_name", ...)`.
- The compiled artifact includes a sanitized `behavior_transitions` list; the Python type also holds live **`_tg_behavior_spec`** for runtime (includes callables). Tests reset with `Element._reset_compilation()`.

**Runtime (same `RunContext` as values):** see [Discrete behavior dispatch](#discrete-behavior-dispatch-phase-6) under [Execution API](#execution-api).

**Explicitly out of scope (methodology):** continuous physical time, wall-clock scheduling — see [behavior_methodology.md](behavior_methodology.md). **Pixel/HTML diagram renderers** are product-side; the library supplies **`behavior_authoring_projection`** and **`behavior_trace_to_records`** as semantic hooks.

## Behavioral Node Types

### Actions

`Action` represents a reusable or concrete behavioral step.

Illustrative authoring:

```python
class MotorController(Part):
    request_power = action()
    energize_motor = action()
    confirm_torque = action()
```

Actions should be allocatable, traceable, and referenceable by transitions, control-flow nodes, and scenarios.

### Control-Flow Nodes

Branching and parallelism are real behavioral requirements and should be explicit in the API.

Relevant nodes:

- `Decision`
- `Merge`
- `Fork`
- `Join`

Illustrative direction:

```python
class StartupLogic(Part):
    request_power = action()
    self_test = action()
    energize_motor = action()
    report_fault = action()
    confirm_torque = action()

    startup_ok = guard(lambda self: self.self_test_passed)

    startup_flow = sequence(
        request_power,
        self_test,
        decision(
            when=startup_ok,
            then=energize_motor,
            otherwise=report_fault,
        ),
        merge(),
        confirm_torque,
    )
```

And for parallel control flow:

```python
class MonitorLogic(Part):
    sample_temperature = action()
    sample_voltage = action()
    sample_current = action()
    compute_health = action()

    monitoring_flow = sequence(
        fork(
            sample_temperature,
            sample_voltage,
            sample_current,
        ),
        join(),
        compute_health,
    )
```

This aligns the API with the methodology’s explicit control-flow vocabulary instead of hiding branches in ad hoc code.

### States

`State` represents a modeled discrete condition or mode of a part or system.

Illustrative authoring:

```python
class MotorController(Part):
    off = state(initial=True)
    starting = state()
    running = state()
    failed = state()
```

States should be first-class nodes so they can be:

- referenced by transitions
- included in graph export
- linked to requirements or analyses
- inspected during sequence validation

### Transitions

`Transition` represents a state-to-state change with trigger, optional guard, and optional effect semantics.

Illustrative authoring:

```python
class MotorController(Part):
    off = state(initial=True)
    starting = state()
    running = state()
    failed = state()

    start_command = event()
    startup_complete = event()
    fault_detected = event()

    start_allowed = guard(lambda self: self.power_available)
    startup_healthy = guard(lambda self: self.self_test_passed)

    request_power = action()
    confirm_torque = action()
    report_fault = action()

    t_start = transition(
        off,
        starting,
        on=start_command,
        when=start_allowed,
        effect=request_power,
    )
    t_run = transition(
        starting,
        running,
        on=startup_complete,
        when=startup_healthy,
        effect=confirm_torque,
    )
    t_fail = transition(
        starting,
        failed,
        on=fault_detected,
        effect=report_fault,
    )
```

This keeps transitions explicit and inspectable.

### Guards

`Guard` is the behavioral routing primitive used by both `Transition` and `Decision`.

Illustrative direction:

```python
start_allowed = guard(lambda self: self.power_available)
startup_healthy = guard(lambda self: self.self_test_passed)
```

This reflects the methodology distinction:

- guards route behavior prospectively
- constraints validate results retrospectively

### Events

`Event` is the first-class trigger concept in the behavioral API.

Illustrative authoring:

```python
class MotorController(Part):
    start_command = event()
    startup_complete = event()
    fault_detected = event()
```

Events may come from:

- external scenario injection
- arrival of an item at a port
- internal behavioral emission

### Items

`Item` is the first-class payload concept for inter-part interaction.

Illustrative authoring:

```python
class CommandPacket(Item):
    command_code = attribute(unit=None)


class StatusPacket(Item):
    status_code = attribute(unit=None)
```

Items are what sequence diagrams should trace across ports and flows.

## Behavioral Relationships

The API should make the relationships between behavioral nodes explicit.

Important behavioral relationships include:

- action ownership by a part or system
- intra-part action sequencing
- decision branch selection
- merge continuation
- forked parallel branches
- join synchronization
- state ownership by a part or system
- state-to-state transition
- event-to-transition binding
- event-to-action binding
- item movement across ports and flows
- scenario-defined intended ordering

This keeps behavior semantically explicit in the same way that structure is explicit.

## Scenarios And Operational Sequences

`Scenario` is the authored behavioral contract, while an execution trace is the runtime result.

Illustrative direction:

```python
class MotorController(Part):
    request_power = action()
    energize_motor = action()
    confirm_torque = action()

    off = state(initial=True)
    starting = state()
    running = state()

    start_command = event()
    startup_complete = event()

    t_start = transition(off, starting, on=start_command, effect=request_power)
    t_run = transition(starting, running, on=startup_complete, effect=energize_motor)

    power_applied = event()
    torque_available = event()

    startup_scenario = scenario(
        parts=[self],
        events=[start_command, startup_complete],
        expected_order=[
            start_command,
            power_applied,
            torque_available,
        ],
    )
```

This direction gives `tg-model` a way to represent:

- intended behavioral order
- expected interactions
- expected state or action progression

without requiring a full continuous-time simulation framework.

For the common case of a linear intra-part control flow, the API should still support a simple `sequence(...)` helper.

Preferred direction:

```python
startup_flow = sequence(
    start_command,
    power_applied,
    torque_available,
)
```

Important distinction:

- `sequence(...)` is the simple intra-part control-flow helper
- `scenario(...)` is the authored contract for expected behavioral interaction over time

More complex branching or graph-shaped scenarios may still require a richer `scenario(...)` form, but the default path should optimize for simple sequential authoring where appropriate.

## Proposed Behavioral Example

Illustrative shape:

```python
class EngineController(Part):
    command_in = port(CommandInterface, direction="in")
    status_out = port(StatusInterface, direction="out")

    receive_start = action()
    run_self_test = action()
    report_running = action()
    report_fault = action()

    off = state(initial=True)
    starting = state()
    running = state()
    failed = state()

    start_command = event()
    startup_complete = event()
    fault_detected = event()

    startup_ok = guard(lambda self: self.self_test_passed)

    t_start = transition(off, starting, on=start_command, effect=receive_start)
    t_run = transition(starting, running, on=startup_complete, when=startup_ok, effect=report_running)
    t_fail = transition(starting, failed, on=fault_detected, effect=report_fault)

    startup_flow = sequence(
        receive_start,
        run_self_test,
        decision(
            when=startup_ok,
            then=report_running,
            otherwise=report_fault,
        ),
        merge(),
    )
```

This is a better fit for the current mission than a tiny anonymous `StateMachine(...)` blob because it keeps mode logic, control flow, events, and effects explicit and graphable.

## Execution API

**Where the lifecycle is specified:** public calls like `evaluate` / `validate` / `compile` sit on top of an **execution pipeline** (type compile → configuration → instance graph → configuration-scoped dependency graph → static validation → resolution → constraints). See [execution_methodology.md](execution_methodology.md) for the engine methodology; this section stays **API-shaped** only.

The execution API should operate on **instantiated configurations**. How instances are constructed from compiled definitions (`DriveSystem(...)`, `configure(...)`, factory methods, etc.) is **under active design** but constrained by that methodology.

Core direction (illustrative):

```python
system = DriveSystem()  # or configure(DriveSystem, ...) — API TBD
result = await system.evaluate(inputs={...}, backend=...)
```

Proposed primary entry points:

- `evaluate(...)`
- `validate(...)`
- `compile(...)`
- `execute_scenario(...)`
- `validate_scenario(...)`

Illustrative shapes:

```python
compiled = system.compile()
```

```python
result = await system.evaluate(
    inputs={
        "battery.voltage": 400 * V,
        "load.torque": 80 * (N * m),
    },
    backend=my_backend,
)
```

```python
report = await system.validate(
    inputs={
        "battery.voltage": 400 * V,
    },
    backend=my_backend,
)
```

```python
trace = await system.execute_scenario(
    scenario=system.startup_scenario,
    backend=my_backend,
)
```

```python
scenario_report = await system.validate_scenario(
    scenario=system.startup_scenario,
    backend=my_backend,
)
```

Expected semantics:

- `compile()` performs model/configuration preparation and pre-execution validation
- `evaluate()` resolves values
- `validate()` evaluates compliance over realized values
- `execute_scenario()` produces an execution trace for an authored scenario
- `validate_scenario()` evaluates authored scenario expectations against modeled behavior and/or runtime trace

This document does not yet decide whether `validate()` always implies `evaluate()` internally or can operate over a pre-resolved state.

### Discrete behavior dispatch (Phase 6)

**Module:** `tg_model.execution.behavior` (re-exported from `tg_model.execution`).

Discrete events are applied to a **`PartInstance`** using the same per-run **`RunContext`** as `Evaluator`.

**Scope (guards, predicates, and effects):** transition **`when`** guards, **decision** branch predicates, and **action** effects run under the same **subtree** rules: **`get_or_create_record`**, **`bind_input`**, **`get_value`**, **`realize`**, **`mark_pending`**, **`get_state`**, and discrete **behavior state** for paths on the **active part subtree** — **API discipline**, not a Python sandbox (callables can still close over **`ConfiguredModel`**). Item payload staging is not subtree-scoped (inter-part delivery).

- **`dispatch_event(...)`** returns **`DispatchResult`** with **`DispatchOutcome`**: **`FIRED`**, **`NO_MATCH`**, or **`GUARD_FAILED`**. **`bool(result)`** is true only when **`FIRED`**.
- **`dispatch_decision(...)`** returns **`DecisionDispatchResult`** / **`DecisionDispatchOutcome`** (**`ACTION_RAN`** vs **`NO_ACTION`**); **`bool(result)`** is true when an action ran. Use **`merge_point=`** on the decision to pair a merge; do not also **`dispatch_merge`** that merge on the same path.
- **Commit order:** active state is set to the **target** state **before** the transition **effect** runs; guards run **before** any state change. If an effect raises, the active state is **rolled back** (no **`BehaviorStep`** recorded).
- **Activity control-flow:** **`dispatch_sequence`**, **`dispatch_decision`**, **`dispatch_merge`**, **`dispatch_fork_join`** (v0: **serial** branch order, not parallel scheduling); **`emit_item`** walks **`cm.connections` in list order** for multiple matches.
- **`validate_scenario_trace`** applies **independent** checks (transition list per part, optional states, **`trace_events_chronological`** = transitions only, optional item-kind order). Passing all checks does not by itself prove full causal equivalence to intent.
- **`behavior_authoring_projection(definition_type)`** — projection for tools (serialized edges/refs per **`compile()`**); not a frozen JSON schema for every metadata field.
- **`behavior_trace_to_records`** flattens **`BehaviorTrace`** for export.
- **`BehaviorTrace`** uses **`PartInstance.path_string`** and declared **event names** (not **`ValueSlot.stable_id`**).

```python
from tg_model.execution import (
    BehaviorTrace,
    DecisionDispatchOutcome,
    DispatchOutcome,
    dispatch_decision,
    dispatch_event,
    validate_scenario_trace,
    instantiate,
    RunContext,
)

cm = instantiate(MotorController)  # root or navigate to a nested part, e.g. host.ctrl
ctx = RunContext()
trace = BehaviorTrace()

assert dispatch_event(ctx, cm, "start_command", trace=trace).outcome is DispatchOutcome.FIRED

# ``decision_name`` must match a ``model.decision(...)`` on this part type (illustrative).
r = dispatch_decision(ctx, cm, "route", trace=trace)
assert r.outcome in (DecisionDispatchOutcome.ACTION_RAN, DecisionDispatchOutcome.NO_ACTION)
assert bool(r) == (r.chosen_action is not None)

ok, errors = validate_scenario_trace(
    definition_type=MotorController,
    scenario_name="startup",
    part_path=cm.path_string,
    trace=trace,
)
```

**`RunContext`** also tracks current mode: **`get_active_behavior_state(part_path_string)`** / **`set_active_behavior_state(part_path_string, state_name)`** (keys are **`PartInstance.path_string`**).

**`BehaviorTrace`** holds ordered **`BehaviorStep`** records (part path, event, from/to state, effect name).

Product-level **`execute_scenario(...)`** / **`validate_scenario(...)`** on a configured system object remain **directional**; the primitives above are the **library** executable surface for Phase 6.

## Analysis API

**Package:** `tg_model.analysis` (Phase 5). Analysis **orchestrates** runs; **single-run** semantics remain `Evaluator` + `compile_graph` + `RunContext`.

Stable **instance-side** handles for studies are **`ValueSlot`** objects (and `stable_id` strings where `evaluate`/`compare_variants` inputs expect a map). Paths for outputs use **`ConfiguredModel.handle(path)`** / `ValueSlot.path_string`, aligned with [Frozen decision 3](#frozen-decision-3-ref-to-handle-mapping).

### `sweep` (synchronous)

```python
from tg_model.analysis import sweep, SweepRecord
from tg_model.execution.configured_model import instantiate
from tg_model.execution.graph_compiler import compile_graph

cm = instantiate(DriveSystem)
graph, handlers = compile_graph(cm)

records = sweep(
    graph=graph,
    handlers=handlers,
    parameter_values={
        cm.battery.voltage: [350 * V, 400 * V, 450 * V],
        cm.motor.shaft_speed: [2000 * rpm, 3000 * rpm],
    },
    configured_model=cm,       # optional but recommended: validates slots vs graph
    prune_to_slots=None,       # optional: upstream closure only — see warning below
    collect=True,              # False => return [] and require sink (large studies)
    sink=None,                 # optional: callable(SweepRecord) per sample
)
```

Semantics:

- **Cartesian product** over `parameter_values` (keys are **`ValueSlot`**; axis order is deterministic by `stable_id`).
- **`configured_model`:** when provided, verifies each sweep (and prune) slot is registered on `cm` and that `val:<slot.path_string>` exists in `graph` (i.e. `graph` came from **`compile_graph(cm)`**).
- **`prune_to_slots`:** if set, evaluation uses the **upstream dependency closure** needed to realize those slots only. Nodes outside that subgraph — including typical **constraint** nodes not in the closure — are **not** executed; **`RunResult.constraint_results` may be empty**. Do **not** treat a pruned sweep as a compliance run unless you explicitly accept what was cut.
- **`collect` / `sink`:** when `collect=False`, the returned list is empty and **`sink` is required**; use this to avoid retaining every `SweepRecord` while still observing each run.
- **Throughput:** samples run **sequentially**; this is not a parallel study runner.

### `sweep_async`

Same parameters as `sweep`, except **`configured_model` is required** (async external evaluation). Uses `Evaluator.evaluate_async` per sample. Async variant: **`async def sweep_async(...)`**.

### `compare_variants` / `compare_variants_async`

```python
from tg_model.analysis import compare_variants, compare_variants_async, CapturedSlotOutput, CompareVariantsValidationError

rows = compare_variants(
    scenarios=[
        ("battery", cm_battery, {slot_id: value, ...}),
        ("fuel_cell", cm_fuel, {slot_id: value, ...}),
    ],
    output_paths=["DriveSystem.motor.shaft_power"],
    validate_before_run=True,              # default: validate_graph(graph, configured_model=cm) first
    require_same_root_definition_type=False,
)
# rows[i].outputs[path] -> CapturedSlotOutput: .value, .present_in_run_outputs, .realized; plus .result (RunResult)
```

Semantics:

- Each scenario: **`compile_graph(cm)`** → optional **static validation** (default on) → **`evaluate`** / **`evaluate_async`** with a **fresh** `RunContext`.
- **`CompareVariantsValidationError`** if `validate_graph` fails for that scenario’s label.
- **`CapturedSlotOutput`** separates “slot absent from `RunResult.outputs`” (`present_in_run_outputs=False`) from a stored value; interpret failures via **`VariantComparisonRow.result`**.
- **`require_same_root_definition_type=True`:** all `cm.root.definition_type` must match the first scenario (guards against accidental path-aligned but semantically different roots).

### Value-graph propagation (`dependency_impact`)

**Not** full program “impact” or FMEA — only **transitive closure** on the compiled **value dependency graph**:

```python
from tg_model.analysis import dependency_impact, value_graph_propagation, impact, ImpactReport

rep: ImpactReport = dependency_impact(
    graph,
    [cm.battery.voltage],
    upstream=True,
    downstream=True,
)
# rep.upstream_slot_ids, rep.downstream_slot_ids (seed slots excluded from both sets)
```

- **`dependency_impact`** is the explicit name; **`value_graph_propagation`** is an alias; **`impact`** is a short alias — all denote the same function.
- Requires the same **`DependencyGraph`** you use for evaluation (typically from **`compile_graph(cm)`**).

### Expected semantics (summary)

- Analysis defines **multi-run intent**; execution still performs **one run at a time** through the existing evaluator.
- Prefer **concrete** `ValueSlot` / path handles from the relevant **`ConfiguredModel`** when specifying inputs and outputs.

## Integration API

The integration API should define how external analyses are bound and invoked.

The v0 public direction should probably stay minimal.

Likely concepts:

- backend object
- adapter registration
- computed attribute binding

Illustrative direction:

```python
backend = SimulationBackend(...)

result = await system.evaluate(backend=backend)
```

The **binding protocol** for `computed_by` external work is **frozen** under [Frozen decision 5](#frozen-decision-5-external-computation-binding-phase-4-gate). Product-specific registration, job queues, and `evaluate(backend=...)` sugar remain non-final.

## Export API

Export remains in scope, but detailed export shape is deliberately deferred.

The public entry point should likely remain simple:

```python
graph = system.to_graph(kind="architecture")
```

Possible `kind` values:

- `"definition"`
- `"architecture"`
- `"state"`

This document does not finalize the exact export schema.

## End-to-End Examples

## Example 1: Structural + Constraint Model

Structural wiring uses **`define` + `model`** (validated direction). Constraints and parameters below still use the **illustrative class-body** style until constraint registration is merged into the same hook.

```python
from tg_model import System, Part, Interface, Requirement, constraint
from unitflow import V, A, W, N, m, percent, rpm, rad, s


class PowerInterface(Interface):
    @classmethod
    def define(cls, model):
        model.attribute("voltage", unit=V)
        model.attribute("current", unit=A)


class Battery(Part):
    @classmethod
    def define(cls, model):
        model.attribute("charge", unit=percent)
        model.parameter("voltage", unit=V)
        model.port("power_out", direction="out")

    @constraint
    def charge_valid(self):
        return 0 <= self.charge <= 100


class Motor(Part):
    @classmethod
    def define(cls, model):
        model.parameter("shaft_speed", unit=rpm)
        model.attribute("shaft_torque", unit=N * m, quantity_kind="torque")
        model.attribute("shaft_power", unit=W)
        model.port("power_in", direction="in")

    @constraint
    def power_balance(self):
        return self.shaft_power == self.shaft_torque * self.shaft_speed.to(rad / s)


class DriveSystem(System):
    @classmethod
    def define(cls, model):
        shall_provide_propulsion = model.requirement(
            "shall_provide_propulsion",
            "The drive system shall provide propulsion torque.",
        )
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)
        model.connect(
            source=battery.power_out,
            target=motor.power_in,
            carrying="electrical_power",
        )
        model.allocate(shall_provide_propulsion, motor)
```

## Example 2: Computed Attribute With External Realization

```python
class ThermalMotor(Part):
    max_temp = parameter(unit=degC)
    ambient_temp = parameter(unit=degC)
    power_in = attribute(unit=W)
    operating_temp = attribute(
        unit=degC,
        computed_by=computed_by(
            backend="openfoam",
            job="steady_state_thermal",
            inputs={
                "power": power_in,
                "ambient": ambient_temp,
            },
        ),
    )

    @constraint
    def thermal_check(self):
        return self.operating_temp < self.max_temp
```

## Example 3: Parametric Study

```python
from tg_model.analysis import sweep
from tg_model.execution.configured_model import instantiate
from tg_model.execution.graph_compiler import compile_graph

cm = instantiate(DriveSystem)
graph, handlers = compile_graph(cm)

records = sweep(
    graph=graph,
    handlers=handlers,
    parameter_values={
        cm.battery.voltage: [350 * V, 400 * V, 450 * V],
        cm.motor.shaft_speed: [2000 * rpm, 3000 * rpm],
    },
    configured_model=cm,
    sink=my_sink,  # optional: called per SweepRecord; use collect=False to avoid storing all records
)
# Full outputs per run: records[i].result.outputs (and constraint results on the full graph)
```

## Example 4: Behavioral Model (Phase 6 — `define` + dispatch)

**Library v0:** state machine in `define`; no class-body `state`/`transition` decorators.

```python
from tg_model.execution import (
    BehaviorTrace,
    DispatchOutcome,
    RunContext,
    dispatch_event,
    instantiate,
    validate_scenario_trace,
)
from tg_model.model.elements import Part


class MotorController(Part):
    @classmethod
    def define(cls, model):  # type: ignore[override]
        model.parameter("self_test_passed", unit="1")  # illustrative flag

        def do_request_power(ctx, part):
            ctx.bind_input(part.self_test_passed.stable_id, True)

        request_power = model.action("request_power", effect=do_request_power)
        confirm_torque = model.action("confirm_torque")
        report_fault = model.action("report_fault")

        off = model.state("off", initial=True)
        starting = model.state("starting")
        running = model.state("running")
        failed = model.state("failed")

        start_command = model.event("start_command")
        startup_complete = model.event("startup_complete")
        fault_detected = model.event("fault_detected")

        model.transition(off, starting, on=start_command, effect="request_power")
        model.transition(
            starting,
            running,
            on=startup_complete,
            when=lambda ctx, part: bool(ctx.get_value(part.self_test_passed.stable_id)),
            effect="confirm_torque",
        )
        model.transition(starting, failed, on=fault_detected, effect="report_fault")

        model.scenario("startup", expected_event_order=[start_command, startup_complete])
```

Runtime (same `RunContext` you use with `Evaluator`):

```python
cm = instantiate(MotorController)
ctx = RunContext()
trace = BehaviorTrace()
assert dispatch_event(ctx, cm, "start_command", trace=trace).outcome is DispatchOutcome.FIRED
assert dispatch_event(ctx, cm, "startup_complete", trace=trace).outcome is DispatchOutcome.FIRED
ok, errors = validate_scenario_trace(
    definition_type=MotorController,
    scenario_name="startup",
    part_path=cm.path_string,
    trace=trace,
)
assert ok
```

Class-body examples elsewhere that show `sequence` / `decision` without `model.` remain **illustrative**; the **library** surface is `model.sequence` / `model.decision` / … as in [Behavioral Modeling](#behavioral-modeling).

## Example 5: Variant Configuration

```python
class DriveSystem(System):
    @classmethod
    def define(cls, model):
        model.choice(
            "propulsion",
            battery=BatteryDriveSystem,
            fuel_cell=FuelCellDriveSystem,
        )


battery_variant = configure(DriveSystem, propulsion="battery")
fuel_cell_variant = configure(DriveSystem, propulsion="fuel_cell")
```

`configure(...)` and instance construction remain **directional** until configured-instance semantics are specified.

## Contract Freeze: Value Authoring And Handle Mapping

This section records the **locked** authoring decisions that govern Phases 2–4. These replace earlier illustrative class-body patterns. They are the binding contract for implementation.

### Frozen decision 1: Value construct taxonomy

All value-bearing constructs are authored through **`model.*`** methods on `ModelDefinitionContext` during `define(cls, model)`.

| Construct | Verb | Produces value? | Expression? |
|-----------|------|----------------|-------------|
| parameter | `model.parameter(name, ...)` | externally bound input | no |
| attribute (bare) | `model.attribute(name, ...)` | slot for realized value | no |
| attribute (derived) | `model.attribute(name, ..., expr=...)` | yes, from local expression | `unitflow` expression |
| attribute (roll-up) | `model.attribute(name, ..., expr=rollup.sum(...))` | yes, from structural aggregation | roll-up expression |
| attribute (external) | `model.attribute(name, ..., computed_by=...)` | yes, from external compute | `ExternalComputeBinding` |
| constraint | `model.constraint(name, expr=...)` | assessment (pass/fail) | predicate expression |
| solve group | `model.solve_group(name, equations=[...], unknowns=[...], givens=[...])` | solved unknowns | equation set |

Key rules:

- **An attribute is an attribute** regardless of how it gets its value. Roll-ups are derived attributes with structural-selector expressions, not a separate concept.
- **Parameters** are externally bindable inputs (sweepable). They do not have expressions.
- **Constraints** produce assessment results, not engineering values. They are not the solving mechanism.
- **Solve groups** are explicit declarations. The engine does not infer solve semantics from constraints.

**Root parameters in nested `define()`:** nested part types do not automatically see the parent `model` object from the configured root. To wire `ExternalComputeBinding.inputs` (or expressions) to **scenario / mission parameters** declared on the **configured root** block type, use **`parameter_ref(root_block_type, "param_name")`** or **`model.parameter_ref(root_block_type, "param_name")`**. Resolution uses the root type’s compiled artifact if it is already compiled, or the active definition context while that root’s `compile()` is still running—so **declare root parameters before** `model.part(...)` for children that reference them. At evaluation time, refs whose `owner_type` is the configured root resolve against `ConfiguredModel.root` (same rule as other cross-scope refs).

**Nested requirements (`RequirementBlock`):** subclass **`RequirementBlock`** and implement **`define(cls, model)`** with **`model.requirement`**, **`model.requirement_input`**, **`model.requirement_accept_expr`**, **`model.citation`**, nested **`model.requirement_block`**, and **`model.references`** (compile-time validation rejects other node kinds and non-`references` edges). Prefer **`requirement_input(requirement_ref, "name", unit=…)`** then **`requirement_accept_expr(requirement_ref, expr=…)`** so acceptance symbols are **requirement-local**; on the configured root, **`model.allocate(req_ref, part_ref, inputs={"name": part_ref.slot, …})`** wires each input to a realized parameter or attribute. You can still pass **`expr=`** directly on **`model.requirement`** for the older pattern (symbols on the root or allocate target). From a **`Part`** or **`System`** `define()`, register a subtree with **`model.requirement_block("name", MyRequirementBlockType)`**, which returns a **`RequirementBlockRef`**; use **dot notation** to reach child requirements (same chaining pattern as **`PartRef`**). **`requirement_ref(root_block_type, ("block", "nested_req"))`** (or **`model.requirement_ref`**) resolves a requirement **`Ref`** by full path from the configured root—use from nested **`Part.define()`** when you cannot chain from a **`RequirementBlockRef`**. Declare **`requirement_block`** entries **before** sibling parts that call **`requirement_ref`**, because blocks are **compiled eagerly** when registered (with the correct symbol anchor for nested blocks). **`model.allocate`** from a nested requirement uses a **`Ref`** whose **`path`** is the **full** tuple (e.g. **`("mission", "range")`**); requirement acceptance validation matches **full paths**, not leaf names only.

### Frozen decision 2: Single authoring surface

**All declarations go through `model.*` methods in `define(cls, model)`.** There are no decorator-based or class-body alternatives for value constructs.

This means:

- constraints are `model.constraint(...)`, not `@constraint` decorators
- computed attributes use `model.attribute(..., computed_by=...)`, not class-body assignments
- solve groups are `model.solve_group(...)`, not implicit equation inference

One authoring path. One recording mechanism. One compilation pipeline.

Illustrative locked shape:

```python
class Motor(Part):
    @classmethod
    def define(cls, model):
        speed = model.parameter("shaft_speed", unit=rpm)
        torque = model.attribute("shaft_torque", unit=N * m)
        power = model.attribute("shaft_power", unit=W, expr=torque * speed)

        model.constraint("power_positive", expr=power > Quantity(0, W))


class Aircraft(System):
    @classmethod
    def define(cls, model):
        fuselage = model.part("fuselage", Fuselage)
        left_wing = model.part("left_wing", Wing)
        right_wing = model.part("right_wing", Wing)

        total_mass = model.attribute(
            "total_mass",
            unit=kg,
            expr=rollup.sum(model.parts(), value=lambda c: c.mass),
        )
```

### Frozen decision 3: Ref-to-handle mapping

At definition time, `model.*` methods return **`Ref` objects** (`PartRef`, `PortRef`, `AttributeRef`). At instance time, configured models expose **handles** for navigation and binding.

The mapping rule:

- the `ConfiguredModel` maintains two internal registries: `path -> handle` and `stable_id -> handle`
- **attribute projection** (`drive.battery.voltage`) is ergonomic sugar that delegates to the path registry
- **explicit lookup** (`drive.handle("battery.voltage")`) is always available
- both resolve to the same underlying handle object
- handles are the stable interface used by `evaluate`, analysis (`sweep` keys **`ValueSlot`**; value-graph propagation takes **`ValueSlot`** + **`DependencyGraph`**), and export

This means:

- definition-time `Ref` paths directly mirror instance-time handle paths (rooted under the configured root)
- the path registry is the canonical navigation mechanism
- attribute projection is a convenience, not a separate system

### Frozen decision 4: Minimum synchronous execution API (Phase 3)

The library’s **single-run synchronous** path is locked as follows (names map to current modules; signatures may gain optional parameters but must remain backward compatible within v0):

- **Topology:** `instantiate(root_type) -> ConfiguredModel` — immutable configured instance graph; navigation via attribute projection and `handle(path)`.
- **Planning:** `compile_graph(cm) -> (DependencyGraph, handlers)` — only public graph-compilation entry; builds value and compute nodes from authored semantics.
- **Static validation:** `validate_graph(graph) -> ValidationResult` — cycles, orphan compute nodes, empty roll-ups, solve-group integrity, duplicate slot writers, etc.
- **Run state:** `RunContext` — per-run, keyed by `ValueSlot.stable_id`; inputs bound with `bind_input(slot_id, value)`. **Phase 6:** same `RunContext` holds **active discrete state** per `PartInstance.path_string` via `get_active_behavior_state` / `set_active_behavior_state` for `dispatch_event`.
- **Evaluation:** `Evaluator(graph, compute_handlers=handlers).evaluate(ctx, inputs=...)` — topological walk; materializes derived values, roll-ups, solve groups, constraints.
- **Phase 6 behavior:** `dispatch_event`, `BehaviorTrace`, `validate_scenario_trace` in `tg_model.execution.behavior` (see [Discrete behavior dispatch](#discrete-behavior-dispatch-phase-6)); not a second value engine.

Constraint evaluation is **part of** `evaluate` (constraint nodes in the graph), not a separate meaning of “validation.” `validate_graph` is **pre-execution** structural/graph integrity.

### Frozen decision 5: External computation binding (Phase 4 gate)

This freezes **contract item 5**: how `computed_by=` binds external work without polluting the declarative authoring model.

#### Naming (avoid generic “adapter”)

| Concept | Public name |
|--------|-------------|
| Implementation object (protocol) | **`ExternalCompute`** |
| Binding declaration (what `computed_by=` accepts) | **`ExternalComputeBinding`** |
| Structured return from one run | **`ExternalComputeResult`** |
| Optional static checks before run | **`ValidatableExternalCompute`** (optional protocol; not required for every backend) |

#### `ExternalCompute` protocol

- **`name: str`** — provenance and errors (human-readable id).
- **`compute(self, inputs: dict[str, Quantity]) -> ExternalComputeResult`** — synchronous body; may block (e.g. local subprocess). Implementations are **library-only**; no product networking assumptions.

Optional async variant for Phase 4:

- **`AsyncExternalCompute`** — same inputs, **`async def compute(...) -> ExternalComputeResult`**. The synchronous **`Evaluator` must not** be turned into an async soup; async orchestration lives in a **separate** entry point (e.g. `AsyncEvaluator` / `evaluate_async`) that can drive **`SlotState.PENDING`** (or equivalent) until results arrive.

**Sync vs async dispatch (frozen):**

- **`ExternalCompute.compute`** is a **normal function**; **`AsyncExternalCompute.compute`** is a **coroutine function**.
- The synchronous **`Evaluator` / `compile_graph` consumer** **MUST** reject async externals **fail-fast** (e.g. `inspect.iscoroutinefunction(obj.compute)` or an explicit capability flag on the binding) with a **clear error** — never “call and drop the coroutine.”
- Only **`AsyncEvaluator`** (or equivalent) may invoke **`AsyncExternalCompute`**. Authors choose one protocol per backend object; **mixing** sync and async **`compute`** on the same object is **invalid**.

#### `ExternalComputeResult` (structured value)

```text
@dataclass(frozen=True)
class ExternalComputeResult:
    value: Quantity | Mapping[str, Quantity]
    provenance: Mapping[str, Any]
```

- **`value`** is either a single **`Quantity`** or a **`Mapping[str, Quantity]`** (e.g. one simulation run feeding several scalar extracts). Future v0.x may extend the union (e.g. typed arrays) only with an explicit second freeze.
- For **`Mapping[str, Quantity]`**, **key equality is a set property**: match is **exactly** the set of keys in **`output_routes`** (when fan-out); **iteration order of the `Mapping` is not semantic**.
- **`provenance`** is **one blob per external run** (shared by all fan-out slots from that run). Per-output lineage is **out of scope** for this freeze.

#### `ExternalComputeBinding`

Binds one **`ExternalCompute`** to **named inputs** (`AttributeRef` → graph edges from those value slots) and defines how **`ExternalComputeResult.value`** maps to one or more attribute slots.

- **`external: ExternalCompute | AsyncExternalCompute`** — see **Sync vs async dispatch** above; it is **invalid** to use an async object with the sync evaluator.
- **`inputs: dict[str, AttributeRef]`** — keys are **implementation-local** argument names; values must be **`AttributeRef`** (or parameter refs surfaced as `AttributeRef`) usable in **`define(cls, model)`** for the **same** `cls`. **Precise locality rule:** every such ref’s **`owner_type`** must be **`cls`** (the type whose definition context records the binding). **Nested member refs** (e.g. `battery.charge` via `PartRef` projection) **are allowed** and **still** use the **parent** type as `owner_type` in the current `tg_model` reference model — i.e. they are **not** “foreign” refs from another top-level type. This matches how expression **`free_symbols`** resolve today.
- **`output_routes: dict[str, AttributeRef] | None`**
  - **`None` (default):** single-slot binding. Used as `computed_by=ExternalComputeBinding(...)` on **one** `model.attribute`. **`ExternalComputeResult.value` must be a `Quantity`**. That attribute’s slot is the only sink.
  - **Non-`None`:** multi-slot fan-out. **`ExternalComputeResult.value` must be a `Mapping[str, Quantity]`** whose **key set equals** `output_routes.keys()`. The graph compiler emits **one** external-compute node and **realizes every** `AttributeRef` in `output_routes.values()` from that single run.

**Multi-output + `computed_by` (frozen compiler / authoring invariant):**

- **One graph node** per distinct **`ExternalComputeBinding` instance** (`id(binding)`), not per attribute line.
- **Every** attribute slot that receives a fan-out value **MUST** record **`computed_by=b`** for **the same object** `b` (Python **identity**). The compiler **MUST** coalesce those lines into **one** external-compute node and **MUST** verify that **`output_routes`** is **consistent** with those declarations (each routed ref corresponds to an attribute whose `computed_by` is that same `b`).
- **Chicken-and-egg** (binding needs `AttributeRef`s, refs need `computed_by=b`): today’s **`model.attribute`** does not support a second pass. **Normative:** Phase 4 **SHALL** ship **some** authoring affordance (helper on `model`, factory, or equivalent) so multi-output bindings can be constructed **without** duplicate declarations or illegal forward references. Until that exists, **only single-slot** (`output_routes is None`) is **guaranteed** ergonomic. The **semantic** rules above still apply once the helper exists.

`model.attribute(..., computed_by=...)` remains the **attachment point** for **`computed_by`** on each participating attribute; multi-output sugar is listed under [Remaining Open Questions](#remaining-open-questions).

#### Graph integration (locked)

- New compute node kind (name implementation-defined, e.g. **`EXTERNAL_COMPUTATION`**) sits in the same bipartite graph as expressions, roll-ups, and solve groups.
- Dependencies: value nodes for every input ref; dependents: one or many attribute value slots per **`output_routes`** / single slot default.
- Fail-fast if a binding references missing backends or impossible routes (Phase 4 implementation).

#### `ValidatableExternalCompute` (optional)

If an object implements this protocol, **`validate_graph`** (or a dedicated pre-pass) may call **`validate_binding`** **before** any external call. This is **not** constraint evaluation; it is **static** contract checking. Objects that do not implement it are trusted at compile time.

**v0 hook shape (minimal freeze):**

```text
def validate_binding(
    self,
    *,
    input_specs: Mapping[str, Any],
    output_specs: Mapping[str, Any],
) -> None
```

- **`input_specs` / `output_specs`** — maps logical names to **engine-defined** descriptors (e.g. declared dimensions/units/metadata from compile). **Exact descriptor types are not frozen** in v0; only the **keyword-only** names and **“raise on failure”** behavior are.
- **Success:** return **`None`**. **Failure:** raise **`ValueError`** or a **`ExternalComputeValidationError`** subclass. Interoperable **cross-backend** validation beyond this is **deferred** until a later freeze tightens descriptor types.

## Remaining Open Questions

These are intentionally deferred past the contract freeze:

- What is the final syntax for explicit IDs?
- Should `choice(...)` remain the declaration form for variants, or should the API use a different variation primitive?
- Should `compile()` be explicit, implicit, or both?
- Should **value-graph propagation** (`dependency_impact` / `impact` in `tg_model.analysis`) gain sugar on **`ConfiguredModel`** (e.g. `cm.dependency_impact(...)`) in addition to the graph-first API?
- What is the exact API boundary between `Action`, `Event`, `Item`, and `Scenario`?
- How should authored scenario ordering, branching, and failure paths be represented?
- How much should the top-level `tg_model` package re-export versus asking users to import from submodules?
- **Required** authoring affordance for multi-output `ExternalComputeBinding` (helper / factory on `model` or equivalent) so `output_routes` and per-attribute `computed_by` can be wired **without** forward-reference hacks — **normative** for Phase 4 per Frozen decision 5

## Proposed Review Criteria

This API proposal should be judged against the following questions:

1. Can an LLM generate this reliably?
2. Can a power user read and refine it without hating it?
3. Does it directly satisfy the current use cases and conceptual requirements?
4. Does it preserve the architecture decisions already made?
5. Does it avoid pretending `tg-model` is a full product rather than a library?
6. Is the contract freeze section consistent with the implementation plan and execution methodology?
