"""Build unitflow expressions from model refs without ``.sym`` boilerplate.

Python evaluates ``a + b + c`` **left to parenthesized**: ``(a + b) + c``. After ``a + b`` you have an
:class:`unitflow.expr.expressions.Expr`. The next ``+ c`` calls **Expr**'s ``__add__``, which uses
unitflow's ``_promote(c)`` — and **AttributeRef** is not a valid operand there, so you get
``ExprError: Cannot promote AttributeRef to Expr``.

**Ways to write roll-ups (pick one):**

- **Parentheses:** ``a + (b + c)`` so every ``+`` still involves an :class:`~tg_model.model.refs.AttributeRef` on the left.
- **Explicit symbols:** ``a.sym + b.sym + c.sym`` (what ``AttributeRef.__add__`` does internally for the left operand).
- **This module:** :func:`sum_attributes` / :func:`as_expr_leaf` — same thing, obvious intent for ME/MBSE authors.
"""

from __future__ import annotations

from typing import Any

from tg_model.model.refs import AttributeRef


def as_expr_leaf(x: Any) -> Any:
    """Promote :class:`~tg_model.model.refs.AttributeRef` to unitflow expr leaf.

    Parameters
    ----------
    x
        Attribute ref or already-expression value.

    Returns
    -------
    Any
        ``x.sym`` for refs; otherwise ``x``.

    Notes
    -----
    Use when hand-building sums so ``expr + AttributeRef`` never hits unitflow's ``_promote``.
    """
    if isinstance(x, AttributeRef):
        return x.sym
    return x


def sum_attributes(*terms: Any) -> Any:
    """Sum two or more attribute refs and/or expressions (associative-safe).

    Avoids the Python ``a + b + c`` left-association trap with mixed
    :class:`~tg_model.model.refs.AttributeRef` and :class:`~unitflow.expr.expressions.Expr`.

    Parameters
    ----------
    *terms
        Two or more refs and/or unitflow expressions.

    Returns
    -------
    Any
        Left-folded unitflow expression after :func:`as_expr_leaf` on each term.

    Raises
    ------
    ValueError
        If fewer than two terms are passed.

    Examples
    --------
    ``model.attribute("total_kg", unit=kg, expr=sum_attributes(a, b, c))``
    """
    if len(terms) < 2:
        raise ValueError("sum_attributes requires at least two terms")
    acc = as_expr_leaf(terms[0])
    for t in terms[1:]:
        acc = acc + as_expr_leaf(t)
    return acc
