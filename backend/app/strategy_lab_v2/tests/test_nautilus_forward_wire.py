from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ShadowFill,
    ShadowOrder,
)
from app.strategy_lab_v2.forward_account_worker import ForwardAccountEventBinding
from app.strategy_lab_v2.forward_context import (
    ForwardStrategyContextPreparation,
    ForwardStrategyContextWindow,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusForwardDeliveryBinding,
    materialize_nautilus_forward_tape,
)
from app.strategy_lab_v2.nautilus_forward_delivery import (
    NautilusForwardDeliveryInput,
)
from app.strategy_lab_v2.nautilus_forward_session import NautilusForwardExecutionResult
from app.strategy_lab_v2.nautilus_forward_wire import (
    NAUTILUS_FORWARD_WIRE_SCHEMA,
    NautilusForwardJsonWireCodec,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    OrderIntent,
    OrderSide,
    StrategyDataDependency,
    StrategySdkManifest,
)

NOW = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
INSTANCE_ID = "forward-1"


def _delivery_and_preparation() -> (
    tuple[
        NautilusForwardDeliveryInput,
        ForwardStrategyContextPreparation,
        CanonicalForwardEvent,
    ]
):
    canonical = CanonicalForwardEvent(
        "event-1",
        7,
        NOW,
        NOW + timedelta(seconds=1),
        content_digest("source-bytes"),
    )
    market_event = MarketEvent(
        "daily-bars",
        canonical.event_id,
        "US.AAPL",
        canonical.event_time,
        canonical.sequence,
        {
            "open": Decimal("100.00"),
            "high": Decimal("102.00"),
            "low": Decimal("99.00"),
            "close": Decimal("101.00"),
            "volume": 1200,
        },
    )
    binding = NautilusForwardDeliveryBinding(
        instance_id=INSTANCE_ID,
        event_fingerprint=content_digest(canonical),
        redis_stream_id="1704205800000-0",
        redis_entry_fingerprint=content_digest("redis-entry"),
        dispatch_record_fingerprint=content_digest("dispatch"),
        request_fingerprint=content_digest("request"),
        pre_event_checkpoint_fingerprint=content_digest("checkpoint"),
        warmup_receipt_fingerprint=content_digest("warmup"),
        admission_decision="enqueue",
    )
    tape = materialize_nautilus_forward_tape(
        INSTANCE_ID,
        (canonical,),
        (market_event,),
        event_type_by_dependency={"daily-bars": "ohlcv"},
        delivery_bindings=(binding,),
    )
    delivery = NautilusForwardDeliveryInput(
        binding,
        tape,
        market_event,
        canonical.source_digest,
    )
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=NOW - timedelta(days=1),
        end=NOW + timedelta(days=1),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="XNYS.regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash",
        corporate_action_semantics="split-adjusted-v1",
    )
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = StrategySdkManifest(
        StrategyVersion("strategy-1", "version-1", "2.0", content_digest(source)),
        (
            StrategyDataDependency(
                "daily-bars", requirement, ("open", "high", "low", "close", "volume"), 2
            ),
        ),
    )
    window = ForwardStrategyContextWindow(
        INSTANCE_ID,
        manifest,
        parameters={"multiplier": Decimal("1.5"), "labels": ("warmup", "live")},
        random_seed=19,
    )
    preparation = window.prepare_delivery(delivery)
    return delivery, preparation, canonical


def test_forward_wire_roundtrips_authenticated_delivery_and_preparation() -> None:
    codec = NautilusForwardJsonWireCodec()
    delivery, preparation, _canonical = _delivery_and_preparation()

    wire = codec.execute_payload(delivery, preparation)
    decoded_delivery, decoded_preparation = codec.decode_execute_payload(wire)

    assert decoded_delivery == delivery
    assert decoded_preparation == preparation
    assert wire["schema"] == NAUTILUS_FORWARD_WIRE_SCHEMA
    assert decoded_delivery.fingerprint == delivery.fingerprint
    assert decoded_preparation.fingerprint == preparation.fingerprint


def test_forward_wire_roundtrips_native_account_result() -> None:
    codec = NautilusForwardJsonWireCodec()
    _delivery, preparation, canonical = _delivery_and_preparation()
    account_binding = ForwardAccountEventBinding(
        canonical,
        ForwardAccountEvent(
            INSTANCE_ID,
            canonical.event_id,
            content_digest(canonical),
            canonical.sequence,
            canonical.event_time,
            orders=(
                ShadowOrder(
                    content_digest("order-1"),
                    canonical.event_id,
                    OrderIntent("US.AAPL", OrderSide.BUY, Decimal("2")),
                ),
            ),
            fills=(
                ShadowFill(
                    content_digest("fill-1"),
                    content_digest("order-1"),
                    Decimal("2"),
                    Decimal("101.00"),
                    Decimal("0.50"),
                    "USD",
                    canonical.event_time,
                ),
            ),
            cash_deltas={"USD": Decimal("-202.50")},
        ),
    )
    result = NautilusForwardExecutionResult(
        delivery_binding_fingerprint=content_digest("delivery-binding"),
        context_preparation_fingerprint=preparation.fingerprint,
        pre_event_checkpoint_fingerprint=content_digest("checkpoint"),
        runtime_session_fingerprint=content_digest("runtime-session"),
        native_output_fingerprint=account_binding.fingerprint,
        account_event_binding=account_binding,
    )

    decoded = codec.execution_result(codec.execution_result_payload(result))

    assert decoded == result
    assert decoded.fingerprint == result.fingerprint


def test_forward_wire_checks_open_restore_and_rejects_unknown_fields() -> None:
    codec = NautilusForwardJsonWireCodec()
    checkpoint = content_digest("checkpoint")

    assert codec.decode_open_payload(codec.open_payload(instance_id=INSTANCE_ID)) == INSTANCE_ID
    assert codec.decode_restore_payload(
        codec.restore_payload(instance_id=INSTANCE_ID, checkpoint_fingerprint=checkpoint)
    ) == (INSTANCE_ID, checkpoint)
    with pytest.raises(ValueError, match="fields are invalid"):
        codec.decode_open_payload(
            {"schema": NAUTILUS_FORWARD_WIRE_SCHEMA, "instance_id": INSTANCE_ID, "extra": True}
        )


def test_forward_wire_rejects_cross_delivery_preparation_binding() -> None:
    codec = NautilusForwardJsonWireCodec()
    delivery, preparation, _canonical = _delivery_and_preparation()
    changed = replace(
        preparation,
        delivery_binding_fingerprint=content_digest("another-delivery"),
    )

    with pytest.raises(ValueError, match="not bound to this delivery"):
        codec.execute_payload(delivery, changed)
