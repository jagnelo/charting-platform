"""Storage-neutral compare-and-set contracts for Strategy Lab v2 aggregates.

The production adapter will map these immutable plans to PostgreSQL rows and a
single transaction.  This module deliberately performs no database or file
I/O; it makes version checks, create/update semantics, and idempotent retries
explicit before an adapter is introduced.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True, order=True)
class AggregateKey:
    """Stable storage key for one logical aggregate."""

    aggregate_type: str
    aggregate_id: str

    def __post_init__(self) -> None:
        _nonempty(self.aggregate_type, "aggregate_type")
        _nonempty(self.aggregate_id, "aggregate_id")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class StoredAggregate:
    """Immutable versioned state read from the authoritative store."""

    key: AggregateKey
    version: int
    state: Any

    def __post_init__(self) -> None:
        if not isinstance(self.key, AggregateKey):
            raise TypeError("key must be an AggregateKey")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("aggregate version must be a positive integer")
        object.__setattr__(self, "state", freeze_json(self.state))

    @property
    def state_fingerprint(self) -> str:
        return content_digest(self.state)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class AggregateMutation:
    """One create or compare-and-set update inside a storage transaction."""

    key: AggregateKey
    state: Any
    expected_version: int = 0
    expected_state_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, AggregateKey):
            raise TypeError("key must be an AggregateKey")
        if (
            not isinstance(self.expected_version, int)
            or isinstance(self.expected_version, bool)
            or self.expected_version < 0
        ):
            raise ValueError("expected_version must be a non-negative integer")
        if self.expected_version == 0 and self.expected_state_fingerprint is not None:
            raise ValueError("create mutations cannot include an expected state fingerprint")
        if self.expected_version > 0:
            require_sha256_digest(
                self.expected_state_fingerprint or "", field_name="expected_state_fingerprint"
            )
        object.__setattr__(self, "state", freeze_json(self.state))

    @property
    def state_fingerprint(self) -> str:
        return content_digest(self.state)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class StorageTransactionRequest:
    """Content-addressed atomic mutation request with no transport metadata."""

    request_id: str
    mutations: tuple[AggregateMutation, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_id, field_name="request_id")
        if not isinstance(self.mutations, tuple):
            raise TypeError("mutations must be a tuple")
        if not self.mutations:
            raise ValueError("storage transaction requires at least one mutation")
        if any(not isinstance(item, AggregateMutation) for item in self.mutations):
            raise TypeError("mutations must contain AggregateMutation values")
        keys = [item.key for item in self.mutations]
        if len(keys) != len(set(keys)):
            raise ValueError("storage transaction mutation keys must be unique")
        object.__setattr__(self, "mutations", tuple(sorted(self.mutations, key=lambda item: item.key)))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class StorageTransactionReceipt:
    """Durable idempotency receipt an adapter records with the transaction."""

    request_id: str
    request_fingerprint: str
    outcome_fingerprint: str
    committed: tuple[StoredAggregate, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_id, field_name="request_id")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        require_sha256_digest(self.outcome_fingerprint, field_name="outcome_fingerprint")
        if not isinstance(self.committed, tuple):
            raise TypeError("committed must be a tuple")
        if any(not isinstance(item, StoredAggregate) for item in self.committed):
            raise TypeError("committed must contain StoredAggregate values")
        if tuple(sorted(self.committed, key=lambda item: item.key)) != self.committed:
            raise ValueError("committed aggregates must be deterministically ordered")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class StorageTransactionDecision(StrEnum):
    APPLY = "apply"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class StorageTransactionResolution:
    """Pure compare-and-set result; adapters persist only one returned state."""

    decision: StorageTransactionDecision
    request_fingerprint: str
    aggregates: tuple[StoredAggregate, ...]
    receipt: StorageTransactionReceipt | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, StorageTransactionDecision):
            raise TypeError("decision must be a StorageTransactionDecision")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if not isinstance(self.aggregates, tuple):
            raise TypeError("aggregates must be a tuple")
        if any(not isinstance(item, StoredAggregate) for item in self.aggregates):
            raise TypeError("aggregates must contain StoredAggregate values")
        if tuple(sorted(self.aggregates, key=lambda item: item.key)) != self.aggregates:
            raise ValueError("aggregates must be deterministically ordered")
        if self.receipt is not None and not isinstance(self.receipt, StorageTransactionReceipt):
            raise TypeError("receipt must be a StorageTransactionReceipt")
        if self.decision in {
            StorageTransactionDecision.APPLY,
            StorageTransactionDecision.REPLAY_EXISTING,
        } and self.receipt is None:
            raise ValueError("successful storage resolutions require a receipt")
        if self.decision in {
            StorageTransactionDecision.CONFLICT,
            StorageTransactionDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("failed storage resolutions require a reason")
        if self.decision in {
            StorageTransactionDecision.APPLY,
            StorageTransactionDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful storage resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def resolve_storage_transaction(
    current: Sequence[StoredAggregate],
    request: StorageTransactionRequest,
    prior_receipts: Sequence[StorageTransactionReceipt] = (),
) -> StorageTransactionResolution:
    """Resolve a deterministic atomic create/update transaction without I/O."""

    if not isinstance(current, Sequence) or isinstance(current, str | bytes):
        raise TypeError("current must be a sequence")
    if not isinstance(request, StorageTransactionRequest):
        raise TypeError("request must be a StorageTransactionRequest")
    if not isinstance(prior_receipts, Sequence) or isinstance(prior_receipts, str | bytes):
        raise TypeError("prior_receipts must be a sequence")
    existing = tuple(current)
    if any(not isinstance(item, StoredAggregate) for item in existing):
        raise TypeError("current must contain StoredAggregate values")
    if len({item.key for item in existing}) != len(existing):
        raise ValueError("current aggregate keys must be unique")
    receipts = tuple(prior_receipts)
    if any(not isinstance(item, StorageTransactionReceipt) for item in receipts):
        raise TypeError("prior_receipts must contain StorageTransactionReceipt values")
    matching = tuple(item for item in receipts if item.request_id == request.request_id)
    if matching:
        first = matching[0]
        if any(
            item.request_fingerprint != first.request_fingerprint
            or item.outcome_fingerprint != first.outcome_fingerprint
            or item.committed != first.committed
            for item in matching[1:]
        ):
            raise ValueError("prior storage receipts contain conflicting request identities")
        if first.request_fingerprint == request.fingerprint:
            return StorageTransactionResolution(
                StorageTransactionDecision.REPLAY_EXISTING,
                request.fingerprint,
                first.committed,
                first,
            )
        return StorageTransactionResolution(
            StorageTransactionDecision.CONFLICT,
            request.fingerprint,
            tuple(sorted(existing, key=lambda item: item.key)),
            rejection_reason="request id is already bound to different transaction content",
        )

    by_key = {item.key: item for item in existing}
    for mutation in request.mutations:
        prior = by_key.get(mutation.key)
        if mutation.expected_version == 0:
            if prior is not None:
                return _failed(
                    request,
                    existing,
                    StorageTransactionDecision.CONFLICT,
                    "create mutation collides with an existing aggregate",
                )
            continue
        if prior is None:
            return _failed(
                request,
                existing,
                StorageTransactionDecision.CONFLICT,
                "expected aggregate is missing",
            )
        if prior.version != mutation.expected_version:
            return _failed(
                request,
                existing,
                StorageTransactionDecision.CONFLICT,
                "aggregate version does not match compare-and-set precondition",
            )
        if prior.state_fingerprint != mutation.expected_state_fingerprint:
            return _failed(
                request,
                existing,
                StorageTransactionDecision.CONFLICT,
                "aggregate state does not match compare-and-set precondition",
            )

    next_by_key = dict(by_key)
    for mutation in request.mutations:
        prior = by_key.get(mutation.key)
        next_by_key[mutation.key] = StoredAggregate(
            mutation.key,
            1 if prior is None else prior.version + 1,
            mutation.state,
        )
    committed = tuple(sorted(next_by_key.values(), key=lambda item: item.key))
    receipt = StorageTransactionReceipt(
        request.request_id,
        request.fingerprint,
        content_digest(committed),
        committed,
    )
    return StorageTransactionResolution(
        StorageTransactionDecision.APPLY,
        request.fingerprint,
        committed,
        receipt,
    )


def _failed(
    request: StorageTransactionRequest,
    current: Sequence[StoredAggregate],
    decision: StorageTransactionDecision,
    reason: str,
) -> StorageTransactionResolution:
    return StorageTransactionResolution(
        decision,
        request.fingerprint,
        tuple(sorted(current, key=lambda item: item.key)),
        rejection_reason=reason,
    )
