from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionState
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_worker_process import _request
from app.strategy_lab_v2.worker_initial_state import ensure_worker_initial_state

NOW = datetime(2024, 1, 2, tzinfo=UTC)


class _ExecutionState:
    def __init__(self) -> None:
        self.context: ExecutionCommandContext | None = None
        self.initialize_calls = 0

    async def read_context(self, *, principal: Any, attempt_id: str):
        assert principal == "owner-a"
        assert self.context is None or self.context.outcome.attempt_id == attempt_id
        return self.context

    async def initialize(self, *, principal: Any, outcome: Any, progress: Any):
        assert principal == "owner-a"
        self.initialize_calls += 1
        if self.context is None:
            self.context = ExecutionCommandContext(outcome, progress)
            decision = "applied"
        elif self.context.outcome == outcome and self.context.progress == progress:
            decision = "replay_existing"
        else:
            decision = "conflict"
        return SimpleNamespace(decision=SimpleNamespace(value=decision))


class _RuntimeExecution:
    def __init__(self) -> None:
        self.state: RuntimeExecutionState | None = None
        self.initialize_calls = 0

    async def load(self, *, principal: Any, attempt_id: str):
        assert principal == "owner-a"
        assert self.state is None or self.state.attempt_id == attempt_id
        return self.state

    async def initialize(self, *, principal: Any, state: RuntimeExecutionState):
        assert principal == "owner-a"
        self.initialize_calls += 1
        if self.state is None:
            self.state = state
            decision = "registered"
        elif self.state == state:
            decision = "replay_existing"
        else:
            decision = "conflict"
        return SimpleNamespace(decision=SimpleNamespace(value=decision))


def _receipt(request) -> SubmissionReceipt:
    submission_request = SubmissionRequest(
        "search-worker-key",
        "strategy-backtest",
        request.runtime_request.attempt_id,
        content_digest("worker-input-payload"),
        NOW,
    )
    return SubmissionReceipt(submission_request, NOW)


@pytest.mark.asyncio
async def test_search_worker_initial_state_is_idempotent_across_restart(tmp_path) -> None:
    request = _request(tmp_path)
    execution = _ExecutionState()
    runtime = _RuntimeExecution()
    receipt = _receipt(request)

    await ensure_worker_initial_state(
        execution_state=execution,
        runtime_execution=runtime,
        principal="owner-a",
        request=request,
        submission=receipt,
    )
    await ensure_worker_initial_state(
        execution_state=execution,
        runtime_execution=runtime,
        principal="owner-a",
        request=request,
        submission=receipt,
    )

    assert execution.initialize_calls == 1
    assert runtime.initialize_calls == 1
    assert execution.context is not None
    assert execution.context.outcome.submission_id == receipt.submission_id
    assert execution.context.outcome.attempt_id == request.runtime_request.attempt_id
    assert runtime.state == request.runtime_state


@pytest.mark.asyncio
async def test_search_worker_initial_state_rejects_mismatched_submission(tmp_path) -> None:
    request = _request(tmp_path)
    receipt = _receipt(request)
    mismatched = SubmissionReceipt(
        SubmissionRequest(
            receipt.request.idempotency_key,
            receipt.request.operation,
            "different-attempt",
            receipt.request.payload_digest,
            receipt.request.submitted_at,
        ),
        receipt.accepted_at,
    )

    with pytest.raises(ValueError, match="different attempts"):
        await ensure_worker_initial_state(
            execution_state=_ExecutionState(),
            runtime_execution=_RuntimeExecution(),
            principal="owner-a",
            request=request,
            submission=mismatched,
        )
