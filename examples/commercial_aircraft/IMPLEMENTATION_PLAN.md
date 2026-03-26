# Commercial cargo jet — example program (implementation plan)

This document defines **scope**, **package architecture**, **ThunderGraph feature coverage**, and **phased delivery** for a **modular, customer-facing** example: a **notional wide-body freighter** program (inspired by public **Class E / Part 25** transport-category cargo aircraft, *not* a claim of modeling any OEM type exactly).

The goal is an **end-to-end** walkthrough larger than a single notebook cell dump: **authoritative requirements (first) → composition → roll-ups → external “simulation” hydration → citations → verification**, with **clean layering** and **maintainable** Python structure (bounded contexts, explicit import rules — not “SOLID” as a sticker on folder names).

**Non-negotiable for this example:** **requirements come first.** Detailed requirement statements are **authored with ThunderGraph’s APIs** inside nested `RequirementBlock.define()` methods (`model.requirement`, `requirement_input`, `requirement_accept_expr`). The program root then attaches **citations**, **`references`**, and **`allocate`** in `CargoJetProgram.define()` so the wiring is explicit and readable. The **system structure** (Parts, attributes, constraints) is **derived to satisfy** those requirements; **`model.allocate`** targets are chosen **deliberately** for traceability — not sprinkled for convenience.

---

## Requirements-first engineering (modular specs + INCOSE-aligned quality)

### Why requirement *text* lives in `RequirementBlock` types (not ad hoc strings in the program root)

Systems engineers need to see **one obvious place** where each requirement is declared with the **real ThunderGraph calls** (`requirement`, `requirement_input`, `allocate`, …). The program root `CargoJetProgram` should mostly **compose** parts and **wire** citations and allocations — not hide requirement statements in a parallel “spec” module that readers must cross-reference. The reporting layer (`reporting/extract.py`) may duplicate short **table metadata** (labels for the ASCII report) but the **authoritative** wording lives in `l1_requirement_blocks.py`.

### INCOSE-aligned requirement writing (demo bar)

The example must showcase **professional** requirement statements aligned with common **INCOSE Systems Engineering Handbook** quality expectations (short labels below — the demo **narrates** these in notebook markdown or docstrings):

| Quality | What readers should see in the demo |
|--------|--------------------------------------|
| **Necessary** | Each requirement states a **real** stakeholder or certification need for this slice — no “filler.” |
| **Appropriate** | **Level** matches allocation (program L1 vs aircraft L2): no implementation trivia in L1. |
| **Unambiguous** | **One** intended meaning; defined terms (e.g. “design mission,” “MTOW”) tied to parameters or glossary. |
| **Complete** (for this slice) | **What**, **under which conditions** (scenario / environment), and enough context to verify. |
| **Verifiable** | Each requirement maps to **evidence** in the model: parameters, attributes, **constraints**, or explicit “verification by analysis” notes — not orphan text. |
| **Feasible / realistic** | Numbers labeled **notional** where needed; no fake precision. |
| **Singular** | Prefer **one** obligation per requirement ID; split merged “and also” statements when it improves testability. |

**Disclaimer:** “INCOSE-compliant” here means **style and quality-characteristic alignment** with widely published SE practice — not a claim of formal INCOSE certification or a complete organizational requirements process.

### Order of work (engineering workflow)

1. **Draft / refine** requirement statements in `program/l1_requirement_blocks.py` (nested blocks) and review text.
2. **Declare citations** and `model.references` from requirements to **C-*** nodes where applicable.
3. **Design** the Part tree and attributes so that **constraints / roll-ups** can **prove** satisfaction of allocated requirements.
4. **`model.allocate(requirement_ref, part_or_system_ref)`** — only **after** the tree exists — choosing the **element that owns the verification** (see below).
5. **Implement** external compute and reporting last, still **traced** to the same requirement IDs.

### Allocation principles (choose carefully)

