# tg-model Brainstorm

## Purpose

`tg-model` is a standalone open source Python library for systems modeling, validation, and execution.

It is built on top of `unitflow`, which provides the engineering math substrate for units, quantities, dimensional reasoning, and symbolic constraints.

It is not ThunderGraph.
It does not depend on Neo4j.
It is not a frontend.
It is not a dashboard framework.

ThunderGraph may sit on top of `tg-model` as a proprietary application layer that provides document ingestion, collaborative workflows, graph persistence, agentic code generation, and UI experiences. But `tg-model` must be valuable on its own to engineers who never touch ThunderGraph.

Most systems engineers should not need to live in the Python source directly. In the broader ThunderGraph vision, the code is primarily authored by LLMs and refined by power users, while many engineers consume diagrams, traces, validation results, and graph views derived from that code.

## Core Vision

`tg-model` should preserve what is valuable about SysML v2 while replacing its terrible software ergonomics with a clean Python API.

It should pair a systems modeling DSL with a serious engineering math substrate, rather than treating math and units as an afterthought.

The library should support:

- Structural modeling
- Behavioral modeling
- Requirements and traceability
- Constraint and attribute evaluation
- Unit-safe parameters and attributes via `unitflow`
- Symbolic engineering equations and dimensional reasoning via `unitflow`
- Executable model validation
- Graph projection for downstream tools and UIs
- Parametric sweeps
- Async execution for external analysis and simulation backends

In short, `tg-model` should be an executable systems modeling library, not just a notation.

## Product Boundary

`tg-model` is the modeling and execution engine.

It should own:

- The Python DSL
- Integration of `unitflow` as the math foundation
- The semantic model
- Runtime evaluation
- Constraint execution
- Behavior execution
- Graph export
- Analysis interfaces
- Extension points for simulation and metamodel backends

It should not own:

- Neo4j persistence
- ThunderGraph project/workspace concepts
- Websocket/chat/task orchestration
- Frontend rendering
- Cluster-specific infrastructure code

ThunderGraph can build a proprietary bridge that maps `tg-model` graphs and execution results into Neo4j and UI-specific formats.

## Foundational Stack

`tg-model` should have a clear layered architecture:

- `unitflow` as the engineering math substrate
- `tg-model` as the systems modeling and execution layer
- ThunderGraph as an optional proprietary application layer on top

Responsibilities by layer:

- `unitflow`
- units
- quantities
- exact dimensional semantics
- symbolic variables and equations
- constraint expression building
- serialization of engineering math objects

- `tg-model`
- systems modeling DSL
- semantic object graph
- structure, behavior, requirements, and traceability
- async evaluation and validation
- sweep execution
- graph projection
- extension points for simulation and metamodel backends

- ThunderGraph
- document ingestion
- agentic generation workflows
- proprietary Neo4j bridge
- collaboration and UI

This separation is important. `unitflow` should be integral to `tg-model`, but `tg-model` still owns systems modeling semantics.

## Source Of Truth

The source of truth should be Python model code and the in-memory semantic object graph produced from that code.

Derived artifacts include:

- Graph exports
- Validation reports
- Simulation traces
- Sweep datasets
- Documentation
- Frontend visualization payloads
- ThunderGraph persistence projections

This is a deliberate break from the existing SysML flow where text must be parsed back into semantic state.

## Design Principles

- Favor explicit semantics over magic
- Keep the public API small and memorable
- Make authoring beautiful for engineers
- Make generation reliable for LLMs
- Make the DSL declarative enough that LLMs can generate it consistently
- Keep the primary user experience diagram- and result-friendly, even if the model is authored in Python
- Make engineering math first-class, not bolted on
- Separate model declaration from execution
- Separate structure changes from runtime state changes
- Preserve SysML concepts without importing SysML syntax baggage
- Prefer stable typed abstractions over stringly-typed graph assembly

## Key Domain Concepts

`tg-model` should keep the useful SysML concept categories:

