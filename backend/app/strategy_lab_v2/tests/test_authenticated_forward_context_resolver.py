from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    CarryInMode,
    EventGranularity,
    ForwardInstance,
    ForwardState,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.forward_account import ForwardAccountState
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.forward_context import ForwardStrategyContextHistory
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt, resolve_forward_warmup
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import (
    VerifiedForwardMarketPayload,
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_session import (
    AuthenticatedForwardContextWindowResolver,
    ForwardStrategyContextRecipe,
)
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    PositionSnapshot,
    StrategyDataDependency,
    StrategySdkManifest,
)

NOW = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
INSTANCE_ID = "forward-1"
OWNER_ID = "owner-1"
PORTFOLIO_FINGERPRINT = content_digest("portfolio")
SNAPSHOT_FINGERPRINT = content_digest("snapshot")
STRATEGY_SOURCE = "class Strategy:\n    def on_event(self, context):\n        return []\n"


def _manifest() -> StrategySdkManifest:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=NOW - timedelta(days=5),
        end=NOW + timedelta(days=5),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="XNYS.regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash",
        corporate_action_semantics="split-adjusted-v1",
    )
    return StrategySdkManifest(
        StrategyVersion("strategy-1", "version-1", "2.0", content_digest(STRATEGY_SOURCE)),
        (
            StrategyDataDependency(
                "daily-bars", requirement, ("open", "high", "low", "close", "volume"), 1
            ),
        ),
    )


def _payload(event_id: str, sequence: int, event_time: datetime) -> VerifiedForwardMarketPayload:
    source_digest = content_digest({"source": event_id})
    canonical = CanonicalForwardEvent(
        event_id,
        sequence,
        event_time,
        event_time + timedelta(milliseconds=1),
        source_digest,
    )
    market = MarketEvent(
        "daily-bars",
        event_id,
        "US.AAPL",
        event_time,
        sequence,
        {
            "open": Decimal(sequence),
            "high": Decimal(sequence + 1),
            "low": Decimal(sequence - 1),
            "close": Decimal(sequence),
            "volume": Decimal(100),
        },
    )
    return VerifiedForwardMarketPayload(canonical, market, source_digest)


def _admission_state() -> (
    tuple[ForwardLiveAdmissionState, ForwardWarmupReceipt, VerifiedForwardMarketPayload]
):
    warmup = _payload("warmup-5", 5, NOW)
    warming = ForwardInstance(
        INSTANCE_ID,
        PORTFOLIO_FINGERPRINT,
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW - timedelta(minutes=1),
        NOW - timedelta(minutes=1),
    )
    receipt = ForwardWarmupReceipt(
        INSTANCE_ID,
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        content_digest("warm-up-result"),
        NOW,
        warmup.canonical_event.event_id,
        warmup.canonical_event.sequence,
        content_digest(warmup.canonical_event),
    )
    active = resolve_forward_warmup(warming, receipt).instance
    return ForwardLiveAdmissionState.from_warmup(active, receipt), receipt, warmup


