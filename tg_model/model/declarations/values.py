"""Value-semantics helpers: roll-up declarations for graph compilation.

Use :attr:`rollup` (a :class:`RollupBuilder`) as ``expr=`` on
:meth:`tg_model.model.definition_context.ModelDefinitionContext.attribute`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class RollupDecl:
    """Opaque roll-up declaration (``kind``, ``selector``, ``value_func``).

    Attributes
    ----------
    kind : str
        Roll-up kind (e.g. ``\"sum\"``).
    selector
        Structural selector passed from authoring.
    value_func : callable
        Per-child mapping function used when compiling the graph.
    """

    def __init__(self, kind: str, selector: Any, value_func: Callable[[Any], Any]):
        self.kind = kind
        self.selector = selector
        self.value_func = value_func


class RollupBuilder:
    """Fluent entrypoint for roll-up declarations (see :attr:`rollup`)."""

    def sum(self, selector: Any, value: Callable[[Any], Any]) -> RollupDecl:
        """Declare a sum roll-up over instances matched by ``selector``.

        Parameters
        ----------
        selector
            Structural selector (e.g. ``model.parts()``) understood by the graph compiler.
        value : callable
            Maps each matched instance to a quantity/expression to sum.

        Returns
        -------
        RollupDecl
            Opaque declaration attached to an attribute's ``expr=``.
        """
        return RollupDecl("sum", selector, value)


rollup = RollupBuilder()