- Parts
- Requirements
- Attributes
- Constraints
- Ports
- Interfaces
- Actions
- States
- Transitions
- Flows
- Compositions
- Aggregations
- Allocations

These should map to Python classes and declarations, not a text language that requires reparsing.

## UnitFlow As A Core Dependency

`unitflow` should be integral to `tg-model`, not an optional convenience package.

`tg-model` should rely on `unitflow` for:

- units
- quantities
- dimensional validation
- symbolic equations
- bounded engineering constraints
- serialization of engineering values
- sweep inputs and outputs

This means `tg-model` should not invent its own parallel unit system or symbolic math layer.

Instead:

- `unitflow` defines engineering math semantics
- `tg-model` defines system semantics

That separation is clean and powerful.

## Identity And Stable References

Stable identity is a hard requirement.

`tg-model` must support deterministic, stable identifiers for model elements so that:

- regenerated source code still maps to the same semantic elements
- graph exports can be merged rather than recreated blindly
- downstream systems can preserve comments, traceability, and external references
- subgraph regeneration does not destroy semantic continuity

This likely means each `Element` needs a stable identity derived from namespace, ownership path, or another deterministic scheme, rather than relying on ephemeral in-memory object identity.

## Naming Direction

Use `Element` as the abstract root type, but use more specific modeling nouns for public authoring.

Current preferred direction:

- `Element` as the universal base
- `System` as the top-level structural root
- `Part` as the main structural abstraction
- `Requirement`
- `Interface`
- `Port`
- `Attribute`
- `Constraint`
- `Action`
- `StateMachine`
- `State`
- `Transition`

`Part` is preferred over `Component` because it aligns better with systems engineering concepts and feels less tied to software architecture terminology.

## Public API Direction

The public API should be class-based and declarative, with explicit relationship verbs.

It should optimize for:

- LLM generation reliability
- readability for power users
- minimal ambiguity in how a concept can be expressed

High-level example:

```python
from tg_model import (
    System,
    Part,
    Requirement,
    Interface,
    part,
    attribute,
    port,
    connect,
    flow,
    allocate,
    constraint,
    action,
)
from unitflow import V, A, percent, N, m


class PowerInterface(Interface):
    voltage = attribute(unit=V)
    current = attribute(unit=A)


class Battery(Part):
    charge = attribute(unit=percent)
    power_out = port(PowerInterface, direction="out")

    @constraint
    def charge_valid(self):
        return 0 <= self.charge <= 100


class Motor(Part):
    torque = attribute(unit=N * m, quantity_kind="torque")
    power_in = port(PowerInterface, direction="in")
    spin_up = action()


class DriveSystem(System):
    shall_provide_propulsion = Requirement(
        "The drive system shall provide propulsion torque."
    )

    battery = part(Battery)
    motor = part(Motor)

    power_link = connect(battery.power_out, motor.power_in)
    power_flow = flow(battery.power_out, motor.power_in, item="electrical_power")
    propulsion_allocation = allocate(shall_provide_propulsion, motor)
```

This shape is intended to feel:

- Pythonic
- readable
- explicit
- reusable
- analyzable

It should also feel mathematically native. Engineers should be able to work with real units, real quantities, and real equations rather than strings and float conventions.

It should also have one obvious way to express the core modeling concepts, so LLMs do not drift across multiple competing idioms.

## Reuse Model

Reuse should come from:

- Inheritance
- Composition
- Reusable interfaces
- Reusable requirement sets
- Reusable behavior/state patterns
- Reusable engineering equations and constraint patterns backed by `unitflow`

The user should primarily extend `Part`, `System`, and other concrete modeling abstractions, not subclass `Element` directly for normal use.

## Relationship Direction

Relationships should be first-class semantic objects, not loose metadata.

Important relationship categories:

- Composition via `part(...)`
- Aggregation via something like `aggregate(...)`
- Connectivity via `connect(...)`
- Directional transfer via `flow(...)`
- Cross-cutting engineering traceability via `allocate(...)`
- State-to-state change via `Transition`
- Action sequencing through a behavior/scenario API

