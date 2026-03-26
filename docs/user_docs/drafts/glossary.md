# Glossary

## Element
Base authoring type. `System`, `Part`, and `RequirementBlock` derive from this.

## System
Top-level composition type (often configured root).

## Part
Composable structural type under a system.

## RequirementBlock
Nested requirements subtree type. Supports requirements, citations, nested blocks, and requirement-local inputs.

## ModelDefinitionContext
The `model` argument in `define(cls, model)`. Records declarations and edges during type authoring.

## Ref / PartRef / AttributeRef / RequirementBlockRef
Symbolic references created at definition time. Not runtime instances.

## compile (type compile)
Transforms declaration recording into cached compiled artifacts with validation.

## ConfiguredModel
Frozen instantiated topology for one root type. Holds instance graph and registries.

## ValueSlot
Topology-level value cell (parameter or attribute) keyed by stable id.

## RunContext
Per-run mutable state container (bound inputs, realized values, failures, behavior state).

## DependencyGraph
Bipartite graph of value nodes and compute nodes used for evaluation order.

## Evaluator
Runs graph nodes in topological order and writes outcomes into `RunContext`.

## RunResult
Summary of one run: outputs, constraint results, and failures.

## Constraint
Boolean validity check over realized values.

## Requirement acceptance
Executable requirement check compiled from acceptance expressions + allocations.

## allocate
Links a requirement to a target model element. Optional `inputs=` binds requirement-local input names to slot refs.

## requirement_input
RequirementBlock-only declaration of requirement-local symbolic inputs.

## requirement_accept_expr
RequirementBlock-only method that attaches executable acceptance expression to a requirement.

## ExternalComputeBinding
Binding from internal refs to external compute backend inputs/outputs.

## BehaviorTrace
Structured trace of behavioral dispatch actions (transitions, decisions, merges, item flows, etc.).

## Scenario
Authored expected behavior contract used by `validate_scenario_trace`.

## Stable ID
Deterministic identifier derived from configured root and full instance path.
