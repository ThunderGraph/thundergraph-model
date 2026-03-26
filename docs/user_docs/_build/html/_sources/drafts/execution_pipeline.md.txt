# Execution Pipeline (Compile -> Instantiate -> Graph -> Evaluate)

This is the canonical flow for ThunderGraph Model.

## 1) Compile types

Call `SomeSystem.compile()` (or let helper APIs call compile implicitly).

What happens:

- `define(cls, model)` records nodes/edges into `ModelDefinitionContext`
- declarations are validated
- child part types and requirement block types are compiled recursively
- a cached compiled artifact is stored on the class

Output: class-level compiled artifact (definition data), not an instance topology.

## 2) Instantiate a configured topology

Call `instantiate(SomeSystem)` to get `ConfiguredModel`.

What happens:

- builds concrete `PartInstance`, `PortInstance`, and `ValueSlot` objects
- resolves structural connections
- resolves allocations and references
- creates registries by path and stable id
- freezes topology (no structural mutation afterward)

Output: one immutable configuration-scoped topology.

## 3) Compile dependency graph

Call `compile_graph(configured_model)`.

What happens:

- creates bipartite value/compute graph
- adds handlers for expressions, rollups, external compute, solve groups, constraints
- encodes dependency edges in evaluation order direction

Output: `DependencyGraph` + `compute_handlers`.

## 4) Validate graph (optional but recommended)

Call `validate_graph(graph, configured_model=cm)`.

What happens:

- checks cycles and orphaned compute
- checks rollups and solve-group integrity
- runs optional external binding validation hooks

Output: `ValidationResult` (pass/fail + failures list).

## 5) Evaluate one run

Create fresh `RunContext`, then run `Evaluator(graph, compute_handlers).evaluate(...)`
(or `.evaluate_async(...)` for async external backends).

What happens:

- input parameters are bound into context
- nodes execute in topological order when dependencies are ready
- realized values and failures are stored in `RunContext`
- constraint results are collected into `RunResult`

Output: `RunResult` + per-slot state in `RunContext`.

## Requirement acceptance path

Requirements become executable checks when:

- requirement has acceptance expression (`expr=` or `requirement_accept_expr`)
- requirement is allocated (`allocate(...)`)
- required inputs are bound (`allocate(..., inputs=...)` for requirement-input patterns)

Then acceptance checks are compiled into the same graph/evaluation pass.

## Behavioral path

Behavior dispatch APIs (`dispatch_event`, `dispatch_decision`, etc.) operate on `RunContext`
and optional `BehaviorTrace`. They do not mutate `ConfiguredModel` topology.

## One sentence summary

**Compile declarations once, instantiate topology once per configuration, evaluate many times with fresh run contexts.**
