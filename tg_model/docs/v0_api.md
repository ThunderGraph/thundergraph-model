# tg-model v0 API Design

## Purpose

This document proposes the first concrete public API shape for `tg-model`.

It is a v0 API proposal, not a final specification.

**Authoring status (major v0 direction):** the preferred structural authoring path is a framework-managed `@classmethod def define(cls, model)` hook and a `ModelDefinitionContext` (`model`) that records declarations and returns typed reference objects. That direction is **validated** (for typed part/port/attribute declaration and `connect` capture) by the early prototype in [`model_prototype_sketch.py`](model_prototype_sketch.py). **Configured instance graphs**, **behavioral compilation**, and **runtime execution semantics** remain under active design; parts of this document still show illustrative class-body or instance APIs that will converge on the same hook.

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
- [Execution API](#execution-api)
- [Execution engine methodology (separate doc)](execution_methodology.md)
- [Analysis API](#analysis-api)
- [Integration API](#integration-api)
- [Export API](#export-api)
- [End-to-End Examples](#end-to-end-examples)
- [Open Questions](#open-questions)

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
- complete behavioral/state-machine semantics
- complete adapter interface details
- how compiled type definitions become **configured instances** (the “`DriveSystem()` / `configure(...)`” shapes below are directional, not locked)
- the final mapping from definition-time `Ref` objects to instance-time handles used by evaluation, sweeps, and export

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
    choice,
    configure,
    computed_by,
    sweep,
)
```

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

The sketch does **not** yet demonstrate:

- materializing **configured instances** from definitions (parameters, variant selection, identity at instance scope)
- **behavioral** nodes (`action`, `state`, `transition`, …) through `model`
- **constraints**, **computed_by**, and **roll-ups** wired into the same compile pipeline
- **execution** (`evaluate`, `validate`, scenarios) against live instance state

Those remain API design targets, consistent with [logical architecture](logical_architecture.md), [execution methodology](execution_methodology.md), and [behavior methodology](behavior_methodology.md).

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

- `model.part(name, part_type, ...)`
- `model.port(name, ...)`
- `model.attribute(name, ...)`
- `model.connect(source_port_ref, target_port_ref, carrying=...)`

**On `model` or companion hooks (specified later, not in the structural prototype):**

- `model.parameter(...)` / `model.allocate(...)` / `model.requirement(...)` / `model.choice(...)` (illustrative)
- `model.action(...)` / `model.state(...)` / `model.transition(...)` / `model.guard(...)` / `model.event(...)` / `model.item(...)` / `model.scenario(...)` / `sequence(...)` / `decision(...)` / `merge(...)` / `fork(...)` / `join(...)`

**Execution and studies (not part of `define`):**

- `configure(...)`
- `sweep(...)`
- `constraint` / `computed_by(...)` (may attach at definition time via `model` or decorators — TBD)

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

Requirements should be first-class model elements. **Illustrative** `define`-time shape (API not in the structural prototype yet):

```python
class DriveSystem(System):
    @classmethod
    def define(cls, model):
        shall_provide_propulsion = model.requirement(
            "shall_provide_propulsion",
            "The drive system shall provide propulsion torque.",
        )
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)
        model.connect(source=battery.power_out, target=motor.power_in)
        model.allocate(shall_provide_propulsion, motor)
```

This v0 proposal assumes allocation can live in a system/configuration context, not only inside reusable part definitions.

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

Illustrative multi-variant comparison:

```python
comparison = await compare_variants(
    variants=[
        configure(DriveSystem, propulsion="battery"),
        configure(DriveSystem, propulsion="fuel_cell"),
    ],
    criteria=["compliance", "total_mass", "power_margin"],
    backend=my_backend,
)
```

This document does not yet finalize whether the declaration primitive should be named `choice(...)`, `variant(...)`, or something else. The key point is that variation must be declared in the model and resolved into independent configurations before execution.

## Behavioral Modeling

Behavior is not deferred. It is a core part of the v0 API problem space.

**Authoring note:** the examples in this section still use **class-body** declarations (`action()`, `state()`, …) for readability. The **target** is the same as structure: record behavioral nodes through **`define(cls, model)`** (or a dedicated companion hook) so declarations, references, and compilation stay framework-managed. Behavioral compilation and validation are **not** covered by the current structural prototype.

Direction:

- support actions as first-class behavioral nodes
- support explicit control-flow nodes for branching and parallelism
- support states as first-class behavioral nodes
- support guards as first-class behavioral routing conditions
- support transitions as first-class behavioral relationships
- support events as first-class triggers
- support items as first-class interaction payloads
- support scenarios as authored contracts for behavioral intent
- support discrete operational sequences and behavioral validation
- do not imply a full continuous-time simulation environment

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

## Analysis API

The analysis API should coordinate multi-run workflows while reusing single-run execution. Study APIs will need stable **instance-side** handles for parameters and attributes; those may mirror definition-time `Ref`s or expose a parallel reference type — **TBD**.

Proposed primary entry points:

- `sweep(...)`
- `compare_variants(...)`
- `impact(...)`

Illustrative direction:

```python
drive = configure(DriveSystem, propulsion="battery")

results = await sweep(
    system=drive,
    inputs={
        drive.battery.voltage: [350 * V, 400 * V, 450 * V],
        drive.motor.shaft_speed: [2000 * rpm, 3000 * rpm],
    },
    outputs=[
        drive.motor.shaft_torque,
        "compliance",
    ],
    sink=my_sink,
)
```

```python
comparison = await compare_variants(
    variants=[
        configure(DriveSystem, propulsion="battery"),
        configure(DriveSystem, propulsion="fuel_cell"),
    ],
    criteria=["compliance", "total_mass", "power_margin"],
    backend=my_backend,
)
```

```python
impact = system.impact(changed=[system.battery.voltage])
```

Expected semantics:

- analysis defines multi-run intent
- execution performs the runs
- results are streamable
- analysis should prefer concrete configured instance references when selecting study inputs and outputs

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

This document intentionally does not finalize the adapter protocol.

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
drive = configure(DriveSystem, propulsion="battery")

results = await sweep(
    system=drive,
    inputs={
        drive.battery.voltage: [350 * V, 400 * V, 450 * V],
        drive.motor.shaft_speed: [2000 * rpm, 3000 * rpm],
    },
    outputs=[drive.motor.shaft_torque, "compliance"],
    sink=my_sink,
)
```

## Example 4: Behavioral Model

```python
from tg_model import (
    Part,
    Action,
    State,
    Transition,
    Guard,
    Event,
    action,
    state,
    transition,
    guard,
    event,
    decision,
    merge,
    sequence,
    scenario,
)


class MotorController(Part):
    request_power = action()
    run_self_test = action()
    confirm_torque = action()
    report_fault = action()

    off = state(initial=True)
    starting = state()
    running = state()
    failed = state()

    start_command = event()
    startup_complete = event()
    fault_detected = event()

    startup_ok = guard(lambda self: self.self_test_passed)

    t_start = transition(off, starting, on=start_command, effect=request_power)
    t_run = transition(starting, running, on=startup_complete, when=startup_ok, effect=confirm_torque)
    t_fail = transition(starting, failed, on=fault_detected, effect=report_fault)

    startup_flow = sequence(
        request_power,
        run_self_test,
        decision(
            when=startup_ok,
            then=confirm_torque,
            otherwise=report_fault,
        ),
        merge(),
    )

    startup_scenario = scenario(
        parts=[self],
        events=[start_command, startup_complete],
        expected_order=[start_command, startup_complete],
    )
```

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

## Open Questions

- What is the final syntax for explicit IDs?
- How are **configured instances** materialized from compiled definitions, and how do they expose parameters/attributes for evaluation and sweeps?
- How do definition-time **`Ref` objects** map to instance-time handles (or parallel reference types) for `evaluate`, `sweep`, and export?
- Should `computed_by(...)` be a helper or an argument type?
- Should roll-ups use Python expressions, special helpers, or both?
- Should `choice(...)` remain the declaration form for variants, or should the API use a different variation primitive?
- Should `compile()` be explicit, implicit, or both?
- Should `impact(...)` live on instantiated systems, a separate analyzer, or both?
- What is the exact API boundary between `Action`, `Event`, `Item`, and `Scenario`?
- How should authored scenario ordering, branching, and failure paths be represented?
- What is the cleanest structural selector API for roll-ups over instantiated children?
- How should **constraints** and **computed_by** attach to types: `model` registration, decorators, or separate objects?
- How much should the top-level `tg_model` package re-export versus asking users to import from submodules?

## Proposed Review Criteria

This API proposal should be judged against the following questions:

1. Can an LLM generate this reliably?
2. Can a power user read and refine it without hating it?
3. Does it directly satisfy the current use cases and conceptual requirements?
4. Does it preserve the architecture decisions already made?
5. Does it avoid pretending `tg-model` is a full product rather than a library?
6. Is it clear which parts are **prototype-backed** (`define` + structural `Ref`s) versus **semantic targets** still being merged into that hook?
