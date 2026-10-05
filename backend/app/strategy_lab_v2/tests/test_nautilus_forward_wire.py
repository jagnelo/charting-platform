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
from app.strategy_lab_v2.nautilus_forward_runtime_server import (
    NautilusForwardRuntimeOperationHandler,
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


class _FakeNativeForwardSession:
    def __init__(
        self,
        instance_id: str = INSTANCE_ID,
        *,
        runtime_session_fingerprint: str | None = None,
        result_runtime_fingerprint: str | None = None,
    ) -> None:
        self.instance_id = instance_id
        self.runtime_session_fingerprint = runtime_session_fingerprint or content_digest(
            "runtime-session"
        )
        self._result_runtime_fingerprint = result_runtime_fingerprint
        self.closed = 0
        self.restored: list[str] = []
        self.executions = 0

    def execute(self, delivery, preparation) -> NautilusForwardExecutionResult:
        self.executions += 1
        canonical = delivery.tape.envelopes[0].canonical_event
        account_event = ForwardAccountEvent(
            INSTANCE_ID,
            canonical.event_id,
            content_digest(canonical),
            canonical.sequence,
            canonical.event_time,
        )
        account_binding = ForwardAccountEventBinding(canonical, account_event)
        return NautilusForwardExecutionResult(
            delivery_binding_fingerprint=delivery.delivery_binding.fingerprint,
            context_preparation_fingerprint=preparation.fingerprint,
            pre_event_checkpoint_fingerprint=(
                delivery.delivery_binding.pre_event_checkpoint_fingerprint
            ),
            runtime_session_fingerprint=(
                self._result_runtime_fingerprint or self.runtime_session_fingerprint
            ),
            native_output_fingerprint=account_binding.fingerprint,
            account_event_binding=account_binding,
        )

    def restore(self, *, checkpoint_fingerprint: str) -> str:
        self.restored.append(checkpoint_fingerprint)
        return checkpoint_fingerprint

    def close(self) -> None:
        self.closed += 1


def test_forward_runtime_handler_binds_open_execute_restore_and_close() -> None:
    codec = NautilusForwardJsonWireCodec()
    delivery, preparation, _canonical = _delivery_and_preparation()
    native_session = _FakeNativeForwardSession()
    handler = NautilusForwardRuntimeOperationHandler(
        instance_id=INSTANCE_ID,
        session_factory=lambda _instance_id: native_session,
        codec=codec,
    )

    opened = handler.open(codec.open_payload(instance_id=INSTANCE_ID))
    assert codec.validate_open_result(opened, instance_id=INSTANCE_ID) == (
        native_session.runtime_session_fingerprint
    )

    execution = codec.execution_result(
        handler.execute(codec.execute_payload(delivery, preparation))
    )
    assert execution.delivery_binding_fingerprint == delivery.delivery_binding.fingerprint
    assert execution.context_preparation_fingerprint == preparation.fingerprint
    assert execution.runtime_session_fingerprint == native_session.runtime_session_fingerprint

    checkpoint = delivery.delivery_binding.pre_event_checkpoint_fingerprint
    restored = handler.restore(
        codec.restore_payload(instance_id=INSTANCE_ID, checkpoint_fingerprint=checkpoint)
    )
    codec.validate_restore_result(
        restored,
        instance_id=INSTANCE_ID,
        checkpoint_fingerprint=checkpoint,
    )
    assert native_session.restored == [checkpoint]

    closed = handler.close(codec.close_payload(instance_id=INSTANCE_ID))
    codec.validate_close_result(closed, instance_id=INSTANCE_ID)
    assert native_session.closed == 1


def test_forward_runtime_handler_rejects_wrong_instance_before_starting_engine() -> None:
    codec = NautilusForwardJsonWireCodec()
    factory_calls: list[str] = []
    handler = NautilusForwardRuntimeOperationHandler(
        instance_id=INSTANCE_ID,
        session_factory=lambda instance_id: factory_calls.append(instance_id)
        or _FakeNativeForwardSession(instance_id),
        codec=codec,
    )

    with pytest.raises(ValueError, match="another instance"):
        handler.open(codec.open_payload(instance_id="another-forward"))

    assert factory_calls == []


def test_forward_runtime_handler_closes_invalid_engine_and_cannot_reopen() -> None:
    codec = NautilusForwardJsonWireCodec()
    invalid_session = _FakeNativeForwardSession(runtime_session_fingerprint="not-a-sha256-digest")
    handler = NautilusForwardRuntimeOperationHandler(
        instance_id=INSTANCE_ID,
        session_factory=lambda _instance_id: invalid_session,
        codec=codec,
    )

    with pytest.raises(ValueError, match="sha256 content digest"):
        handler.open(codec.open_payload(instance_id=INSTANCE_ID))

    assert invalid_session.closed == 1

    class _BrokenOpenResponseCodec(NautilusForwardJsonWireCodec):
        def open_result_payload(self, *, instance_id: str, runtime_session_fingerprint: str):
            raise ValueError("open response could not be encoded")

    response_session = _FakeNativeForwardSession()
    response_handler = NautilusForwardRuntimeOperationHandler(
        instance_id=INSTANCE_ID,
        session_factory=lambda _instance_id: response_session,
        codec=_BrokenOpenResponseCodec(),
    )
    with pytest.raises(ValueError, match="could not be encoded"):
        response_handler.open(codec.open_payload(instance_id=INSTANCE_ID))
    assert response_session.closed == 1

    valid_session = _FakeNativeForwardSession()
    close_handler = NautilusForwardRuntimeOperationHandler(
        instance_id=INSTANCE_ID,
        session_factory=lambda _instance_id: valid_session,
        codec=codec,
    )
    close_handler.open(codec.open_payload(instance_id=INSTANCE_ID))
    codec.validate_close_result(close_handler.close({}), instance_id=INSTANCE_ID)
    assert valid_session.closed == 1
    with pytest.raises(ValueError, match="cannot be reopened"):
        close_handler.open(codec.open_payload(instance_id=INSTANCE_ID))


def test_forward_runtime_handler_rejects_unbound_preparation_before_native_execution() -> None:
    class _TamperingCodec(NautilusForwardJsonWireCodec):
        def decode_execute_payload(self, payload):
            delivery, preparation = super().decode_execute_payload(payload)
            return delivery, replace(
                preparation,
                delivery_binding_fingerprint=content_digest("different-delivery"),
            )

    codec = _TamperingCodec()
    delivery, preparation, _canonical = _delivery_and_preparation()
    native_session = _FakeNativeForwardSession()
    handler = NautilusForwardRuntimeOperationHandler(
        instance_id=INSTANCE_ID,
        session_factory=lambda _instance_id: native_session,
        codec=codec,
    )
    handler.open(codec.open_payload(instance_id=INSTANCE_ID))

    with pytest.raises(ValueError, match="not bound to this instance and delivery"):
        handler.execute(codec.execute_payload(delivery, preparation))

    assert native_session.executions == 0


def test_forward_runtime_handler_rejects_result_from_another_native_session() -> None:
    codec = NautilusForwardJsonWireCodec()
    delivery, preparation, _canonical = _delivery_and_preparation()
    native_session = _FakeNativeForwardSession(
        result_runtime_fingerprint=content_digest("different-runtime-session")
    )
    handler = NautilusForwardRuntimeOperationHandler(
        instance_id=INSTANCE_ID,
        session_factory=lambda _instance_id: native_session,
        codec=codec,
    )
    handler.open(codec.open_payload(instance_id=INSTANCE_ID))

    with pytest.raises(ValueError, match="authenticated execution input"):
        handler.execute(codec.execute_payload(delivery, preparation))
