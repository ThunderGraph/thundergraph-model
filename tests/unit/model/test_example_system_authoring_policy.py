"""Guard official examples against forbidden root System value/check declarations."""

from __future__ import annotations

import ast
from pathlib import Path


_THUNDERGRAPH_MODEL = Path(__file__).resolve().parents[3]
_EXAMPLES_ROOT = _THUNDERGRAPH_MODEL / "examples"


def _is_system_base(expr: ast.expr) -> bool:
    # This AST-only guard intentionally matches direct ``System`` bases in official
    # examples. Indirect subclasses would require import-time resolution instead.
    return isinstance(expr, ast.Name) and expr.id == "System"


def _forbidden_calls_in_system_define(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    hits: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(_is_system_base(base) for base in node.bases):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.FunctionDef) or stmt.name != "define":
                continue
            if len(stmt.args.args) < 2:
                continue
            model_name = stmt.args.args[1].arg
            for inner in stmt.body:
                if not isinstance(inner, ast.Expr):
                    if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        continue
                for call in ast.walk(inner):
                    if not isinstance(call, ast.Call):
                        continue
                    func = call.func
                    if (
                        isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == model_name
                        and func.attr in {"attribute", "constraint"}
                    ):
                        hits.append(f"{path.relative_to(_THUNDERGRAPH_MODEL)}:{node.name}.define -> model.{func.attr}(...)")
    return hits


def test_official_examples_keep_system_root_structural_only() -> None:
    violations: list[str] = []
    for path in sorted(_EXAMPLES_ROOT.rglob("*.py")):
        violations.extend(_forbidden_calls_in_system_define(path))
    assert violations == [], "System authoring policy violations:\n" + "\n".join(violations)
