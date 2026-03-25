"""Deterministic identity derivation for model elements.

Identity is derived from fully qualified type names and declaration paths.
Two unrelated types with the same class name in different modules get
different identifiers.
"""

from __future__ import annotations

import uuid


_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def qualified_name(cls: type) -> str:
    """Return the fully qualified name of a class (module + qualname)."""
    return f"{cls.__module__}.{cls.__qualname__}"


def derive_type_id(cls: type) -> str:
    """Derive a deterministic type-level identifier from a class."""
    return str(uuid.uuid5(_NAMESPACE, qualified_name(cls)))


def derive_declaration_id(owner_cls: type, *path_segments: str) -> str:
    """Derive a deterministic declaration-level identifier from an ownership path."""
    full_path = ".".join([qualified_name(owner_cls), *path_segments])
    return str(uuid.uuid5(_NAMESPACE, full_path))