**Allocation is not decorative.** Each `allocate` must answer: **which model element owns the attributes and checks that demonstrate this requirement is met?**

| Guideline | Rationale |
|-----------|-----------|
| **Allocate to the lowest part that can be verified** for that obligation | Avoid dumping everything on the root unless the root **holds** the constraint (e.g. mission-level closure). |
| **Mission / program L1** (payload–range, certification framing) | Often **`allocate` to `CargoJetProgram` root** or to **`Aircraft`** if the **vehicle** block owns the roll-up and mission constraints — **pick one pattern per requirement** and document in a one-line comment next to `allocate`. |
| **Discipline / subsystem** (thrust margin, wing mass breakdown) | **`allocate` to the Part** that owns the **externally computed** or **rolled-up** evidence (e.g. `PropulsionInstallation`, `WingAssembly`). |
| **No double-allocation confusion** | Same requirement ID should not be implicitly “owned” by two competing blocks without a **clear** split (parent vs child) explained in the spec module. |
| **Traceability** | Requirement module lists **intended allocatee** (field or comment) so code review matches intent. |

**Anti-pattern:** allocating all L1 requirements to a single generic part “because it’s easy” — the demo should **show intentional** mapping from **text → architecture → verification**.

---

## Showcase thesis (v1 “golden thread”)

**One primary verdict** the notebook and report must open with (and requirements/constraints must support):

> **Does the declared mission (payload + design range at the scenario design point) close inside the modeled **mass / performance envelope** — with explicit margin on the chosen figure?**

**v1 closure metric (chosen):** **range–payload / fuel–mass feasibility** at the root: modeled **mission-required fuel / weight** (from roll-ups + external mission desk where applicable) vs **available** capacity (MTOW / MZFW-style caps and **notional** fuel volume — all labeled **notional**). The **first screen of the report** states: scenario inputs → computed margin → PASS/FAIL on the top requirement(s).

Secondary tables (mass tree, external-compute provenance, subsystem stubs) **support** that story; they do not replace it. If Phase 3 slips, Phase 2 still delivers a **coherent** constraint + rollup that answers the thesis with parameters only.

---

## 1. Objectives

| Objective | Success criterion |
|-----------|-------------------|
| **Requirements-first + INCOSE-aligned demo** | **Authoritative** requirement text in **`program/l1_requirement_blocks.py`**; program root **`define()`** wires citations and **`allocate`**; statements meet the **quality bar** in §“Requirements-first engineering”; **`allocate`** follows **allocation principles** with traceability from requirement → owning Part. |
| **Parametric MBSE + integration slice** | Exercise **System/Part** composition, **parameters** vs **attributes** (expr + external), **constraints**, **citations** + **references**, **parameter_ref**, **ExternalComputeBinding** at **multiple hierarchy levels**, **evaluator** path, and a **readable report** tied to the **showcase thesis**. |
| **MBSE credibility** | **Requirements drive** structure: top-down **mission / program** context, assemblies and attributes **justify** allocated requirements. |
| **Provenance** | **Web-backed citations** attached to requirements or parameters where appropriate via `model.citation` + `model.references` — see **Citation policy** below. |
| **Software quality** | **Modular packages**, **thin notebooks**, **explicit import boundaries** (see §5.3), fake sims as small **adapters** + **binding factories**, **no** cross-module globals for scenario wiring. |
| **Honest scope** | **Not** aero CFD, **not** full Part 25 compliance matrix — a **traceable slice** with clear “notional” vs “cited” labels. |

**Explicitly out of scope for v1 (platform headline):** full **behavior** graphs (state machines / `emit_item`). This example is a **parametric architecture + verification** showcase; behavior can be a **later** add-on. **`solve_group`** remains optional.

---

## 2. Reference sources (for citations)

These are **representative public** anchors the example can cite.

### Citation policy (read this once)

