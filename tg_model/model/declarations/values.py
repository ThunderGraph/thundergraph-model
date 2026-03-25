"""Value semantics declarations (roll-ups, etc.)."""

from __future__ import annotations

from typing import Any, Callable


class RollupDecl:
    """A declared roll-up computation."""

    def __init__(self, kind: str, selector: Any, value_func: Callable[[Any], Any]):
        self.kind = kind
        self.selector = selector
        self.value_func = value_func


class RollupBuilder:
    """Builder for roll-up expressions."""

    def sum(self, selector: Any, value: Callable[[Any], Any]) -> RollupDecl:
        return RollupDecl("sum", selector, value)


rollup = RollupBuilder()
