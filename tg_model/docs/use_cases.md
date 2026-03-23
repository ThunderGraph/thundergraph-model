# tg-model Use Cases

## Purpose

This document defines the primary use cases for `tg-model` in an MBSE-oriented format.

The goal is to describe:

- who interacts with `tg-model`
- what they are trying to achieve
- what value `tg-model` provides
- how those interactions should be understood at the system level

This document is intentionally product- and architecture-focused. It is not an API spec and it is not an implementation plan.

## Scope

This use case model covers `tg-model` as a standalone Python systems modeling library.

It assumes:

- `tg-model` is the modeling and execution engine
- `unitflow` is an integral lower-layer math substrate
- ThunderGraph may integrate with `tg-model`, but is not required for `tg-model` to be useful
- `tg-model` may orchestrate local and external async computations
- the Python DSL is expected to be authored heavily by LLMs and refined by power users
- many systems engineers may primarily consume diagrams, graph views, and validation outputs rather than edit source directly
- graph export is a core outcome, but frontend rendering is out of scope

## System Of Interest

The system of interest is `tg-model`, a Python-native systems modeling and execution library that allows engineers and software systems to:

- define system structure, behavior, constraints, and requirements
- verify system compliance and design validity
- compare alternative architectures
- calculate system-level roll-ups and derived budgets
- determine the impact of changes through dependency relationships
- execute parametric studies
- validate operational sequences and behaviors
- orchestrate external simulations and analyses
- export model graphs for downstream tools

## Actor Analysis

## Primary Actors

### Systems Engineer

The Systems Engineer uses `tg-model` directly or indirectly to reason about system architecture, requirements, allocations, interfaces, and behaviors.

Primary goals:

- understand and review an executable model of a system
- preserve system structure and traceability
- validate architecture and requirement relationships
- communicate architecture clearly to other stakeholders

Primary interaction style:

- often through derived diagrams, traces, and reports
- sometimes through direct model editing

### Power User Engineer

The Power User Engineer directly authors or refines `tg-model` source code when generated output must be corrected, extended, or reviewed in detail.

Primary goals:

- inspect and refine generated model code
- encode advanced semantics not easily captured in prompts alone
- keep the source elegant, explicit, and maintainable
- serve as the bridge between automated authoring and engineering intent

### Domain Engineer

The Domain Engineer uses `tg-model` to encode engineering properties, constraints, analyses, and performance relationships in an executable form.

Primary goals:

- work with unit-safe parameters and attributes
- validate discipline-specific constraints
- run trade studies and parametric sweeps
- connect discipline-specific simulations to system-level reasoning

### Simulation / Analysis Engineer

The Simulation / Analysis Engineer uses `tg-model` as an orchestration and semantic integration layer for external analyses.

Primary goals:

- connect external solvers and simulation tools into a coherent system model
- run async or distributed analyses
- propagate computed results back into the system model
- evaluate requirement and constraint satisfaction using analysis outputs

### Application Integrator

The Application Integrator embeds `tg-model` inside a larger application or workflow, such as ThunderGraph or another engineering platform.

Primary goals:

- load and execute models programmatically
- consume graph exports and validation outputs
- connect persistence, orchestration, and visualization layers
- treat `tg-model` as a stable semantic engine

## Supporting Actors

### External Simulation Backend

This actor represents an external compute system, solver, cluster, or metamodel service that performs calculations requested by `tg-model`.

Examples:

- HPC cluster
- CFD or FEA solver
- controls simulation
- optimization engine
- remote metamodel service

### Graph Consumer

This actor consumes exported model graphs for storage, visualization, downstream analysis, or integration.

Examples:

- ThunderGraph proprietary Neo4j bridge
- a local graph analysis tool
- a frontend visualization service

### Requirements / Compliance Stakeholder

This actor cares about whether requirements are allocated, satisfied, validated, and explainable, but may not directly author models.

Examples:

