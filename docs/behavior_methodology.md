# tg-model Behavioral Modeling Methodology

## Purpose

This document defines the behavioral modeling methodology for `tg-model`.

The goal is to support the three behavioral views engineers actually care about:

- **Activity Diagrams** for functional/control flow
- **State Diagrams** for modes and transitions
- **Sequence Diagrams** for interactions between parts over time

**Related:** structural/value **execution lifecycle** (configuration, instantiation, dependency graph, evaluation) lives in [execution_methodology.md](execution_methodology.md). This document focuses on **behavioral** concepts and diagram views.

The methodology must:

- remain simpler than SysML v2
- stay executable
- align with the structural model of parts, ports, and flows
- avoid fragmented ontological nonsense
- still be rich enough to generate meaningful aerospace-grade behavioral views

## Table of Contents

- [Why SysML v2 Behavior Is Painful](#why-sysml-v2-behavior-is-painful)
- [Behavioral Design Goals](#behavioral-design-goals)
- [Core Behavioral Ontology](#core-behavioral-ontology)
- [Execution Hierarchy](#execution-hierarchy)
- [Time Semantics](#time-semantics)
- [Structural Boundaries](#structural-boundaries)
- [Scenario Model](#scenario-model)
- [Control-Flow Vocabulary](#control-flow-vocabulary)
- [Behavioral Views](#behavioral-views)
  - [Activity Diagrams](#activity-diagrams)
  - [State Diagrams](#state-diagrams)
  - [Sequence Diagrams](#sequence-diagrams)
- [Static Contract vs Runtime Trace](#static-contract-vs-runtime-trace)
- [Methodology Summary](#methodology-summary)

## Why SysML v2 Behavior Is Painful

SysML v2 behavior is fragmented across different semantic constructs that force users to describe the same intent multiple ways.

Examples:

- Activity-style behavior is expressed through action usages and successions.
- State behavior is expressed through state usages, transitions, and state-owned entry/do/exit actions.
- Sequence-style behavior is expressed through occurrence definitions, occurrence usages, messages, and flow bindings.

That fragmentation creates three problems:

1. The user or LLM has to duplicate intent across multiple constructs.
2. The execution model becomes much harder to reason about.
3. The diagrams stop being simple views over one behavioral truth and become partially disconnected authored artifacts.

`tg-model` should not reproduce that fragmentation.

## Behavioral Design Goals

The behavioral methodology should satisfy the following goals:

- use a small number of first-class concepts
- preserve clear separation between structure and behavior while still connecting them tightly
- support deterministic execution
- support both early-phase behavioral intent and later-phase executable validation
- allow generation of activity, state, and sequence diagrams from one underlying model

## Core Behavioral Ontology

The behavioral model should use the following first-class concepts.

### `Action`

An `Action` is a discrete unit of behavior that executes logic.

Responsibilities:

- consume inputs from attributes, ports, or events
- perform work
- produce outputs to attributes or ports

An `Action` is not a message, not a state, and not a transition.

### `Decision`

A `Decision` is a control-flow node that selects one behavioral path from multiple candidates.

Responsibilities:

- evaluate one or more `Guard` conditions
- select the next control-flow branch
- make branching explicit in the behavioral graph

Guard usage rule:

- a `Decision` uses the same `Guard` semantic primitive used by `Transition`
- the difference is context, not meaning
- in a `Transition`, the guard selects whether a state change is legal
- in a `Decision`, the guard selects which control-flow branch is taken

### `Merge`

A `Merge` is a control-flow node that reunites alternative branches without synchronization semantics.

Responsibilities:

- collect mutually exclusive alternative paths
- continue control flow after branching

### `Fork`

A `Fork` is a control-flow node that splits one path into multiple concurrent branches.

Responsibilities:

- create parallel execution branches
- make concurrency explicit in the behavioral graph

### `Join`

A `Join` is a control-flow node that synchronizes parallel branches before control continues.

Responsibilities:

- wait for required parallel branches to complete
- reunify concurrent execution paths

### `State`

A `State` is a discrete mode of a `Part`.

Responsibilities:

- define which mode the part is currently in
- constrain which transitions are valid
- influence which actions are allowed or triggered

### `Transition`

A `Transition` is a directed edge between states.

Responsibilities:

- respond to an `Event`
- optionally evaluate a `Guard`
- update the active `State`
- optionally trigger an `Action` as an effect

### `Guard`

A `Guard` is a behavioral routing condition used during execution.

Responsibilities:

- determine whether a transition or branch is allowed during runtime
- route control flow

A `Guard` should evaluate synchronously over the current realized state of the model.

Important distinction:

- a `Guard` is not a `Constraint`
- a `Constraint` checks validity
- a `Guard` selects behavior

This distinction is critical for keeping behavioral execution separate from compliance evaluation.

Further distinction:

- a `Guard` is evaluated prospectively to choose what happens next
- a `Constraint` is evaluated retrospectively to determine whether the resulting state is acceptable

### `Event`

An `Event` is a discrete trigger.

Examples:

- external command
- timer tick
- arrival of an item at a port
- internal signal produced by an action

### `Item`

An `Item` is the thing that moves across a behavioral interaction path.

Examples:

- command packet
- sensor measurement
- target track
- actuator setpoint
- power request

An `Item` is needed because a sequence diagram cannot just trace “stuff happened.” It must trace what moved, between whom, and in what order.

### `Scenario`

A `Scenario` is a defined behavioral thread.

Responsibilities:

- define intended ordering of events and/or actions
- define initial conditions
- define expected outcomes when needed

A `Scenario` is the bridge between authored intent and executable validation.

## Execution Hierarchy

Behavioral execution must follow a deterministic hierarchy.

Default runtime order:

1. An `Event` arrives at a `Part`.
2. If the `Part` has a relevant state machine, the engine evaluates matching `Transition` candidates.
3. Any `Guard` conditions for those transitions are evaluated.
4. If a valid `Transition` fires, the active `State` changes.
5. The `Transition` effect `Action`, if any, executes.
6. If the `Part` has no relevant state machine, the event may trigger an `Action` directly.
7. The `Action` updates attributes and/or writes `Item`s to ports.
8. Any `Item` written to a port propagates along structural flows.
9. The arrival of that item at the target port generates a new `Event` for the receiving part.

This hierarchy is important because it defines exactly how states, transitions, events, and actions interact.

## Time Semantics

`tg-model` v0 should use discrete logical time, not continuous physical time.

That means:

- behavioral execution proceeds in ordered logical steps
- `next` means the next event or execution step in the causal order
- sequence diagrams primarily represent causal order, not guaranteed wall-clock duration

Default v0 assumptions:

- actions execute in zero logical time unless explicitly modeled otherwise
- state transitions occur at a logical step boundary
- item propagation across flows preserves causal order
- external asynchronous analyses may block logical progress until a required value is realized

This is an intentional simplification.

It keeps the behavioral model executable and deterministic without pretending that `tg-model` is already a full real-time simulation environment.

### Why This Choice Matters

Without explicit time semantics, users may incorrectly assume that:

- actions imply physical duration by default
- sequence diagrams are time-accurate simulations
- concurrent branches imply continuous-time scheduling behavior

That would be misleading.

For v0:

- sequence diagrams should be understood as ordered interaction views
- activity diagrams should be understood as ordered control-flow views
- state diagrams should be understood as discrete mode-transition views

### Future Extension

This choice does not forbid richer timing semantics later.

Possible future extensions include:

- explicit delays
- logical clocks
- bounded timing constraints
- real-time scheduling semantics

But those should be added deliberately rather than implied accidentally.

### Parallel Semantics In v0

`Fork` and `Join` are necessary for modeling branching concurrency, but their meaning in v0 is intentionally constrained.

In v0:

- a `Fork` creates multiple logically independent branches
- those branches belong to the same behavioral stage unless the model introduces later timing semantics
- the engine may evaluate those branches in any implementation order that preserves deterministic outcomes
- a `Join` blocks downstream continuation until the required branches have completed

This means:

- `Fork` and `Join` support activity-graph concurrency semantics
- they do not, by themselves, imply physical-time overlap
- they do not imply hard real-time scheduling
- they do not imply a distributed concurrency model

That is enough to support rich activity diagrams and executable behavioral validation without overclaiming continuous-time behavior.

## Structural Boundaries

Behavior does not bypass structure.

That means:

- an `Action` inside `Part A` does not directly invoke an `Action` inside `Part B`
- inter-part interaction must happen through ports and structural flows
- the arrival of an `Item` at a receiving port becomes an `Event` for the receiving part

This rule preserves architectural integrity.

### Intra-Part vs Inter-Part Behavior

This distinction matters.

#### Intra-Part

Within a single part:

- actions may be sequenced directly
- actions may read and write local attributes
- actions may be triggered by local events or transitions

#### Inter-Part

Across part boundaries:

- interaction must be mediated by ports and flows
- actions cannot “teleport” control across the system boundary
- if one part influences another, the influence must appear as an item or event crossing the structural interface

## Control-Flow Vocabulary

`tg-model` should include a small explicit activity/control-flow vocabulary.

This vocabulary exists because branching and parallelism are real engineering needs, not optional syntactic decoration.

The key control-flow nodes are:

- `Action`
- `Decision`
- `Merge`
- `Fork`
- `Join`

These belong in the activity/control-flow layer, not the state layer.

Important distinction:

- `State`, `Transition`, and `Guard` define mode logic
- `Action`, `Decision`, `Merge`, `Fork`, and `Join` define activity/control-flow logic

This separation matters because state evolution and activity routing are related, but not identical.

### Why These Nodes Are Needed

Without explicit control-flow nodes, the methodology falls into bad alternatives:

- using `Constraint` objects to route execution
- hiding branching in ad hoc Python control flow
- pretending all behaviors are linear
- hand-waving away concurrency

That would make the model harder to analyze, harder to export, and less faithful to the actual engineering views users expect.

### Default Simplicity Rule

These nodes should not burden the simple case.

For most common paths:

- a linear `sequence` should be enough

Only when behavior actually branches or runs in parallel should the model need:

- `Decision`
- `Merge`
- `Fork`
- `Join`

### Relationship To Diagrams

In projected views:

- `Action`, `Decision`, `Merge`, `Fork`, and `Join` become activity-diagram nodes
- `State` and `Transition` become state-diagram nodes
- sequence diagrams are still derived from scenarios and interaction traces over ports and flows, not from these control nodes alone

## Scenario Model

`tg-model` should support two related but distinct scenario notions.

### 1. Authored Scenario

An Authored Scenario is the intended behavioral contract.

It exists before full execution fidelity is available.

Uses:

- early-phase architecture communication
- expected sequence definition
- intended interaction documentation
- sequence-diagram generation before full computation is available

### 2. Execution Trace

An Execution Trace is the actual runtime behavioral record produced by the engine.

Uses:

- validation
- debugging
- sequence-diagram generation from actual behavior
- authored-vs-executed comparison

These two concepts must remain distinct.

If you collapse them, you lose the ability to model intended behavior before the full executable math exists.

## Behavioral Views

The behavioral model should be unified, but the engineering views are still distinct.

### Activity Diagrams

Activity diagrams should show functional/control flow.

They are projected from:

- `Action` nodes
- intra-part sequencing relationships
- `Decision` and `Merge` nodes for branching
- `Fork` and `Join` nodes for parallelism
- `Guard` conditions where needed
- item dependencies between actions

Important note:

- direct action-to-action sequencing should be treated as an intra-part concept by default
- inter-part causality should be shown through ports, flows, and resulting events

So an activity diagram can show:

- action order
- branch logic
- merge logic
- parallel fan-out and synchronization
- local functional flow

without pretending inter-part control jumps directly between actions.

### State Diagrams

State diagrams should show:

- states
- transitions
- triggering events
- guards
- transition effects

They are projected from the state machine owned by a specific part or system.

State diagrams are about modes and legal transitions, not full action pipelines.

### Sequence Diagrams

Sequence diagrams should show:

- lifelines as part instances
- interactions over time
- items crossing ports and flows
- triggering events and resulting actions or transitions

In `tg-model`, sequence diagrams are not based on invented message ontologies.

They should be derived from:

- authored scenarios when expressing intended interaction contracts
- execution traces when expressing actual runtime behavior

This means a sequence diagram is fundamentally tied to:

- `Part`
- `Port`
- `Flow`
- `Item`
- `Event`
- `Scenario`

## Static Contract vs Runtime Trace

This distinction is important enough to state separately.

### Static Contract

A static contract says:

- these parts are expected to interact
- these events are expected to occur
- these items are expected to move
- this order is expected

This is what engineers often want in early design.

### Runtime Trace

A runtime trace says:

- these events actually occurred
- these actions actually executed
- these state transitions actually fired
- these items actually crossed these flows in this order

This is what engineers want for validation and debugging.

`tg-model` should support both.

## Methodology Summary

The simplified behavioral methodology for `tg-model` is:

1. Use a small behavioral ontology:
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
2. Keep execution deterministic:
   - event
   - transition/guard resolution
   - state update
   - action execution
   - item propagation
   - next event
3. Preserve structural boundaries:
   - intra-part behavior may sequence directly
   - inter-part behavior must go through ports and flows
4. Separate authored intent from runtime fact:
   - authored scenario = contract
   - execution trace = result
5. Project the same behavioral truth into multiple engineering views:
   - activity
   - state
   - sequence

This gives `tg-model` a behavior model that is:

- much simpler than SysML v2
- executable
- structurally honest
- diagram-friendly
- suitable for both LLM generation and human review
