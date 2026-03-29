"""Solve group handler factory (SciPy ``root`` + unitflow residuals)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from unitflow.core.quantities import Quantity
from unitflow.core.units import Unit
from unitflow.expr.compile import compile_residual
from unitflow.expr.symbols import Symbol


def build_solve_group_handler(
    equations: list[Any],
    unknowns: list[Symbol],
    givens: list[Symbol],
    given_to_node_id: dict[Symbol, str],
    sym_to_slot_id: dict[int, str],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a compute handler that solves coupled equations for unknown slots.

    Parameters
    ----------
    equations : list
        Scalar expressions (length must match ``unknowns``).
    unknowns : list[Symbol]
        Unitflow symbols to solve for.
    givens : list[Symbol]
        Symbols bound from upstream graph values.
    given_to_node_id : dict
        Maps each given symbol to its dependency graph node id.
    sym_to_slot_id : dict
        Maps ``id(symbol)`` to unknown ``ValueSlot.stable_id``.

    Returns
    -------
    callable
        ``handler(dep_values) -> dict[stable_id, Quantity]``.

    Raises
    ------
    RuntimeError
        If SciPy/NumPy are not installed, the solver fails to converge, or symbol mapping is broken.
    ValueError
        If the system is empty or mismatched counts.
    TypeError
        If a given is not a :class:`~unitflow.core.quantities.Quantity`.
    """
    try:
        import numpy as np
        from scipy.optimize import root
    except ImportError:
        raise RuntimeError("scipy and numpy are required for solve group execution")

    if not equations:
        raise ValueError("Solve group requires at least one equation")
    if not unknowns:
        raise ValueError("Solve group requires at least one unknown")
    if len(equations) != len(unknowns):
        raise ValueError(f"Underdetermined/overdetermined system: {len(equations)} equations, {len(unknowns)} unknowns")

    all_syms = unknowns + givens
    reference_units: dict[Symbol, Unit] = {}
    for sym in all_syms:
        u = sym.unit
        if u is None:
            raise ValueError(f"Solve group symbol {sym.name!r} has no unit")
        reference_units[sym] = u

    residual_fns = [compile_residual(eq, all_syms, reference_units) for eq in equations]

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
                    f"Unknown symbol '{sym.name}' has no stable_id mapping. This is a graph compilation error."
                )
            solved[slot_id] = Quantity(float(res.x[i]), reference_units[sym])

        return solved

    return handler
