# Behavioral Modeling: States and Actions

This document covers the behavioral modeling capabilities in `tg-model` and how they map to
the ThunderGraph persistence and visualization layer.

For the design philosophy and diagram methodology, see
`docs/generation_docs/behavior_methodology.md`.

---


## What tg-model Supports Today

All behavioral declarations live inside a `Part` or `System` subclass's `define(cls, model)` method,
on the same `ModelDefinitionContext` object used for structural declarations.

### State Machine API

Declare discrete states, events, guards, and transitions that define how a part changes mode.

```python
from tg_model.model.elements import Part

class PropulsionSystem(Part):
    @classmethod
    def define(cls, model):
        model.name("Propulsion System")

        # States — exactly one must be initial=True
        idle    = model.state("idle",    initial=True)
        spooling = model.state("spooling")
        running = model.state("running")
        fault   = model.state("fault")

        # Events (discrete triggers)
        start_cmd  = model.event("start_cmd")
        spool_done = model.event("spool_done")
        fail       = model.event("fail")
        stop_cmd   = model.event("stop_cmd")

        # Named guard (reusable)
        power_ok = model.guard(
            "power_ok",
            predicate=lambda ctx, part: part.power_available_kw.value > 10.0,
        )

        # Named action (optional effect on a transition)
        log_start = model.action("log_start", effect=lambda ctx, part: None)

        # Transitions: from_state → to_state triggered by event
        model.transition(idle,    spooling, start_cmd,  guard=power_ok, effect="log_start")
        model.transition(spooling, running, spool_done)
        model.transition(running, fault,   fail)
        model.transition(fault,   idle,    stop_cmd)
```

**API reference:**

| Method | Purpose |
|--------|---------|
| `model.state(name, *, initial=False)` | Declare a state vertex. Exactly one per type should be `initial=True`. |
| `model.event(name)` | Declare a named trigger. Returned `Ref` is passed to `transition(on=)`. |
| `model.guard(name, *, predicate)` | Declare a reusable `(RunContext, PartInstance) -> bool` condition. |
| `model.action(name, *, effect=None)` | Declare a named action. `effect` is `(RunContext, PartInstance) -> None`. |
| `model.transition(from_state, to_state, on, *, when=None, guard=None, effect=None)` | Wire one state transition. Use either `when=` (inline callable) or `guard=` (named guard ref), not both. `effect=` is the action name to run after the state advances. |

**Runtime execution:**

```python
from tg_model.execution.behavior import dispatch_event, BehaviorTrace

trace = BehaviorTrace()
result = dispatch_event(ctx, part_instance, "start_cmd", trace=trace)
# result.outcome: "fired" | "no_match" | "guard_failed"
```

---

### Activity / Control-Flow API

Declare actions and the control-flow graph that sequences them within a part.

```python
class GuidanceComputer(Part):
    @classmethod
    def define(cls, model):
        model.name("Guidance Computer")

        # Actions
        sense    = model.action("sense_inputs")
        filter_  = model.action("kalman_filter")
        compute  = model.action("compute_guidance")
        actuate  = model.action("send_actuation")
        log_err  = model.action("log_error")
        recover  = model.action("recovery_mode")

        # Linear sequence (simplest case)
        model.sequence("nominal_loop", steps=["sense_inputs", "kalman_filter", "compute_guidance", "send_actuation"])

        # Guard for branching
        valid_solution = model.guard(
            "valid_solution",
            predicate=lambda ctx, part: part.convergence_residual.value < 1e-4,
        )

        # Merge point (shared continuation after decision branches)
        after_check = model.merge("after_check", then_action="send_actuation")

        # Decision: route based on guard
        model.decision(
            "check_solution",
            branches=[
                (valid_solution, "compute_guidance"),  # guard passes → compute
                (None, "log_error"),                   # unconditional fallback
            ],
            merge_point=after_check,
        )

        # Fork/join for parallel branches (v0: serial execution, logical parallelism)
        model.fork_join(
            "parallel_sensors",
            branches=[
                ["sense_inputs"],
                ["kalman_filter"],
            ],
            then_action="compute_guidance",
        )
```