**Citations justify requirement wording, regulatory/methodological context, and order-of-magnitude sanity — not reproduction of OEM type-specific data.** The program name **Atlas-400F** and numeric attributes in the model are **notional** unless a cell or metadata explicitly labels them as taken from a specific public table. References to OEM **ACAPS**-style documents illustrate **typical** transport-category airport-planning **categories** (e.g. weight class bands); they **do not** claim the model’s numbers are Boeing’s or any OEM’s published weights for a particular variant.

### Source table

| ID | Topic | Suggested citation node (metadata) |
|----|--------|--------------------------------------|
| **C-ACAPS** | Airport planning / external dimensions / weights **bands** typical of wide-body programs (illustrative family docs in public ACAPS) | Boeing *Airplane Characteristics for Airport Planning* (e.g. 777 family materials on `boeing.com` airport planning) — use for **terminology and categories**, not to copy OEM numbers into “Atlas-400F”. |
| **C-FAR25** | Airworthiness standards for transport category | 14 CFR Part 25 (eCFR), Title 14, Chapter I, Subchapter C, Part 25. |
| **C-AC25-7C** | Flight test / performance demonstration philosophy (high-level) | FAA AC 25-7C, *Flight Test Guide for Certification of Transport Category Airplanes*. |
| **C-AC25-22** | Mechanical systems certification context | FAA AC 25-22 (as applicable to “systems” requirements in the demo). |

**Implementation rule:** each `model.citation(...)` carries `uri=`, `title=`, `publisher=`, `retrieved=` (ISO date) in metadata for export and human audit.

---

## 3. Concept of operations (example story)

**Program:** “Atlas-400F” — **notional** Class E freighter for **long-range cargo** (single deck main deck ULD operation).

**Mission scenario (parameters on root `System`):**

- Payload demand (kg), design range (nmi or km), alternate fuel policy flag (simplified), departure field elevation (ft) — **not all need to be used in v1**; **minimum** set must support the **showcase thesis**.

**Top-level product:** **Aircraft** (configuration root for the vehicle product line in this repo example).

**External compute (fake “tools”):**

- **Program / vehicle:** mission performance desk (range–payload trade, reserve fuel lump) — feeds **thesis** closure.
- **Propulsion:** engine deck (thrust / SFC at a flight condition) — **one binding per owning part** (compiler rule).
- **Structures:** wing / empennage **mass breakdown** export (notional CAE).
- **Systems:** ECS thermal load snapshot, hydraulic demand snapshot — **discipline-sized** outputs, **not** duplicate masses that should be roll-ups.

**Roll-ups:** operating empty weight (OEW)-like and **mass** subtotals from **child parts** via **expressions**; **simulation** does **not** invent a second parallel “total mass” at the root unless explicitly documented as a separate accounting line.

---

## 4. ThunderGraph feature matrix (what this example must touch)

| Feature | Where it shows up |
|---------|-------------------|
| `System` root + `Part` tree | Root program type (see **Decisions & defaults**) → `Aircraft` → wings, fuselage, empennage, landing gear, propulsion, systems… |
| `model.requirement` + `model.allocate` | Requirement **text** in **`program/l1_requirement_blocks.py`**; **`allocate`** in `cargo_jet_program.py` to Parts that **own verification** (see **Allocation principles**). |
| `model.parameter` | Scenario + design knobs bound at `evaluate()`. |
| `model.attribute(expr=...)` | Mass, CG aggregates (where in scope), performance indices built from children. |
| `model.attribute(computed_by=...)` + `link_external_routes` | Discipline outputs per part owner. |
| `parameter_ref(RootSystem, ...)` | Nested parts consume **mission** parameters without globals. |
| `model.citation` + `model.references` | Requirements / key parameters trace to **C-*** nodes (per **Citation policy**). |
| `model.constraint` | Mass limits, **mission closure** vs scenario, min thrust margin — **tunable** for demo closure. |
| `instantiate` → `compile_graph` → `Evaluator` | One **evaluation** path with **inputs** map and **report** (see **Reporting snapshot**). |

