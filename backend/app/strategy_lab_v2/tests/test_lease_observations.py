from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationKind,
    LeaseObservationState,
    apply_lease_observation,
)
from app.strategy_lab_v2.lifecycle import acquire_attempt_lease

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _lease():
    attempt = RunAttempt("attempt-1", "trial-1", 1, AttemptState.RUNNING, NOW)
    return acquire_attempt_lease(
        attempt,
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW,
        lease_duration=timedelta(minutes=5),
    )


def _observation(
    value: str,
    sequence: int,
    kind: LeaseObservationKind = LeaseObservationKind.HEARTBEAT,
    *,
    observed_at: datetime = NOW + timedelta(minutes=1),
    expires_at: datetime | None = NOW + timedelta(minutes=6),
    lease_id: str = "lease-1",
) -> LeaseObservation:
    return LeaseObservation(
        observation_id=content_digest({"observation": value}),
        lease_id=lease_id,
        worker_id="worker-1",
        attempt_id="attempt-1",
        sequence=sequence,
        kind=kind,
        observed_at=observed_at,
        expires_at=expires_at,
    )


def test_heartbeat_advances_lease_and_exact_retry_replays() -> None:
    state = LeaseObservationState(_lease())
    heartbeat = _observation("one", 1)
    applied = apply_lease_observation(state, heartbeat)
    assert applied.decision is LeaseObservationDecision.APPLY
    assert applied.state.lease.heartbeat_at == heartbeat.observed_at
    replay = apply_lease_observation(applied.state, heartbeat)
    assert replay.decision is LeaseObservationDecision.REPLAY_EXISTING
    assert replay.state == applied.state


def test_observation_id_conflict_does_not_mutate_state() -> None:
    applied = apply_lease_observation(
        LeaseObservationState(_lease()), _observation("one", 1)
    )
    changed = _observation(
        "one",
        1,
        observed_at=NOW + timedelta(minutes=2),
        expires_at=NOW + timedelta(minutes=7),
    )
    conflict = apply_lease_observation(applied.state, changed)
    assert conflict.decision is LeaseObservationDecision.CONFLICT
    assert conflict.state == applied.state


def test_gaps_and_stale_sequences_are_explicit() -> None:
    state = LeaseObservationState(_lease())
    gap = apply_lease_observation(state, _observation("two", 2))
    assert gap.decision is LeaseObservationDecision.GAP
    assert gap.expected_sequence == 1
    applied = apply_lease_observation(state, _observation("one", 1)).state
    stale = apply_lease_observation(applied, _observation("old", 1))
    assert stale.decision is LeaseObservationDecision.STALE
    assert stale.state == applied


def test_release_is_terminal_and_exact_release_retry_replays() -> None:
    state = LeaseObservationState(_lease())
    release = _observation(
        "release", 1, LeaseObservationKind.RELEASE, observed_at=NOW + timedelta(minutes=1), expires_at=None
    )
    applied = apply_lease_observation(state, release)
    assert applied.decision is LeaseObservationDecision.APPLY
    assert applied.state.lease.released_at == release.observed_at
    replay = apply_lease_observation(applied.state, release)
    assert replay.decision is LeaseObservationDecision.REPLAY_EXISTING
    heartbeat = apply_lease_observation(applied.state, _observation("late", 2))
    assert heartbeat.decision is LeaseObservationDecision.REJECT
    assert "released" in (heartbeat.rejection_reason or "")


def test_expired_lease_rejects_heartbeat() -> None:
    state = LeaseObservationState(_lease())
    late = _observation(
        "late",
        1,
        observed_at=NOW + timedelta(minutes=6),
        expires_at=NOW + timedelta(minutes=7),
    )
    rejected = apply_lease_observation(state, late)
    assert rejected.decision is LeaseObservationDecision.REJECT
    assert "expired" in (rejected.rejection_reason or "")


def test_identity_mismatch_fails_closed_without_mutation() -> None:
    state = LeaseObservationState(_lease())
    rejected = apply_lease_observation(state, _observation("foreign", 1, lease_id="other-lease"))
    assert rejected.decision is LeaseObservationDecision.REJECT
    assert rejected.state == state


def test_state_orders_observations_and_requires_release_to_match_lease() -> None:
    first = _observation("one", 1)
    state = apply_lease_observation(LeaseObservationState(_lease()), first).state
    assert state.applied_observations == (first,)
    with pytest.raises(ValueError, match="contiguous"):
        LeaseObservationState(_lease(), (_observation("two", 2),))


def test_observation_contract_rejects_invalid_kind_expiry_and_ids() -> None:
    with pytest.raises(ValueError, match="observation_id"):
        LeaseObservation("bad", "lease-1", "worker-1", "attempt-1", 1, LeaseObservationKind.RELEASE, NOW)
    with pytest.raises(ValueError, match="require expires_at"):
        _observation("missing-expiry", 1, expires_at=None)
    with pytest.raises(ValueError, match="cannot contain expires_at"):
        _observation("release-expiry", 1, LeaseObservationKind.RELEASE, expires_at=NOW + timedelta(minutes=2))
    with pytest.raises(ValueError, match="positive"):
        _observation("zero", 0)
