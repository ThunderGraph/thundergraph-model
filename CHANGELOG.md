# Changelog

All notable changes to **thundergraph-model** are documented here. The format is loosely
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added

- **Evaluation façade:** `ConfiguredModel.evaluate(inputs=…)` — lazy compilation (shared cache with `compile_graph`), optional `validate_graph` per call (default on), handle-keyed inputs (`ValueSlot` or slot `stable_id` strings). Non-breaking; existing `compile_graph` → `Evaluator` → `RunContext` flow unchanged.
- **`System.instantiate()`** — class-method alias for `instantiate(SomeSystem)` on `System` subclasses.

### Documentation

- User guide (quickstart, mental model, FAQ, execution draft, external-compute concept) describes the **recommended** `evaluate` path vs the **explicit** pipeline.
- Sphinx API reference: `sphinx-build -W` (warnings as errors) passes; API index links façade entry points (`ConfiguredModel.evaluate`, `instantiate`, `System.instantiate`).
- Developer guide (`docs/user_docs/developer/`): architecture, extension playbook, testing, and repository map describe the **recommended** façade for app code and the **explicit** pipeline for extensions, async, and debugging; cross-links from the mental model and docs implementation plan.
- Commercial aircraft example (`examples/commercial_aircraft/`): README and integration smoke tests use **`ConfiguredModel.evaluate`** with **`ValueSlot`** keys; **`extract_cargo_jet_evaluation_report(cm, result)`** needs only **`RunResult`**; optional **`ctx=`** for demo provenance / slot summaries; explicit pipeline cross-linked from README.