---

## 5. Software architecture (bounded contexts + import rules)

### 5.1 Package layout (proposed)

```text
examples/commercial_aircraft/     # Python package ``commercial_aircraft`` (put ``examples/`` on PYTHONPATH)
  IMPLEMENTATION_PLAN.md            # this file
  README.md
  __init__.py                     # CargoJetProgram, reset_commercial_aircraft_types
  program/
    mission_context.py
    l1_requirement_blocks.py
    cargo_jet_program.py
  product/
    aircraft.py
    major_assemblies/...
  integrations/
    adapters.py
    bindings.py
  reporting/
    extract.py                    # ConfiguredModel + RunContext + RunResult → plain dict
    snapshot.py                   # dict → ASCII report

thundergraph-model/notebooks/
  cargo_jet_program.ipynb         # thin: path setup, instantiate, evaluate, extract → snapshot
```

### 5.2 Design principles (honest, not buzzwords)

- **Bounded contexts:** `program` (scenario ids/strings, **requirement blocks + program root**), `product` (Parts/Systems), `integrations` (adapters + binding factories), `reporting` (human output).
- **Extend tools without editing unrelated parts:** new fake tool = new adapter + **one** factory entry in `bindings.py` (or a dedicated small module if `bindings.py` grows).
- **Consistent `define()` contracts:** each `Part` / `System` uses the same patterns for parameters, attributes, and external compute.
- **Small adapters:** avoid one mega-simulator class; several discipline-sized `ExternalCompute` implementations.

### 5.3 Import boundaries and binding ownership

**Allowed dependency edges:**

| From | To | Notes |
|------|-----|--------|
| `notebooks/*` | `commercial_aircraft.*`, `tg_model` | Thin orchestration only. |
| `program/l1_requirement_blocks.py` | `tg_model` | Requirement **text** and inputs live next to **`model.requirement`** calls. |
| `product/*` | `tg_model`, `integrations.bindings`, `integrations.adapters` (only if a `define()` must name an adapter — prefer factories in `bindings` so `define()` calls **one** `make_foo_binding(model, ...)`). |
| `integrations/adapters.py` | `tg_model`, stdlib | No import of `product`. |
| `integrations/bindings.py` | `tg_model`, `adapters` | Factories accept **`root_block_type`** and **`ModelDefinitionContext`** / refs from caller — **avoid** `integrations` importing `product` types **if** that creates cycles; pass `CargoJetProgram` (or whatever root) **as an argument** from `define()` in `product` instead. |
| `reporting/extract.py` | `tg_model` (evaluator types) | **Only** module that turns runtime objects into **plain structures** for `snapshot.py`. |
| `reporting/snapshot.py` | `unitflow` (formatting quantities) optional | **No** `ConfiguredModel` / `Evaluator` types — only dicts/str/float inputs. |

**Binding ownership:** Each `ExternalComputeBinding` is constructed where the **owning part’s** attributes are hydrated — typically inside that part’s `define()` via a factory in `integrations/bindings.py`. **`link_external_routes`** stays next to the same factory call. **No** notebook-global binding variables.

### 5.4 Reporting snapshot

- **`reporting/extract.py` (optional but recommended):** one place that walks evaluation results and builds a **plain dict** (scenario, roll-ups, requirement checks, external provenance, **thesis margin**).
- **`reporting/snapshot.py`:** **pure** formatters: take that dict, print tables / banners. This avoids dumping `repr()` of framework objects in the notebook **without** pretending formatters need zero knowledge of domain — they only need **data**, not `Evaluator`.

---

## 6. Part breakdown (high level → drill down)

**Requirements drive decomposition:** the Level-1 set in `program/l1_requirement_blocks.py` is fixed (for v1) **before** the Part tree is finalized; each major block exists because it **supports** verification of one or more allocated requirements (or is an explicit stub for a future requirement).

