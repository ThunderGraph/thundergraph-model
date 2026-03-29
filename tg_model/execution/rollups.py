"""Build evaluation handlers for attribute roll-ups (sum over child slots)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def build_rollup_handler(
    kind: str,
    value_func: Callable[[Any], Any],
    child_slots: list[str],
) -> Callable[[dict[str, Any]], Any]:
    """Build a graph compute handler for one roll-up node.

    Parameters
    ----------
    kind : str
        Roll-up kind (currently ``\"sum\"``).
    value_func : callable
        Per-child mapper (from graph compiler).
    child_slots : list[str]
        Stable ids of contributor value nodes.

    Returns
    -------
    callable
        ``handler(dep_values) -> aggregated quantity``.

    Raises
    ------
    ValueError
        At **handler build** time if ``child_slots`` is empty; at **evaluation** time if no
        child values are present (avoids silent zero).

    Notes
    -----
    Empty selector is a structural error, not a numeric zero.
    """
    if not child_slots:
        raise ValueError(
            f"Roll-up ({kind}) has no child slots — the selector resolved to nothing. "
            f"This likely indicates a missing child part or incorrect selector."
        )

    def handler(dep_values: dict[str, Any]) -> Any:
        values = [dep_values[slot_id] for slot_id in child_slots if slot_id in dep_values]
        if not values:
            raise ValueError(
                f"Roll-up ({kind}) received no realized child values at evaluation time. "
                f"Expected values from: {child_slots}"
            )
        if kind == "sum":
            total = values[0]
            for v in values[1:]:
                total = total + v
            return total
        raise ValueError(f"Unknown rollup kind: {kind}")

    return handler
