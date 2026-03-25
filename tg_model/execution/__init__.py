"""Execution subsystem: configured topology, validation, and run execution."""

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
from tg_model.execution.evaluator import Evaluator, RunResult
from tg_model.execution.graph_compiler import GraphCompilationError, compile_graph
from tg_model.execution.instances import ElementInstance, PartInstance, PortInstance
from tg_model.execution.requirements import (
    RequirementSatisfactionResult,
    RequirementSatisfactionSummary,
    all_requirements_satisfied,
    iter_requirement_satisfaction,
    summarize_requirement_satisfaction,
)
from tg_model.execution.run_context import ConstraintResult, RunContext, SlotState
from tg_model.execution.validation import ValidationResult, validate_graph
from tg_model.execution.value_slots import ValueSlot

__all__ = [
    "AllocationBinding",
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
    "ItemFlowStep",
    "MergeTraceStep",
    "NodeKind",
    "PartInstance",
    "PortInstance",
    "ReferenceBinding",
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