**API reference:**

| Method | Purpose |
|--------|---------|
| `model.action(name, *, effect=None)` | Declare a named action node. |
| `model.sequence(name, *, steps)` | Linear chain of action names (simplest control flow). |
| `model.decision(name, *, branches, default_action=None, merge_point=None)` | Exclusive branch: first matching guard wins. `branches` is `list[(guard_ref \| None, action_name)]`. |
| `model.merge(name, *, then_action=None)` | Reunite alternative branches at a shared continuation action. |
| `model.fork_join(name, *, branches, then_action=None)` | Parallel branches (serial in v0), each branch is a list of action names. Joins at optional `then_action`. |

**Runtime execution:**

```python
from tg_model.execution.behavior import dispatch_sequence, dispatch_decision, dispatch_fork_join

dispatch_sequence(ctx, part, "nominal_loop", trace=trace)
dispatch_decision(ctx, part, "check_solution", trace=trace)
dispatch_fork_join(ctx, part, "parallel_sensors", trace=trace)
```

---

### Inter-Part Items

Items flow across structural connections between ports. Declare the item kind on the sending part;
the structural connection determines which receiving part gets the event.

```python
class RadarSensor(Part):
    @classmethod
    def define(cls, model):
        model.name("Radar Sensor")
        out_port = model.port("track_out", direction="out")

        # Declare the item kind label
        track = model.item_kind("radar_track")

        # Runtime: emit_item() dispatches along structural connections
        send_track = model.action("send_track", effect=lambda ctx, part: emit_item(
            ctx, cm, part.track_out, "radar_track", payload={"range_m": 1200.0}
        ))
```

**API reference:**

| Method | Purpose |
|--------|---------|
| `model.item_kind(name)` | Declare an item kind label for inter-part flows. |
| `emit_item(ctx, cm, source_port, item_kind, payload, *, trace=None)` | At runtime, send an item across structural connections from `source_port`. Triggers `dispatch_event` on each receiving part. |

---

### Scenarios

Scenarios declare a behavioral contract — an expected ordering of events and/or interactions —
for validation against execution traces.

```python
class PropulsionSystem(Part):
    @classmethod
    def define(cls, model):
        # ... states, events, transitions ...

        model.scenario(
            "normal_startup",
            expected_event_order=[start_cmd, spool_done],
            initial_behavior_state="idle",
            expected_final_behavior_state="running",
        )
```

**API reference:**

| Method | Purpose |
|--------|---------|
| `model.scenario(name, *, expected_event_order, initial_behavior_state=None, expected_final_behavior_state=None, expected_interaction_order=None, expected_item_kind_order=None)` | Declare a behavioral contract. Validated by `validate_scenario_trace()` at runtime. |

---

### Projection Hook

`behavior_authoring_projection(definition_type)` extracts the full compiled behavioral
declaration from a type, returning JSON-friendly structure. This is the intended entry point
for the ThunderGraph projector.

```python
from tg_model.execution.behavior import behavior_authoring_projection

proj = behavior_authoring_projection(PropulsionSystem)
# {
#   "owner": "PropulsionSystem",
#   "states": ["fault", "idle", "running", "spooling"],
#   "events": ["fail", "spool_done", "start_cmd", "stop_cmd"],
#   "actions": ["log_start"],
#   "guards": ["power_ok"],
#   "merges": [],
#   "decisions": [],
#   "fork_joins": [],
#   "sequences": [],
#   "item_kinds": [],
#   "scenarios": [],
#   "transitions": [
#     { "from_state": <Ref idle>, "to_state": <Ref spooling>, "on": <Ref start_cmd>,
#       "guard_ref": <Ref power_ok>, "when": None, "effect": "log_start" },
#     ...
#   ],
#   "edges": [...]
# }
```