The public API should expose explicit verbs rather than forcing users to think in terms of generic graph edges.

## Model Structure vs Runtime State

Important distinction:

- Model structure should be defined in source code
- Runtime values and execution state should change in memory

Good runtime mutation:

- Attribute values changing
- Derived values being recomputed
- States transitioning
- Scenario events executing
- Constraints passing or failing

Good runtime math behavior:

- Unit-safe values being set on parameters and attributes
- Derived quantities being computed from `unitflow` expressions
- Constraints evaluating over quantities with dimensional correctness

Avoid in v0:

- Structural mutation of the model during runtime
- Dynamically adding/removing parts and relationships in normal execution

Architecture changes should happen by editing Python source and reloading the model.

In the ThunderGraph context, that source may often be generated or updated by an LLM, then reloaded into the semantic engine.

## Parametric Sweeps

Parametric sweeps are a first-class fit for `tg-model`.

Key idea:

- The architecture stays fixed
- Parameters vary across runs
- Each run evaluates the same model structure with different inputs
- Results are collected as datasets

This suggests a distinction between:

- `parameter(...)` for sweepable external inputs, often backed by `unitflow` quantities
- `attribute(...)` for model state and derived properties

Possible direction:

```python
results = await DriveSystem.sweep(
    inputs={
        "battery.voltage": [350.0, 400.0, 450.0],
        "motor.resistance": [0.10, 0.12, 0.15],
    },
    outputs=[
        "motor.torque",
        "battery.current",
        "constraints",
    ],
).run()
```

Each sweep point should ideally execute against a fresh model instance to avoid cross-run state leakage.

## Parameters, Attributes, And Engineering Math

One likely direction is:

- `parameter(...)` represents externally supplied, sweepable, unit-aware inputs
- `attribute(...)` represents stateful or derived model properties
- `constraint(...)` operates over parameters, attributes, and `unitflow` expressions

Possible direction:

```python
from unitflow import W, rpm, rad, s, N, m


class Motor(Part):
    shaft_speed = parameter(unit=rpm)
    shaft_torque = attribute(unit=N * m, quantity_kind="torque")
    shaft_power = attribute(unit=W)

    @constraint
    def power_balance(self):
        return self.shaft_power == self.shaft_torque * self.shaft_speed.to(rad / s)
```

This is a major part of the value proposition. `tg-model` should not just model system structure. It should support executable engineering reasoning over that structure.

## Async Execution

`tg-model` should be async-first in execution, even if it later provides sync convenience wrappers.

Reason:

- Constraint evaluation may depend on remote compute
- Simulations may run on clusters
- Metamodel-backed analysis may be async
- Long-running jobs may need submission, polling, and result retrieval

The modeling DSL itself should remain simple, declarative, and effectively synchronous from the author's point of view.

Important boundary:

- constraints should remain pure synchronous logic over realized values
- async behavior belongs in attribute or analysis resolution
- the evaluation engine owns orchestration, polling, retries, and concurrency

`unitflow` does not replace this runtime. It strengthens it by giving the runtime meaningful math objects to propagate and validate.

Likely execution model:

- Build a dependency graph
- Resolve local values
- Resolve computed attributes, including async external analyses where needed
- Parallelize independent branches
- Materialize realized values
- Evaluate constraints synchronously over those realized values
- Collect diagnostics, provenance, and outputs

Possible user-facing shape:

```python
result = await system.evaluate(
    inputs={
        "battery.voltage": 400.0,
        "load.torque": 80.0,
    },
    backend=my_backend,
)

report = await system.validate(backend=my_backend)
```

Possible declarative direction:

```python
class Motor(Part):
    max_temp = parameter(unit=degC)
    operating_temp = attribute(
        unit=degC,
        computed_by=Simulation(
            backend="openfoam",
            job="steady_state_thermal",
            inputs={"power": "power_in", "ambient": "ambient_temp"},
        ),
    )

    @constraint
    def thermal_check(self):
        return self.operating_temp < self.max_temp
```

