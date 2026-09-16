from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_warmup import (
    ForwardWarmupDecision,
    ForwardWarmupReceipt,
    resolve_forward_warmup,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
SNAPSHOT = content_digest("warmup-snapshot")


def _instance(*, state: ForwardState = ForwardState.WARMING_UP) -> ForwardInstance:
    return ForwardInstance(
        instance_id="forward-1",
        portfolio_fingerprint=content_digest("portfolio"),
        warmup_snapshot_fingerprint=SNAPSHOT,
        carry_in_mode=CarryInMode.FLAT,
        state=state,
        last_event_id=None,
        last_event_sequence=0,
        correction_count=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _receipt(
    *,
    completed_at: datetime = NOW + timedelta(minutes=1),
    final_event_id: str | None = None,
    final_event_sequence: int = 0,
    final_event_fingerprint: str | None = None,
) -> ForwardWarmupReceipt:
    return ForwardWarmupReceipt(
        instance_id="forward-1",
        warmup_snapshot_fingerprint=SNAPSHOT,
        carry_in_mode=CarryInMode.FLAT,
        warmup_result_fingerprint=content_digest("warmup-result"),
        completed_at=completed_at,
        final_event_id=final_event_id,
        final_event_sequence=final_event_sequence,
        final_event_fingerprint=final_event_fingerprint,
    )


def test_warmup_completion_activates_instance_and_seeds_cursor() -> None:
    receipt = _receipt(
        final_event_id="historical-0",
        final_event_sequence=0,
        final_event_fingerprint=content_digest("historical-0"),
    )
    result = resolve_forward_warmup(_instance(), receipt)
    assert result.decision is ForwardWarmupDecision.COMPLETE
    assert result.instance.state is ForwardState.ACTIVE
    assert result.instance.last_event_id == "historical-0"
    assert result.instance.updated_at == receipt.completed_at


def test_exact_existing_receipt_replays_without_rewriting_live_state() -> None:
    receipt = _receipt()
    active = resolve_forward_warmup(_instance(), receipt).instance
    replay = resolve_forward_warmup(active, receipt, existing_receipt=receipt)
    assert replay.decision is ForwardWarmupDecision.REPLAY_EXISTING
    assert replay.instance == active


def test_changed_existing_receipt_is_a_conflict() -> None:
    receipt = _receipt()
    changed = _receipt(completed_at=NOW + timedelta(minutes=2))
    conflict = resolve_forward_warmup(_instance(), changed, existing_receipt=receipt)
    assert conflict.decision is ForwardWarmupDecision.CONFLICT
    assert conflict.instance == _instance()


def test_receipt_must_match_instance_snapshot_and_carry_mode() -> None:
    foreign_snapshot = ForwardWarmupReceipt(
        instance_id="forward-1",
        warmup_snapshot_fingerprint=content_digest("other-snapshot"),
        carry_in_mode=CarryInMode.FLAT,
        warmup_result_fingerprint=content_digest("warmup-result"),
        completed_at=NOW + timedelta(minutes=1),
    )
    rejected = resolve_forward_warmup(_instance(), foreign_snapshot)
    assert rejected.decision is ForwardWarmupDecision.REJECT
    assert "snapshot" in (rejected.rejection_reason or "")

    synthetic = ForwardWarmupReceipt(
        instance_id="forward-1",
        warmup_snapshot_fingerprint=SNAPSHOT,
        carry_in_mode=CarryInMode.SYNTHETIC_HISTORICAL,
        warmup_result_fingerprint=content_digest("warmup-result"),
        completed_at=NOW + timedelta(minutes=1),
    )
    rejected_mode = resolve_forward_warmup(_instance(), synthetic)
    assert rejected_mode.decision is ForwardWarmupDecision.REJECT
    assert "carry-in" in (rejected_mode.rejection_reason or "")


def test_warmup_completes_only_from_warming_up_state() -> None:
    rejected = resolve_forward_warmup(_instance(state=ForwardState.CREATED), _receipt())
    assert rejected.decision is ForwardWarmupDecision.REJECT
    assert "warming_up" in (rejected.rejection_reason or "")


def test_warmup_completion_time_and_live_cursor_are_monotonic() -> None:
    stale = resolve_forward_warmup(
        _instance(), _receipt(completed_at=NOW - timedelta(seconds=1))
    )
    assert stale.decision is ForwardWarmupDecision.REJECT
    assert "backwards" in (stale.rejection_reason or "")

    with_cursor = ForwardInstance(
        instance_id="forward-1",
        portfolio_fingerprint=content_digest("portfolio"),
        warmup_snapshot_fingerprint=SNAPSHOT,
        carry_in_mode=CarryInMode.FLAT,
        state=ForwardState.WARMING_UP,
        last_event_id="live-0",
        last_event_sequence=0,
        correction_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    overwritten = resolve_forward_warmup(with_cursor, _receipt())
    assert overwritten.decision is ForwardWarmupDecision.REJECT
    assert "existing live cursor" in (overwritten.rejection_reason or "")


def test_warmup_receipt_identity_requires_event_id_for_nonzero_sequence() -> None:
    with pytest.raises(ValueError, match="final_event_id"):
        _receipt(final_event_sequence=2)
    with pytest.raises(ValueError, match="final_event_fingerprint"):
        _receipt(final_event_id="historical-0")


def test_warmup_contract_rejects_invalid_digest_and_timestamp() -> None:
    with pytest.raises(ValueError, match="warmup_result_fingerprint"):
        ForwardWarmupReceipt(
            "forward-1",
            SNAPSHOT,
            CarryInMode.FLAT,
            "bad",
            NOW,
        )
    with pytest.raises(ValueError, match="timezone"):
        _receipt(completed_at=datetime(2024, 1, 1))
