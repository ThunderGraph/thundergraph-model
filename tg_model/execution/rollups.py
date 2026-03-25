"""Roll-up compilation and execution."""

from __future__ import annotations

from typing import Any, Callable


def build_rollup_handler(
    kind: str,
    value_func: Callable[[Any], Any],
    child_slots: list[str],
) -> Callable[[dict[str, Any]], Any]:
    """Build a compute handler for a roll-up.

    Raises at evaluation time if no child values are available,
    since a silent zero would hide structural modeling mistakes.
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
