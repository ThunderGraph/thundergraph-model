"""Canonical stable-id computation for tg-model elements and value slots.

These functions are the **single source of truth** for class-scoped stable IDs.
Both the projection layer (bundle_walker) and the evaluation runner import from here,
ensuring the same ID format is used everywhere.

Class-scoped IDs are stable across rename/re-instantiation of the same type under
different root systems, because they are anchored to the Python class (module +
qualname), not the instance path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_model.execution.instances import ElementInstance
    from tg_model.execution.value_slots import ValueSlot


def class_scoped_constraint_sid(
    element: "ElementInstance",
    path_registry: dict,
) -> str | None:
    """Return the class-scoped stable_id for a constraint element.

    Mirrors the formula in bundle_walker._element_record / _declaring_class_for:
      1. Walk up ``element.instance_path`` to find the nearest
         ``RequirementPackageInstance`` ancestor.  If found, use its
         ``package_type`` as the declaring class.
      2. Fallback to ``element.definition_type`` (set to the owning Part class
         by tg_model during instantiation for directly-declared constraints).

    Returns ``None`` only when ``element.definition_type`` is also None
    (should never happen in a valid configured model).

    Format: ``"class_constraint:{module}.{qualname}:{local_name}"``
    """
    from tg_model.execution.instances import RequirementPackageInstance

    local_name = element.instance_path[-1] if element.instance_path else ""
    ip = element.instance_path

    for i in range(len(ip) - 1, 0, -1):
        parent = path_registry.get(".".join(ip[:i]))
        if isinstance(parent, RequirementPackageInstance):
            cls = parent.package_type
            return f"class_constraint:{cls.__module__}.{cls.__qualname__}:{local_name}"

    cls = element.definition_type
    if cls is not None:
        return f"class_constraint:{cls.__module__}.{cls.__qualname__}:{local_name}"

    return None


def class_scoped_slot_sid(
    slot: "ValueSlot",
    path_registry: dict,
) -> str | None:
    """Return the class-scoped stable_id for a value slot.

    Mirrors the formula in bundle_walker._declaring_class_for_slot /
    _value_slot_record:
      Walk up ``slot.instance_path`` to find the nearest
      ``RequirementPackageInstance`` or ``PartInstance`` ancestor.
      Use its class as the declaring class.

    Returns ``None`` when no ancestor is found (should not occur in valid models).

    Format: ``"class_slot:{module}.{qualname}:{local_name}"``
    """
    from tg_model.execution.instances import PartInstance, RequirementPackageInstance

    local_name = slot.definition_path[-1] if slot.definition_path else (
        slot.instance_path[-1] if slot.instance_path else ""
    )
    ip = slot.instance_path

    for i in range(len(ip) - 1, 0, -1):
        parent = path_registry.get(".".join(ip[:i]))
        if isinstance(parent, RequirementPackageInstance):
            cls = parent.package_type
            return f"class_slot:{cls.__module__}.{cls.__qualname__}:{local_name}"
        if isinstance(parent, PartInstance):
            cls = parent.definition_type
            return f"class_slot:{cls.__module__}.{cls.__qualname__}:{local_name}"

    return None