- chief engineer
- systems lead
- certification lead
- verification lead

### AI Model Authoring Agent

This actor programmatically generates or modifies `tg-model` source code.

This actor is important because `tg-model` is expected to be authored not only by human engineers, but also by LLM-based systems that need a clean, explicit, and reliable API surface.

## Actor Relationships

- The Systems Engineer is often a primary consumer and reviewer of derived system representations, and may also act as an author in some workflows.
- The Domain Engineer is a primary human author of engineering semantics.
- The Power User Engineer is the primary human code author when direct source refinement is needed.
- The Simulation / Analysis Engineer extends the model with external execution capabilities.
- The Application Integrator consumes `tg-model` as a library and connects it to larger software systems.
- The External Simulation Backend is a supporting execution actor.
- The Graph Consumer is a supporting downstream actor.
- The Requirements / Compliance Stakeholder consumes results and traceability outputs.
- The AI Model Authoring Agent is a major authoring actor whose needs strongly influence API clarity.

## Use Case Catalog

The following use cases define the core value delivered by `tg-model`.

| ID | Use Case | Primary Actor |
|---|---|---|
| UC-01 | Define Executable System Structure | AI Model Authoring Agent / Power User Engineer |
| UC-02 | Define Unit-Safe Parameters, Attributes, and Constraints | Domain Engineer |
| UC-03 | Verify System Compliance | Systems Engineer |
| UC-04 | Allocate Requirements to Model Elements | Systems Engineer |
| UC-05 | Evaluate Architectural Variants | Systems Engineer |
| UC-06 | Calculate System Roll-Ups And Budgets | Domain Engineer |
| UC-07 | Determine Impact Of Change | Systems Engineer |
| UC-08 | Execute Parametric Sweep | Domain Engineer |
| UC-09 | Validate Operational Sequences | Systems Engineer |
| UC-10 | Orchestrate External Simulation Or Analysis | Simulation / Analysis Engineer |
| UC-11 | Export System Graph | Application Integrator |
| UC-12 | Stream Or Capture Study Results | Application Integrator |

## Use Case Relationships

- `UC-01` is foundational. Most other use cases depend on a defined model structure.
- `UC-02` extends `UC-01` by adding executable engineering semantics.
- `UC-03` depends on `UC-01`, `UC-02`, and often on `UC-04`.
- `UC-04` depends on `UC-01`.
- `UC-05` depends on `UC-01`, `UC-02`, and often on `UC-03`.
- `UC-06` depends on `UC-01` and `UC-02`.
- `UC-07` depends on `UC-01`, `UC-02`, and `UC-04`.
- `UC-08` depends on `UC-02` and often feeds `UC-03`, `UC-05`, and `UC-06`.
- `UC-09` depends on `UC-01` and optionally `UC-02`.
- `UC-10` may support `UC-03`, `UC-05`, `UC-06`, `UC-08`, and `UC-09`.
- `UC-11` can occur after `UC-01` and after any evaluation-oriented use case.
- `UC-12` commonly accompanies `UC-05`, `UC-06`, `UC-08`, `UC-09`, and `UC-10`.

## Detailed Use Cases

## UC-01 Define Executable System Structure

### Goal

Define the structural architecture of a system in a Python-native, semantically meaningful, executable form.

### Primary Actor

AI Model Authoring Agent / Power User Engineer

### Supporting Actors

- Systems Engineer
- Graph Consumer

### Preconditions

- The actor has identified the system or subsystem to be modeled.
- Relevant structural concepts are understood, such as parts, ports, interfaces, connections, and flows.
- A stable identity scheme exists so model elements can survive regeneration and downstream graph merging.

### Trigger

The actor wants to model a new system architecture or formalize an existing one.

### Main Flow

