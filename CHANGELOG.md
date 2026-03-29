# Changelog

All notable changes to **thundergraph-model** are documented here. The format is loosely
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-03-28

### Removed

- **Breaking:** **`RequirementBlock`**, **`RequirementBlockRef`**, and **`ModelDefinitionContext.requirement_block(...)`** were removed from the public API. Use **`Requirement`**, **`RequirementRef`**, and **`requirement_package`**. Internal compiled node **`kind`** remains the string **`"requirement_block"`** (serialization / inspection only).

### Documentation

- FAQ **Upgrading from thundergraph-model before 0.2.0**; **concepts**, **API index**, **extension playbook**, **glossary**, and **drafts** updated so they no longer document removed shims. Requirement composition implementation plan **Phase 10** recorded.

## [0.1.0] - 2026-03-27

### Changed

- **Examples:** `commercial_aircraft` Level-1 module renamed to **`program/l1_requirement_packages.py`** (was `l1_requirement_blocks.py`); **`hpc_datacenter`** gains **`README.md`** with run / evaluate / pytest commands.
- **Tooling / quality:** `ruff check tg_model tests` and `ruff format tg_model tests` are clean; `pyright` passes on the repo (including tests and `docs/generation_docs/model_prototype_sketch.py`). Behavior dispatch tests use `cm.root` where the API expects a `PartInstance`.
- **Requirement package constraints:** compile rejects ``expr=None``; graph compile supports symbol-free expressions (with an anchor edge from a package slot so validation/evaluation order stay well-formed).
- **`slot_ids_for_part_subtree`** now includes value slots under composable requirement packages; uses `getattr(..., "_child_lookup", None)` so callers that pass a **`ConfiguredModel`** (only `value_slots` / `children` are forwarded) do not break behavior scoping.

### Added

- **`Requirement`** composable type and **`RequirementRef`** dot-access ref for nested requirement packages.
- **`ModelDefinitionContext.requirement_package(name, type)`** — registers a nested composable requirements package; internal compiled node kind remains **`requirement_block`** for artifact compatibility.
- **Composable `Requirement.define()`** may declare package-level **`parameter`**, **`attribute`**, and **`constraint`**. They materialize as **`ValueSlot`** handles under the configured root (e.g. ``cm.mission.x_m``), use **`symbol_owner` + path prefix** for `AttributeRef` threading (same idea as **`requirement_input`**), and participate in **`compile_graph`** / **`evaluate`** (constraints and derived attributes use **`_resolve_symbol_to_slot(..., model.root, ...)`**). **`RequirementPackageInstance`** exposes dot access from **`PartInstance`**; **`computed_by`** and **`RollupDecl`** on package slots are rejected at graph compile until supported.
- **Compile-time expression checks** for those package **`attribute`** / **`constraint`** values: tracked unitflow symbols must be prior package parameters/attributes (declaration order), **`symbol_owner`** threaded symbols (e.g. requirement inputs), or rejected as foreign; **negative tests** cover **`port`**, **`allocate`** edges, **`parameter_ref`** from another type, and undeclared package slots.
- **`examples/hpc_datacenter/`** — minimal notional colocation facility model (two Level-1 power requirements) plus **`notebooks/hpc_datacenter_parameter_sweep.ipynb`** demonstrating a factorial **parameter sweep** with **`compile_graph` + `validate_graph` once**, then **`ConfiguredModel.evaluate(..., validate=False)`** for each design point.
- **Evaluation façade:** `ConfiguredModel.evaluate(inputs=…)` — lazy compilation (shared cache with `compile_graph`), optional `validate_graph` per call (default on), handle-keyed inputs (`ValueSlot` or slot `stable_id` strings). Non-breaking; existing `compile_graph` → `Evaluator` → `RunContext` flow unchanged.
- **`System.instantiate()`** — class-method alias for `instantiate(SomeSystem)` on `System` subclasses.

### Deprecated (removed in 0.2.0)

- **`ModelDefinitionContext.requirement_block(...)`** and import aliases **`RequirementBlock`** / **`RequirementBlockRef`** — see **[0.2.0] Removed**.

### Documentation

- User guide (quickstart, mental model, FAQ, execution draft, external-compute concept) describes the **recommended** `evaluate` path vs the **explicit** pipeline.
- Sphinx API reference: `sphinx-build -W` (warnings as errors) passes; API index links façade entry points (`ConfiguredModel.evaluate`, `instantiate`, `System.instantiate`) and a **Composable requirements** cross-reference map (`Requirement`, `requirement_package`, `RequirementRef`, `RequirementPackageInstance`).
- Developer guide (`docs/user_docs/developer/`): architecture, extension playbook, testing, and repository map describe the **recommended** façade for app code and the **explicit** pipeline for extensions, async, and debugging; cross-links from the mental model and docs implementation plan.
- Commercial aircraft example (`examples/commercial_aircraft/`): README and integration smoke tests use **`ConfiguredModel.evaluate`** with **`ValueSlot`** keys; **`extract_cargo_jet_evaluation_report(cm, result)`** needs only **`RunResult`**; optional **`ctx=`** for demo provenance / slot summaries; explicit pipeline cross-linked from README.
- Terminology aligned for composable requirements: **`Requirement`** / **`requirement_package`** / **`RequirementRef`** in user-facing docs.
- **Phases 6–9** (user guide, developer guide, API index / Sphinx gate, notebooks): see requirement composition implementation plan §13.
