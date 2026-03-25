"""RunContext — per-run mutable state container.

Topology lives on ConfiguredModel; mutable values live here.
One ConfiguredModel may support many RunContexts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from tg_model.execution.instances import PartInstance


class SlotState(Enum):
    UNBOUND = "unbound"
    BOUND_INPUT = "bound_input"
    PENDING = "pending"  # reserved for deferred external jobs (poll/resume); not used in evaluate_async yet
    REALIZED = "realized"
    FAILED = "failed"
    BLOCKED = "blocked"


class SlotRecord:
    """Per-slot mutable state for one run."""

    __slots__ = ("failure", "provenance", "state", "value")

    def __init__(self) -> None:
        self.state: SlotState = SlotState.UNBOUND
        self.value: Any = None
        self.failure: str | None = None
        self.provenance: str | None = None

    def bind_input(self, value: Any) -> None:
        self.state = SlotState.BOUND_INPUT
        self.value = value
        self.provenance = "input"

    def realize(self, value: Any, provenance: Any = "computed") -> None:
        self.state = SlotState.REALIZED
        self.value = value
        self.provenance = provenance

    def mark_pending(self, note: str = "") -> None:
        self.state = SlotState.PENDING
        self.failure = note or None

    def fail(self, reason: str) -> None:
        self.state = SlotState.FAILED
        self.failure = reason

    def block(self, reason: str) -> None:
        self.state = SlotState.BLOCKED
        self.failure = reason

    @property
    def is_terminal(self) -> bool:
        return self.state in (SlotState.REALIZED, SlotState.FAILED, SlotState.BLOCKED)

    @property
    def is_ready(self) -> bool:
        return self.state in (SlotState.BOUND_INPUT, SlotState.REALIZED)


class ConstraintResult:
    """Result of one constraint evaluation."""

    __slots__ = (
        "allocation_target_path",
        "evidence",
        "name",
        "passed",
        "requirement_path",
    )

    def __init__(
        self,
        name: str,
        passed: bool,
        evidence: str = "",
        *,
        requirement_path: str | None = None,
        allocation_target_path: str | None = None,
    ) -> None:
        self.name = name
        self.passed = passed
        self.evidence = evidence
        self.requirement_path = requirement_path
        self.allocation_target_path = allocation_target_path

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        if self.requirement_path:
            return (
                f"<ConstraintResult: {self.name} {status} "
                f"requirement={self.requirement_path!r} target={self.allocation_target_path!r}>"
            )
        return f"<ConstraintResult: {self.name} {status}>"


class RunContext:
    """Per-run mutable state. Created fresh for each evaluation.

    Keyed by ValueSlot.stable_id to maintain isolation from topology.

    **Behavior effects and guards (Phase 6):** while :meth:`push_behavior_effect_scope`
    is active (during transition guards, decision predicates, and action effects), slot
    and discrete-state accessors above are restricted to the **active part subtree**.
    This is **API discipline** for well-behaved callables — not a security sandbox:
    code can still close over
    :class:`~tg_model.execution.configured_model.ConfiguredModel` or use other Python
    escape hatches. Item payload staging (:meth:`prime_item_payload`, etc.) is
    intentionally **not** subtree-scoped (inter-part delivery).
    """

    def __init__(self) -> None:
        self._slot_records: dict[str, SlotRecord] = {}
        self._constraint_results: list[ConstraintResult] = []
        self._behavior_active_state: dict[str, str] = {}
        # (part_path_string, event_name) -> payload for one in-flight item delivery (see emit_item)
        self._behavior_item_payloads: dict[tuple[str, str], Any] = {}
        # Stack of (owner part path, allowed slot ids) while a behavior *effect* runs (Phase 6).
        self._behavior_scope_stack: list[tuple[str, frozenset[str]]] = []

    def push_behavior_effect_scope(self, part: PartInstance) -> None:
        """Restrict value-slot access to the subtree of ``part`` until :meth:`pop_behavior_effect_scope`."""
        from tg_model.execution.instances import slot_ids_for_part_subtree

        self._behavior_scope_stack.append((part.path_string, slot_ids_for_part_subtree(part)))

    def pop_behavior_effect_scope(self) -> None:
        if not self._behavior_scope_stack:
            raise RuntimeError(
                "pop_behavior_effect_scope() without a matching push_behavior_effect_scope(); "
                "scope stack is empty."
            )
        self._behavior_scope_stack.pop()

    def _enforce_behavior_slot(self, slot_id: str) -> None:
        if not self._behavior_scope_stack:
            return
        allowed = self._behavior_scope_stack[-1][1]
        if slot_id not in allowed:
            raise RuntimeError(
                "Behavior effect may only read/write value slots declared on the active part's "
                f"subtree; slot {slot_id!r} is out of scope (structural boundary)."
            )

    def _enforce_behavior_part_path(self, part_path: str) -> None:
        """Disallow reading/writing another part's discrete state from a behavior effect."""
        if not self._behavior_scope_stack:
            return
        owner = self._behavior_scope_stack[-1][0]
        if part_path != owner and not part_path.startswith(owner + "."):
            raise RuntimeError(
                "Behavior effect may only use the active part's behavior state paths; "
                f"{part_path!r} is outside {owner!r} (structural boundary)."
            )

    def get_or_create_record(self, slot_id: str) -> SlotRecord:
        """Return the mutable :class:`SlotRecord` for ``slot_id``, creating it if needed.

        When a behavior effect scope is active, the same subtree rule as :meth:`bind_input`
        applies (see class docstring).
        """
        self._enforce_behavior_slot(slot_id)
        if slot_id not in self._slot_records:
            self._slot_records[slot_id] = SlotRecord()
        return self._slot_records[slot_id]

    def bind_input(self, slot_id: str, value: Any) -> None:
        record = self.get_or_create_record(slot_id)
        record.bind_input(value)

    def realize(self, slot_id: str, value: Any, provenance: Any = "computed") -> None:
        record = self.get_or_create_record(slot_id)
        record.realize(value, provenance)

    def mark_pending(self, slot_id: str, note: str = "") -> None:
        self.get_or_create_record(slot_id).mark_pending(note)

    def get_value(self, slot_id: str) -> Any:
        self._enforce_behavior_slot(slot_id)
        record = self._slot_records.get(slot_id)
        if record is None or not record.is_ready:
            raise ValueError(f"Slot '{slot_id}' has no ready value")
        return record.value

    def get_state(self, slot_id: str) -> SlotState:
        self._enforce_behavior_slot(slot_id)
        record = self._slot_records.get(slot_id)
        if record is None:
            return SlotState.UNBOUND
        return record.state

    def add_constraint_result(self, result: ConstraintResult) -> None:
        self._constraint_results.append(result)

    @property
    def constraint_results(self) -> list[ConstraintResult]:
        return list(self._constraint_results)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self._constraint_results)

    def get_active_behavior_state(self, part_path_string: str) -> str | None:
        """Current discrete state name for a part instance path (Phase 6), if set."""
        self._enforce_behavior_part_path(part_path_string)
        return self._behavior_active_state.get(part_path_string)

    def set_active_behavior_state(self, part_path_string: str, state_name: str) -> None:
        """Set current discrete state for ``part_path_string`` (``ValueSlot``-style path string)."""
        self._enforce_behavior_part_path(part_path_string)
        self._behavior_active_state[part_path_string] = state_name

    def prime_item_payload(self, part_path_string: str, event_name: str, payload: Any) -> None:
        """Stage payload for the next behavioral event on ``part_path_string`` (used by :func:`emit_item`)."""
        self._behavior_item_payloads[(part_path_string, event_name)] = payload

    def peek_item_payload(self, part_path_string: str, event_name: str) -> Any | None:
        """Return staged item payload for this part/event, if any (does not consume)."""
        return self._behavior_item_payloads.get((part_path_string, event_name))

    def clear_item_payload(self, part_path_string: str, event_name: str) -> None:
        """Drop staged payload after a transition has been processed."""
        self._behavior_item_payloads.pop((part_path_string, event_name), None)
