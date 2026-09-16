"""Deterministic, storage-neutral attempt recovery decisions.

Recovery is infrastructure control flow, not a new scientific trial.  This
module decides whether a terminal attempt may be retried and, when it can,
computes a deterministic retry time.  Queue/database adapters own durable
compare-and-set and scheduling; the simulator is never invoked here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.lifecycle import create_retry_attempt


class RecoveryReason(StrEnum):
    """Recorded cause presented by a worker or orchestration adapter."""

    WORKER_CRASH = "worker_crash"
    LEASE_EXPIRED = "lease_expired"
    TRANSIENT_ENGINE_ERROR = "transient_engine_error"
    ARTIFACT_PUBLISH_FAILURE = "artifact_publish_failure"
    CANCELLED = "cancelled"


class RecoveryDisposition(StrEnum):
    RETRY = "retry"
    TERMINAL = "terminal"
    NOOP = "noop"


_DEFAULT_RETRYABLE_REASONS = frozenset(
    {
        RecoveryReason.WORKER_CRASH,
        RecoveryReason.LEASE_EXPIRED,
        RecoveryReason.TRANSIENT_ENGINE_ERROR,
        RecoveryReason.ARTIFACT_PUBLISH_FAILURE,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential retry policy with no wall-clock dependency."""

    max_attempts: int = 3
    retryable_reasons: frozenset[RecoveryReason] = _DEFAULT_RETRYABLE_REASONS
    initial_backoff: timedelta = timedelta(seconds=5)
    max_backoff: timedelta = timedelta(minutes=5)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or self.max_attempts < 1
        ):
            raise ValueError("max_attempts must be a positive integer")
        reasons = frozenset(self.retryable_reasons)
        if any(not isinstance(reason, RecoveryReason) for reason in reasons):
            raise TypeError("retryable_reasons must contain RecoveryReason values")
        if RecoveryReason.CANCELLED in reasons:
            raise ValueError("cancelled attempts require explicit non-retryable handling")
        object.__setattr__(self, "retryable_reasons", reasons)
        for name in ("initial_backoff", "max_backoff"):
            value = getattr(self, name)
            if not isinstance(value, timedelta) or value <= timedelta(0):
                raise ValueError(f"{name} must be positive")
        if self.max_backoff < self.initial_backoff:
            raise ValueError("max_backoff must be at least initial_backoff")

    def backoff_for(self, next_ordinal: int) -> timedelta:
        """Return capped ``initial * 2**(ordinal-1)`` without float arithmetic."""

        if not isinstance(next_ordinal, int) or isinstance(next_ordinal, bool) or next_ordinal < 2:
            raise ValueError("next retry ordinal must be at least two")
        delay = self.initial_backoff
        for _ in range(next_ordinal - 2):
            delay = min(delay * 2, self.max_backoff)
            if delay == self.max_backoff:
                break
        return delay


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """Pure decision that an adapter can persist and execute idempotently."""

    disposition: RecoveryDisposition
    reason: RecoveryReason
    trial_id: str
    prior_attempt_id: str
    prior_ordinal: int
    next_ordinal: int | None
    retry_at: datetime | None
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, RecoveryDisposition):
            raise TypeError("disposition must be a RecoveryDisposition")
        if not isinstance(self.reason, RecoveryReason):
            raise TypeError("reason must be a RecoveryReason")
        if not self.trial_id.strip() or not self.prior_attempt_id.strip():
            raise ValueError("recovery identity must not be empty")
        if self.prior_ordinal < 1:
            raise ValueError("prior_ordinal must be positive")
        if not self.rationale.strip():
            raise ValueError("recovery rationale must not be empty")
        if self.retry_at is not None and (
            self.retry_at.tzinfo is None or self.retry_at.utcoffset() is None
        ):
            raise ValueError("retry_at must be timezone-aware")
        if self.disposition is RecoveryDisposition.RETRY:
            if self.next_ordinal != self.prior_ordinal + 1 or self.retry_at is None:
                raise ValueError("retry plans require the next ordinal and retry_at")
        elif self.next_ordinal is not None or self.retry_at is not None:
            raise ValueError("non-retry plans cannot schedule an attempt")

    def materialize_retry_attempt(
        self, prior_attempts: tuple[RunAttempt, ...], *, attempt_id: str
    ) -> RunAttempt:
        """Create the queued attempt described by this plan without persistence."""

        if self.disposition is not RecoveryDisposition.RETRY:
            raise ValueError("only retry plans can materialize an attempt")
        attempt = create_retry_attempt(
            prior_attempts, attempt_id=attempt_id, created_at=self.retry_at  # type: ignore[arg-type]
        )
        if attempt.trial_id != self.trial_id or attempt.ordinal != self.next_ordinal:
            raise ValueError("prior attempts do not match the recovery plan")
        return attempt