1. The actor defines a `System` or `Part` type.
2. The actor declares constituent parts and their composition or aggregation relationships.
3. The actor defines ports and interfaces for structural interaction points.
4. The actor defines connections and flows between parts.
5. `tg-model` constructs a semantic object graph from the declarations.
6. `tg-model` assigns or resolves stable deterministic identities for model elements.
7. The actor can inspect, evaluate, and export the model as a first-class system representation.

### Alternate Flows

1. The actor may extend an existing system definition rather than creating one from scratch.
2. The actor may generate the model source using an AI authoring system instead of writing it manually.

### Postconditions

- A structural system model exists in executable Python form.
- Stable semantic identities are available for its elements.
- The structural relationships are available to validation, execution, and graph export workflows.

### Value

This use case replaces static structural documentation with a living architectural model.

## UC-02 Define Unit-Safe Parameters, Attributes, and Constraints

### Goal

Represent engineering quantities, derived properties, and constraints with dimensional correctness and executable semantics.

### Primary Actor

Domain Engineer

### Supporting Actors

- Systems Engineer
- AI Model Authoring Agent

### Preconditions

- The structural model context exists or is being defined.
- Relevant engineering properties, quantities, and rules are known.
- `unitflow` provides the underlying math constructs used by `tg-model`.

### Trigger

The actor needs to encode engineering meaning into the model beyond structure alone.

### Main Flow

1. The actor defines parameters as externally supplied, sweepable, unit-aware inputs.
2. The actor defines attributes as stateful or derived engineering properties.
3. The actor may bind some attributes to declarative external computations or simulations.
4. The actor defines constraints over realized parameters, attributes, and equations.
5. `tg-model` binds these model elements to `unitflow` quantities and expressions.
6. The resulting model can be evaluated with dimensional correctness.

### Alternate Flows

1. Constraints may be simple local expressions.
2. Derived attributes may depend on external analyses.
3. Constraints remain synchronous even when some attribute realization depends on async computation.

### Postconditions

- The model contains executable engineering semantics.
- Unit-safe reasoning is available for validation and analysis.

### Value

This use case makes `tg-model` more than a structural language. It turns it into an engineering reasoning engine.

## UC-03 Verify System Compliance

### Goal

Determine whether a modeled design satisfies its constraints, requirements, and other compliance criteria under the provided assumptions and inputs.

### Primary Actor

Systems Engineer

### Supporting Actors

- Domain Engineer
- External Simulation Backend

### Preconditions

- A model structure exists.
- Relevant parameters, attributes, and constraints have been defined where needed.

### Trigger

The actor wants to know whether the current design is compliant, acceptable, or broken.

### Main Flow

1. The actor provides input values or a configuration.
2. `tg-model` resolves the dependency graph needed for evaluation.
3. Local expressions and declarative computed attributes are identified.
4. Async external computations are orchestrated where needed to realize attribute values.
5. Realized values are materialized into the model state.
6. Constraints, requirement satisfaction conditions, and other relevant checks are evaluated synchronously over those realized values.
7. Structural and semantic issues are identified.
8. `tg-model` returns compliance outcomes, failures, and diagnostics.

### Alternate Flows

1. Validation may require external job-backed analyses.
2. Validation may be partial if some values are missing or unresolved.
3. Unresolved external computations may leave some outcomes indeterminate.

### Postconditions

- The actor receives a clear compliance outcome.
- Violated constraints, failed requirements, and other issues are available for inspection.

### Value

This use case turns architecture into something verifiable rather than purely descriptive.

## UC-04 Allocate Requirements to Model Elements

### Goal

Associate requirements with the model elements responsible for satisfying, implementing, or verifying them.

### Primary Actor

Systems Engineer

### Supporting Actors

- Requirements / Compliance Stakeholder
- AI Model Authoring Agent

### Preconditions

- Requirements exist in the model.
- Relevant parts, behaviors, or constraints exist in the model.

### Trigger

The actor needs to represent how requirements map onto the architecture.

### Main Flow