def _delivery(admission: ForwardLiveAdmissionState):
    current = _payload("live-6", 6, NOW + timedelta(minutes=1))
    event_fingerprint = content_digest(current.canonical_event)
    request = DispatchRequest(
        "event-key-1",
        INSTANCE_ID,
        content_digest({"event_fingerprint": event_fingerprint, "replay_plan_fingerprint": None}),
        "strategy-lab:v2:forward-events",
        NOW + timedelta(seconds=2),
    )
    record = ForwardEventDispatchRecord(
        OWNER_ID,
        INSTANCE_ID,
        event_fingerprint,
        request,
        pre_event_checkpoint_fingerprint=admission.checkpoint.fingerprint,
        warmup_receipt_fingerprint=admission.warmup_receipt_fingerprint,
        admission_decision="enqueue",
    )
    entry = RedisStreamEntry(
        request.queue_name,
        "1704205800000-0",
        request.fingerprint,
        request.attempt_id,
        request.payload_digest,
        request.fingerprint,
    )
    work_item = ForwardEventWorkItem(record, ForwardEventDispatchPayload(event_fingerprint))
    factory = create_nautilus_forward_delivery_callback_factory(
        lambda **_kwargs: current,
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    return factory(entry, work_item)


class AdmissionStore:
    def __init__(
        self,
        admission: ForwardLiveAdmissionState,
        receipt: ForwardWarmupReceipt,
    ) -> None:
        self.admission = admission
        self.receipt = receipt

    async def load_state_at_checkpoint(self, **kwargs: Any):
        assert kwargs["principal"] == OWNER_ID
        assert kwargs["instance_id"] == INSTANCE_ID
        if kwargs["checkpoint_fingerprint"] != self.admission.checkpoint.fingerprint:
            return None
        return self.admission

    async def load_warmup_receipt(self, **kwargs: Any):
        assert kwargs == {"principal": OWNER_ID, "instance_id": INSTANCE_ID}
        return self.receipt


class AccountHistoryStore:
    def __init__(self, state: ForwardAccountState) -> None:
        self.state = state

    async def load_at_checkpoint(
        self, *, principal: Any, admission_state: ForwardLiveAdmissionState
    ):
        assert principal == OWNER_ID
        assert admission_state.checkpoint.instance.instance_id == INSTANCE_ID
        return self.state


@pytest.mark.anyio
async def test_authenticated_resolver_composes_exact_history_recipe_and_account_positions() -> None:
    admission, receipt, warmup = _admission_state()
    manifest = _manifest()
    position = PositionSnapshot("US.AAPL", Decimal("2"), Decimal("100"), Decimal("200"))
    account = ForwardAccountState(INSTANCE_ID, "USD", positions=(position,))
    history = ForwardStrategyContextHistory(
        INSTANCE_ID,
        manifest.fingerprint,
        admission.checkpoint.fingerprint,
        receipt.fingerprint,
        (warmup,),
    )

    def recipe_resolver(*, principal: Any, instance: ForwardInstance):
        assert principal == OWNER_ID
        return ForwardStrategyContextRecipe(
            instance.portfolio_fingerprint,
            "component-1",
            manifest,
            {"threshold": Decimal("1.5")},
            17,
        )

    def history_resolver(**kwargs: Any):
        assert kwargs["principal"] == OWNER_ID
        assert kwargs["instance"].instance_id == INSTANCE_ID
        assert kwargs["admission_state"] == admission
        assert kwargs["warmup_receipt"] == receipt
        return history

    resolver = AuthenticatedForwardContextWindowResolver(
        AdmissionStore(admission, receipt),
        AccountHistoryStore(account),
        recipe_resolver,
        history_resolver,
        principal=OWNER_ID,
    )

    delivery = await _delivery(admission)
    resolved = await resolver(delivery)
    preparation = resolved.window.prepare_delivery(delivery, positions=resolved.positions)

    assert resolved.pre_event_checkpoint_fingerprint == admission.checkpoint.fingerprint
    assert resolved.warmup_receipt_fingerprint == receipt.fingerprint
    assert resolved.positions == {"US.AAPL": position}
    assert preparation.context.positions == {"US.AAPL": position}
    assert preparation.context.market_events["daily-bars"] == (
        warmup.market_event,
        delivery.market_event,
    )


@pytest.mark.anyio
async def test_authenticated_resolver_rejects_live_history_outside_processed_checkpoint() -> None:
    admission, receipt, _warmup = _admission_state()
    manifest = _manifest()
    uncommitted = _payload("uncommitted-6", 6, NOW + timedelta(minutes=1))
    history = ForwardStrategyContextHistory(
        INSTANCE_ID,
        manifest.fingerprint,
        admission.checkpoint.fingerprint,
        receipt.fingerprint,
        (uncommitted,),
    )
    account = ForwardAccountState(INSTANCE_ID, "USD")
    resolver = AuthenticatedForwardContextWindowResolver(
        AdmissionStore(admission, receipt),
        AccountHistoryStore(account),
        lambda *, principal, instance: ForwardStrategyContextRecipe(
            instance.portfolio_fingerprint, "component-1", manifest, {}, 1
        ),
        lambda **_kwargs: history,
        principal=OWNER_ID,
    )

    delivery = await _delivery(admission)
    with pytest.raises(ValueError, match="outside the processed prefix"):
        await resolver(delivery)
