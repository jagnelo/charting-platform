from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_worker_authorization import (
    AuthorizedForwardEventHandler,
    ForwardWorkerAuthorization,
    ForwardWorkerAuthorizationDecision,
    resolve_forward_worker_authorization,
)
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.tests.test_forward_worker_service import _work
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.workers import WorkerKind, WorkerReservation

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _authorization(*, released: bool = False) -> ForwardWorkerAuthorization:
    reservation = WorkerReservation(
        content_digest("reservation"),
        "worker-1",
        WorkerKind.FORWARD,
        "forward-instance",
        NOW,
        NOW if released else None,
    )
    lease = ExecutionAttemptLease(
        "forward-instance",
        "worker-1",
        "lease-1",
        NOW,
        NOW,
        NOW + timedelta(minutes=5),
        NOW if released else None,
    )
    return ForwardWorkerAuthorization(reservation, lease)


def test_forward_worker_authorization_accepts_matching_active_lease() -> None:
    _, _, work_item = _work()
    resolution = resolve_forward_worker_authorization(
        _authorization(), work_item, now=NOW + timedelta(minutes=1)
    )
    assert resolution.decision is ForwardWorkerAuthorizationDecision.ACCEPT


def test_forward_worker_authorization_retries_expired_lease() -> None:
    _, _, work_item = _work()
    resolution = resolve_forward_worker_authorization(
        _authorization(), work_item, now=NOW + timedelta(minutes=6)
    )
    assert resolution.decision is ForwardWorkerAuthorizationDecision.EXPIRED


def test_forward_worker_authorization_rejects_released_reservation() -> None:
    _, _, work_item = _work()
    resolution = resolve_forward_worker_authorization(
        _authorization(released=True), work_item, now=NOW + timedelta(minutes=1)
    )
    assert resolution.decision is ForwardWorkerAuthorizationDecision.REJECT


@pytest.mark.asyncio
async def test_authorized_handler_gates_delegate_and_preserves_receipt() -> None:
    entry, _, work_item = _work()
    calls: list[str] = []

    async def handler(received_entry, received_item):
        assert received_item == work_item
        calls.append(received_entry.fingerprint)
        return WorkerHandleResult(
            received_entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("receipt"),
        )

    wrapped = AuthorizedForwardEventHandler(
        lambda _entry, _item: _authorization(),
        handler,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    result = await wrapped(entry, work_item)
    assert result.decision is WorkerHandleDecision.COMPLETE
    assert calls == [entry.fingerprint]


@pytest.mark.asyncio
async def test_authorized_handler_does_not_delegate_expired_work() -> None:
    entry, _, work_item = _work()
    called = False

    async def handler(_entry, _item):
        nonlocal called
        called = True
        raise AssertionError("expired work must not reach the handler")

    wrapped = AuthorizedForwardEventHandler(
        lambda _entry, _item: _authorization(),
        handler,
        clock=lambda: NOW + timedelta(minutes=6),
    )
    result = await wrapped(entry, work_item)
    assert result.decision is WorkerHandleDecision.RETRY
    assert called is False
