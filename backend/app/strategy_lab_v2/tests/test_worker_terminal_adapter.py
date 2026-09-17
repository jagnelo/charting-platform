from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.tests.test_worker_process import _request
from app.strategy_lab_v2.tests.test_worker_service import _entry
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision
from app.strategy_lab_v2.worker_process import (
    WorkerProcessDecision,
    WorkerProcessResolution,
)
from app.strategy_lab_v2.worker_service import WorkerCompletionContext
from app.strategy_lab_v2.worker_terminal_adapter import (
    PostgresWorkerTerminalAdapter,
    WorkerTerminalEvidence,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _context(tmp_path: Path) -> WorkerCompletionContext:
    request = _request(tmp_path)
    payload = DispatchPayload.from_mapping({"attempt_id": request.admission.attempt_id})
    entry = _entry(payload)
    process = WorkerProcessResolution(
        request.request_fingerprint,
        WorkerProcessDecision.TIMED_OUT,
        error_digest=content_digest("timed out"),
    )
    return WorkerCompletionContext(entry, request, process, NOW)


def _adapter(resolver) -> PostgresWorkerTerminalAdapter:
    return PostgresWorkerTerminalAdapter(
        resolver,
        runtime_execution=cast(Any, object()),
        execution_state=cast(Any, object()),
        execution_summaries=object(),
        result_completion=cast(Any, object()),
        worker_state=cast(Any, object()),
        settlements=cast(Any, object()),
    )


@pytest.mark.asyncio
async def test_terminal_adapter_keeps_timeout_pending_without_partial_writes(tmp_path: Path) -> None:
    called = False

    async def resolver(_context: Any):
        nonlocal called
        called = True
        raise AssertionError("timeout recovery must not resolve terminal result evidence")

    result = await _adapter(resolver).write(_context(tmp_path))
    assert result.decision is WorkerHandleDecision.RETRY
    assert result.rejection_reason == "worker process did not produce terminal evidence"
    assert not called


def test_terminal_evidence_requires_typed_submission() -> None:
    with pytest.raises(TypeError, match="SubmissionReceipt"):
        WorkerTerminalEvidence(
            principal="owner-a",
            submission="not-a-receipt",
            outcome=object(),  # type: ignore[arg-type]
            progress=object(),  # type: ignore[arg-type]
        )