---

## ThunderGraph Data Model

### State Diagram Shape

ThunderGraph exposes state machine data through `GET /systems-model/state-view` and renders
it with `StateViewWrapper`. The expected shape is:

```typescript
interface StateData {
  id: string;
  name: string;
  state_type: string;       // "idle" | "running" | etc (same as name for tg-model)
  parent_state: string | null;  // nested state support
  parent_part: string;
  is_initial: boolean;
  is_parallel: boolean;     // parallel region flag (not used in tg-model v0)
  entry_action: string | null;
  exit_action: string | null;
  do_action: string | null;
  doc: string | null;
}

interface TransitionData {
  id: string;
  source: string;           // state id
  target: string;           // state id
  trigger: string;          // event name
  guard: string;            // guard name or ""
  effect: string;           // action name or ""
}

interface StateViewData {
  part: { id: string; name: string };
  states: StateData[];
  transitions: TransitionData[];
}
```

Neo4j nodes: `State_{project_id}` (inherits `Element_{project_id}`)
Neo4j relationship: `TRANSITION` with properties `trigger`, `guard`, `effect`

### Activity Diagram Shape

ThunderGraph exposes activity/flow data through `GET /systems-model/action-view` and renders
it with `FlowViewWrapper`. The expected shape is:

```typescript
interface ActionData {
  id: string;
  name: string;
  action_type: string;      // same as name for tg-model actions
  parent_action?: string;   // for nested action decomposition
  parent_part?: string;
  input_params?: string;    // JSON-serialized input slot names
  output_params?: string;   // JSON-serialized output slot names
  doc?: string;
}

interface ControlNodeData {
  id: string;
  name: string;
  node_type: 'fork' | 'join' | 'decision' | 'merge' | 'start' | 'done';
  parent_action?: string;
  doc?: string;
}

interface SuccessionData {
  id: string;
  source: string;           // action or control-node id
  target: string;           // action or control-node id
  guard?: string;           // guard name (for decision → branch edges)
}

interface ItemFlowData {
  source: string;           // source action id
  target: string;           // target action id
  source_path: string;      // e.g. "radar_sensor.track_out"
  target_path: string;      // e.g. "tracker.track_in"
}

interface FlowViewData {
  root: { id: string; name: string; type: 'action' | 'part' };
  actions: ActionData[];
  control_nodes: ControlNodeData[];
  successions: SuccessionData[];
  item_flows?: ItemFlowData[];
}
```

Neo4j nodes: `Action_{project_id}` (inherits `Element_{project_id}`)
Neo4j relationships: `SUCCESSION` (control flow), `ITEM_FLOW` (data flow)

---

## DSL → ThunderGraph Mapping

### State Diagram Mapping

| tg-model DSL | ThunderGraph `StateData` / `TransitionData` |
|---|---|
| `model.state("idle", initial=True)` | `StateData { name="idle", is_initial=True, state_type="idle" }` |
| `model.state("running")` | `StateData { name="running", is_initial=False }` |
| `model.transition(idle, running, on=start_cmd, guard=power_ok, effect="log_start")` | `TransitionData { source=idle.id, target=running.id, trigger="start_cmd", guard="power_ok", effect="log_start" }` |
| `model.transition(idle, running, on=start_cmd, when=lambda ctx, p: ...)` | `TransitionData { trigger="start_cmd", guard="<inline>", effect="" }` |

**Fields not yet in tg-model DSL:**

| ThunderGraph field | Status |
|---|---|
| `parent_state` | Not in DSL — nested states are not declared in v0 |
| `is_parallel` | Not in DSL — parallel regions are not in v0 (fork/join is the parallel primitive) |
| `entry_action` / `exit_action` / `do_action` | Not in DSL — entry/exit behavior is a planned future extension |

### Activity Diagram Mapping

