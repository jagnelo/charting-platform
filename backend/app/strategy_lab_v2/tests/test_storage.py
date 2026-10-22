from __future__ import annotations

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.storage import (
    AggregateKey,
    AggregateMutation,
    StorageTransactionDecision,
    StorageTransactionReceipt,
    StorageTransactionRequest,
    resolve_storage_transaction,
)


def _request(*, request: str = "request", value: int = 1, expected_version: int = 0,
             expected_state_fingerprint: str | None = None) -> StorageTransactionRequest:
    return StorageTransactionRequest(
        content_digest(request),
        (
            AggregateMutation(
                AggregateKey("attempt", "attempt-1"),
                {"status": "queued", "value": value},
                expected_version,
                expected_state_fingerprint,
            ),
        ),
    )


def test_create_and_compare_set_update_are_content_addressed() -> None:
    create = _request()
    applied = resolve_storage_transaction((), create)
    assert applied.decision is StorageTransactionDecision.APPLY
    assert applied.receipt is not None
    assert applied.aggregates[0].version == 1
    assert applied.aggregates[0].state["value"] == 1

    current = applied.aggregates
    update = _request(
        request="update",
        value=2,
        expected_version=1,
        expected_state_fingerprint=current[0].state_fingerprint,
    )
    updated = resolve_storage_transaction(current, update)
    assert updated.decision is StorageTransactionDecision.APPLY
    assert updated.aggregates[0].version == 2
    assert updated.aggregates[0].state["value"] == 2
    assert updated.fingerprint.startswith("sha256:")


def test_exact_request_retry_replays_receipt_without_reapplying() -> None:
    request = _request()
    applied = resolve_storage_transaction((), request)
    assert applied.receipt is not None
    replay = resolve_storage_transaction((), request, (applied.receipt,))
    assert replay.decision is StorageTransactionDecision.REPLAY_EXISTING
    assert replay.receipt == applied.receipt
    assert replay.aggregates == applied.aggregates


def test_request_id_conflict_and_compare_set_drift_keep_original_state() -> None:
    request = _request()
    applied = resolve_storage_transaction((), request)
    assert applied.receipt is not None
    changed_request = _request(value=9)
    conflict = resolve_storage_transaction((), changed_request, (applied.receipt,))
    assert conflict.decision is StorageTransactionDecision.CONFLICT
    assert conflict.aggregates == ()

    drift = resolve_storage_transaction(
        applied.aggregates,
        _request(
            request="drift",
            expected_version=1,
            expected_state_fingerprint=content_digest({"status": "wrong"}),
        ),
    )
    assert drift.decision is StorageTransactionDecision.CONFLICT
    assert drift.aggregates == applied.aggregates


def test_create_collision_and_missing_update_are_conflicts() -> None:
    request = _request()
    applied = resolve_storage_transaction((), request)
    assert applied.receipt is not None
    collision = resolve_storage_transaction(applied.aggregates, request)
    assert collision.decision is StorageTransactionDecision.CONFLICT
    missing = resolve_storage_transaction(
        (),
        _request(request="missing", expected_version=1, expected_state_fingerprint=content_digest("state")),
    )
    assert missing.decision is StorageTransactionDecision.CONFLICT


def test_multiple_mutations_are_sorted_and_duplicate_keys_fail() -> None:
    first = AggregateMutation(AggregateKey("z", "2"), {"value": 2})
    second = AggregateMutation(AggregateKey("a", "1"), {"value": 1})
    request = StorageTransactionRequest(content_digest("multi"), (first, second))
    result = resolve_storage_transaction((), request)
    assert [item.key.aggregate_type for item in result.aggregates] == ["a", "z"]
    with pytest.raises(ValueError, match="mutation keys"):
        StorageTransactionRequest(content_digest("duplicate"), (first, first))


def test_states_and_receipts_are_immutable_and_inputs_fail_closed() -> None:
    request = _request()
    result = resolve_storage_transaction((), request)
    assert result.receipt is not None
    with pytest.raises(TypeError):
        result.aggregates[0].state["status"] = "changed"  # type: ignore[index]
    with pytest.raises(ValueError, match="non-negative integer"):
        AggregateMutation(AggregateKey("attempt", "attempt-1"), {}, -1)
    with pytest.raises(ValueError, match="at least one"):
        StorageTransactionRequest(content_digest("empty"), ())
    with pytest.raises(TypeError, match="current"):
        resolve_storage_transaction("bad", request)  # type: ignore[arg-type]


def test_receipt_replay_detects_contradictory_historical_outcomes() -> None:
    request = _request()
    applied = resolve_storage_transaction((), request)
    assert applied.receipt is not None
    contradictory = StorageTransactionReceipt(
        applied.receipt.request_id,
        applied.receipt.request_fingerprint,
        content_digest("different-outcome"),
        applied.receipt.committed,
    )
    with pytest.raises(ValueError, match="conflicting request identities"):
        resolve_storage_transaction((), request, (applied.receipt, contradictory))