**Level 0 — Program / mission (`System`):**

- Scenario parameters; **Level-1 requirements** in nested blocks; citations / references; **`allocate`** per **Allocation principles**.
- Composes: **`Aircraft`** (vehicle).

**Level 1 — Aircraft (`Part` or `System` under program):**

- **Mass / CG envelope** (simplified), **performance** roll-ups tied to the **showcase thesis**.
- Children (illustrative):
  - `FuselageAssembly`
  - `WingAssembly`
  - `EmpennageAssembly`
  - `LandingGearAssembly`
  - `PropulsionInstallation` (engines + mounts + nacelles lump)
  - `AircraftSystems` (avionics + electrical + hydraulic + environmental **as separate parts** where feasible)

**Level 2 — Example deep dives (pick 2–3 for v1 depth):**

- **Propulsion:** `EngineInstallation` → external **engine deck** compute.
- **Structures:** `WingAssembly` → skin/stringers simplified **notional** CAE masses.
- **Systems:** `EnvironmentalControlSystem` → **thermal load** external compute.

Everything else can be **parameterized stubs** with clear docstrings until a later phase.

---

## 7. Simulation integration pattern

| Layer | Typical hydration | Binding scope |
|-------|-------------------|---------------|
| Mission / program | Range–payload desk, reserve fuel | **Root** `System` owns binding; inputs from **scenario parameters** via `parameter_ref` in children |
| Aircraft | Performance indices (e.g. thrust margin) | **Aircraft**-local binding |
| Wing / propulsion / ECS | CAE / engine deck / thermal | **Same-type** part as attribute owner; **one binding per owner** |

**Anti-pattern to avoid:** a single notebook cell that constructs ten globals — use **factories** in `integrations/bindings.py`.

---

## 8. Phased implementation

### Phase 0 — Skeleton

- [x] `README.md` (run instructions, link to plan).
- [x] Package skeleton under `examples/commercial_aircraft/` with **docstrings** and modules per §5.1 — include **`program/l1_requirement_blocks.py`**.
- [x] No notebook execution requirement in CI yet unless the monorepo already standardizes it.

### Phase 1 — Requirements modules + program shell + citations

- [x] **`program/l1_requirement_blocks.py`:** **5** INCOSE-aligned Level-1 requirements (IDs, full statements, rationale) aligned with the **showcase thesis**.
- [x] Root `System` type (**`CargoJetProgram`**): explicit **`references`** / **`allocate`** wiring next to composition (requirement bodies stay in nested blocks).
- [x] `model.citation` nodes for **C-ACAPS** (Boeing airport planning), **C-FAR25** (eCFR), **C-AC25-7C** (FAA) — metadata with URIs.
- [x] `model.references` from requirements to citations.
- [x] **`model.allocate(...)`** for each requirement to the chosen Part/System ref — **consistent** with the nested block definitions.
- [x] Scenario parameters (**minimal** set for thesis): `scenario_payload_mass_kg`, `scenario_design_range_m`.
- [x] Integration smoke test: `tests/integration/test_commercial_aircraft_smoke.py`.

### Phase 2 — Aircraft tree + roll-ups

- [x] `Aircraft` + major assemblies **structured to match allocations** (each assembly **justifies** at least one constraint or future L2 requirement).
- [x] **Mass attributes** rolling up from children (`sum_attributes` / explicit expr).
- [x] Constraints: MTOW / MZFW-style sanity + **thesis** closure (notional caps) — **evidence** for allocated L1 requirements (scenario-linked closure constraints authored on **`CargoJetProgram`** so `parameter_ref` symbols resolve).

### Phase 3 — External compute (multi-level)