1. The actor defines one or more requirements.
2. The actor identifies which system elements, behaviors, or analyses are intended to satisfy, implement, or verify those requirements.
3. The actor defines allocation relationships in the relevant system, variant, or configuration context.
4. `tg-model` stores these relationships as first-class semantic links.
5. Downstream validation and traceability workflows can inspect the allocations.

### Alternate Flows

1. Allocations may be one-to-one.
2. Allocations may be many-to-many.
3. Allocations may vary by architecture variant or configuration context.

### Postconditions

- The architecture and the requirement model are linked.
- Traceability becomes executable rather than purely documentary.

### Value

This use case preserves a central MBSE strength while making the mapping programmatic and analyzable.

## UC-05 Evaluate Architectural Variants

### Goal

Compare alternative architectural solutions against common criteria such as requirements, constraints, performance, and tradeoff metrics.

### Primary Actor

Systems Engineer

### Supporting Actors

- Domain Engineer
- External Simulation Backend
- Requirements / Compliance Stakeholder

### Preconditions

- Two or more candidate architectural variants exist or can be constructed.
- Common evaluation criteria exist across those variants.

### Trigger

The actor wants to compare competing design approaches rather than just tune parameters within a single design.

### Main Flow

1. The actor identifies a set of candidate architectures or topological alternatives.
2. `tg-model` evaluates each variant against common requirements, constraints, and analysis criteria.
3. Performance, compliance, and tradeoff results are collected for each variant.
4. The actor compares the variants and identifies strengths, weaknesses, and feasible options.

### Alternate Flows

1. Some variants may remain indeterminate due to missing data.
2. Some variants may require external simulation results before meaningful comparison can occur.

### Postconditions

- Comparative results exist across multiple architectures.
- The rationale for preferring or rejecting a variant can be traced back to model elements and evaluation outcomes.

### Value

This use case addresses one of the central MBSE problems: comparing different system solutions, not merely tuning one design.

## UC-06 Calculate System Roll-Ups And Budgets

### Goal

Calculate aggregated system-level values across the architecture, such as mass, power, cost, resource, and margin budgets.

### Primary Actor

Domain Engineer

### Supporting Actors

- Systems Engineer

### Preconditions

- A system hierarchy exists.
- Relevant part-level values are available or derivable.

### Trigger

The actor wants to know the total, rolled-up, or budgeted impact of values distributed across the system structure.

### Main Flow

1. The actor identifies the system-level quantity or budget of interest.
2. `tg-model` traverses the relevant compositional hierarchy.
3. Relevant part-level values are aggregated according to the declared model semantics.
4. Derived totals, margins, or budget allocations are calculated.
5. The actor inspects whether the resulting system-level values remain acceptable.

### Alternate Flows

1. Some part-level values may need to be derived before roll-up.
2. Some budgets may include externally computed values.
3. Some aggregated results may remain indeterminate if upstream values are unresolved.

### Postconditions

- System-level aggregate values are available.
- Budget or margin violations can be identified at the system level.

### Value

This use case addresses a fundamental systems-engineering problem: understanding whole-system totals rather than isolated part values.

## UC-07 Determine Impact Of Change

### Goal

Determine what parts of the model, requirement set, or analysis space are affected by a change to an input, parameter, attribute, or architectural element.

### Primary Actor

Systems Engineer

### Supporting Actors

- Domain Engineer
- Requirements / Compliance Stakeholder

### Preconditions

- A model with meaningful dependencies, traceability, or derived relationships exists.
- A proposed or actual change has been identified.

### Trigger

The actor wants to understand what downstream consequences follow from a change before or after evaluation.

### Main Flow

1. The actor identifies a changed element, value, or relationship.
2. `tg-model` traverses the dependency and traceability relationships associated with that change.
3. Potentially impacted requirements, constraints, roll-ups, analyses, and derived values are identified.
4. The actor inspects the affected subgraph or dependency slice.
5. The actor decides whether full reevaluation or redesign is needed.

### Alternate Flows

