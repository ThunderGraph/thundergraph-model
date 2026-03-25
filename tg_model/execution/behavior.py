"""Discrete behavioral execution (Phase 6) on the ``RunContext`` spine.

Includes: state machines (:func:`dispatch_event`), activity control-flow
(:func:`dispatch_sequence`, :func:`dispatch_decision`, :func:`dispatch_merge`,
:func:`dispatch_fork_join`), and inter-part :func:`emit_item` with traces and scenario
validation.

**Guards and effects** both run under the same **subtree** scope on
:class:`~tg_model.execution.run_context.RunContext` (see that class for limits: API
discipline, not a sandbox).

**Transition commit order:** when a transition fires, the active state is updated to the
*target* state **before** the transition's action effect runs. Effects observe the
post-transition state via :meth:`~tg_model.execution.run_context.RunContext.get_active_behavior_state`.
Guards run **before** any state change.

**Effect errors:** if an effect callable raises, the active state is reverted to the
pre-transition state and the exception propagates (no :class:`BehaviorStep` is recorded).

**Fork/join (v0):** :func:`dispatch_fork_join` runs branch actions **serially** in a fixed
order (deterministic); it does not interleave or schedule parallel threads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from tg_model.execution.instances import PartInstance, PortInstance
from tg_model.execution.run_context import RunContext


class DispatchOutcome(StrEnum):
    """Why :func:`dispatch_event` did or did not fire a transition."""

    FIRED = "fired"
    NO_MATCH = "no_match"
    """No transition for the current state and event name (or no behavior spec)."""
    GUARD_FAILED = "guard_failed"
    """A transition matched but its ``when`` guard returned false."""


@dataclass(frozen=True)
class DispatchResult:
    """Result of :func:`dispatch_event`.

    ``bool(result)`` is true only when a transition fired (same truthiness as the
    legacy ``bool`` return for success).
    """

    outcome: DispatchOutcome

    def __bool__(self) -> bool:
        return self.outcome == DispatchOutcome.FIRED


class DecisionDispatchOutcome(StrEnum):
    """Outcome of :func:`dispatch_decision`."""

    ACTION_RAN = "action_ran"
    """A branch or ``default_action`` ran (name in :attr:`DecisionDispatchResult.chosen_action`)."""
    NO_ACTION = "no_action"
    """No branch matched and there was no ``default_action``."""


@dataclass(frozen=True)
class DecisionDispatchResult:
    """Result of :func:`dispatch_decision`. ``bool(result)`` is true when an action ran."""

    outcome: DecisionDispatchOutcome
    chosen_action: str | None = None
    merge_ran: bool = False
    """True when a paired merge was executed (after a chosen action)."""

    def __bool__(self) -> bool:
        return self.chosen_action is not None


@dataclass(frozen=True)
class BehaviorStep:
    """One fired transition in causal order."""

    step_index: int
    part_path: str
    event_name: str
    from_state: str
    to_state: str
    effect_name: str | None


@dataclass(frozen=True)
class ItemFlowStep:
    """Record of an item crossing a structural connection (inter-part behavior)."""

    step_index: int
    source_port_path: str
    target_port_path: str
    item_kind: str
    payload: Any | None = None


@dataclass(frozen=True)
class DecisionTraceStep:
    """Record of a decision node choosing an action branch."""

    step_index: int
    part_path: str
    decision_name: str
    chosen_action: str | None


@dataclass(frozen=True)
class ForkJoinTraceStep:
    """Record of a fork/join block executing."""

    step_index: int
    part_path: str
    block_name: str


@dataclass(frozen=True)
class MergeTraceStep:
    """Record of control reaching a merge (shared continuation after branching)."""

    step_index: int
    part_path: str
    merge_name: str
    then_action: str | None


@dataclass(frozen=True)
class SequenceTraceStep:
    """Record of a linear :class:`sequence` activity region completing."""

    step_index: int
    part_path: str
    sequence_name: str


@dataclass
class BehaviorTrace:
    """Append-only trace of discrete behavioral steps (stable ordering by ``step_index``).

    Steps use :attr:`PartInstance.path_string` (instance path) and declared **event**
    **names** — not :attr:`~tg_model.execution.value_slots.ValueSlot.stable_id`.
    """

    steps: list[BehaviorStep] = field(default_factory=list)
    item_flows: list[ItemFlowStep] = field(default_factory=list)
    decision_steps: list[DecisionTraceStep] = field(default_factory=list)
    fork_join_steps: list[ForkJoinTraceStep] = field(default_factory=list)
    merge_steps: list[MergeTraceStep] = field(default_factory=list)
    sequence_steps: list[SequenceTraceStep] = field(default_factory=list)


def _next_global_step_index(trace: BehaviorTrace) -> int:
    return (
        len(trace.steps)
        + len(trace.item_flows)
        + len(trace.decision_steps)
        + len(trace.fork_join_steps)
        + len(trace.merge_steps)
        + len(trace.sequence_steps)
    )


def _eval_guard_or_predicate(
    ctx: RunContext,
    part: PartInstance,
    fn: Callable[[RunContext, PartInstance], Any],
) -> bool:
    """Evaluate a transition ``when`` guard or decision branch predicate under behavior scope."""
    ctx.push_behavior_effect_scope(part)
    try:
        return bool(fn(ctx, part))
    finally:
        ctx.pop_behavior_effect_scope()


def _behavior_spec(part: PartInstance) -> list[dict[str, Any]]:
    raw = getattr(part.definition_type, "_tg_behavior_spec", None)
    return list(raw or [])


def _initial_state_name(definition_type: type) -> str:
    cached = getattr(definition_type, "_tg_initial_state_name", None)
    if cached is not None:
        return cached
    compiled = definition_type.compile()
    for name, node in compiled["nodes"].items():
        if node["kind"] == "state" and node["metadata"].get("initial"):
            return name
    raise ValueError(f"No initial state declared on {definition_type.__name__}")


def _ensure_active_state(ctx: RunContext, part: PartInstance) -> str:
    key = part.path_string
    cur = ctx.get_active_behavior_state(key)
    if cur is not None:
        return cur
    initial = _initial_state_name(part.definition_type)
    ctx.set_active_behavior_state(key, initial)
    return initial


def dispatch_event(
    ctx: RunContext,
    part: PartInstance,
    event_name: str,
    *,
    trace: BehaviorTrace | None = None,
) -> DispatchResult:
    """Dispatch one discrete event on ``part``'s state machine.

    Returns :class:`DispatchResult` with :attr:`~DispatchResult.outcome` distinguishing
    **no matching transition** (:attr:`DispatchOutcome.NO_MATCH`) from **guard blocked**
    (:attr:`DispatchOutcome.GUARD_FAILED`). ``bool(result)`` is true only when a
    transition fired.

    Guards and effects are arbitrary callables; exceptions propagate. If an effect
    raises after the state was advanced, the active state is rolled back first.
    """
    spec = _behavior_spec(part)
    if not spec:
        return DispatchResult(DispatchOutcome.NO_MATCH)
    current = _ensure_active_state(ctx, part)
    for tr in spec:
        if tr["from_state"].path[-1] != current:
            continue
        if tr["on"].path[-1] != event_name:
            continue
        guard = tr.get("when")
        if guard is not None and not _eval_guard_or_predicate(ctx, part, guard):
            return DispatchResult(DispatchOutcome.GUARD_FAILED)
        to_name = tr["to_state"].path[-1]
        ctx.set_active_behavior_state(part.path_string, to_name)
        eff_name = tr.get("effect")
        try:
            if eff_name:
                _run_action_effect(part.definition_type, eff_name, ctx, part)
        except Exception:
            ctx.set_active_behavior_state(part.path_string, current)
            raise
        finally:
            ctx.clear_item_payload(part.path_string, event_name)
        if trace is not None:
            trace.steps.append(
                BehaviorStep(
                    step_index=_next_global_step_index(trace),
                    part_path=part.path_string,
                    event_name=event_name,
                    from_state=current,
                    to_state=to_name,
                    effect_name=eff_name,
                )
            )
        return DispatchResult(DispatchOutcome.FIRED)
    return DispatchResult(DispatchOutcome.NO_MATCH)


def _run_action_effect(definition_type: type, action_name: str, ctx: RunContext, part: PartInstance) -> None:
    ctx.push_behavior_effect_scope(part)
    try:
        effects = getattr(definition_type, "_tg_action_effects", None)
        if effects is not None:
            fn = effects.get(action_name)
            if fn is not None:
                fn(ctx, part)
                return
        compiled = definition_type.compile()
        node = compiled["nodes"].get(action_name)
        if node is None or node["kind"] != "action":
            raise KeyError(f"No action {action_name!r} on {definition_type.__name__}")
        fn = node["metadata"].get("_effect")
        if callable(fn):
            fn(ctx, part)
    finally:
        ctx.pop_behavior_effect_scope()


def behavior_authoring_projection(definition_type: type) -> dict[str, Any]:
    """Static behavioral data for activity / state / sequence diagram hooks (Phase 6).

    Returns mostly JSON-friendly data: node names by kind, serialized transitions, and
    structural edges (refs are serialized via ``to_dict()`` as in :func:`compile_type`).
    Treat as a **projection** for tools, not a hardened JSON schema guarantee for every
    metadata field on every node.
    """
    compiled = definition_type.compile()
    nodes = compiled["nodes"]

    def names(kind: str) -> list[str]:
        return sorted(n for n, d in nodes.items() if d["kind"] == kind)

    return {
        "owner": compiled["owner"],
        "states": names("state"),
        "events": names("event"),
        "actions": names("action"),
        "guards": names("guard"),
        "merges": names("merge"),
        "decisions": names("decision"),
        "fork_joins": names("fork_join"),
        "sequences": names("sequence"),
        "item_kinds": names("item_kind"),
        "scenarios": names("scenario"),
        "transitions": compiled.get("behavior_transitions", []),
        "edges": compiled.get("edges", []),
    }


def scenario_expected_event_names(definition_type: type, scenario_name: str) -> list[str]:
    """Return authored expected event sequence for a scenario node."""
    compiled = definition_type.compile()
    node = compiled["nodes"].get(scenario_name)
    if node is None or node["kind"] != "scenario":
        raise KeyError(f"No scenario {scenario_name!r} on {definition_type.__name__}")
    order = node["metadata"].get("_expected_event_order")
    if not isinstance(order, list):
        raise ValueError(f"Malformed scenario {scenario_name!r}")
    return list(order)


def _scenario_node_metadata(definition_type: type, scenario_name: str) -> dict[str, Any]:
    compiled = definition_type.compile()
    node = compiled["nodes"].get(scenario_name)
    if node is None or node["kind"] != "scenario":
        raise KeyError(f"No scenario {scenario_name!r} on {definition_type.__name__}")
    return node["metadata"]


def trace_events_chronological(trace: BehaviorTrace) -> list[tuple[str, str]]:
    """State-machine transition events only, in global ``step_index`` order ``(part_path, event_name)``."""
    ordered = sorted(trace.steps, key=lambda s: s.step_index)
    return [(s.part_path, s.event_name) for s in ordered]


def validate_scenario_trace(
    *,
    definition_type: type,
    scenario_name: str,
    part_path: str,
    trace: BehaviorTrace,
    ctx: RunContext | None = None,
    root: PartInstance | None = None,
) -> tuple[bool, list[str]]:
    """Compare trace slices to an authored scenario (partial contracts).

    This is a **bundle of independent checks**, not a single end-to-end story:

    - **Transition events** for ``part_path`` vs ``expected_event_order``.
    - Optionally **final / initial** discrete state for that path (needs ``ctx`` for final).
    - Optionally **global transition order** via :func:`trace_events_chronological` (state-machine
      steps only — not decisions, merges, or item flows).
    - Optionally **item kind** order from :class:`ItemFlowStep` only.

    Passing all enabled checks does **not** imply the full causal trace (including activity
    nodes) matches intent; combine with explicit tests or richer tooling as needed.

    Call with ``ctx`` from **outside** behavior effects when checking final state (scopes on
    ``RunContext`` can restrict ``get_active_behavior_state`` during an effect).

    When the scenario declares ``expected_interaction_order`` (list of
    ``(relative_part_path, event_name)`` from the scenario owner root), pass
    ``root`` (the configured root :class:`~tg_model.execution.instances.PartInstance`)
    and this compares :func:`trace_events_chronological` to that global ordering.

    When the scenario declares ``expected_item_kind_order``, compares the ordered
    list of :class:`ItemFlowStep` ``item_kind`` values in the trace.
    """
    errors: list[str] = []
    expected = scenario_expected_event_names(definition_type, scenario_name)
    fired = [s.event_name for s in trace.steps if s.part_path == part_path]
    if fired != expected:
        errors.append(f"expected events {expected!r}, got {fired!r}")

    meta = _scenario_node_metadata(definition_type, scenario_name)
    final_s = meta.get("_expected_final_behavior_state")
    if ctx is not None and final_s is not None:
        cur = ctx.get_active_behavior_state(part_path)
        if cur != final_s:
            errors.append(f"expected final behavior state {final_s!r}, got {cur!r}")

    initial_s = meta.get("_initial_behavior_state")
    if initial_s is not None:
        part_steps = [s for s in trace.steps if s.part_path == part_path]
        if part_steps:
            first = min(part_steps, key=lambda s: s.step_index)
            if first.from_state != initial_s:
                errors.append(
                    f"expected initial behavior state {initial_s!r}, first transition from {first.from_state!r}"
                )

    iord = meta.get("_expected_interaction_order")
    if iord:
        if root is None:
            errors.append("expected_interaction_order requires validate_scenario_trace(..., root=<PartInstance>)")
        else:
            if root.definition_type is not definition_type:
                errors.append("root part type does not match scenario definition_type")
            else:
                resolved: list[tuple[str, str]] = []
                for pair in iord:
                    if len(pair) != 2:
                        errors.append(f"malformed interaction pair {pair!r}")
                        break
                    rel, ev = pair[0], pair[1]
                    full = root.path_string if not rel else f"{root.path_string}.{rel}"
                    resolved.append((full, ev))
                if not errors:
                    actual = trace_events_chronological(trace)
                    if actual != resolved:
                        errors.append(f"expected interaction order {resolved!r}, got {actual!r}")

    iko = meta.get("_expected_item_kind_order")
    if iko is not None:
        actual_k = [s.item_kind for s in sorted(trace.item_flows, key=lambda x: x.step_index)]
        if actual_k != list(iko):
            errors.append(f"expected item kind order {list(iko)!r}, got {actual_k!r}")

    return (not errors, errors)


def dispatch_decision(
    ctx: RunContext,
    part: PartInstance,
    decision_name: str,
    *,
    trace: BehaviorTrace | None = None,
    run_merge: bool = True,
) -> DecisionDispatchResult:
    """Run a declared ``decision``: first branch whose guard passes runs its action.

    If the decision was declared with ``merge_point=`` to a :meth:`merge` node, also runs
    that merge's ``then_action`` after the branch action (unless ``run_merge=False`` for
    manual :func:`dispatch_merge` — do **not** call :func:`dispatch_merge` again for the
    same merge when pairing is enabled, or the continuation runs twice).

    Returns :class:`DecisionDispatchResult`: :attr:`~DecisionDispatchResult.outcome` is
    :attr:`DecisionDispatchOutcome.NO_ACTION` only when no branch matched and there is no
    ``default_action``. ``bool(result)`` is true iff an action ran.

    Branches with ``guard is None`` match unconditionally (place them last unless you
    intend a catch-all).
    """
    specs = getattr(part.definition_type, "_tg_decision_specs", None) or {}
    spec = specs.get(decision_name)
    if spec is None:
        raise KeyError(f"No decision {decision_name!r} on {part.definition_type.__name__}")
    chosen: str | None = None
    for pred, aname in spec["branches"]:
        if pred is None:
            chosen = aname
            break
        if _eval_guard_or_predicate(ctx, part, pred):
            chosen = aname
            break
    if chosen is None:
        chosen = spec.get("default_action")
    if chosen is not None:
        _run_action_effect(part.definition_type, chosen, ctx, part)
    if trace is not None:
        idx = _next_global_step_index(trace)
        trace.decision_steps.append(
            DecisionTraceStep(
                step_index=idx,
                part_path=part.path_string,
                decision_name=decision_name,
                chosen_action=chosen,
            )
        )
    merge_name = spec.get("merge_name")
    merge_ran = False
    if chosen is not None and merge_name and run_merge:
        dispatch_merge(ctx, part, merge_name, trace=trace)
        merge_ran = True
    outcome = (
        DecisionDispatchOutcome.ACTION_RAN
        if chosen is not None
        else DecisionDispatchOutcome.NO_ACTION
    )
    return DecisionDispatchResult(
        outcome=outcome,
        chosen_action=chosen,
        merge_ran=merge_ran,
    )


def dispatch_merge(
    ctx: RunContext,
    part: PartInstance,
    merge_name: str,
    *,
    trace: BehaviorTrace | None = None,
) -> str | None:
    """Continue at a declared ``merge``: runs optional ``then_action`` (shared after branches).

    Call after exclusive branches (e.g. following :func:`dispatch_decision`) to model a
    methodology **Merge** node. If no ``then_action`` was declared, returns ``None`` and
    only records the trace step when ``trace`` is set.
    """
    specs = getattr(part.definition_type, "_tg_merge_specs", None) or {}
    spec = specs.get(merge_name)
    if spec is None:
        raise KeyError(f"No merge {merge_name!r} on {part.definition_type.__name__}")
    then_a = spec.get("then_action")
    if then_a:
        _run_action_effect(part.definition_type, then_a, ctx, part)
    if trace is not None:
        idx = _next_global_step_index(trace)
        trace.merge_steps.append(
            MergeTraceStep(
                step_index=idx,
                part_path=part.path_string,
                merge_name=merge_name,
                then_action=then_a,
            )
        )
    return then_a


def dispatch_fork_join(
    ctx: RunContext,
    part: PartInstance,
    block_name: str,
    *,
    trace: BehaviorTrace | None = None,
) -> None:
    """Execute a ``fork_join`` block: branches run **one after another** (fixed list order).

    v0 semantics are **deterministic serial** execution, not OS-level parallelism or
    arbitrary interleaving; ``fork``/``join`` name the *logical* activity structure.
    """
    specs = getattr(part.definition_type, "_tg_fork_join_specs", None) or {}
    spec = specs.get(block_name)
    if spec is None:
        raise KeyError(f"No fork_join {block_name!r} on {part.definition_type.__name__}")
    for branch in spec["branches"]:
        for aname in branch:
            _run_action_effect(part.definition_type, aname, ctx, part)
    then_a = spec.get("then_action")
    if then_a:
        _run_action_effect(part.definition_type, then_a, ctx, part)
    if trace is not None:
        idx = _next_global_step_index(trace)
        trace.fork_join_steps.append(
            ForkJoinTraceStep(
                step_index=idx,
                part_path=part.path_string,
                block_name=block_name,
            )
        )


def dispatch_sequence(
    ctx: RunContext,
    part: PartInstance,
    sequence_name: str,
    *,
    trace: BehaviorTrace | None = None,
) -> None:
    """Run a declared linear ``sequence`` of actions (methodology default simplicity rule)."""
    specs = getattr(part.definition_type, "_tg_sequence_specs", None) or {}
    step_names = specs.get(sequence_name)
    if step_names is None:
        raise KeyError(f"No sequence {sequence_name!r} on {part.definition_type.__name__}")
    for aname in step_names:
        _run_action_effect(part.definition_type, aname, ctx, part)
    if trace is not None:
        idx = _next_global_step_index(trace)
        trace.sequence_steps.append(
            SequenceTraceStep(
                step_index=idx,
                part_path=part.path_string,
                sequence_name=sequence_name,
            )
        )


def emit_item(
    ctx: RunContext,
    cm: Any,
    source_port: PortInstance,
    item_kind: str,
    payload: Any,
    *,
    trace: BehaviorTrace | None = None,
) -> list[DispatchResult]:
    """Send an item from ``source_port`` across structural connections.

    For each matching :class:`~tg_model.execution.connection_bindings.ConnectionBinding`
    (same source port; if ``carrying`` is set on the binding it must equal ``item_kind``),
    dispatches event ``item_kind`` on the **receiving part** (declare a matching
    ``model.event(item_kind)`` on the receiver). ``payload`` is staged on
    :class:`~tg_model.execution.run_context.RunContext` (``prime_item_payload``) so the
    receiver's effect can read it via ``peek_item_payload(part.path_string, item_kind)``
    during the transition; it is cleared after dispatch completes.

    **Order:** bindings are visited in ``cm.connections`` list order; multiple matches
    produce multiple dispatches in that order (deterministic for a frozen ``ConfiguredModel``).

    Inter-part effects use the same :class:`RunContext` and topology as values.
    """
    results: list[DispatchResult] = []
    for cb in cm.connections:
        if cb.source.stable_id != source_port.stable_id:
            continue
        if cb.carrying is not None and cb.carrying != item_kind:
            continue
        tgt = cb.target
        parent_path = ".".join(tgt.instance_path[:-1])
        receiver = cm.handle(parent_path)
        if not isinstance(receiver, PartInstance):
            continue
        ctx.prime_item_payload(receiver.path_string, item_kind, payload)
        if trace is not None:
            trace.item_flows.append(
                ItemFlowStep(
                    step_index=_next_global_step_index(trace),
                    source_port_path=source_port.path_string,
                    target_port_path=tgt.path_string,
                    item_kind=item_kind,
                    payload=payload,
                )
            )
        res = dispatch_event(ctx, receiver, item_kind, trace=trace)
        if res.outcome != DispatchOutcome.FIRED:
            ctx.clear_item_payload(receiver.path_string, item_kind)
        results.append(res)
    return results


def behavior_trace_to_records(trace: BehaviorTrace) -> list[dict[str, Any]]:
    """Flatten a trace into JSON-friendly dicts (export / diagram hook)."""
    out: list[dict[str, Any]] = []
    for s in trace.steps:
        out.append({
            "kind": "transition",
            "step_index": s.step_index,
            "part_path": s.part_path,
            "event_name": s.event_name,
            "from_state": s.from_state,
            "to_state": s.to_state,
            "effect_name": s.effect_name,
        })
    for s in trace.item_flows:
        rec: dict[str, Any] = {
            "kind": "item_flow",
            "step_index": s.step_index,
            "source_port_path": s.source_port_path,
            "target_port_path": s.target_port_path,
            "item_kind": s.item_kind,
        }
        if s.payload is not None:
            rec["payload"] = s.payload
        out.append(rec)
    for s in trace.decision_steps:
        out.append({
            "kind": "decision",
            "step_index": s.step_index,
            "part_path": s.part_path,
            "decision_name": s.decision_name,
            "chosen_action": s.chosen_action,
        })
    for s in trace.fork_join_steps:
        out.append({
            "kind": "fork_join",
            "step_index": s.step_index,
            "part_path": s.part_path,
            "block_name": s.block_name,
        })
    for s in trace.merge_steps:
        out.append({
            "kind": "merge",
            "step_index": s.step_index,
            "part_path": s.part_path,
            "merge_name": s.merge_name,
            "then_action": s.then_action,
        })
    for s in trace.sequence_steps:
        out.append({
            "kind": "sequence",
            "step_index": s.step_index,
            "part_path": s.part_path,
            "sequence_name": s.sequence_name,
        })
    out.sort(key=lambda r: r["step_index"])
    return out