## External Compute And Simulation Backends

`tg-model` should not contain cluster-specific logic, but it should define extension points for external compute.

Potential concepts:

- `compute(...)`
- `backend`
- `SimulationAdapter`
- `MetamodelAdapter`
- `Evaluator`
- `ModelicaAdapter`

The library should support:

- Pure local deterministic computation
- Async local/external calls
- Long-running job-backed execution

Those computations may produce or consume `unitflow` quantities, equations, and constraint values.

`tg-model` should not try to become a full-blown physics language or ODE-solving environment for very large continuous models.

For heavy simulation domains, the better strategy is likely orchestration and integration with specialized tools, including potential future Modelica-based workflows.

This means the runtime needs room for:

- submission
- polling
- result materialization
- retries
- timeouts
- failure reporting
- provenance capture

## Graph Representation

`tg-model` should represent systems semantically first, then export graph views as derived artifacts.

Important rule:

- Do not make a graph library the public modeling API

`networkx` may be useful internally or optionally for:

- dependency DAGs
- topological ordering
- cycle detection
- connectivity analysis
- impact tracing
- debug views

But the primary source of truth should remain domain objects and semantic relationships, not raw node/edge construction.

The public boundary should likely be a stable graph export schema rather than a leaked `networkx` object type.

Graph export should preserve engineering semantics where needed, including:

- units
- quantity kinds
- evaluated values
- constraint outcomes
- traceability metadata

## Why This Is Better Than SysML Text

Current SysML-based approaches suffer from:

- poor tooling
- fragile parsing
- weak execution semantics
- awkward authoring
- external validation dependency
- poor fit for LLM-native code generation

Python improves:

- authoring ergonomics
- runtime execution
- debugging
- testing
- introspection
- packaging
- reuse
- code generation quality from LLMs

`unitflow` further improves:

- dimensional correctness
- exact unit-aware calculations
- symbolic engineering equations
- stronger constraint semantics
- more trustworthy evaluation results

The goal is not "SysML but in Python syntax."

The goal is "an executable, opinionated, Python-native systems modeling language inspired by the good parts of SysML."

## v0 Direction

Probable v0 scope:

- Native `unitflow` integration
- Structural modeling with `System`, `Part`, `Interface`, `Port`
- Requirements and allocations
- Parameters, attributes, and constraints with engineering units
- Graph export
- Async evaluation
- Parametric sweeps
- Basic state/action support if it can stay simple
- Stable deterministic element identity

Probably not v0:

- Full SysML concept coverage
- Full interoperability/export to every SysML representation
- Arbitrary runtime structural mutation
- Full-blown HPC orchestration built into the library
- Massive continuous-physics solving for complex ODE systems
- Frontend/view rendering concerns

## Important Open Questions

- Should `parameter(...)` and `attribute(...)` be separate first-class concepts?
- How directly should the public API expose `unitflow` concepts versus wrapping them?
- Should actions and scenarios be separate concepts, or should `Action` cover both for v0?
- How much behavior support belongs in v0 versus later phases?
- What is the exact declarative API for computed attributes backed by external analysis?
- What is the exact runtime API for `evaluate()`, `validate()`, and `sweep()`?
- What is the right extension interface for long-running remote compute jobs?
- How opinionated should `tg-model` be about requiring units on parameters and attributes?
- What stable identity scheme should every `Element` use?
- Should graph export have multiple views, such as structure, behavior, and traceability?
- How should requirements satisfaction and verification be represented beyond allocation?

## Current Thesis

`tg-model` should be a standalone Python systems modeling library with:

- beautiful authoring ergonomics
- strong semantic typing
- `unitflow` as an integral engineering math foundation
- executable validation
- async-capable runtime execution
- graph projection for downstream tools

ThunderGraph can then become a product built on top of `tg-model`, rather than the thing that defines the modeling core.
