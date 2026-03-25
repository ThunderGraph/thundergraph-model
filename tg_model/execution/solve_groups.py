"""Solve group execution using scipy.optimize."""

from __future__ import annotations

from typing import Any, Callable

from unitflow.core.quantities import Quantity
from unitflow.expr.compile import compile_residual
from unitflow.expr.symbols import Symbol


def build_solve_group_handler(
    equations: list[Any],
    unknowns: list[Symbol],
    givens: list[Symbol],
    given_to_node_id: dict[Symbol, str],
    sym_to_slot_id: dict[int, str],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a compute handler for a solve group using scipy.optimize.root.

    Returns a handler that takes dep_values (keyed by node_id) and
    returns solved values keyed by stable_id (not symbol name).
    """
    try:
        from scipy.optimize import root
        import numpy as np
    except ImportError:
        raise RuntimeError("scipy and numpy are required for solve group execution")

    if not equations:
        raise ValueError("Solve group requires at least one equation")
    if not unknowns:
        raise ValueError("Solve group requires at least one unknown")
    if len(equations) != len(unknowns):
        raise ValueError(
            f"Underdetermined/overdetermined system: "
            f"{len(equations)} equations, {len(unknowns)} unknowns"
        )

    all_syms = unknowns + givens
    reference_units = {sym: sym.unit for sym in all_syms}

    residual_fns = [
        compile_residual(eq, all_syms, reference_units)
        for eq in equations
    ]

    def handler(dep_values: dict[str, Any]) -> dict[str, Quantity]:
        given_floats = []
        for sym in givens:
            node_id = given_to_node_id[sym]
            qty = dep_values[node_id]
            if not isinstance(qty, Quantity):
                raise TypeError(f"Expected Quantity for given '{sym.name}', got {type(qty)}")
            val = qty.to(reference_units[sym]).magnitude
            given_floats.append(float(val))

        def objective(x: np.ndarray) -> np.ndarray:
            args = list(x) + given_floats
            return np.array([f(*args) for f in residual_fns])

        x0 = np.ones(len(unknowns))

        res = root(objective, x0)
        if not res.success:
            raise RuntimeError(f"Solver failed to converge: {res.message}")

        solved: dict[str, Quantity] = {}
        for i, sym in enumerate(unknowns):
            slot_id = sym_to_slot_id.get(id(sym))
            if slot_id is None:
                raise RuntimeError(
                    f"Unknown symbol '{sym.name}' has no stable_id mapping. "
                    f"This is a graph compilation error."
                )
            solved[slot_id] = Quantity(float(res.x[i]), reference_units[sym])

        return solved

    return handler