1. Impact analysis may occur before full reevaluation.
2. Impact analysis may be followed by reevaluation to confirm actual downstream effects.

### Postconditions

- The impacted portion of the model is identified.
- The actor understands what areas of the system are likely to be affected by the change.

### Value

This use case justifies why traceability and dependency structure matter in the first place.

## UC-08 Execute Parametric Sweep

### Goal

Explore how changing parameter values affects system performance, validity, and compliance outcomes.

### Primary Actor

Domain Engineer

### Supporting Actors

- Systems Engineer
- External Simulation Backend

### Preconditions

- The model includes parameterized engineering semantics.
- Relevant outputs, constraints, or compliance criteria are known.

### Trigger

The actor wants to run a trade study, sensitivity analysis, or design-space exploration.

### Main Flow

1. The actor defines ranges or sets of input parameter values.
2. `tg-model` constructs a set of evaluation runs over a fixed model structure.
3. Each run is executed against a fresh model instance or equivalent isolated evaluation context.
4. Any declarative external computations needed for a sweep point are orchestrated by the engine.
5. Outputs, constraint results, and relevant metrics are generated for each point.
6. Results are emitted to a sink, stream, or collector rather than assumed to fit only in memory.
7. The actor analyzes feasible regions, tradeoffs, and sensitivities.

### Alternate Flows

1. Sweeps may run serially for simple problems.
2. Sweeps may run concurrently for larger studies.
3. Sweep points may invoke external async analysis backends.
4. Some sweep outputs may remain indeterminate if external analyses fail or timeout.

### Postconditions

- A set of sweep results exists for downstream comparison.
- The actor can compare design behavior across parameter variations without overloading the execution engine with monolithic in-memory result assumptions.

### Value

This use case transforms `tg-model` into an engineering decision-support tool rather than just a modeling notation.

## UC-09 Validate Operational Sequences

### Goal

Determine whether a sequence of actions, events, modes, or state transitions leads to acceptable or unacceptable system behavior.

### Primary Actor

Systems Engineer

### Supporting Actors

- Domain Engineer
- External Simulation Backend

### Preconditions

- Behavioral elements such as actions, states, transitions, or operating modes are defined.
- A scenario, sequence, or operational context exists to be evaluated.

### Trigger

The actor wants to verify that a mission sequence, operating procedure, or state progression is safe, valid, and logically consistent.

### Main Flow

1. The actor defines or selects an operational sequence or scenario.
2. `tg-model` initializes the relevant execution context.
3. Actions, state transitions, and relevant attribute dependencies are identified.
4. Any required external computations are orchestrated by the engine.
5. System state evolves according to the sequence semantics supported by the model.
6. Relevant constraints and compliance checks are evaluated over the realized sequence outcomes.
7. The actor inspects whether unacceptable states, failures, or logic violations occur.

### Alternate Flows

1. The sequence may branch, fail, or become indeterminate due to missing information.
2. Some operational outcomes may depend on external analysis results.

### Postconditions

- A behavioral assessment exists for the operational sequence.
- The actor understands whether the modeled logic and state progression remain acceptable.

### Value

This use case addresses the real engineering problem of proving that important operating sequences do not drive the system into unacceptable behavior.

## UC-10 Orchestrate External Simulation Or Analysis

### Goal

Integrate external async analysis or simulation backends into the system evaluation process without forcing async authoring semantics into constraints.

### Primary Actor

Simulation / Analysis Engineer

### Supporting Actors

- External Simulation Backend
- Application Integrator

### Preconditions

- The model contains values or analyses that require external execution.
- A backend integration or adapter exists.
- The model expresses external computation declaratively through attributes or analysis bindings.

### Trigger

The actor wants to incorporate external solver or simulation results into `tg-model` evaluation.

### Main Flow

