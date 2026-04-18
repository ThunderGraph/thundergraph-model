# Glossary

## Element
Base authoring type. `System`, `Part`, and `Requirement` all derive from this.

## System
Top-level composition type and configured root. A `System` owns the `Part` tree and
the `Requirement` tree, and declares `allocate` wiring between them. Must call
`model.name(...)` exactly once in `define()`.

## Part
Composable structural type nested under a `System`. Declares `model.parameter`,
`model.attribute`, `model.constraint`, and `model.composed_of` in its `define()`.
Must call `model.name(...)` exactly once.

## Requirement
Composable **requirements package** type. Declares executable checks using the same
`model.parameter` / `model.attribute` / `model.constraint` surface as a `Part`.
Must call `model.name(...)` and `model.doc(...)` exactly once in `define()`.
Mounted on a `System` via `model.composed_of(name, RequirementType)`.

## ModelDefinitionContext
The `model` argument in `define(cls, model)`. Records declarations and edges during
type authoring. Frozen automatically after `define()` returns.

## model.name
`model.name(str)` — declares a human-readable snake_case identifier for any element
(`Part`, `System`, or `Requirement`). Required exactly once per `define()`.

## model.doc
`model.doc(str)` — declares the primary "shall" statement for a `Requirement`.
Required exactly once per `Requirement.define()`. Not available on `Part` or `System`.

## model.composed_of
`model.composed_of(name, ChildType)` — unified composition primitive. Dispatches to
`PartRef` or `RequirementRef` based on whether `ChildType` is a `Part` or `Requirement`
subclass. Replaces the old `model.part(name, Type)` and `model.requirement_package(name, Type)`.

## model.parameter
`model.parameter(name, unit=...)` — declares a bindable input slot on a `Part` or
`Requirement`. Values are supplied at evaluation time via the `inputs=` map.
On a `Requirement`, parameter slots are wired at allocation time via `allocate(..., inputs=...)`.

## model.attribute
`model.attribute(name, unit=..., expr=...)` — declares a derived value slot computed
from an expression over other slots. Use `computed_by=` to bind an external compute backend.

## model.constraint
`model.constraint(name, expr=...)` — declares a boolean pass/fail check. Results appear
in `RunResult.constraint_results`.

## allocate
`model.allocate(req_ref, target_ref, inputs={...})` — links a `Requirement` package to
a target `Part`. The `inputs` dict maps `parameter` names declared in the requirement
class to `AttributeRef` slots on the Part (or System-level parameters). Produces
`ConstraintResult` rows tagged with `requirement_path` and `allocation_target_path`.

## Ref / PartRef / AttributeRef / RequirementRef
Symbolic references created at definition time. Returned by `model.composed_of`,
`model.parameter`, `model.attribute`, etc. Not runtime instances — they are used for
wiring expressions and allocations.

## compile (type compile)
Transforms declaration recording into cached compiled artifacts with validation.
Triggered lazily by `instantiate()` or explicitly by `compile_type()`.

## ConfiguredModel
Frozen instantiated topology for one root `System` type. Holds the instance graph,
path registry, and compiled graph cache. Created by `instantiate(SystemType)`.

## ValueSlot
Topology-level value cell (parameter or attribute) keyed by a stable id string.
Access via `cm.root.child_name.slot_name`. Use as keys in `cm.evaluate(inputs={slot: qty})`.

## RunContext
Per-run mutable state container. Holds bound inputs, realized values, and constraint
results. Created automatically by `cm.evaluate()`, or manually for the explicit pipeline.

## DependencyGraph
Bipartite graph of value nodes and compute nodes used for topological evaluation order.
Built by `compile_graph(cm)`.

## Evaluator
Runs graph nodes in topological order and writes outcomes into a `RunContext`.
Created by `Evaluator(graph, compute_handlers=handlers)`.

## RunResult
Summary of one evaluation run: `.passed` (bool), `.constraint_results` (list of
`ConstraintResult`), and `.outputs` (dict of stable_id → Quantity).

## ConstraintResult
Result row for one constraint check. Fields include `name`, `passed`, `requirement_path`
(dot-separated path of the owning `Requirement` package, or `None` for Part constraints),
and `allocation_target_path` (path of the allocated Part, or `None`).

## ExternalComputeBinding
Binding from internal `AttributeRef` slots to an external compute backend. Passed to
`model.attribute(..., computed_by=ExternalComputeBinding(...))`.

## BehaviorTrace
Structured trace of behavioral dispatch actions (transitions, decisions, merges, item
flows, etc.) produced by the behavior evaluation engine.

## Scenario
Authored expected behavior contract used by `validate_scenario_trace`.

## Stable ID
Deterministic string identifier derived from configured root type and full instance path.
Used as input keys in the explicit `Evaluator` pipeline.

## ExternalCompute / AsyncExternalCompute
Protocols for external backends. Implement `name` property and `compute(inputs)` /
`compute_async(inputs)`. Optionally implement `validate_binding(...)` from
`ValidatableExternalCompute`.
