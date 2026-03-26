"""Deterministic identity derivation for model elements.

Identity is derived from fully qualified type names and declaration paths.
Two unrelated types with the same class name in different modules get
different identifiers.
"""

from __future__ import annotations

import uuid


_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def qualified_name(cls: type) -> str:
    """Return ``module.qualname`` for a class (stable across simple name clashes).

    Parameters
    ----------
    cls : type
        Class object.

    Returns
    -------
    str
        Fully qualified name string.
    """
    return f"{cls.__module__}.{cls.__qualname__}"


def derive_type_id(cls: type) -> str:
    """Return a deterministic UUID string derived from :func:`qualified_name`.

    Parameters
    ----------
    cls : type
        Class object.

    Returns
    -------
    str
        UUIDv5 hex string in the library namespace.
    """
    return str(uuid.uuid5(_NAMESPACE, qualified_name(cls)))


def derive_declaration_id(owner_cls: type, *path_segments: str) -> str:
    """Return a deterministic id for ``owner_cls`` plus instance path segments.

    Parameters
    ----------
    owner_cls : type
        Configured root type.
    *path_segments : str
        Declaration/instance path segments (e.g. part names).

    Returns
    -------
    str
        UUIDv5 hex string unique to that ownership path.
    """
    full_path = ".".join([qualified_name(owner_cls), *path_segments])
    return str(uuid.uuid5(_NAMESPACE, full_path))
