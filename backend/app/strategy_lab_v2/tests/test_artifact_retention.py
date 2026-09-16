from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.artifact_retention import (
    ArtifactRetentionPin,
    ArtifactRetentionState,
    RetentionDecision,
    RetentionPinDecision,
    add_retention_pin,
    release_retention_pin,
    resolve_artifact_retention,
)
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention

NOW = datetime(2024, 1, 1, tzinfo=UTC)
PAYLOAD = b"artifact"
MANIFEST = ArtifactManifest(
    content_digest=artifact_content_digest(PAYLOAD),
    byte_length=len(PAYLOAD),
    media_type="application/octet-stream",
    schema_version="v1",
    storage_key=artifact_content_digest(PAYLOAD),
    retention_class=ArtifactRetention.PINNED_RESULT,
)


def _state(
    retention_class: ArtifactRetention = ArtifactRetention.PINNED_RESULT,
    *,
    eligible_at: datetime | None = None,
) -> ArtifactRetentionState:
    return ArtifactRetentionState(
        manifest_fingerprint=content_digest(MANIFEST),
        content_digest=MANIFEST.content_digest,
        retention_class=retention_class,
        retention_eligible_at=eligible_at,
    )


def _pin(value: str, *, expires_at: datetime | None = None) -> ArtifactRetentionPin:
    return ArtifactRetentionPin(
        pin_id=content_digest({"pin": value}),
        artifact_manifest_fingerprint=content_digest(MANIFEST),
        owner_type="experiment",
        owner_id="experiment-1",
        created_at=NOW,
        expires_at=expires_at,
    )


def test_retention_state_binds_manifest_and_sorts_pin_ids() -> None:
    state = ArtifactRetentionState.from_manifest(MANIFEST)
    assert state.manifest_fingerprint == content_digest(MANIFEST)
    assert state.content_digest == MANIFEST.content_digest
    assert state.pins == ()


def test_pin_add_and_exact_replay_are_idempotent() -> None:
    state = _state()
    pin = _pin("one")
    added = add_retention_pin(state, pin)
    assert added.decision is RetentionPinDecision.ADD
    replay = add_retention_pin(added.state, pin)
    assert replay.decision is RetentionPinDecision.REPLAY_EXISTING
    assert replay.state == added.state


def test_same_pin_id_with_changed_metadata_is_a_conflict() -> None:
    state = add_retention_pin(_state(), _pin("one")).state
    changed = replace(_pin("one"), owner_id="different-owner")
    conflict = add_retention_pin(state, changed)
    assert conflict.decision is RetentionPinDecision.CONFLICT
    assert conflict.state == state


def test_pinned_artifact_requires_a_pin_then_retains_active_pin() -> None:
    state = _state()
    assert resolve_artifact_retention(state, observed_at=NOW).decision is RetentionDecision.PIN_REQUIRED
    pinned = add_retention_pin(state, _pin("one")).state
    resolution = resolve_artifact_retention(pinned, observed_at=NOW)
    assert resolution.decision is RetentionDecision.RETAIN_PINNED
    assert resolution.active_pin_ids == (pinned.pins[0].pin_id,)


def test_expired_pin_reveals_ephemeral_expiry_eligibility() -> None:
    eligible = NOW + timedelta(days=2)
    state = _state(ArtifactRetention.EPHEMERAL, eligible_at=eligible)
    pinned = add_retention_pin(state, _pin("one", expires_at=eligible)).state
    assert resolve_artifact_retention(pinned, observed_at=NOW).decision is RetentionDecision.RETAIN_PINNED
    assert (
        resolve_artifact_retention(pinned, observed_at=eligible).decision
        is RetentionDecision.EXPIRE_ELIGIBLE
    )


def test_tiered_result_remains_tiered_until_eligibility() -> None:
    eligible = NOW + timedelta(days=2)
    state = _state(ArtifactRetention.TIERED_RESULT, eligible_at=eligible)
    assert resolve_artifact_retention(state, observed_at=NOW).decision is RetentionDecision.RETAIN_TIERED
    assert (
        resolve_artifact_retention(state, observed_at=eligible).decision
        is RetentionDecision.TIER_ELIGIBLE
    )


def test_release_is_idempotent_and_reopens_retention_decision() -> None:
    pin = _pin("one")
    state = add_retention_pin(_state(), pin).state
    released = release_retention_pin(
        state, pin_id=pin.pin_id, released_at=NOW + timedelta(hours=1)
    )
    assert resolve_artifact_retention(released, observed_at=NOW).decision is RetentionDecision.RETAIN_PINNED
    assert (
        resolve_artifact_retention(released, observed_at=NOW + timedelta(hours=1)).decision
        is RetentionDecision.PIN_REQUIRED
    )
    assert release_retention_pin(
        released, pin_id=pin.pin_id, released_at=NOW + timedelta(hours=2)
    ) == released


def test_retention_contract_rejects_invalid_deadlines_and_foreign_pins() -> None:
    with pytest.raises(ValueError, match="require retention_eligible_at"):
        _state(ArtifactRetention.EPHEMERAL)
    foreign = replace(
        _pin("one"), artifact_manifest_fingerprint=content_digest({"other": "manifest"})
    )
    with pytest.raises(ValueError, match="reference the state manifest"):
        add_retention_pin(_state(), foreign)
    with pytest.raises(ValueError, match="precede"):
        _pin("bad", expires_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="not present"):
        release_retention_pin(_state(), pin_id=content_digest({"missing": True}), released_at=NOW)
