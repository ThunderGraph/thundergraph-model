# Testing

## Layout

| Location | Role |
|----------|------|
| `tests/unit/` | Fast, focused tests of **one module or behavior** (compiler edge cases, ref resolution, evaluator semantics). |
| `tests/integration/` | **Cross-module** flows: end-to-end instantiate → graph → evaluate, example smoke, multi-scenario analysis. |

Use the same conventions as the rest of the repo: **pytest**, fixtures where they reduce duplication, **no network** unless a test explicitly requires it (external compute tests use fakes or local callables).

## Adding a regression

1. **Reproduce** the bug or contract with the smallest `ConfiguredModel` / graph you can.
2. Place the test next to the subsystem it guards: **compiler** regressions near graph or compile tests; **execution** regressions near evaluator or run context tests.
3. **Assert** on stable outcomes: `RunResult.passed`, `ValidationResult.failures`, `constraint_results`, or specific slot values via `RunContext.get_value` / stable ids.
4. Run locally:

```bash
cd thundergraph-model
uv run pytest tests/unit/path/test_file.py -q
uv run pytest -q
```

## Coverage

`pyproject.toml` enables coverage on `tg_model` for the default pytest run. For **quick iteration** you can use `uv run pytest --no-cov`.

## References

- Repository layout: {doc}`repository_map`
- Contributing: {doc}`contributing`
