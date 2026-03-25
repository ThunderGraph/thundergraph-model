"""Behavior declaration utilities (compile-time checks).

Authoring: :class:`tg_model.model.definition_context.ModelDefinitionContext`
``state``, ``event``, ``action``, ``transition``, ``scenario``.
"""

from __future__ import annotations

from typing import Any


def check_transition_determinism(transitions: list[dict[str, Any]]) -> None:
    """At most one transition per (from_state_name, event_name) for v0 determinism."""
    from tg_model.model.definition_context import ModelDefinitionError

    seen: set[tuple[str, str]] = set()
    for t in transitions:
        fs = t["from_state"].path[-1]
        ev = t["on"].path[-1]
        key = (fs, ev)
        if key in seen:
            raise ModelDefinitionError(
                f"Duplicate transition for state {fs!r} on event {ev!r}; "
                "v0 allows only one transition per (from_state, event) pair."
            )
        seen.add(key)
