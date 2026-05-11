"""Per-run mutable state: :class:`RunContext`, :class:`SlotRecord`, :class:`ConstraintResult`.

Topology and slot identities live on :class:`~tg_model.execution.configured_model.ConfiguredModel`;
this module holds **values and constraint outcomes** for one evaluation. Behavior helpers may
push a subtree scope stack so effects/guards only touch allowed slots (see :class:`RunContext`).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from tg_model.execution.instances import PartInstance


class SlotState(Enum):
    """Lifecycle state for one :class:`ValueSlot` in a :class:`RunContext`."""

    UNBOUND = "unbound"
    BOUND_INPUT = "bound_input"
    PENDING = "pending"  # reserved for deferred external jobs (poll/resume); not used in evaluate_async yet
    REALIZED = "realized"
    FAILED = "failed"
    BLOCKED = "blocked"


class SlotRecord:
    """Mutable value cell for a single slot id within one run."""

    __slots__ = ("failure", "provenance", "state", "value")

    def __init__(self) -> None:
        self.state: SlotState = SlotState.UNBOUND
        self.value: Any = None
        self.failure: str | None = None
        self.provenance: str | None = None

    def bind_input(self, value: Any) -> None:
        """Mark slot as supplied by caller input."""
        self.state = SlotState.BOUND_INPUT
        self.value = value
        self.provenance = "input"

    def realize(self, value: Any, provenance: Any = "computed") -> None:
        """Store a computed value (``provenance`` is stored for auditing)."""
        self.state = SlotState.REALIZED
        self.value = value
        self.provenance = provenance

    def mark_pending(self, note: str = "") -> None:
        """Reserved for deferred external work (placeholder state)."""
        self.state = SlotState.PENDING
        self.failure = note or None

    def fail(self, reason: str) -> None:
        """Terminal failure (required input missing, evaluation error, ...)."""
        self.state = SlotState.FAILED
        self.failure = reason

    def block(self, reason: str) -> None:
        """Upstream dependency not ready; not a hard failure."""
        self.state = SlotState.BLOCKED
        self.failure = reason

    @property
    def is_terminal(self) -> bool:
        """True for realized, failed, or blocked states."""
        return self.state in (SlotState.REALIZED, SlotState.FAILED, SlotState.BLOCKED)

    @property
    def is_ready(self) -> bool:
        """True when a value is available from input binding or realization."""
        return self.state in (SlotState.BOUND_INPUT, SlotState.REALIZED)


class ConstraintResult:
    """Outcome of one constraint or requirement-acceptance check.

    Three-outcome model:
      - ``state="passed"``  — expression evaluated to True.
      - ``state="failed"``  — expression evaluated to False; ``operand_values``
        contains the symbol values that caused the failure.
      - ``state="blocked"`` — at least one upstream dependency was not ready
        (missing input or upstream compute error); ``evidence`` says which.

    ``passed`` is a computed property (``state == "passed"``) for backward
    compatibility. Old code that reads ``cr.passed`` keeps working; new code
    should read ``cr.state`` directly.
    """

    __slots__ = (
        "_state",
        "allocation_target_path",
        "evidence",
        "expression_str",
        "name",
        "operand_values",
        "requirement_path",
    )

    def __init__(
        self,
        name: str,
        passed: bool | None = None,
        evidence: str = "",
        *,
        state: str | None = None,
        expression_str: str = "",
        operand_values: dict | None = None,
        requirement_path: str | None = None,
        allocation_target_path: str | None = None,
    ) -> None:
        """Record one constraint or requirement acceptance outcome.

        Parameters
        ----------
        name : str
            Graph/check identifier (often dotted path).
        passed : bool, optional
            Legacy positional arg.  Derives ``state`` when ``state`` is not
            provided: ``True`` → ``"passed"``, ``False`` → ``"failed"``.
            Ignored when ``state`` is provided explicitly.
        evidence : str, optional
            Human-readable detail; used for blocked/exception messages.
        state : str, optional
            Canonical three-value outcome: ``"passed"``, ``"failed"``, or
            ``"blocked"``.  Takes priority over ``passed`` when both supplied.
        expression_str : str, optional
            Human-readable constraint expression string (e.g. ``"x >= 0 kW"``).
        operand_values : dict, optional
            Symbol name → formatted value string for failed/blocked states.
        requirement_path : str, optional
            Set for requirement acceptance rows.
        allocation_target_path : str, optional
            Part path where the requirement was allocated.
        """
        if state is not None:
            self._state = state
        elif passed is not None:
            self._state = "passed" if passed else "failed"
        else:
            self._state = "passed"

        self.name = name
        self.evidence = evidence
        self.expression_str = expression_str
        self.operand_values: dict[str, str] = operand_values or {}
        self.requirement_path = requirement_path
        self.allocation_target_path = allocation_target_path

    @property
    def state(self) -> str:
        """Canonical three-value outcome: ``"passed"``, ``"failed"``, or ``"blocked"``."""
        return self._state

    @property
    def passed(self) -> bool:
        """True when ``state == "passed"`` (computed — not stored)."""
        return self._state == "passed"

    def __repr__(self) -> str:
        status = self._state.upper()
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
        """Restrict value-slot access to the subtree of ``part`` until :meth:`pop_behavior_effect_scope`.

        Parameters
        ----------
        part : PartInstance
            Active part for guard/effect callables.
        """
        from tg_model.execution.instances import slot_ids_for_part_subtree

        self._behavior_scope_stack.append((part.path_string, slot_ids_for_part_subtree(part)))

    def pop_behavior_effect_scope(self) -> None:
        """Pop the innermost behavior scope pushed by :meth:`push_behavior_effect_scope`.

        Raises
        ------
        RuntimeError
            If the stack is empty.
        """
        if not self._behavior_scope_stack:
            raise RuntimeError(
                "pop_behavior_effect_scope() without a matching push_behavior_effect_scope(); scope stack is empty."
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
        """Bind ``value`` to ``slot_id`` (creates record if needed)."""
        record = self.get_or_create_record(slot_id)
        record.bind_input(value)

    def realize(self, slot_id: str, value: Any, provenance: Any = "computed") -> None:
        """Write computed ``value`` to ``slot_id``."""
        record = self.get_or_create_record(slot_id)
        record.realize(value, provenance)

    def mark_pending(self, slot_id: str, note: str = "") -> None:
        """Mark ``slot_id`` pending (external deferral hook)."""
        self.get_or_create_record(slot_id).mark_pending(note)

    def get_value(self, slot_id: str) -> Any:
        """Return the current value when the slot is in a ready state.

        Raises
        ------
        ValueError
            If the slot has no record or is not ready.
        RuntimeError
            If a behavior scope forbids access to this slot.
        """
        self._enforce_behavior_slot(slot_id)
        record = self._slot_records.get(slot_id)
        if record is None or not record.is_ready:
            raise ValueError(f"Slot '{slot_id}' has no ready value")
        return record.value

    def get_state(self, slot_id: str) -> SlotState:
        """Return :class:`SlotState` for ``slot_id`` (``UNBOUND`` if no record).

        Raises
        ------
        RuntimeError
            If a behavior effect scope forbids access to this slot.
        """
        self._enforce_behavior_slot(slot_id)
        record = self._slot_records.get(slot_id)
        if record is None:
            return SlotState.UNBOUND
        return record.state

    def add_constraint_result(self, result: ConstraintResult) -> None:
        """Append one constraint or requirement-acceptance outcome to this run."""
        self._constraint_results.append(result)

    @property
    def constraint_results(self) -> list[ConstraintResult]:
        """Copy of all :class:`ConstraintResult` rows recorded during evaluation."""
        return list(self._constraint_results)

    @property
    def all_passed(self) -> bool:
        """True when every stored :class:`ConstraintResult` has ``passed`` (empty is vacuously true)."""
        return all(r.passed for r in self._constraint_results)

    def get_active_behavior_state(self, part_path_string: str) -> str | None:
        """Return the current discrete behavior state name for ``part_path_string``, if any.

        Raises
        ------
        RuntimeError
            If called from a behavior effect with an out-of-scope ``part_path_string``.
        """
        self._enforce_behavior_part_path(part_path_string)
        return self._behavior_active_state.get(part_path_string)

    def set_active_behavior_state(self, part_path_string: str, state_name: str) -> None:
        """Set discrete behavior state for ``part_path_string`` (dotted instance path).

        Raises
        ------
        RuntimeError
            If a behavior effect scope forbids mutating this part's state.
        """
        self._enforce_behavior_part_path(part_path_string)
        self._behavior_active_state[part_path_string] = state_name

    def prime_item_payload(self, part_path_string: str, event_name: str, payload: Any) -> None:
        """Stage ``payload`` for the next ``event_name`` on ``part_path_string`` (see :func:`emit_item`).

        Notes
        -----
        Not restricted by behavior subtree scope (inter-part delivery).
        """
        self._behavior_item_payloads[(part_path_string, event_name)] = payload

    def peek_item_payload(self, part_path_string: str, event_name: str) -> Any | None:
        """Return staged payload for ``(part_path_string, event_name)`` without consuming it."""
        return self._behavior_item_payloads.get((part_path_string, event_name))

    def clear_item_payload(self, part_path_string: str, event_name: str) -> None:
        """Remove staged payload for ``(part_path_string, event_name)`` after handling."""
        self._behavior_item_payloads.pop((part_path_string, event_name), None)
