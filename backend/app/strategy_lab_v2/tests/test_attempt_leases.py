from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.lifecycle import (
    AttemptLeaseStatus,
    acquire_attempt_lease,
    transition_attempt,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _running_attempt() -> RunAttempt:
    queued = RunAttempt("attempt-1", "trial-1", 1, AttemptState.QUEUED, NOW)
    return transition_attempt(queued, AttemptState.RUNNING, now=NOW + timedelta(seconds=1))


def test_attempt_lease_acquisition_renewal_and_release_are_typed() -> None:
    attempt = _running_attempt()
    lease = acquire_attempt_lease(
        attempt,
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(seconds=30),
    )
    assert lease.attempt_id == attempt.attempt_id
    assert lease.status_at(NOW + timedelta(seconds=3)) is AttemptLeaseStatus.ACTIVE

    renewed = lease.renew(
        now=NOW + timedelta(seconds=10),
        lease_duration=timedelta(seconds=30),
    )
    assert renewed.heartbeat_at == NOW + timedelta(seconds=10)
    assert renewed.expires_at == NOW + timedelta(seconds=40)
    released = renewed.release(now=NOW + timedelta(seconds=11))
    assert released.status_at(NOW + timedelta(seconds=12)) is AttemptLeaseStatus.RELEASED


def test_attempt_lease_expiry_blocks_renewal() -> None:
    lease = acquire_attempt_lease(
        _running_attempt(),
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(seconds=1),
    )
    assert lease.status_at(NOW + timedelta(seconds=3)) is AttemptLeaseStatus.EXPIRED
    with pytest.raises(ValueError, match="active lease"):
        lease.renew(now=NOW + timedelta(seconds=3), lease_duration=timedelta(seconds=10))


def test_attempt_lease_requires_running_attempt_and_monotonic_times() -> None:
    queued = RunAttempt("attempt-queued", "trial-1", 1, AttemptState.QUEUED, NOW)
    with pytest.raises(ValueError, match="running attempt"):
        acquire_attempt_lease(
            queued,
            worker_id="worker-1",
            lease_id="lease-1",
            now=NOW,
            lease_duration=timedelta(seconds=10),
        )

    lease = acquire_attempt_lease(
        _running_attempt(),
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(seconds=10),
    )
    with pytest.raises(ValueError, match="move backwards"):
        lease.release(now=NOW + timedelta(seconds=1))
