# Concept: Behavioral Modeling

Parts can carry behavioral declarations alongside their structural and parametric ones.
Two diagram views come from this: **state machines** (modes and transitions) and
**activity diagrams** (ordered action flow).

Both live inside `Part.define()` on the same `model` object used for parameters and constraints.

---

## State Machines

A state machine on a Part defines which discrete modes it can be in and what causes it to
change. Declare states, events, and transitions.

### Minimal state machine

```python
from tg_model import Part


class PropulsionSystem(Part):
    @classmethod
    def define(cls, model):
        model.name("propulsion_system")

        # States — exactly one must be initial=True
        idle     = model.state("idle",     initial=True)
        spooling = model.state("spooling")
        running  = model.state("running")
        fault    = model.state("fault")

        # Events (discrete triggers)
        start_cmd  = model.event("start_cmd")
        spool_done = model.event("spool_done")
        fail       = model.event("fail")
        stop_cmd   = model.event("stop_cmd")

        # Wire transitions
        model.transition(idle,     spooling, start_cmd)
        model.transition(spooling, running,  spool_done)
        model.transition(running,  fault,    fail)
        model.transition(fault,    idle,     stop_cmd)
```

`model.transition(from_state, to_state, on_event)` is the minimum — no guard, no effect.
The compiler enforces that at most one transition can exist for any `(from_state, event)` pair.

---

### Guards

A guard is a boolean condition that must pass before a transition fires.

Declare a named guard with `model.guard(name, predicate=...)` and pass it to `transition()`:

```python
class PropulsionSystem(Part):
    @classmethod
    def define(cls, model):
        model.name("propulsion_system")
        idle    = model.state("idle",    initial=True)
        running = model.state("running")

        power_ok = model.guard(
            "power_ok",
            predicate=lambda ctx, part: part.power_available_kw.value >= 10.0,
        )

        start = model.event("start_cmd")
        model.transition(idle, running, start, guard=power_ok)
```

For a one-off condition you can also use `when=` (inline callable) instead of a named guard:

```python
model.transition(idle, running, start,
                 when=lambda ctx, part: part.power_available_kw.value >= 10.0)
```

Use a named guard (`guard=`) when the same condition is reused across multiple transitions.
Use `when=` for a single-use inline check.

---

### Transition effects

An effect is an action that runs after the state advances when a transition fires.
Declare the action first, then reference it by name in `effect=`:

```python
class PropulsionSystem(Part):
    @classmethod
    def define(cls, model):
        model.name("propulsion_system")
        idle    = model.state("idle",    initial=True)
        running = model.state("running")
        start   = model.event("start_cmd")

        model.action("log_start", effect=lambda ctx, part: None)  # real logic goes here

        model.transition(idle, running, start, effect="log_start")
```

The `effect=` parameter takes the **action name** as a string, not the ref.

---

### Dispatching events at runtime

```python
from tg_model.execution.behavior import dispatch_event, BehaviorTrace

trace  = BehaviorTrace()
result = dispatch_event(ctx, part_instance, "start_cmd", trace=trace)

# result.outcome: "fired" | "no_match" | "guard_failed"
if result:  # bool(result) is True only on "fired"
    print("Transition fired")
```

---

## Activity / Control Flow

Activity declarations define how actions are ordered inside a part.

### Two kinds of actions

Actions fall into two categories based on whether they participate in an activity flow:

**Flow actions** — part of a functional sequence. They appear in the activity diagram.
Declare the successor with `then=`:

```python
model.action("sense_inputs",     then="filter_data")
model.action("filter_data",      then="compute_guidance")
model.action("compute_guidance", then="send_actuation")
model.action("send_actuation")   # terminal — no then= needed
```

The activity diagram renders: `sense_inputs → filter_data → compute_guidance → send_actuation`.

**Effect-only actions** — used purely as transition effects (`effect="action_name"` on a
`model.transition()`). Declare them plain with no `then=`. They appear as labels on
state-machine transitions but are **excluded from the activity diagram**:

