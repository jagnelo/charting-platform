from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    WorkerReservationDecision,
    release_worker_slot,
    reserve_worker_slot,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
RUNTIME = content_digest({"runtime": "strategy-v2"})


def _pool() -> WorkerPoolState:
    return WorkerPoolState(WorkerProfile("worker-1", WorkerKind.BACKTEST, RUNTIME))


def _reservation_id(value: str) -> str:
    return content_digest({"reservation": value})


def test_worker_pool_reserves_one_serial_slot_and_replays_same_attempt() -> None:
    pool = _pool()
    reservation_id = _reservation_id("one")
    accepted = reserve_worker_slot(
        pool,
        attempt_id="attempt-1",
        reservation_id=reservation_id,
        acquired_at=NOW,
    )
    assert accepted.decision is WorkerReservationDecision.ACCEPT
    assert accepted.reservation is not None
    assert len(accepted.pool.active_reservations) == 1
    replay = reserve_worker_slot(
        accepted.pool,
        attempt_id="attempt-1",
        reservation_id=_reservation_id("different-id"),
        acquired_at=NOW + timedelta(seconds=1),
    )
    assert replay.decision is WorkerReservationDecision.REPLAY_EXISTING
    assert replay.reservation == accepted.reservation


def test_worker_pool_reports_saturation_and_reopens_after_release() -> None:
    accepted = reserve_worker_slot(
        _pool(),
        attempt_id="attempt-1",
        reservation_id=_reservation_id("one"),
        acquired_at=NOW,
    )
    saturated = reserve_worker_slot(
        accepted.pool,
        attempt_id="attempt-2",
        reservation_id=_reservation_id("two"),
        acquired_at=NOW + timedelta(seconds=1),
    )
    assert saturated.decision is WorkerReservationDecision.SATURATED
    released = release_worker_slot(
        accepted.pool,
        reservation_id=_reservation_id("one"),
        released_at=NOW + timedelta(seconds=2),
    )
    reopened = reserve_worker_slot(
        released,
        attempt_id="attempt-2",
        reservation_id=_reservation_id("two"),
        acquired_at=NOW + timedelta(seconds=3),
    )
    assert reopened.decision is WorkerReservationDecision.ACCEPT
    assert release_worker_slot(
        released,
        reservation_id=_reservation_id("one"),
        released_at=NOW + timedelta(seconds=4),
    ) == released


def test_worker_pool_rejects_unsafe_profile_and_reused_reservation_id() -> None:
    unsafe = replace(_pool().profile, isolation_required=False)
    rejected = reserve_worker_slot(
        WorkerPoolState(unsafe),
        attempt_id="attempt-1",
        reservation_id=_reservation_id("one"),
        acquired_at=NOW,
    )
    assert rejected.decision is WorkerReservationDecision.REJECT
    assert rejected.rejection_reason == "worker isolation is required"

    accepted = reserve_worker_slot(
        _pool(),
        attempt_id="attempt-1",
        reservation_id=_reservation_id("one"),
        acquired_at=NOW,
    )
    reused = reserve_worker_slot(
        accepted.pool,
        attempt_id="attempt-2",
        reservation_id=_reservation_id("one"),
        acquired_at=NOW + timedelta(seconds=1),
    )
    assert reused.decision is WorkerReservationDecision.REJECT
    assert reused.rejection_reason == "reservation id is already bound"


def test_worker_contract_rejects_non_serial_or_invalid_time_and_ids() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        WorkerProfile("worker-1", WorkerKind.FORWARD, RUNTIME, max_concurrent_nodes=2)
    with pytest.raises(ValueError, match="reservation_id"):
        reserve_worker_slot(
            _pool(), attempt_id="attempt-1", reservation_id="bad", acquired_at=NOW
        )
    accepted = reserve_worker_slot(
        _pool(),
        attempt_id="attempt-1",
        reservation_id=_reservation_id("one"),
        acquired_at=NOW,
    )
    with pytest.raises(ValueError, match="precede"):
        release_worker_slot(
            accepted.pool,
            reservation_id=_reservation_id("one"),
            released_at=NOW - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="not present"):
        release_worker_slot(
            accepted.pool,
            reservation_id=_reservation_id("missing"),
            released_at=NOW,
        )
