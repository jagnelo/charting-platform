from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardRuntimeExecutionReceipt,
    apply_forward_account_event,
    initial_forward_account_state,
)
from app.strategy_lab_v2.forward_admission import (
    ForwardAdmissionDecision,
    ForwardLiveAdmissionState,
    admit_forward_event,
)
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt, resolve_forward_warmup
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    observe_forward_event,
)
from app.strategy_lab_v2.nautilus_forward_recovery import (
    AuthenticatedNautilusForwardCheckpointResolver,
)

_NOW = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
_INSTANCE_ID = "forward-recovery-1"
_OWNER = "recovery-owner"


@dataclass
class _AdmissionStore:
    state: ForwardLiveAdmissionState | None
    receipt: ForwardWarmupReceipt | None
    calls: list[dict[str, Any]]

    async def load_state_at_checkpoint(self, **kwargs: Any):
        self.calls.append({"state": kwargs})
        return self.state

    async def load_warmup_receipt(self, **kwargs: Any):
        self.calls.append({"warmup": kwargs})
        return self.receipt


@dataclass
class _AccountStore:
    state: Any
    calls: list[dict[str, Any]]

    async def load_at_checkpoint(self, **kwargs: Any):
        self.calls.append(kwargs)
        return self.state


def _warmup() -> tuple[ForwardLiveAdmissionState, ForwardWarmupReceipt]:
    instance = ForwardInstance(
        _INSTANCE_ID,
        content_digest("recovery-portfolio"),
        content_digest("recovery-snapshot"),
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        _NOW,
        _NOW,
    )
    receipt = ForwardWarmupReceipt(
        _INSTANCE_ID,
        instance.warmup_snapshot_fingerprint,
        CarryInMode.FLAT,
        content_digest("empty-warmup-result"),
        _NOW + timedelta(seconds=1),
    )
    active = resolve_forward_warmup(instance, receipt).instance
    return ForwardLiveAdmissionState.from_warmup(active, receipt), receipt


def _live_checkpoint():
    admission, receipt = _warmup()
    canonical = CanonicalForwardEvent(
        "live-1",
        0,
        _NOW + timedelta(minutes=1),
        _NOW + timedelta(minutes=1, seconds=1),
        content_digest("source-live-1"),
    )
    observation = observe_forward_event(ForwardCursor(), canonical)
    admitted = admit_forward_event(admission, canonical, observation)
    assert admitted.decision is ForwardAdmissionDecision.ACCEPTED
    event = ForwardAccountEvent(
        _INSTANCE_ID,
        canonical.event_id,
        content_digest(canonical),
        canonical.sequence,
        canonical.event_time,
    )
    execution_receipt = ForwardRuntimeExecutionReceipt(
        _INSTANCE_ID,
        canonical.event_id,
        content_digest(canonical),
        content_digest("delivery-binding"),
        content_digest("context-preparation"),
        admission.checkpoint.fingerprint,
        content_digest("runtime-session"),
        content_digest("native-output"),
    )
    initial = initial_forward_account_state(_INSTANCE_ID, base_currency="USD")
    settled = apply_forward_account_event(
        initial,
        event,
        execution_receipt=execution_receipt,
    )
    assert settled.state is not None
    return admitted.state, receipt, settled.state


@pytest.mark.asyncio
async def test_resolves_exact_persisted_admission_warmup_and_account_checkpoint() -> None:
    admission, receipt, account = _live_checkpoint()
    admissions = _AdmissionStore(admission, receipt, [])
    accounts = _AccountStore(account, [])
    resolver = AuthenticatedNautilusForwardCheckpointResolver(
        admissions,
        accounts,
        principal=_OWNER,
    )

    resolved = await resolver.resolve(
        instance_id=_INSTANCE_ID,
        checkpoint_fingerprint=admission.checkpoint.fingerprint,
    )

    assert resolved.admission_state == admission
    assert resolved.warmup_receipt == receipt
    assert resolved.account_state == account
    assert resolved.checkpoint_fingerprint == admission.checkpoint.fingerprint
    assert admissions.calls[0]["state"] == {
        "principal": _OWNER,
        "instance_id": _INSTANCE_ID,
        "checkpoint_fingerprint": admission.checkpoint.fingerprint,
    }
    assert accounts.calls[0]["admission_state"] == admission


@pytest.mark.asyncio
async def test_rejects_missing_or_unsettled_durable_account_history() -> None:
    admission, receipt, _account = _live_checkpoint()
    admissions = _AdmissionStore(admission, receipt, [])
    accounts = _AccountStore(None, [])
    resolver = AuthenticatedNautilusForwardCheckpointResolver(
        admissions,
        accounts,
        principal=_OWNER,
    )

    with pytest.raises(ValueError, match="not settled"):
        await resolver.resolve(
            instance_id=_INSTANCE_ID,
            checkpoint_fingerprint=admission.checkpoint.fingerprint,
        )


@pytest.mark.asyncio
async def test_rejects_admission_store_returning_a_different_checkpoint() -> None:
    admission, receipt, account = _live_checkpoint()
    admissions = _AdmissionStore(admission, receipt, [])
    accounts = _AccountStore(account, [])
    resolver = AuthenticatedNautilusForwardCheckpointResolver(
        admissions,
        accounts,
        principal=_OWNER,
    )

    with pytest.raises(ValueError, match="differs from the requested checkpoint"):
        await resolver.resolve(
            instance_id=_INSTANCE_ID,
            checkpoint_fingerprint=content_digest("stale-checkpoint"),
        )


@pytest.mark.asyncio
async def test_rejects_live_checkpoint_without_matching_native_receipt() -> None:
    live_admission, receipt, valid_account = _live_checkpoint()
    applied_without_receipt = apply_forward_account_event(
        initial_forward_account_state(_INSTANCE_ID, base_currency="USD"),
        ForwardAccountEvent(
            _INSTANCE_ID,
            valid_account.last_event_id or "live-1",
            valid_account.last_event_fingerprint or content_digest("live-event"),
            valid_account.last_event_sequence,
            _NOW + timedelta(minutes=1),
        ),
    )
    assert applied_without_receipt.state is not None
    resolver = AuthenticatedNautilusForwardCheckpointResolver(
        _AdmissionStore(live_admission, receipt, []),
        _AccountStore(applied_without_receipt.state, []),
        principal=_OWNER,
    )

    with pytest.raises(ValueError, match="native execution receipt"):
        await resolver.resolve(
            instance_id=_INSTANCE_ID,
            checkpoint_fingerprint=live_admission.checkpoint.fingerprint,
        )