def _validate_attempt_chain(prior_attempts: Sequence[RunAttempt]) -> tuple[RunAttempt, ...]:
    if not isinstance(prior_attempts, Sequence) or isinstance(prior_attempts, str | bytes):
        raise TypeError("prior_attempts must be a sequence")
    attempts = tuple(prior_attempts)
    if not attempts:
        raise ValueError("recovery requires at least one prior attempt")
    if any(not isinstance(item, RunAttempt) for item in attempts):
        raise TypeError("prior_attempts must contain RunAttempt values")
    ordered = tuple(sorted(attempts, key=lambda item: item.ordinal))
    if [item.ordinal for item in ordered] != list(range(1, len(ordered) + 1)):
        raise ValueError("attempt ordinals must be contiguous from one")
    if len({item.trial_id for item in ordered}) != 1:
        raise ValueError("all attempts in a recovery chain must reference one trial")
    if any(item.state not in {AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.CANCELLED} for item in ordered[:-1]):
        raise ValueError("all earlier attempts must be terminal before recovery")
    return ordered


def plan_attempt_recovery(
    prior_attempts: Sequence[RunAttempt],
    *,
    reason: RecoveryReason,
    observed_at: datetime,
    policy: RetryPolicy = RetryPolicy(),
) -> RecoveryPlan:
    """Plan retry/no-op/terminal handling for the latest attempt.

    The latest attempt must already be terminal.  A successful attempt is a
    no-op, while an exhausted or non-retryable failure is terminal.  Retry
    timing depends only on the attempt ordinal, policy, and supplied timestamp,
    making repeated adapter evaluations deterministic.
    """

    if not isinstance(reason, RecoveryReason):
        raise TypeError("reason must be a RecoveryReason")
    if not isinstance(policy, RetryPolicy):
        raise TypeError("policy must be a RetryPolicy")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("recovery observation time must be timezone-aware")
    ordered = _validate_attempt_chain(prior_attempts)
    latest = ordered[-1]
    latest_updated = latest.updated_at or latest.created_at
    if observed_at < latest_updated:
        raise ValueError("recovery observation time cannot precede the latest attempt")
    if latest.state not in {AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.CANCELLED}:
        raise ValueError("only a terminal attempt can be recovered")
    if latest.state is AttemptState.SUCCEEDED:
        return RecoveryPlan(
            disposition=RecoveryDisposition.NOOP,
            reason=reason,
            trial_id=latest.trial_id,
            prior_attempt_id=latest.attempt_id,
            prior_ordinal=latest.ordinal,
            next_ordinal=None,
            retry_at=None,
            rationale="attempt already succeeded",
        )
    if reason not in policy.retryable_reasons or latest.state is AttemptState.CANCELLED:
        rationale = (
            "recovery reason is not retryable"
            if reason not in policy.retryable_reasons
            else "cancelled attempts are not retried by default"
        )
        return RecoveryPlan(
            disposition=RecoveryDisposition.TERMINAL,
            reason=reason,
            trial_id=latest.trial_id,
            prior_attempt_id=latest.attempt_id,
            prior_ordinal=latest.ordinal,
            next_ordinal=None,
            retry_at=None,
            rationale=rationale,
        )
    if len(ordered) >= policy.max_attempts:
        return RecoveryPlan(
            disposition=RecoveryDisposition.TERMINAL,
            reason=reason,
            trial_id=latest.trial_id,
            prior_attempt_id=latest.attempt_id,
            prior_ordinal=latest.ordinal,
            next_ordinal=None,
            retry_at=None,
            rationale="retry attempt limit exhausted",
        )
    next_ordinal = latest.ordinal + 1
    return RecoveryPlan(
        RecoveryDisposition.RETRY,
        reason,
        rationale="terminal infrastructure failure is eligible for retry",
        trial_id=latest.trial_id,
        prior_attempt_id=latest.attempt_id,
        prior_ordinal=latest.ordinal,
        next_ordinal=next_ordinal,
        retry_at=observed_at + policy.backoff_for(next_ordinal),
    )