```python
model.action("activate_ads")      # effect-only — transition label only
model.action("handover_to_ops")   # effect-only
```

Attach runtime logic with `effect=` regardless of kind:

```python
def _compute(ctx, part):
    pass  # read part state, write outputs

model.action("compute_guidance", then="send_actuation", effect=_compute)
```

---

### Linear flow with `then=` (default — use this)

`then=` replaces `model.sequence()` for the common linear case. One declaration per action:

```python
class GuidanceComputer(Part):
    @classmethod
    def define(cls, model):
        model.name("guidance_computer")

        # Effect-only (transition effects) — no then=
        model.action("log_error")

        # Flow actions — chained with then=
        model.action("sense_inputs",     then="filter_data")
        model.action("filter_data",      then="compute_guidance")
        model.action("compute_guidance", then="send_actuation")
        model.action("send_actuation")
```

`model.sequence()` still works and is kept for backward compatibility, but `then=` is
preferred — it co-locates the flow declaration with the action itself.

---

### Decisions and Merges (exclusive branching)

A decision evaluates guards in order and runs the action of the first matching branch.
A merge is the shared continuation point after the branches rejoin.

```python
valid = model.guard("valid_solution",
                    predicate=lambda ctx, p: p.residual.value < 1e-4)

# Merge: shared continuation after either branch
after_check = model.merge("after_check", then_action="send_actuation")

model.decision(
    "check_solution",
    branches=[
        (valid, "compute_guidance"),  # if valid → compute
        (None,  "log_error"),         # else (unconditional fallback)
    ],
    merge_point=after_check,
)
```

- Branches are evaluated top-to-bottom. First match wins.
- `None` guard means "always match" — use it as the last branch for a default.
- `merge_point=` wires the decision to an existing `merge` node; `dispatch_decision`
  runs the merge's `then_action` automatically after the branch action completes.

At runtime:

```python
from tg_model.execution.behavior import dispatch_decision

dispatch_decision(ctx, part, "check_solution", trace=trace)
```

---

### Fork / Join (parallel branches)

A fork splits control into multiple branches; a join waits for all of them to complete.
In v0 the branches run **serially in list order** (deterministic; not OS-level parallelism):

```python
model.fork_join(
    "sensor_fan_out",
    branches=[
        ["read_imu"],
        ["read_radar"],
        ["read_gps"],
    ],
    then_action="fuse_measurements",
)
```

At runtime:

```python
from tg_model.execution.behavior import dispatch_fork_join

dispatch_fork_join(ctx, part, "sensor_fan_out", trace=trace)
```

---

## Inter-Part Items

Items are the things that move across structural connections between parts.
Declare the item kind label on the sending part; at runtime `emit_item()` routes it
along the structural connection wired with `model.connect()`.

```python
from tg_model.execution.behavior import emit_item


class RadarSensor(Part):
    @classmethod
    def define(cls, model):
        model.name("radar_sensor")
        model.port("track_out", direction="out")
        model.item_kind("radar_track")

        def _send(ctx, part):
            emit_item(ctx, cm, part.track_out, "radar_track",
                      payload={"range_m": 1200.0}, trace=trace)

        model.action("send_track", effect=_send)
```

When `emit_item()` fires, it dispatches `"radar_track"` as an event on every receiving part
connected to `track_out`. This keeps inter-part behavior tied to the structural connection
graph — parts cannot call each other directly.

---

## Scenarios

A scenario is a behavioral contract: an expected ordering of events and/or interactions.
Use it to declare intent before full execution is available, or to validate execution traces.

```python
class PropulsionSystem(Part):
    @classmethod
    def define(cls, model):
        model.name("propulsion_system")
        # ... states, events, transitions ...

        model.scenario(
            "normal_startup",
            expected_event_order=[start_cmd, spool_done],
            initial_behavior_state="idle",
            expected_final_behavior_state="running",
        )
```

Validate a scenario against a collected `BehaviorTrace`:

