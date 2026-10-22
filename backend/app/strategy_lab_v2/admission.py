"""Fail-closed admission of an authorized attempt onto an isolated worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerReservationDecision,
    reserve_worker_slot,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ExecutionAdmissionRequest:
    """Stable admission intent used for compare-and-set by an adapter."""

    authorization_fingerprint: str
    runtime_request_fingerprint: str
    attempt_id: str
    worker_id: str
    worker_kind: WorkerKind
    worker_profile_fingerprint: str
    reservation_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "authorization_fingerprint",
            "runtime_request_fingerprint",
            "worker_profile_fingerprint",
            "reservation_id",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("attempt_id", "worker_id"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.worker_kind, WorkerKind):
            raise TypeError("worker_kind must be a WorkerKind")
        _aware(self.requested_at, "requested_at")
        object.__setattr__(self, "requested_at", self.requested_at.astimezone(UTC))

    @property
    def fingerprint(self) -> str:
        """Identity excludes scheduling time so retries can replay exactly."""

        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "authorization_fingerprint": self.authorization_fingerprint,
                "reservation_id": self.reservation_id,
                "runtime_request_fingerprint": self.runtime_request_fingerprint,
                "worker_id": self.worker_id,
                "worker_kind": self.worker_kind,
                "worker_profile_fingerprint": self.worker_profile_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class ExecutionAdmission:
    """Receipt proving one authorized attempt holds one worker reservation."""

    request_fingerprint: str
    authorization_fingerprint: str
    runtime_request_fingerprint: str
    attempt_id: str
    worker_id: str
    worker_kind: WorkerKind
    worker_profile_fingerprint: str
    reservation_id: str
    admitted_at: datetime
    authoritative: bool

    def __post_init__(self) -> None:
        for name in (
            "request_fingerprint",
            "authorization_fingerprint",
            "runtime_request_fingerprint",
            "worker_profile_fingerprint",
            "reservation_id",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("attempt_id", "worker_id"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.worker_kind, WorkerKind):
            raise TypeError("worker_kind must be a WorkerKind")
        _aware(self.admitted_at, "admitted_at")
        object.__setattr__(self, "admitted_at", self.admitted_at.astimezone(UTC))
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ExecutionAdmissionLedger:
    """Append-only admission receipts keyed by attempt and intent identity."""

    admissions: tuple[ExecutionAdmission, ...] = ()

    def __post_init__(self) -> None:
        admissions = tuple(self.admissions)
        if any(not isinstance(item, ExecutionAdmission) for item in admissions):
            raise TypeError("admissions must contain ExecutionAdmission values")
        request_ids = [item.request_fingerprint for item in admissions]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("admission request fingerprints must be unique")
        attempt_ids = [item.attempt_id for item in admissions]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("an attempt may have only one admission receipt")
        reservation_ids = [item.reservation_id for item in admissions]
        if len(reservation_ids) != len(set(reservation_ids)):
            raise ValueError("admission reservation ids must be unique")
        object.__setattr__(
            self,
            "admissions",
            tuple(sorted(admissions, key=lambda item: item.request_fingerprint)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ExecutionAdmissionDecision(StrEnum):
    ADMIT = "admit"
    REPLAY_EXISTING = "replay_existing"
    SATURATED = "saturated"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ExecutionAdmissionResolution:
    decision: ExecutionAdmissionDecision
    ledger: ExecutionAdmissionLedger
    pool: WorkerPoolState
    request_fingerprint: str
    admission: ExecutionAdmission | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ExecutionAdmissionDecision):
            raise TypeError("decision must be an ExecutionAdmissionDecision")
        if not isinstance(self.ledger, ExecutionAdmissionLedger):
            raise TypeError("ledger must be an ExecutionAdmissionLedger")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if self.admission is not None and not isinstance(self.admission, ExecutionAdmission):
            raise TypeError("admission must be an ExecutionAdmission")
        if self.decision in {
            ExecutionAdmissionDecision.ADMIT,
            ExecutionAdmissionDecision.REPLAY_EXISTING,
        } and self.admission is None:
            raise ValueError("admitted resolutions require an admission receipt")
        if self.decision in {
            ExecutionAdmissionDecision.CONFLICT,
            ExecutionAdmissionDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision in {
            ExecutionAdmissionDecision.SATURATED,
            ExecutionAdmissionDecision.ADMIT,
            ExecutionAdmissionDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("non-rejected admission resolutions cannot contain a reason")


def resolve_execution_admission(
    ledger: ExecutionAdmissionLedger,
    authorization: ExecutionAuthorization,
    runtime_request: StrategyRuntimeRequest,
    runtime_preflight: StrategyRuntimePreflight,
    pool: WorkerPoolState,
    *,
    reservation_id: str,
    now: datetime,
) -> ExecutionAdmissionResolution:
    """Atomically resolve authorization, runtime, and serial-capacity gates.

    The returned states are storage-neutral. An adapter must persist the ledger
    and pool together; an existing pool reservation without a matching receipt
    is treated as an inconsistency rather than silently replayed.
    """

    if not isinstance(ledger, ExecutionAdmissionLedger):
        raise TypeError("ledger must be an ExecutionAdmissionLedger")
    if not isinstance(authorization, ExecutionAuthorization):
        raise TypeError("authorization must be an ExecutionAuthorization")
    if not isinstance(runtime_request, StrategyRuntimeRequest):
        raise TypeError("runtime_request must be a StrategyRuntimeRequest")
    if not isinstance(runtime_preflight, StrategyRuntimePreflight):
        raise TypeError("runtime_preflight must be a StrategyRuntimePreflight")
    if not isinstance(pool, WorkerPoolState):
        raise TypeError("pool must be a WorkerPoolState")
    require_sha256_digest(reservation_id, field_name="reservation_id")
    _aware(now, "admission time")
    request = ExecutionAdmissionRequest(
        authorization_fingerprint=authorization.fingerprint,
        runtime_request_fingerprint=runtime_request.fingerprint,
        attempt_id=authorization.attempt_id,
        worker_id=pool.profile.worker_id,
        worker_kind=pool.profile.kind,
        worker_profile_fingerprint=pool.profile.runtime_profile_fingerprint,
        reservation_id=reservation_id,
        requested_at=now,
    )
    if now < authorization.authorized_at:
        return _reject(ledger, pool, request.fingerprint, "admission time cannot precede authorization")
    if now < runtime_request.submitted_at:
        return _reject(ledger, pool, request.fingerprint, "admission time cannot precede runtime submission")
    if authorization.attempt_id != runtime_request.attempt_id:
        return _reject(
            ledger,
            pool,
            request.fingerprint,
            "authorization and runtime request reference different attempts",
        )
    if authorization.source_digest != runtime_request.source_digest:
        return _reject(ledger, pool, request.fingerprint, "authorization and runtime source digests differ")
    if authorization.lease_worker_id != pool.profile.worker_id:
        return _reject(ledger, pool, request.fingerprint, "authorization lease is bound to a different worker")
    if runtime_request.runtime_profile_fingerprint != pool.profile.runtime_profile_fingerprint:
        return _reject(ledger, pool, request.fingerprint, "runtime request profile does not match worker profile")
    if runtime_preflight.request_fingerprint != runtime_request.fingerprint:
        return _reject(ledger, pool, request.fingerprint, "runtime preflight references a different request")
    if runtime_preflight.profile_fingerprint != pool.profile.runtime_profile_fingerprint:
        return _reject(ledger, pool, request.fingerprint, "runtime preflight profile does not match worker profile")
    if not runtime_preflight.accepted:
        return _reject(ledger, pool, request.fingerprint, "runtime preflight is not accepted")
    existing = next(
        (item for item in ledger.admissions if item.attempt_id == request.attempt_id),
        None,
    )
    if existing is not None:
        if existing.request_fingerprint != request.fingerprint:
            return ExecutionAdmissionResolution(
                ExecutionAdmissionDecision.CONFLICT,
                ledger,
                pool,
                request.fingerprint,
                rejection_reason="attempt is already bound to different admission content",
            )
        active = next(
            (
                item
                for item in pool.active_reservations
                if item.reservation_id == existing.reservation_id
                and item.attempt_id == existing.attempt_id
            ),
            None,
        )
        if active is None:
            return _reject(
                ledger,
                pool,
                request.fingerprint,
                "admission receipt is missing its active worker reservation",
            )
        return ExecutionAdmissionResolution(
            ExecutionAdmissionDecision.REPLAY_EXISTING,
            ledger,
            pool,
            request.fingerprint,
            existing,
        )

    reservation = reserve_worker_slot(
        pool,
        attempt_id=request.attempt_id,
        reservation_id=request.reservation_id,
        acquired_at=now,
    )
    if reservation.decision is WorkerReservationDecision.SATURATED:
        return ExecutionAdmissionResolution(
            ExecutionAdmissionDecision.SATURATED,
            ledger,
            pool,
            request.fingerprint,
        )
    if reservation.decision is WorkerReservationDecision.REJECT:
        return _reject(
            ledger,
            pool,
            request.fingerprint,
            reservation.rejection_reason or "worker reservation rejected",
        )
    if reservation.decision is WorkerReservationDecision.REPLAY_EXISTING:
        return _reject(
            ledger,
            pool,
            request.fingerprint,
            "worker reservation exists without an admission receipt",
        )
    assert reservation.reservation is not None
    admission = ExecutionAdmission(
        request_fingerprint=request.fingerprint,
        authorization_fingerprint=request.authorization_fingerprint,
        runtime_request_fingerprint=request.runtime_request_fingerprint,
        attempt_id=request.attempt_id,
        worker_id=request.worker_id,
        worker_kind=request.worker_kind,
        worker_profile_fingerprint=request.worker_profile_fingerprint,
        reservation_id=reservation.reservation.reservation_id,
        admitted_at=now,
        authoritative=authorization.authoritative,
    )
    return ExecutionAdmissionResolution(
        ExecutionAdmissionDecision.ADMIT,
        ExecutionAdmissionLedger(ledger.admissions + (admission,)),
        reservation.pool,
        request.fingerprint,
        admission,
    )


def _reject(
    ledger: ExecutionAdmissionLedger,
    pool: WorkerPoolState,
    request_fingerprint: str,
    reason: str,
) -> ExecutionAdmissionResolution:
    return ExecutionAdmissionResolution(
        ExecutionAdmissionDecision.REJECT,
        ledger,
        pool,
        request_fingerprint,
        rejection_reason=reason,
    )
