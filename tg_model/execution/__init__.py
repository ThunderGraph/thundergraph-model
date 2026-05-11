"""Execution subsystem: frozen topology, dependency graph, validation, and evaluation.

Typical pipeline: compile element types (``SomeSystem.compile()``), build a
:class:`~tg_model.execution.configured_model.ConfiguredModel` with
:func:`~tg_model.execution.configured_model.instantiate`, then call
:meth:`~tg_model.execution.configured_model.ConfiguredModel.evaluate` (lazy compile + optional
validation per call) **or** explicitly :func:`~tg_model.execution.graph_compiler.compile_graph`,
optionally :func:`~tg_model.execution.validation.validate_graph`, then run
:class:`~tg_model.execution.evaluator.Evaluator` with a fresh
:class:`~tg_model.execution.run_context.RunContext`. Per-run values live in ``RunContext``; the
configured model may cache a compiled graph on the instance.

Notes
-----
Behavioral APIs (:func:`~tg_model.execution.behavior.dispatch_event`, etc.) mutate
:class:`~tg_model.execution.run_context.RunContext` discrete state and optional
:class:`~tg_model.execution.behavior.BehaviorTrace` records; they do not change
:class:`~tg_model.execution.configured_model.ConfiguredModel` topology.
"""

from tg_model.execution.behavior import (
    BehaviorStep,
    BehaviorTrace,
    DecisionDispatchOutcome,
    DecisionDispatchResult,
    DecisionTraceStep,
    DispatchOutcome,
    DispatchResult,
    ForkJoinTraceStep,
    ItemFlowStep,
    MergeTraceStep,
    SequenceTraceStep,
    behavior_authoring_projection,
    behavior_trace_to_records,
    dispatch_decision,
    dispatch_event,
    dispatch_fork_join,
    dispatch_merge,
    dispatch_sequence,
    emit_item,
    scenario_expected_event_names,
    trace_events_chronological,
    validate_scenario_trace,
)
from tg_model.execution.configured_model import ConfiguredModel, instantiate
from tg_model.execution.connection_bindings import (
    AllocationBinding,
    ConnectionBinding,
    ReferenceBinding,
)
from tg_model.execution.dependency_graph import DependencyGraph, DependencyNode, NodeKind
from tg_model.execution.evaluation import Evaluation
from tg_model.execution.evaluator import EvaluationIssue, Evaluator, RunResult
from tg_model.execution.stable_ids import class_scoped_constraint_sid, class_scoped_slot_sid
from tg_model.execution.graph_compiler import GraphCompilationError, compile_graph
from tg_model.execution.instances import (
    ElementInstance,
    PartInstance,
    PortInstance,
    RequirementPackageInstance,
)
from tg_model.execution.requirements import (
    RequirementSatisfactionResult,
    RequirementSatisfactionSummary,
    all_requirements_satisfied,
    iter_requirement_satisfaction,
    summarize_requirement_satisfaction,
)
from tg_model.execution.run_context import ConstraintResult, RunContext, SlotRecord, SlotState
from tg_model.execution.validation import GraphValidationError, ValidationResult, validate_graph
from tg_model.execution.value_slots import ValueSlot

__all__ = [
    "AllocationBinding",
    "class_scoped_constraint_sid",
    "class_scoped_slot_sid",
    "Evaluation",
    "EvaluationIssue",
    "BehaviorStep",
    "BehaviorTrace",
    "ConfiguredModel",
    "ConnectionBinding",
    "ConstraintResult",
    "DecisionDispatchOutcome",
    "DecisionDispatchResult",
    "DecisionTraceStep",
    "DependencyGraph",
    "DependencyNode",
    "DispatchOutcome",
    "DispatchResult",
    "ElementInstance",
    "Evaluator",
    "ForkJoinTraceStep",
    "GraphCompilationError",
    "GraphValidationError",
    "ItemFlowStep",
    "MergeTraceStep",
    "NodeKind",
    "PartInstance",
    "PortInstance",
    "ReferenceBinding",
    "RequirementPackageInstance",
    "RequirementSatisfactionResult",
    "RequirementSatisfactionSummary",
    "RunContext",
    "RunResult",
    "SequenceTraceStep",
    "SlotState",
    "ValidationResult",
    "ValueSlot",
    "all_requirements_satisfied",
    "behavior_authoring_projection",
    "behavior_trace_to_records",
    "compile_graph",
    "dispatch_decision",
    "dispatch_event",
    "dispatch_fork_join",
    "dispatch_merge",
    "dispatch_sequence",
    "emit_item",
    "instantiate",
    "iter_requirement_satisfaction",
    "scenario_expected_event_names",
    "summarize_requirement_satisfaction",
    "trace_events_chronological",
    "validate_graph",
    "validate_scenario_trace",
]