1. The actor configures or supplies an analysis backend.
2. `tg-model` identifies declarative computations that must be delegated.
3. Requests are submitted to the backend.
4. `tg-model` awaits completion, including polling or asynchronous result retrieval when needed.
5. Returned results are materialized into attributes or analysis outputs in the system model.
6. Evaluation and validation continue using those realized values.

### Alternate Flows

1. External jobs may fail, timeout, or be cancelled.
2. External results may be cached or reused.
3. Different parts of the model may run against different backends.
4. Some backends may eventually include Modelica-based integrations for heavy physics domains.

### Postconditions

- External analysis results are incorporated into the model evaluation.
- The model remains the semantic integration point for multi-tool reasoning.

### Value

This use case allows `tg-model` to serve as a real orchestration layer for digital engineering workflows rather than attempting to internalize every solver.

## UC-11 Export System Graph

### Goal

Produce a graph representation of the system model for downstream storage, visualization, analysis, or integration.

### Primary Actor

Application Integrator

### Supporting Actors

- Graph Consumer
- Systems Engineer

### Preconditions

- A model exists.
- Optional evaluation results may also exist.

### Trigger

A downstream system or tool requests a graph representation of the model.

### Main Flow

1. The actor requests graph export.
2. `tg-model` traverses the semantic model using stable element identities.
3. Nodes and relationships are projected into a stable graph export schema.
4. Engineering semantics such as units, values, and constraint outcomes are included as appropriate.
5. The Graph Consumer receives the exported graph.

### Alternate Flows

1. Export may focus on structural views only.
2. Export may include behavior, requirements, traceability, or evaluated state.

### Postconditions

- A consumable graph representation exists.
- Downstream tools can visualize or persist the model without owning core modeling semantics.

### Value

This use case allows `tg-model` to serve as the semantic origin of a broader engineering graph ecosystem.

## UC-12 Stream Or Capture Study Results

### Goal

Emit, capture, or persist evaluation and study results incrementally so large analyses do not depend on monolithic in-memory result handling.

### Primary Actor

Application Integrator

### Supporting Actors

- Domain Engineer
- Simulation / Analysis Engineer

### Preconditions

- A sweep, variant study, scenario evaluation, or external analysis run is being executed.
- A result sink, stream consumer, or collection mechanism is available.

### Trigger

The actor needs to consume or store results from a potentially large evaluation workload.

### Main Flow

1. The actor configures a result sink, stream, or collection interface.
2. `tg-model` emits results incrementally as study points or evaluations complete.
3. The sink captures outputs, metrics, and failure information.
4. The actor analyzes or stores the resulting dataset without requiring the full study state to remain only in process memory.

### Alternate Flows

1. Results may be streamed live.
2. Results may be buffered in batches.
3. Failed study points may emit partial diagnostics instead of full outputs.

### Postconditions

- Study results are available to downstream analysis or storage workflows.
- Large studies are operationally feasible without assuming that all results remain only in memory.

### Value

This use case ensures that large analyses remain practical and that the library can support real engineering workloads instead of only toy studies.

## Priority Assessment

The highest-value near-term use cases appear to be:

1. `UC-01 Define Executable System Structure`
2. `UC-02 Define Unit-Safe Parameters, Attributes, and Constraints`
3. `UC-03 Verify System Compliance`
4. `UC-05 Evaluate Architectural Variants`
5. `UC-06 Calculate System Roll-Ups And Budgets`
6. `UC-07 Determine Impact Of Change`
7. `UC-08 Execute Parametric Sweep`
8. `UC-11 Export System Graph`

These establish the foundation for later higher-complexity use cases such as operational sequence validation and distributed simulation orchestration.

## Strategic Interpretation

The use case model suggests that `tg-model` is not merely a Python replacement for SysML notation.

It is better understood as:

- an executable systems architecture language
- an engineering reasoning engine
- a variant and trade-study comparison engine
- a roll-up and impact-analysis engine
- a graph-producing semantic core
- an orchestration layer for system-level analysis

This interpretation should guide future API and architecture decisions.
