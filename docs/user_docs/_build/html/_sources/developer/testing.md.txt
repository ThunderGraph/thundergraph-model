# Testing

## Layout

| Location | Role |
|----------|------|
| `tests/unit/` | Fast, focused tests of **one module or behavior** (compiler edge cases, ref resolution, evaluator semantics). |
| `tests/integration/` | **Cross-module** flows: end-to-end instantiate → graph → evaluate, example smoke, multi-scenario analysis. |

Use the same conventions as the rest of the repo: **pytest**, fixtures where they reduce duplication, **no network** unless a test explicitly requires it (external compute tests use fakes or local callables).

## Adding a regression

1. **Reproduce** the bug or contract with the smallest `ConfiguredModel` / graph you can.
2. Place the test next to the subsystem it guards: **compiler** regressions near graph or compile tests; **execution** regressions near evaluator, run context, or **`configured_model`** (facade) tests.
3. **Assert** on stable outcomes: `RunResult.passed`, `ValidationResult.failures`, `constraint_results`, or specific slot values via `RunContext.get_value` / stable ids.
4. **Facade vs explicit pipeline:** Product-facing behavior is often easiest to exercise with **`ConfiguredModel.evaluate`** and **`ValueSlot`** keys. Use **`compile_graph` → `Evaluator.evaluate`** when the regression is about graph identity, handler wiring, **`evaluate_async`**, or parity with the low-level API. Integration tests may compare both paths for the same inputs.
5. **Requirement packages and nested scopes:** Policy, symbol threading, instantiation, and graph resolution for composable **`Requirement`** types are easy to get subtly wrong across **nested packages**, **package-level** slots, and **`allocate`** wiring. Prefer adding focused tests next to **`tests/unit/model/test_requirement_block.py`** (name is historical; coverage includes **`requirement_package`**, package **`parameter`**/**`attribute`**/**`constraint`**, nested outer/inner packages, and **`slot_ids_for_part_subtree`**). Mirror real examples with the smallest **`System`** that reproduces the bug.
6. Run locally:

```bash
cd thundergraph-model
uv run pytest tests/unit/path/test_file.py -q
uv run pytest -q
```

## Notebooks

After changing **`notebooks/*.ipynb`** or example code they import, execute them headless from **`thundergraph-model/`** ( **`nbconvert`** lives in the **`dev`** dependency group):

```bash
uv run --group dev python -m jupyter nbconvert --execute --inplace notebooks/<name>.ipynb
```

If **`IPython`** warns about a non-writable **`~/.ipython`**, set **`IPYTHONDIR`** to a writable directory for that command.

## Coverage

`pyproject.toml` enables coverage on `tg_model` for the default pytest run. For **quick iteration** you can use `uv run pytest --no-cov`.

## References

- Execution vocabulary (default vs advanced): {doc}`architecture`
- Repository layout: {doc}`repository_map`
- Contributing: {doc}`contributing`
