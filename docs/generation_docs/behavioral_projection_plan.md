# Behavioral Projection — Implementation Plan

## Purpose

`tg-model` has a complete behavioral authoring API (state machines, activity control flow,
inter-part items, scenarios). It was designed and implemented in Phase 6. What is missing is
the projection pipeline that reads these declarations and writes them to ThunderGraph's Neo4j
graph — making state and activity diagrams available in the ThunderGraph UI.

This document is the authoritative plan for closing that gap across three parallel workstreams:

1. **User Docs** — document behavioral authoring for engineers and agent consumers
2. **Projection Plumbing** — wire behavioral data from bundle walk → Neo4j → REST API
3. **Agent Skill and Tooling** — give the authoring agent access to behavioral capabilities

---

## Context: What Already Exists

### In tg-model (complete)

All behavioral declarations use the same `ModelDefinitionContext` (`model`) object available
inside any `Part.define()` method.

**State machine primitives:**
`model.state()`, `model.event()`, `model.guard()`, `model.action()`, `model.transition()`

**Activity / control-flow primitives:**
`model.action()`, `model.sequence()`, `model.decision()`, `model.merge()`, `model.fork_join()`

**Inter-part items:**
`model.item_kind()` + `emit_item()` at runtime

**Scenarios:**
`model.scenario()` + `validate_scenario_trace()` at runtime

**Projection extraction hook:**
`behavior_authoring_projection(definition_type)` returns a JSON-ready dict of all
behavioral declarations on a compiled type. This is the exact entry point `bundle_walker`
should call.

### In ThunderGraph (complete — frontend side)

- `StateViewWrapper` + all React Flow state diagram components already exist
- `FlowViewWrapper` + all React Flow activity diagram components already exist
- `GET /systems-model/state-view` route exists (queries legacy SysML data)
- `GET /systems-model/action-view` route was deleted (needs restoration)
- TypeScript types for `StateViewData` and `FlowViewData` are already defined

### What is missing

- `bundle_walker.py` does not call `behavior_authoring_projection()`
- `types.py` has no `StateRecord`, `ActionRecord`, `ControlNodeRecord`, or `SuccessionRecord`
- `diff_writer.py` does not write `State_*` or `Action_*` nodes or behavioral edges
- `/systems-model/action-view` does not exist
- `/systems-model/state-view` queries SysML parser data, not tg-model projection data
- User docs for behavioral authoring do not exist
- The agent authoring skill has no behavioral authoring guidance

---

## Workstream 1: User Documentation

### 1.1 New concept page — `user/concepts_behavior.md`

Write a user-facing guide covering behavioral authoring.
Style follows `concepts_parts.md` — minimal prose, working code examples.

**Sections:**

| Section | Content |
|---|---|
| State Machines | `model.state`, `model.event`, `model.guard`, `model.transition` — full worked example with a realistic part (mode machine) |
| Named Actions | `model.action` with `effect=` callable — what an action is, how it runs at simulation time |
| Activity Sequencing | `model.sequence` — the default, simplest control flow |
| Branching | `model.decision` + `model.merge` — exclusive branch/rejoin |
| Parallelism | `model.fork_join` — logically parallel branches |
| Inter-part Items | `model.item_kind` + `emit_item()` — how items cross structural connections |
| Scenarios | `model.scenario` + `validate_scenario_trace()` — behavioral contracts and validation |
| State + Activity Together | Short note: state machines and activity flow can coexist on the same Part |
| What ThunderGraph Shows | Brief paragraph on which declarations appear in state vs. activity diagram views |

**Target path:** `thundergraph-model/docs/user_docs/user/concepts_behavior.md`

Wire into `thundergraph-model/docs/user_docs/index.md` toctree after `concepts_evaluation`.

### 1.2 Internal integration reference — `user_docs/concepts_behavior.md`

The file at `docs/user_docs/concepts_behavior.md` (top-level, not in `user/`) currently holds
the ThunderGraph integration reference (DSL → ThunderGraph mapping, gap analysis, Neo4j schema).
Keep it as-is. It is not user-facing; it is reference material for ThunderGraph engineers
implementing the projection pipeline.

### 1.3 Update `api/index.md`

Add a short entry for the behavioral API surface:
`model.state`, `model.event`, `model.action`, `model.transition`, `model.sequence`,
`model.decision`, `model.merge`, `model.fork_join`, `model.item_kind`, `model.scenario`.
Link to the `concepts_behavior` page and to the Sphinx automodule for
`tg_model.execution.behavior`.

---

## Workstream 2: Projection Plumbing

### Guiding principle

Behavioral data is projection-only — engineers never write Neo4j schema directly.
The same `bundle_walker → diff_writer` pattern used for structural elements applies here.

### 2.1 `common/services/tg_model_projector/types.py`

Add TypedDicts for behavioral records:

```python
class StateRecord(TypedDict):
    stable_id: str          # deterministic from owner_stable_id + state name
    name: str
    owner_stable_id: str    # Part/System that owns this state machine
    is_initial: bool

class TransitionRecord(TypedDict):
    source_stable_id: str
    target_stable_id: str
    trigger: str            # event name
    guard: str              # guard name or "" for inline guards
    effect: str             # action name or ""

class ActionRecord(TypedDict):
    stable_id: str
    name: str
    owner_stable_id: str
    is_control_node: bool   # False for plain actions; True for decision/merge/fork/join
    node_type: str          # "action" | "decision" | "merge" | "fork" | "join"
    doc: str | None

class SuccessionRecord(TypedDict):
    source_stable_id: str
    target_stable_id: str
    guard: str              # guard label for decision→branch edges; "" otherwise

class ItemFlowRecord(TypedDict):
    source_port_stable_id: str
    target_port_stable_id: str
    item_kind: str
```

### 2.2 `common/services/tg_model_projector/bundle_walker.py`

Add `_walk_behavior(element_type, owner_stable_id)` function.

Detection: an element type has behavioral declarations when:
- `bool(getattr(element_type, "_tg_behavior_spec", None))` — has transitions (state machine)
- `bool(getattr(element_type, "_tg_decision_specs", None))` — has decisions (activity)
- `bool(getattr(element_type, "_tg_fork_join_specs", None))` — has fork/joins
- `bool(getattr(element_type, "_tg_sequence_specs", None))` — has sequences

When any of the above are truthy, call `behavior_authoring_projection(element_type)` and
translate the returned dict into `StateRecord`, `TransitionRecord`, `ActionRecord`,
`SuccessionRecord`, and `ItemFlowRecord` lists.

**Control node → ActionRecord mapping:**

| tg-model concept | `node_type` | Notes |
|---|---|---|
| `model.action()` | `"action"` | `is_control_node=False` |
| `model.decision()` | `"decision"` | `is_control_node=True`; emit `SuccessionRecord` for each branch |
| `model.merge()` | `"merge"` | `is_control_node=True`; emit `SuccessionRecord` to `then_action` if set |
| `model.fork_join()` | `"fork"` + `"join"` | Two `ActionRecord`s (fork start + join end); branches become `SuccessionRecord`s between fork and join; `then_action` is a `SuccessionRecord` from join |
| `model.sequence()` | N/A | Emits `SuccessionRecord` chains only; no node of its own |

**Sequence → SuccessionRecord translation:**

For `model.sequence("loop", steps=["a", "b", "c"])`, emit:
- `SuccessionRecord(source=stable_id(a), target=stable_id(b), guard="")`
- `SuccessionRecord(source=stable_id(b), target=stable_id(c), guard="")`

**Stable ID scheme:**

Stable IDs for behavioral nodes should follow the same deterministic pattern as structural
nodes: `hash(owner_stable_id + "." + node_name)`. This ensures re-projection is idempotent.

### 2.3 `common/services/tg_model_projector/diff_writer.py`

Add behavioral write operations (parallel to existing structural element writes):

**State nodes:**
```cypher
MERGE (s:State_{project_id}:Element_{project_id} {stable_id: $stable_id})
SET s.name = $name, s.is_initial = $is_initial
MERGE (owner)-[:AGGREGATES]->(s)
```

**Transition relationships:**
```cypher
MATCH (a:Element_{project_id} {stable_id: $source})
MATCH (b:Element_{project_id} {stable_id: $target})
MERGE (a)-[t:TRANSITION]->(b)
SET t.trigger = $trigger, t.guard = $guard, t.effect = $effect
```

**Action / control nodes:**
```cypher
MERGE (a:Action_{project_id}:Element_{project_id} {stable_id: $stable_id})
SET a.name = $name, a.node_type = $node_type, a.is_control_node = $is_control_node
MERGE (owner)-[:AGGREGATES]->(a)
```

**Succession relationships:**
```cypher
MATCH (a:Element_{project_id} {stable_id: $source})
MATCH (b:Element_{project_id} {stable_id: $target})
MERGE (a)-[s:SUCCESSION]->(b)
SET s.guard = $guard
```

**Item flow relationships:**
```cypher
MATCH (p1:Element_{project_id} {stable_id: $source_port})
MATCH (p2:Element_{project_id} {stable_id: $target_port})
MERGE (p1)-[f:ITEM_FLOW]->(p2)
SET f.item_kind = $item_kind
```

### 2.4 Backend API — `api_server/services/sysml/`

**State view service** (`state_view_data.py`):

The existing query targets `State_{project_id}` nodes from the SysML parser ingest.
For tg-model projects these nodes now come from the projection pipeline (same label,
same properties). The query should work unchanged — verify against projected data.

Properties to confirm are written: `name`, `is_initial`, `is_parallel` (default False),
`parent_part` (owner element name), `entry_action`, `exit_action`, `do_action` (all null for now).

**Action view service** (new — `action_view_data.py`):

Restore this file (it was deleted during the SysML migration). Query:

```cypher
MATCH (root:Element_{project_id} {stable_id: $view_id})
OPTIONAL MATCH (root)-[:AGGREGATES*1..]->(a:Action_{project_id})
WHERE NOT a.is_control_node
OPTIONAL MATCH (root)-[:AGGREGATES*1..]->(cn:Action_{project_id})
WHERE cn.is_control_node
OPTIONAL MATCH (a1:Element_{project_id})-[s:SUCCESSION]->(a2:Element_{project_id})
WHERE (root)-[:AGGREGATES*1..]->(a1)
  AND (root)-[:AGGREGATES*1..]->(a2)
OPTIONAL MATCH (p1:Port_{project_id})-[f:ITEM_FLOW]->(p2:Port_{project_id})
...
RETURN root, collect(distinct a), collect(distinct cn), collect(distinct s), collect(distinct f)
```

**Action view route** (`api_server/routers/systems_model.py`):

Re-add `GET /systems-model/action-view` handler. Mirrors the signature of
`GET /systems-model/state-view`.

### 2.5 Tests

- Unit test: `_walk_behavior()` on a compiled `Part` with known states and transitions
- Unit test: `_walk_behavior()` on a `Part` with sequence + decision + fork_join
- Integration test: project a small model with behavior → assert Neo4j has `State_*` nodes and `TRANSITION` edges
- API test: `GET /systems-model/state-view` returns correct `StateViewData` for a projected model
- API test: `GET /systems-model/action-view` returns correct `FlowViewData`

---

## Workstream 3: Agent Skill and Tooling

### 3.1 `agents/skills/tg_model_authoring/SKILL.md`

Add a **Behavioral Authoring** section after the existing System Composition section.

Cover:
- When to use state machines vs. activity sequencing (short decision guide)
- State machine authoring: `model.state`, `model.event`, `model.guard`, `model.transition` — worked example
- Activity authoring: `model.action`, `model.sequence`, `model.decision`, `model.merge`, `model.fork_join` — worked example
- Common mistakes / guard rails (inline guard `when=` vs. named `guard=`, no cross-part direct action calls)
- What ThunderGraph displays once projection is live (state diagram tab, activity/flow diagram tab)

The section should be at the same verbosity level as the existing Ports and Citations sections —
concrete examples, explicit rules, no ambiguity.

### 3.2 Access to tg-model user docs

The agent currently has no mechanism to read the `thundergraph-model/docs/user_docs/` pages
at tool-call time. Two options:

**Option A — embed key excerpts in SKILL.md (immediate, zero tooling)**

Copy the most important worked examples and rule tables directly into SKILL.md. The agent
reads the skill file at runtime; no new infrastructure needed. This is the right approach
for the authoring skill because the agent needs behavioral authoring rules to be in-context,
not discoverable.

**Option B — add a `read_tg_model_docs` tool (future)**

Expose a tool that accepts a doc page name and returns its content from the filesystem.
Useful for deeper reference (API index, concepts pages) when the agent needs to look up
detailed semantics it was not pre-loaded with. Lower priority — implement after Option A
proves insufficient.

**Recommended:** Implement Option A now. Add Option B when the agent demonstrates it
needs more than SKILL.md can carry.

### 3.3 Agent authoring skill update for behavioral tooling

Once the projection plumbing (Workstream 2) is live, update the skill to reflect:
- Behavioral declarations *are* projected and *do* appear in ThunderGraph
- State diagram tab appears for Parts with `model.state()` declarations
- Activity/flow diagram tab appears for Parts with `model.action()` / sequence declarations
- Engineers can see and navigate behavioral structure the same way they navigate structural Parts

---

## Execution Order

The workstreams are mostly independent. Recommended order:

| Step | Workstream | Dependency |
|---|---|---|
| 1 | Write user docs (`concepts_behavior.md`) | None |
| 2 | Update SKILL.md with behavioral authoring | None |
| 3 | Add `StateRecord`, `ActionRecord`, etc. to `types.py` | None |
| 4 | Implement `_walk_behavior()` in `bundle_walker.py` | Step 3 |
| 5 | Add behavioral write ops to `diff_writer.py` | Step 3 |
| 6 | Write projection unit + integration tests | Steps 4–5 |
| 7 | Verify state-view API against projected data | Steps 5–6 |
| 8 | Restore action-view API | Steps 5–6 |
| 9 | Add action-view route | Step 8 |
| 10 | Update SKILL.md again — note projection is live | Step 9 |

Steps 1–3 can start in parallel immediately.
Steps 4–5 depend on Step 3 only.
Steps 6–9 depend on Steps 4–5.

---

## Open Questions

| Question | Notes |
|---|---|
| Nested states (`parent_state`) | tg-model v0 has no nested state declaration. `StateData.parent_state` should be null for all projected states. Add nested state support in a later DSL version if needed. |
| Parallel state regions (`is_parallel`) | Not in tg-model v0. `StateData.is_parallel` should be false. |
| Entry/exit/do actions on states | Not in tg-model v0 DSL. `entry_action`, `exit_action`, `do_action` in `StateData` should be null for projected states. Add in a later DSL version. |
| Inline guards in transitions | `model.transition(when=lambda ...)` stores an un-serializable callable. Transition guard label should be `"<inline>"` in the projected `TransitionData.guard` string. |
| SysML-path projects | `State_*` and `Action_*` nodes from SysML ingest should still work. The state-view API query does not distinguish by ingest path — it queries by label. The action-view API is tg-model only (SysML action-view was already deleted). |
