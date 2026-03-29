"""Symbolic references produced during ``define(cls, model)``.

Refs are **not** runtime instances. :class:`PartRef` and
:class:`RequirementRef` support dotted member access resolved against the
**compiled** child type. :class:`AttributeRef` forwards arithmetic to unitflow
:class:`~unitflow.expr.expressions.Expr` via :attr:`AttributeRef.sym`.

See Also
--------
tg_model.model.definition_context.ModelDefinitionContext
tg_model.model.expr.sum_attributes
"""

from __future__ import annotations

from typing import Any


class Ref:
    """Symbolic reference to one declared model element.

    Parameters
    ----------
    owner_type : type
        Type whose compiled artifact owns this path (often the configured root).
    path : tuple[str, ...]
        Declaration names from that owner (``()`` for the root part ref).
    kind : str
        Node kind (``requirement``, ``constraint``, ``event``, ...).
    target_type : type, optional
        Composed type for ``part`` / ``requirement_block`` refs.
    metadata : dict, optional
        Declaration metadata copied from compile records.
    """

    __slots__ = ("kind", "metadata", "owner_type", "path", "target_type")

    def __init__(
        self,
        owner_type: type,
        path: tuple[str, ...],
        kind: str,
        target_type: type | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.owner_type = owner_type
        self.path = path
        self.kind = kind
        self.target_type = target_type
        self.metadata = metadata or {}

    @property
    def local_name(self) -> str:
        """Dotted path string for this ref (``a.b.c``)."""
        return ".".join(self.path)

    def to_dict(self) -> dict[str, Any]:
        """Serialize ref to a JSON-friendly dict (owner name, path, kind, optional target).

        Returns
        -------
        dict
            Keys: ``owner``, ``path``, ``kind``; optional ``target_type``, ``metadata``.
        """
        payload: dict[str, Any] = {
            "owner": self.owner_type.__name__,
            "path": list(self.path),
            "kind": self.kind,
        }
        if self.target_type is not None:
            payload["target_type"] = self.target_type.__name__
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.owner_type.__name__}.{self.local_name}>"


class PortRef(Ref):
    """Reference to a declared port.

    Use with :meth:`tg_model.model.definition_context.ModelDefinitionContext.connect`.
    """


_symbol_cache: dict[tuple[type, tuple[str, ...]], Any] = {}
_symbol_id_to_path: dict[int, tuple[type, tuple[str, ...]]] = {}


class AttributeRef(Ref):
    """Reference to a declared attribute or parameter (value slot at configure time)."""

    @property
    def sym(self) -> Any:
        """Canonical unitflow symbol for this reference (cached per ref identity).

        Returns
        -------
        Symbol
            Unitflow symbol with ``unit`` from declaration metadata.

        Raises
        ------
        ValueError
            If ``metadata`` has no ``unit`` (symbols cannot be constructed).
        """
        key = (self.owner_type, self.path)
        if key not in _symbol_cache:
            from unitflow import symbol

            unit = self.metadata.get("unit")
            if unit is None:
                raise ValueError(f"AttributeRef '{self.local_name}' has no unit defined, cannot create Symbol.")
            sym = symbol(self.local_name, unit=unit)
            _symbol_cache[key] = sym
            _symbol_id_to_path[id(sym)] = key
        return _symbol_cache[key]

    def _unwrap(self, other: Any) -> Any:
        return other.sym if hasattr(other, "sym") else other

    def __add__(self, other: Any) -> Any:
        return self.sym + self._unwrap(other)

    def __radd__(self, other: Any) -> Any:
        return self._unwrap(other) + self.sym

    def __sub__(self, other: Any) -> Any:
        return self.sym - self._unwrap(other)

    def __rsub__(self, other: Any) -> Any:
        return self._unwrap(other) - self.sym

    def __mul__(self, other: Any) -> Any:
        return self.sym * self._unwrap(other)

    def __rmul__(self, other: Any) -> Any:
        return self._unwrap(other) * self.sym

    def __truediv__(self, other: Any) -> Any:
        return self.sym / self._unwrap(other)

    def __rtruediv__(self, other: Any) -> Any:
        return self._unwrap(other) / self.sym

    def __pow__(self, other: Any) -> Any:
        return self.sym ** self._unwrap(other)

    def __eq__(self, other: Any) -> Any:  # type: ignore[override]
        return self.sym == self._unwrap(other)

    def __lt__(self, other: Any) -> Any:
        return self.sym < self._unwrap(other)

    def __le__(self, other: Any) -> Any:
        return self.sym <= self._unwrap(other)

    def __gt__(self, other: Any) -> Any:
        return self.sym > self._unwrap(other)

    def __ge__(self, other: Any) -> Any:
        return self.sym >= self._unwrap(other)

    def to(self, target_unit: Any) -> Any:
        return self.sym.to(target_unit)


