# Releasing

## Version

The package version lives in **`pyproject.toml`** (`[project].version`). Bump it when you cut a release that publishes artifacts (wheel or PyPI).

## What ships

The **wheel** includes the **`tg_model`** package as defined by Hatch (`tool.hatch.build.targets.wheel`). Examples and notebooks live **beside** the package in the repo; they are not installed with the wheel unless you package them separately.

## Documentation

Static HTML is produced locally (or in CI in Phase 6) with:

```bash
cd thundergraph-model
uv run --group docs sphinx-build -W -b html docs/user_docs docs/user_docs/_build/html
```

Use **`-W`** (warnings as errors) so broken autodoc cross-references fail the build, matching the project documentation gate.

Publish the **contents** of `docs/user_docs/_build/html` to your hosting target (Read the Docs, GitHub Pages, or object storage). Align **site version** with **package version** policy when you formalize releases.

## References

- Install and dev setup: {doc}`../user/install`
- Contributing: {doc}`contributing`