```python
from tg_model.execution.behavior import validate_scenario_trace

ok, errors = validate_scenario_trace(
    definition_type=PropulsionSystem,
    scenario_name="normal_startup",
    part_path=part.path_string,
    trace=trace,
    ctx=ctx,
)
```

---

## State Machines and Activity Together

A single Part can have both a state machine and activity declarations. A common pattern
is using transition effects to trigger activity sequences:

```python
class FlightController(Part):
    @classmethod
    def define(cls, model):
        model.name("flight_controller")

        # State machine — mode tracking
        standby = model.state("standby", initial=True)
        active  = model.state("active")
        arm     = model.event("arm_cmd")

        # Activity — what happens when activated
        model.action("initialize_sensors")
        model.action("start_nav_loop")
        model.sequence("activation_sequence",
                       steps=["initialize_sensors", "start_nav_loop"])

        # Transition effect triggers the sequence
        def _on_arm(ctx, part):
            from tg_model.execution.behavior import dispatch_sequence
            dispatch_sequence(ctx, part, "activation_sequence")

        model.action("run_activation", effect=_on_arm)
        model.transition(standby, active, arm, effect="run_activation")
```

---

## ThunderGraph Diagram Views

Once behavioral declarations are projected to Neo4j (via the standard projection pipeline),
ThunderGraph displays two additional diagram tabs for any Part with behavioral data:

| Diagram | Shows | Driven by |
|---|---|---|
| **State Diagram** | States as nodes, transitions as edges with trigger/guard/effect labels | `model.state()`, `model.transition()` |
| **Activity Diagram** | Actions and control nodes, succession edges, item flows | `model.action()`, `model.sequence()`, `model.decision()`, `model.fork_join()`, `model.item_kind()` |

Both tabs use the same element selection mechanism as other diagram types —
select a Part in the navigation tree and the available diagram views appear.

---

## API Reference Summary

### State machine

| Call | Purpose |
|---|---|
| `model.state(name, *, initial=False)` | Declare a state vertex. Mark exactly one `initial=True`. |
| `model.event(name)` | Declare a named trigger. |
| `model.guard(name, *, predicate)` | Declare a reusable `(RunContext, PartInstance) → bool` condition. |
| `model.action(name, *, effect=None)` | Declare a named action. `effect` is `(RunContext, PartInstance) → None`. |
| `model.transition(from_state, to_state, on, *, when=None, guard=None, effect=None)` | Wire one transition. Use `when=` or `guard=`, not both. `effect=` is an action name string. |

### Activity / control flow

| Call | Purpose |
|---|---|
| `model.action(name, *, then=None, effect=None)` | Declare an action. `then=` names the successor — creates a succession edge and makes this action appear in the activity diagram. Omit `then=` for effect-only actions (transition effects only). |
| `model.sequence(name, *, steps)` | Linear chain of action names (backward compat — prefer `then=` instead). |
| `model.decision(name, *, branches, default_action=None, merge_point=None)` | Exclusive branch. `branches` is `list[(guard_ref \| None, action_name)]`. |
| `model.merge(name, *, then_action=None)` | Shared continuation after branching. |
| `model.fork_join(name, *, branches, then_action=None)` | Parallel branches; each branch is a list of action names. |
| `model.item_kind(name)` | Declare an inter-part item kind label. |
| `model.scenario(name, *, expected_event_order, ...)` | Behavioral contract declaration. |

### Runtime dispatch

| Call | Purpose |
|---|---|
| `dispatch_event(ctx, part, event_name, *, trace=None)` | Fire one event on the part's state machine. |
| `dispatch_sequence(ctx, part, sequence_name, *, trace=None)` | Run a declared linear sequence. |
| `dispatch_decision(ctx, part, decision_name, *, trace=None)` | Evaluate a decision and run the matching branch. |
| `dispatch_fork_join(ctx, part, block_name, *, trace=None)` | Execute a fork/join block. |
| `emit_item(ctx, cm, source_port, item_kind, payload, *, trace=None)` | Send an item across structural connections. |
| `validate_scenario_trace(...)` | Compare a `BehaviorTrace` against an authored scenario contract. |
