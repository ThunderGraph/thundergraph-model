# Commercial aircraft example (cargo freighter)

End-to-end ThunderGraph showcase: **authoritative requirements first** (declared with `model.requirement`, `requirement_input`, and **`requirement_attribute`** for mission-envelope margins in [`program/l1_requirement_blocks.py`](./program/l1_requirement_blocks.py), then citations and `allocate` in [`program/cargo_jet_program.py`](./program/cargo_jet_program.py)) **→** composition **→** roll-ups **→** external compute **→** citations **→** verification, with deliberate **`allocate`** traceability. After `instantiate`, derived requirement values appear on **`ConfiguredModel.requirement_value_slots`**.

**Start here:** [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) — requirements-first workflow, showcase thesis (golden thread), bounded contexts, import boundaries, citation policy, simulation touchpoints, and phased delivery.

## Status

**Phase 0–4 implemented:** root `System` [`CargoJetProgram`](./program/cargo_jet_program.py) (scenario-linked **thesis constraints**, **mission desk** `ExternalComputeBinding` → `mission_range_margin_m` + constraint), nested Level-1 requirements in [`program/l1_requirement_blocks.py`](./program/l1_requirement_blocks.py) with two atomic mission requirements and **`requirement_attribute`** margins (payload vs range), explicit `references` / `allocate` in `CargoJetProgram`, `allocate(..., inputs=…)` into derived [`Aircraft`](./product/aircraft.py) attributes, **six major assemblies** with roll-ups, **[`integrations/adapters.py`](./integrations/adapters.py)** + **[`integrations/bindings.py`](./integrations/bindings.py)** (scenario inputs via `parameter_ref` — no scenario globals; wing tool also uses wing-local parameters), **second binding owner** [`WingAssembly`](./product/major_assemblies/parts.py) (`wing_structural_intensity_kg_per_m`), citations + `references` + `allocate`. **Phase 4:** [`reporting/extract.py`](./reporting/extract.py) + [`reporting/snapshot.py`](./reporting/snapshot.py) and notebook [`notebooks/cargo_jet_program.ipynb`](../../notebooks/cargo_jet_program.ipynb) (evaluate → report).

## How to run (import path)

The installable wheel only includes `tg_model`. Import the example by putting **`thundergraph-model/examples`** on `PYTHONPATH` (the package root is **`examples/commercial_aircraft/`**):

```bash
cd thundergraph-model
export PYTHONPATH="examples${PYTHONPATH:+:$PYTHONPATH}"
uv run python -c "from commercial_aircraft import CargoJetProgram; print(CargoJetProgram.compile()['owner'])"
```

Notebook (from repo root or `thundergraph-model/`; the notebook prepends both the package root and `examples/`):

```bash
cd thundergraph-model
uv run jupyter nbconvert --to notebook --execute notebooks/cargo_jet_program.ipynb --stdout
```

## Tests

From `thundergraph-model/`:

```bash
uv run pytest tests/integration/test_commercial_aircraft_smoke.py -v --no-cov
```

The smoke test prepends `examples/` to `sys.path` so `import commercial_aircraft` resolves without packaging the example.

## Demo honesty (thesis + Level-1 requirements)

The **showcase “closure”** is **two stitched checks**, not one physics model: (1) the **mission desk** toy (`mission_range_margin_m` + non-negative constraint), (2) **declared envelope** constraints (scenario vs roll-ups / parameters). The ASCII report opens with the same explanation.

The printed report’s **verification** column describes how each Level-1 row is intended to be read: **executable acceptance** (mission closure with `allocate(inputs=…)`), **evidenced by constraints** (roll-ups / program constraints), or **context and citations only** (regulatory framing — **not** a certification claim). The extra unnamed `model.part()` on `CargoJetProgram` is the allocation target for **program-level** requirements that are not placed under the named `aircraft` part.