| tg-model DSL | ThunderGraph `ActionData` / `ControlNodeData` / `SuccessionData` |
|---|---|
| `model.action("sense_inputs")` | `ActionData { name="sense_inputs", action_type="sense_inputs" }` |
| `model.sequence("loop", steps=["a","b","c"])` | `SuccessionData` edges: `a→b`, `b→c` |
| `model.decision("check", branches=[(g,"a"),(None,"b")])` | `ControlNodeData { node_type="decision" }` + `SuccessionData` to each branch action (with guard label on edge where applicable) |
| `model.merge("after", then_action="c")` | `ControlNodeData { node_type="merge" }` + `SuccessionData` to `c` |
| `model.fork_join("parallel", branches=[["a"],["b"]], then_action="c")` | `ControlNodeData { node_type="fork" }`, `ControlNodeData { node_type="join" }`, edges to/from branches, edge from join to `c` |
| `model.item_kind("radar_track")` + `emit_item(...)` | `ItemFlowData { source_path=..., target_path=... }` across the structural connection |

**Start/done control nodes** are implied by the activity diagram — the projector should synthesize:
- A `start` node connected to the first action(s) in each sequence/fork/decision
- A `done` node at the terminal actions

---

## Gaps: What Is Not Yet Wired

The tg-model DSL has full behavioral declaration support today. What is missing is the
**projection pipeline** in the ThunderGraph backend that reads this data and writes it to Neo4j.

### Required new work

**1. `bundle_walker.py` — emit behavioral records**

Call `behavior_authoring_projection(element_type)` for each `Part`/`System` that has
behavioral declarations (detected by checking `bool(type._tg_behavior_spec or [])`
or `bool(getattr(type, "_tg_decision_specs", None))`), and emit:

- `StateRecord` per state
- `TransitionRecord` per transition
- `ActionRecord` per action
- `ControlNodeRecord` per decision/merge/fork_join (resolved to fork+join pair)
- `SuccessionRecord` per succession edge (from sequence steps, decision branches, merge continuations)
- `ItemFlowRecord` per declared `item_kind` that crosses a structural connection

**2. `types.py` — add behavioral TypedDicts**

```python
class StateRecord(TypedDict):
    stable_id: str
    name: str
    owner_stable_id: str   # parent Part/System stable_id
    is_initial: bool

class TransitionRecord(TypedDict):
    from_stable_id: str
    to_stable_id: str
    trigger: str
    guard: str             # guard name or ""
    effect: str            # action name or ""

class ActionRecord(TypedDict):
    stable_id: str
    name: str
    owner_stable_id: str
    doc: str | None

class ControlNodeRecord(TypedDict):
    stable_id: str
    name: str
    node_type: str         # "fork"|"join"|"decision"|"merge"
    owner_stable_id: str

class SuccessionRecord(TypedDict):
    source_stable_id: str
    target_stable_id: str
    guard: str             # guard label or ""

class ItemFlowRecord(TypedDict):
    source_port_stable_id: str
    target_port_stable_id: str
    item_kind: str
```

**3. `diff_writer.py` — create/update Neo4j nodes and edges**

- Write `State_{project_id}` nodes with `AGGREGATES` from owning element
- Write `TRANSITION` relationships between state nodes
- Write `Action_{project_id}` nodes with `AGGREGATES` from owning element
- Write control-node elements (can reuse `Action_{project_id}` with a `node_type` field)
- Write `SUCCESSION` relationships between action/control nodes
- Write `ITEM_FLOW` relationships for inter-part item flows

**4. Backend API**

- Restore `GET /systems-model/state-view` to query the tg-model projected `State_{project_id}`
  and `TRANSITION` data (it currently queries SysML ingest data, which remains available for
  SysML-path projects)
- Restore `GET /systems-model/action-view` endpoint (was deleted during SysML migration)
  to query tg-model projected `Action_{project_id}` / `SUCCESSION` / `ITEM_FLOW` data

**The frontend is already complete** — `StateViewWrapper`, `FlowViewWrapper`, and all React
components for both diagram types exist and are wired to the correct API endpoints.