class PartRef(Ref):
    """Reference to a declared part; dot access chains into the child compiled type.

    Raises
    ------
    AttributeError
        If ``target_type`` is missing, the type is not compiled, or the member does not exist.
    """

    def __getattr__(self, name: str) -> Ref:
        if name.startswith("_"):
            raise AttributeError(name)
        if self.target_type is None:
            raise AttributeError(f"{self!r} has no target_type for member lookup")

        compiled = self.target_type.compile()
        member = compiled["nodes"].get(name)
        if member is None:
            raise AttributeError(f"{self.target_type.__name__} has no declared member named '{name}'")

        chained_path = (*self.path, name)
        member_kind: str = member["kind"]
        member_metadata: dict[str, Any] = member.get("metadata", {})
        type_registry: dict[str, type] = compiled.get("_type_registry", {})
        member_target_type: type | None = type_registry.get(name)

        if member_kind == "port":
            return PortRef(self.owner_type, chained_path, kind="port", metadata=member_metadata)
        if member_kind == "attribute" or member_kind == "parameter":
            return AttributeRef(self.owner_type, chained_path, kind=member_kind, metadata=member_metadata)
        if member_kind == "part":
            return PartRef(
                self.owner_type,
                chained_path,
                kind="part",
                target_type=member_target_type,
                metadata=member_metadata,
            )
        if member_kind == "state":
            return Ref(self.owner_type, chained_path, kind="state", metadata=member_metadata)
        if member_kind == "event":
            return Ref(self.owner_type, chained_path, kind="event", metadata=member_metadata)
        if member_kind == "action":
            return Ref(self.owner_type, chained_path, kind="action", metadata=member_metadata)
        if member_kind == "scenario":
            return Ref(self.owner_type, chained_path, kind="scenario", metadata=member_metadata)
        if member_kind == "guard":
            return Ref(self.owner_type, chained_path, kind="guard", metadata=member_metadata)
        if member_kind == "merge":
            return Ref(self.owner_type, chained_path, kind="merge", metadata=member_metadata)
        if member_kind == "item_kind":
            return Ref(self.owner_type, chained_path, kind="item_kind", metadata=member_metadata)
        if member_kind == "decision":
            return Ref(self.owner_type, chained_path, kind="decision", metadata=member_metadata)
        if member_kind == "fork_join":
            return Ref(self.owner_type, chained_path, kind="fork_join", metadata=member_metadata)
        if member_kind == "sequence":
            return Ref(self.owner_type, chained_path, kind="sequence", metadata=member_metadata)
        if member_kind == "requirement":
            return Ref(
                self.owner_type,
                chained_path,
                kind="requirement",
                metadata=member_metadata,
            )
        if member_kind == "requirement_block":
            return RequirementRef(
                self.owner_type,
                chained_path,
                kind="requirement_block",
                target_type=member_target_type,
                metadata=member_metadata,
            )
        if member_kind == "citation":
            return Ref(
                self.owner_type,
                chained_path,
                kind="citation",
                metadata=member_metadata,
            )
        raise AttributeError(
            f"Member '{name}' on {self.target_type.__name__} has kind '{member_kind}' "
            "which cannot be projected into a typed reference."
        )


class RequirementRef(Ref):
    """Reference to a declared composable requirement package (dot access like :class:`PartRef`).

    Raises
    ------
    AttributeError
        If the package type is not compiled yet, the member is missing, or the kind cannot
        be projected (only requirement subtree kinds are allowed).
    """

    def __getattr__(self, name: str) -> Ref | RequirementRef:
        if name.startswith("_"):
            raise AttributeError(name)
        if self.target_type is None:
            raise AttributeError(f"{self!r} has no target_type for member lookup")

        compiled = getattr(self.target_type, "_compiled_definition", None)
        if compiled is None:
            raise AttributeError(
                f"{self.target_type.__name__} is not compiled yet; register it with "
                f"model.requirement_package(...) before using dot access on the ref"
            )
        member = compiled["nodes"].get(name)
        if member is None:
            raise AttributeError(f"{self.target_type.__name__} has no declared member named '{name}'")

        chained_path = (*self.path, name)
        member_kind: str = member["kind"]
        member_metadata: dict[str, Any] = member.get("metadata", {})
        type_registry: dict[str, type] = compiled.get("_type_registry", {})
        member_target_type: type | None = type_registry.get(name)

        if member_kind == "requirement":
            return Ref(
                self.owner_type,
                chained_path,
                kind="requirement",
                metadata=member_metadata,
            )
        if member_kind == "requirement_block":
            return RequirementRef(
                self.owner_type,
                chained_path,
                kind="requirement_block",
                target_type=member_target_type,
                metadata=member_metadata,
            )
        if member_kind == "citation":
            return Ref(
                self.owner_type,
                chained_path,
                kind="citation",
                metadata=member_metadata,
            )
        raise AttributeError(
            f"Member '{name}' on {self.target_type.__name__} has kind '{member_kind}' "
            "which cannot be projected from a RequirementRef "
            "(allowed: requirement, requirement_block, citation)."
        )