- [x] Adapters in `integrations/adapters.py` (fake but structured).
- [x] Bindings via `integrations/bindings.py`; **no** `_SCENARIO` globals; **`parameter_ref`** only (plus local wing parameters in the wing binding).
- [x] At least **two distinct** `ExternalComputeBinding` owners: **`CargoJetProgram`** (`mission_range_margin_m`) and **`WingAssembly`** (`wing_structural_intensity_kg_per_m`).

### Phase 4 — Notebook + report

- [x] Notebook at `thundergraph-model/notebooks/cargo_jet_program.ipynb` — thin narrative + **extract → snapshot** report (LEO-style `sys.path` bootstrap, **thesis margin** first, constraints + L1 table + external provenance).
- [x] `reporting/extract.py` + `reporting/snapshot.py` (**import boundaries:** `snapshot` stays dict-in / str-out; `extract` is the only module here that imports `tg_model`).
- [ ] Optional: `nbconvert` execute in CI (no monorepo pattern yet — run locally as in README).

---

## 9. Testing strategy

**Canonical smoke test path (pick this one):**

`thundergraph-model/tests/integration/test_commercial_aircraft_smoke.py`

- Import the root `System` type from the example package.
- `compile()` → `instantiate()` → `compile_graph()` → `Evaluator.evaluate()` with **minimal** inputs.
- Assert no throw; optionally assert **one** requirement or constraint outcome for regression.

**Compile-only tests** can live alongside other `tests/unit` patterns that import part types. **Citations:** assert `references` / compile edges using existing ThunderGraph test patterns where applicable.

Do **not** leave “if repo allows tests under examples” — the **default** is **`tests/integration/`** as above.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Scope creep | Freeze **Phase 1–3** deliverables; mark “future” assemblies as stubs; **thesis** stays the report’s spine. |
| Weak requirements as afterthought | **Phase 1** starts in **`program/l1_requirement_blocks.py`**; reviews treat those `model.requirement` calls as the **source of truth** for wording. |
| Careless allocation | Follow **Allocation principles**; keep **intended allocatee** in the requirement record; reject `allocate` that does not match **verification ownership**. |
| Misleading OEM numbers | **Citation policy** + **notional** labels on numbers; ACAPS for **categories**, not data copying. |
| Global state | Factories + `parameter_ref`; `reset_*` hook for notebook re-runs (mirror LEO pattern). |
| Integration/product import cycles | **Pass `root_block_type` into binding factories** from `define()`; keep `integrations` free of `import product` where possible. |

---

## 11. Decisions & defaults

Open items may still be discussed; **if nothing is decided before Phase 1 coding, use these defaults:**

| Topic | Default |
|--------|---------|
| **Root `System` type name** | `CargoJetProgram` |
| **Notebook location** | `thundergraph-model/notebooks/cargo_jet_program.ipynb` (alongside LEO and other demos — single place for “run the model”). |
| **CI** | **Smoke test only** (`tests/integration/...`) in CI; **no** notebook execute in CI until the monorepo has a clear pattern for it. |
| **v1 thesis metric** | **Mission mass / fuel closure** vs scenario payload + range (see **Showcase thesis**). |

---

## 12. Next step

Implement **Phase 0–1** in small steps: **`program/l1_requirement_blocks.py`** (INCOSE-aligned Level-1 text) **→** root `System` wiring + citations + **`allocate`** **→** scenario parameters, then Phase 2–4 following the **golden thread**, **allocation intent**, and **import boundaries** above.

---

## 13. Library-wide documentation (Sphinx + NumPy docstrings)

This file is the **commercial aircraft example** plan only. The roadmap for **hosted user/developer HTML docs** (Sphinx), **NumPy-style docstrings** across `tg_model`, and site structure lives here:

**[`docs/user_docs/IMPLEMENTATION_PLAN.md`](../../docs/user_docs/IMPLEMENTATION_PLAN.md)**

That plan covers user vs developer sections, API autodoc, phased rollout, and hosting — independent of this example.
