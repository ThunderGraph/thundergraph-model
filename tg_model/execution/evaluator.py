"""Synchronous (and async-capable) evaluation over a :class:`~tg_model.execution.dependency_graph.DependencyGraph`.

:class:`Evaluator` walks topological order, runs compute nodes, and writes results into
:class:`~tg_model.execution.run_context.RunContext`. Sync vs async external backends are split
between :meth:`Evaluator.evaluate` and :meth:`Evaluator.evaluate_async` by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tg_model.execution.dependency_graph import DependencyGraph, NodeKind
from tg_model.execution.run_context import ConstraintResult, RunContext, SlotState

if TYPE_CHECKING:
    from tg_model.execution.configured_model import ConfiguredModel


@dataclass
class EvaluationIssue:
    """One structured problem encountered during evaluation.

    ``kind`` is one of:
      - ``"missing_input"``      — required parameter had no bound value.
      - ``"compute_error"``      — an expression or external computation raised.
      - ``"constraint_exception"`` — the constraint handler itself raised.
    """

    kind: str   # "missing_input" | "compute_error" | "constraint_exception"
    path: str   # dotted slot or node path
    message: str


@dataclass
class RunResult:
    """Aggregated outcome of one :meth:`~Evaluator.evaluate` / :meth:`~Evaluator.evaluate_async` run."""

    outputs: dict[str, Any] = field(default_factory=dict)
    constraint_results: list[ConstraintResult] = field(default_factory=list)
    issues: list[EvaluationIssue] = field(default_factory=list)

    @property
    def failures(self) -> list[str]:
        """Backward-compat list of human-readable failure messages.

        Returns ``[issue.message for issue in self.issues]``.  Old code that
        reads or checks ``result.failures`` continues to work; new code should
        use ``result.issues`` for structured access.

        Note: this is now read-only.  Use ``result.issues.append(...)`` to add
        new issues programmatically.
        """
        return [i.message for i in self.issues]

    @property
    def passed(self) -> bool:
        """True when there are no issues and every constraint result passed."""
        return len(self.issues) == 0 and all(c.passed for c in self.constraint_results)


def _format_operand_values(dep_values: dict[str, Any]) -> dict[str, str]:
    """Format dependency values into a symbol-name → value-string dict.

    Keys are the local name of each dep node id (last dotted segment after
    stripping the ``val:`` prefix), giving readable names like ``"load_kw"``
    instead of full paths.
    """
    result: dict[str, str] = {}
    for dep_id, val in dep_values.items():
        # dep_id format: "val:root.part.slot_name" or "val:root.slot_name"
        local = dep_id.split(".")[-1] if "." in dep_id else dep_id
        result[local] = _value_to_str(val)
    return result


def _value_to_str(value: Any) -> str:
    """Best-effort human-readable string for a slot value."""
    try:
        mag = getattr(value, "magnitude", None)
        units = getattr(value, "units", None)
        if mag is not None and units is not None:
            return f"{float(mag):.6g} {units}"
    except Exception:
        pass
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return repr(value)


class Evaluator:
    """Synchronous evaluation engine over a dependency graph.

    Walks the topological order, evaluates ready compute nodes,
    and materializes results into the RunContext.

    ``evaluate`` and ``evaluate_async`` intentionally duplicate the topological driver:
    bridging them through one coroutine would force ``asyncio.run`` (or worse) from
    ``evaluate``, which breaks callers that already own an event loop.
    Shared helpers only cover non-async steps (see ``_bind_run_inputs`` / ``_finalize_run``).
    """

    def __init__(
        self,
        graph: DependencyGraph,
        *,
        compute_handlers: dict[str, Any] | None = None,
    ) -> None:
        """Wrap a compiled graph and its node handlers.

        Parameters
        ----------
        graph : DependencyGraph
            Output of :func:`~tg_model.execution.graph_compiler.compile_graph`.
        compute_handlers : dict, optional
            Handler map from the same compile call (defaults to empty).
        """
        self._graph = graph
        self._compute_handlers = compute_handlers or {}

    def evaluate(
        self,
        ctx: RunContext,
        inputs: dict[str, Any] | None = None,
    ) -> RunResult:
        """Run one synchronous evaluation (external ``compute`` must not be async).

        Parameters
        ----------
        ctx : RunContext
            Fresh or reset per-run state.
        inputs : dict, optional
            Bound by stable slot id (see graph node metadata / compile conventions).

        Returns
        -------
        RunResult
            Aggregated failures and constraint outcomes.

        Raises
        ------
        TypeError
            Propagated from :func:`~tg_model.integrations.external_compute.assert_sync_external`
            when an async external is present.

        See Also
        --------
        evaluate_async
        """
        self._bind_run_inputs(ctx, inputs)
        order = self._graph.topological_order()
        result = RunResult()

        for node_id in order:
            node = self._graph.get_node(node_id)

            if node.kind == NodeKind.INPUT_PARAMETER:
                if node.slot_id and ctx.get_state(node.slot_id) == SlotState.UNBOUND:
                    if node.metadata.get("required", True):
                        ctx.get_or_create_record(node.slot_id).fail(
                            f"Required parameter '{node_id}' has no bound input"
                        )
                        result.issues.append(EvaluationIssue(
                            kind="missing_input",
                            path=node_id,
                            message=f"Missing required input: {node_id}",
                        ))
                continue

            if node.kind == NodeKind.ATTRIBUTE_VALUE:
                continue

            deps_ready = self._check_dependencies_ready(node_id, ctx)
            if not deps_ready:
                if node.kind == NodeKind.CONSTRAINT_CHECK:
                    blocked_by = self._describe_blocking_dep(node_id, ctx)
                    ctx.add_constraint_result(ConstraintResult(
                        name=node.metadata.get("name", node_id),
                        state="blocked",
                        expression_str=node.metadata.get("expression_str", ""),
                        evidence=f"blocked: {blocked_by}",
                        requirement_path=node.metadata.get("requirement_path"),
                        allocation_target_path=node.metadata.get("allocation_target_path"),
                    ))
                elif node.slot_id:
                    ctx.get_or_create_record(node.slot_id).block(
                        f"Blocked: upstream dependency not ready for '{node_id}'"
                    )
                elif node.kind == NodeKind.EXTERNAL_COMPUTATION:
                    for sid in node.metadata.get("output_slot_ids", ()):
                        ctx.get_or_create_record(sid).block(f"Blocked: upstream dependency not ready for '{node_id}'")
                continue

            if node.kind == NodeKind.LOCAL_EXPRESSION or node.kind == NodeKind.ROLLUP_COMPUTATION:
                self._evaluate_expression(node_id, node, ctx, result)

            elif node.kind == NodeKind.EXTERNAL_COMPUTATION:
                self._evaluate_external(node_id, node, ctx, result)

            elif node.kind == NodeKind.SOLVE_GROUP:
                self._evaluate_solve_group(node_id, node, ctx, result)

            elif node.kind == NodeKind.CONSTRAINT_CHECK:
                self._evaluate_constraint(node_id, node, ctx, result)

        return self._finalize_run(ctx, result)

    async def evaluate_async(
        self,
        ctx: RunContext,
        *,
        configured_model: ConfiguredModel,
        inputs: dict[str, Any] | None = None,
    ) -> RunResult:
        """Evaluate with async external backends (await ``compute`` when it returns a coroutine).

        Parameters
        ----------
        ctx : RunContext
            Per-run state.
        configured_model : ConfiguredModel
            Topology context for external resolution paths.
        inputs : dict, optional
            Same binding convention as :meth:`evaluate`.

        Returns
        -------
        RunResult
            Same shape as :meth:`evaluate`.

        See Also
        --------
        evaluate
        """
        self._bind_run_inputs(ctx, inputs)
        order = self._graph.topological_order()
        result = RunResult()

        for node_id in order:
            node = self._graph.get_node(node_id)

            if node.kind == NodeKind.INPUT_PARAMETER:
                if node.slot_id and ctx.get_state(node.slot_id) == SlotState.UNBOUND:
                    if node.metadata.get("required", True):
                        ctx.get_or_create_record(node.slot_id).fail(
                            f"Required parameter '{node_id}' has no bound input"
                        )
                        result.issues.append(EvaluationIssue(
                            kind="missing_input",
                            path=node_id,
                            message=f"Missing required input: {node_id}",
                        ))
                continue

            if node.kind == NodeKind.ATTRIBUTE_VALUE:
                continue

            deps_ready = self._check_dependencies_ready(node_id, ctx)
            if not deps_ready:
                if node.kind == NodeKind.CONSTRAINT_CHECK:
                    blocked_by = self._describe_blocking_dep(node_id, ctx)
                    ctx.add_constraint_result(ConstraintResult(
                        name=node.metadata.get("name", node_id),
                        state="blocked",
                        expression_str=node.metadata.get("expression_str", ""),
                        evidence=f"blocked: {blocked_by}",
                        requirement_path=node.metadata.get("requirement_path"),
                        allocation_target_path=node.metadata.get("allocation_target_path"),
                    ))
                elif node.slot_id:
                    ctx.get_or_create_record(node.slot_id).block(
                        f"Blocked: upstream dependency not ready for '{node_id}'"
                    )
                elif node.kind == NodeKind.EXTERNAL_COMPUTATION:
                    for sid in node.metadata.get("output_slot_ids", ()):
                        ctx.get_or_create_record(sid).block(f"Blocked: upstream dependency not ready for '{node_id}'")
                continue

            if node.kind == NodeKind.LOCAL_EXPRESSION or node.kind == NodeKind.ROLLUP_COMPUTATION:
                self._evaluate_expression(node_id, node, ctx, result)

            elif node.kind == NodeKind.EXTERNAL_COMPUTATION:
                await self._evaluate_external_async(node_id, node, ctx, result, configured_model)

            elif node.kind == NodeKind.SOLVE_GROUP:
                self._evaluate_solve_group(node_id, node, ctx, result)

            elif node.kind == NodeKind.CONSTRAINT_CHECK:
                self._evaluate_constraint(node_id, node, ctx, result)

        return self._finalize_run(ctx, result)

    @staticmethod
    def _bind_run_inputs(ctx: RunContext, inputs: dict[str, Any] | None) -> None:
        if inputs:
            for slot_id, value in inputs.items():
                ctx.bind_input(slot_id, value)

    @staticmethod
    def _finalize_run(ctx: RunContext, result: RunResult) -> RunResult:
        result.constraint_results = ctx.constraint_results
        result.outputs = {
            slot_id: ctx.get_value(slot_id) for slot_id, record in ctx._slot_records.items() if record.is_ready
        }
        return result

    def _check_dependencies_ready(self, node_id: str, ctx: RunContext) -> bool:
        for dep_id in self._graph.dependencies_of(node_id):
            dep_node = self._graph.get_node(dep_id)
            if dep_node.slot_id:
                state = ctx.get_state(dep_node.slot_id)
                if state not in (SlotState.BOUND_INPUT, SlotState.REALIZED):
                    return False
        return True

    def _describe_blocking_dep(self, node_id: str, ctx: RunContext) -> str:
        """Return a human-readable description of the first unready dependency."""
        for dep_id in self._graph.dependencies_of(node_id):
            dep_node = self._graph.get_node(dep_id)
            if dep_node.slot_id:
                state = ctx.get_state(dep_node.slot_id)
                if state not in (SlotState.BOUND_INPUT, SlotState.REALIZED):
                    record = ctx._slot_records.get(dep_node.slot_id)
                    reason = (record.failure or state.value) if record else state.value
                    return f"{dep_id} ({reason})"
        return "upstream dependency not ready"

    def _evaluate_expression(
        self,
        node_id: str,
        node: Any,
        ctx: RunContext,
        result: RunResult,
    ) -> None:
        handler = self._compute_handlers.get(node_id)
        if handler is None:
            if node.slot_id:
                ctx.get_or_create_record(node.slot_id).fail(f"No handler for '{node_id}'")
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"No compute handler: {node_id}",
            ))
            return

        try:
            dep_values = {}
            for dep_id in self._graph.dependencies_of(node_id):
                dep_node = self._graph.get_node(dep_id)
                if dep_node.slot_id:
                    dep_values[dep_id] = ctx.get_value(dep_node.slot_id)

            computed = handler(dep_values)
            if node.slot_id:
                ctx.realize(node.slot_id, computed)
        except Exception as e:
            if node.slot_id:
                ctx.get_or_create_record(node.slot_id).fail(str(e))
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"Evaluation failed for '{node_id}': {e}",
            ))

    def _evaluate_external(
        self,
        node_id: str,
        node: Any,
        ctx: RunContext,
        result: RunResult,
    ) -> None:
        handler = self._compute_handlers.get(node_id)
        if handler is None:
            for sid in node.metadata.get("output_slot_ids", ()):
                ctx.get_or_create_record(sid).fail(f"No handler for '{node_id}'")
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"No compute handler: {node_id}",
            ))
            return

        dep_values: dict[str, Any] = {}
        for dep_id in self._graph.dependencies_of(node_id):
            dep_node = self._graph.get_node(dep_id)
            if dep_node.slot_id:
                dep_values[dep_id] = ctx.get_value(dep_node.slot_id)

        try:
            handler(dep_values, ctx, result)
        except Exception as e:
            for sid in node.metadata.get("output_slot_ids", ()):
                ctx.get_or_create_record(sid).fail(str(e))
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"External evaluation failed for '{node_id}': {e}",
            ))

    async def _evaluate_external_async(
        self,
        node_id: str,
        node: Any,
        ctx: RunContext,
        result: RunResult,
        cm: ConfiguredModel,
    ) -> None:
        from tg_model.execution.external_ops import materialize_external_result, navigate_to_part
        from tg_model.execution.value_slots import ValueSlot
        from tg_model.integrations.external_compute import ExternalComputeResult, is_async_external

        binding = node.metadata.get("binding")
        owner_path = node.metadata.get("owner_path")
        output_ids = node.metadata.get("output_slot_ids", ())
        input_name_to_dep: dict[str, str] = node.metadata.get("input_name_to_dep", {})
        if binding is None or owner_path is None:
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"Malformed external node metadata: {node_id}",
            ))
            return

        slots: list[ValueSlot] = []
        for sid in output_ids:
            s = cm.id_registry[sid]
            if not isinstance(s, ValueSlot):
                result.issues.append(EvaluationIssue(
                    kind="compute_error",
                    path=node_id,
                    message=f"External node '{node_id}' output is not a ValueSlot",
                ))
                return
            slots.append(s)

        dep_values: dict[str, Any] = {}
        try:
            for dep_id in self._graph.dependencies_of(node_id):
                dep_node = self._graph.get_node(dep_id)
                if dep_node.slot_id:
                    dep_values[dep_id] = ctx.get_value(dep_node.slot_id)
        except ValueError as e:
            for sid in output_ids:
                ctx.get_or_create_record(sid).block(str(e))
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=str(e),
            ))
            return

        owner = navigate_to_part(cm.root, tuple(owner_path))
        inputs_dict: dict[str, Any] = {}
        try:
            for name, dep_node_id in input_name_to_dep.items():
                if dep_node_id not in dep_values:
                    raise KeyError(f"missing dependency {dep_node_id}")
                inputs_dict[name] = dep_values[dep_node_id]

            ext = binding.external
            if is_async_external(ext):
                res = await ext.compute(inputs_dict)
            else:
                res = ext.compute(inputs_dict)

            if not isinstance(res, ExternalComputeResult):
                raise TypeError(f"External compute must return ExternalComputeResult, got {type(res).__name__}")
            materialize_external_result(binding, res, owner, cm, ctx, slots)
        except Exception as e:
            msg = str(e)
            for sid in output_ids:
                ctx.get_or_create_record(sid).fail(msg)
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"External compute '{node_id}' failed: {msg}",
            ))

    def _evaluate_solve_group(
        self,
        node_id: str,
        node: Any,
        ctx: RunContext,
        result: RunResult,
    ) -> None:
        handler = self._compute_handlers.get(node_id)
        if handler is None:
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"No compute handler for solve group: {node_id}",
            ))
            return

        try:
            dep_values = {}
            for dep_id in self._graph.dependencies_of(node_id):
                dep_node = self._graph.get_node(dep_id)
                if dep_node.slot_id:
                    dep_values[dep_id] = ctx.get_value(dep_node.slot_id)

            solved_values = handler(dep_values)

            for slot_id, val in solved_values.items():
                ctx.realize(slot_id, val, provenance="solve_group")
        except Exception as e:
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"Solve group failed for '{node_id}': {e}",
            ))
            target_slots = node.metadata.get("target_slots", {})
            for slot_id in target_slots.values():
                ctx.get_or_create_record(slot_id).fail(str(e))

    def _evaluate_constraint(
        self,
        node_id: str,
        node: Any,
        ctx: RunContext,
        result: RunResult,
    ) -> None:
        handler = self._compute_handlers.get(node_id)
        if handler is None:
            result.issues.append(EvaluationIssue(
                kind="compute_error",
                path=node_id,
                message=f"No constraint handler: {node_id}",
            ))
            return

        constraint_name = node.metadata.get("name", node_id)
        expression_str = node.metadata.get("expression_str", "")

        try:
            dep_values: dict[str, Any] = {}
            for dep_id in self._graph.dependencies_of(node_id):
                dep_node = self._graph.get_node(dep_id)
                if dep_node.slot_id:
                    dep_values[dep_id] = ctx.get_value(dep_node.slot_id)

            passed = bool(handler(dep_values))

            operand_values: dict[str, str] = {}
            if not passed:
                operand_values = _format_operand_values(dep_values)

            ctx.add_constraint_result(ConstraintResult(
                name=constraint_name,
                state="passed" if passed else "failed",
                expression_str=expression_str,
                operand_values=operand_values,
                requirement_path=node.metadata.get("requirement_path"),
                allocation_target_path=node.metadata.get("allocation_target_path"),
            ))
        except Exception as e:
            ctx.add_constraint_result(ConstraintResult(
                name=constraint_name,
                state="failed",
                expression_str=expression_str,
                evidence=str(e),
                requirement_path=node.metadata.get("requirement_path"),
                allocation_target_path=node.metadata.get("allocation_target_path"),
            ))
            result.issues.append(EvaluationIssue(
                kind="constraint_exception",
                path=node_id,
                message=f"Constraint raised for '{node_id}': {e}",
            ))
