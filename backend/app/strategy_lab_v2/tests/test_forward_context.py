from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.forward_context import (
    ForwardStrategyContextHistory,
    ForwardStrategyContextWindow,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import VerifiedForwardMarketPayload
from app.strategy_lab_v2.postgres_result_materialization import decode_canonical_contract
from app.strategy_lab_v2.sdk import MarketEvent, StrategyDataDependency, StrategySdkManifest

NOW = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
SOURCE = "class Strategy:\n    def on_event(self, context):\n        return []\n"


def _manifest() -> StrategySdkManifest:
    def dependency(dependency_id: str, instrument_id: str, lookback: int):
        requirement = CapabilityRequirement(
            instrument_id=instrument_id,
            product_class=ProductClass.EQUITY,
            event_granularity=EventGranularity.BAR,
            event_type="ohlcv",
            timeframe="1d",
            start=NOW - timedelta(days=10),
            end=NOW + timedelta(days=10),
            adjustment=AdjustmentMode.SPLIT_ADJUSTED,
            session="XNYS.regular",
            feed="consolidated",
            execution_model="bar-close",
            account_model="cash",
            corporate_action_semantics="split-adjusted-v1",
        )
        return StrategyDataDependency(dependency_id, requirement, ("close",), lookback)

    return StrategySdkManifest(
        StrategyVersion("strategy-1", "version-1", "2.0", content_digest(SOURCE)),
        (
            dependency("daily-bars", "US.AAPL", 1),
            dependency("benchmark-bars", "US.SPY", 0),
        ),
    )


def _payload(
    *,
    event_id: str,
    sequence: int,
    event_time: datetime,
    dependency_id: str = "daily-bars",
    instrument_id: str = "US.AAPL",
    values: dict[str, object] | None = None,
) -> VerifiedForwardMarketPayload:
    source_digest = content_digest({"source": event_id})
    canonical = CanonicalForwardEvent(
        event_id,
        sequence,
        event_time,
        event_time + timedelta(milliseconds=1),
        source_digest,
    )
    market = MarketEvent(
        dependency_id,
        event_id,
        instrument_id,
        event_time,
        sequence,
        values or {"close": Decimal(sequence)},
    )
    return VerifiedForwardMarketPayload(canonical, market, source_digest)


def test_forward_context_window_uses_only_declared_rolling_history() -> None:
    window = ForwardStrategyContextWindow(
        "forward-1",
        _manifest(),
        parameters={"threshold": Decimal("1.5")},
        random_seed=17,
    )

    first = _payload(event_id="aapl-1", sequence=1, event_time=NOW)
    context1 = window.append(first, instance_id="forward-1")
    assert context1.event_sequence == 1
    assert context1.market_events["daily-bars"] == (first.market_event,)
    assert context1.market_events["benchmark-bars"] == ()

    benchmark = _payload(
        event_id="spy-2",
        sequence=2,
        event_time=NOW + timedelta(minutes=1),
        dependency_id="benchmark-bars",
        instrument_id="US.SPY",
    )
    context2 = window.append(benchmark, instance_id="forward-1")
    assert context2.market_events["daily-bars"] == (first.market_event,)
    assert context2.market_events["benchmark-bars"] == (benchmark.market_event,)

    second = _payload(
        event_id="aapl-3",
        sequence=3,
        event_time=NOW + timedelta(minutes=2),
    )
    context3 = window.append(second, instance_id="forward-1")
    assert context3.market_events["daily-bars"] == (first.market_event, second.market_event)
    assert context3.market_events["benchmark-bars"] == (benchmark.market_event,)
    assert context3.random_seed == 17
    assert context3.parameters["threshold"] == Decimal("1.5")
    assert window.last_event_key == (second.canonical_event.event_time, 3)


def test_context_window_trims_to_lookback_plus_current_event() -> None:
    window = ForwardStrategyContextWindow("forward-1", _manifest(), parameters={}, random_seed=17)
    contexts = [
        window.append(
            _payload(
                event_id=f"aapl-{sequence}",
                sequence=sequence,
                event_time=NOW + timedelta(minutes=sequence),
            ),
            instance_id="forward-1",
        )
        for sequence in (1, 2, 3)
    ]

    assert tuple(event.event_id for event in contexts[-1].market_events["daily-bars"]) == (
        "aapl-2",
        "aapl-3",
    )
    assert window.window_fingerprint == content_digest(
        {
            "instance_id": "forward-1",
            "manifest_fingerprint": _manifest().fingerprint,
            "parameters_digest": content_digest({}),
            "random_seed": 17,
            "last_event_key": (NOW + timedelta(minutes=3), 3),
            "events": {
                "benchmark-bars": (),
                "daily-bars": (contexts[-1].market_events["daily-bars"]),
            },
        }
    )


def test_verified_history_replay_rebuilds_the_same_bounded_context_window() -> None:
    manifest = _manifest()
    payloads = (
        _payload(event_id="aapl-1", sequence=1, event_time=NOW),
        _payload(
            event_id="spy-2",
            sequence=2,
            event_time=NOW + timedelta(minutes=1),
            dependency_id="benchmark-bars",
            instrument_id="US.SPY",
        ),
        _payload(
            event_id="aapl-3",
            sequence=3,
            event_time=NOW + timedelta(minutes=2),
        ),
    )
    original = ForwardStrategyContextWindow(
        "forward-1",
        manifest,
        parameters={"threshold": Decimal("1.5")},
        random_seed=17,
    )
    context_records = []
    for payload in payloads:
        context_records.append(original.append(payload, instance_id="forward-1"))
    history = ForwardStrategyContextHistory(
        "forward-1",
        manifest.fingerprint,
        content_digest("checkpoint-3"),
        content_digest("warmup-receipt"),
        payloads,
    )

    restored = ForwardStrategyContextWindow.replay_verified_history(
        history,
        manifest,
        parameters={"threshold": Decimal("1.5")},
        random_seed=17,
        expected_pre_event_checkpoint_fingerprint=content_digest("checkpoint-3"),
        expected_warmup_receipt_fingerprint=content_digest("warmup-receipt"),
    )

    assert restored.window_fingerprint == original.window_fingerprint
    assert restored.last_event_key == original.last_event_key
    restored_from_contexts = ForwardStrategyContextWindow(
        "forward-1",
        manifest,
        parameters={"threshold": Decimal("1.5")},
        random_seed=17,
    )
    restored_from_contexts.seed_from_authenticated_contexts(
        context_records,
        context_stream_fingerprint=content_digest("verified-context-stream"),
    )
    assert restored_from_contexts.window_fingerprint == original.window_fingerprint
    next_event = _payload(
        event_id="aapl-4",
        sequence=4,
        event_time=NOW + timedelta(minutes=3),
    )
    preparation = restored.prepare(next_event, instance_id="forward-1")
    assert tuple(event.event_id for event in preparation.context.market_events["daily-bars"]) == (
        "aapl-3",
        "aapl-4",
    )
    assert preparation.context.market_events["benchmark-bars"] == (payloads[1].market_event,)


def test_authenticated_context_stream_seed_rebuilds_bounded_window_without_fabricating_events() -> (
    None
):
    manifest = _manifest()
    bounded_events = (
        _payload(
            event_id="spy-2",
            sequence=2,
            event_time=NOW + timedelta(minutes=1),
            dependency_id="benchmark-bars",
            instrument_id="US.SPY",
        ).market_event,
        _payload(
            event_id="aapl-3",
            sequence=3,
            event_time=NOW + timedelta(minutes=2),
        ).market_event,
    )
    expected = ForwardStrategyContextWindow(
        "forward-1",
        manifest,
        parameters={"threshold": Decimal("1.5")},
        random_seed=17,
    )
    for market_event in bounded_events:
        expected.append(
            _payload(
                event_id=market_event.event_id,
                sequence=market_event.sequence,
                event_time=market_event.event_time,
                dependency_id=market_event.dependency_id,
                instrument_id=market_event.instrument_id,
                values=dict(market_event.values),
            ),
            instance_id="forward-1",
        )

    restored = ForwardStrategyContextWindow(
        "forward-1",
        manifest,
        parameters={"threshold": Decimal("1.5")},
        random_seed=17,
    )
    restored.seed_from_authenticated_context_stream(
        bounded_events,
        context_stream_fingerprint=content_digest("verified-context-stream"),
    )

    assert restored.window_fingerprint == expected.window_fingerprint
    assert restored.last_event_key == expected.last_event_key
    next_payload = _payload(
        event_id="aapl-4",
        sequence=4,
        event_time=NOW + timedelta(minutes=3),
    )
    assert (
        restored.prepare(next_payload, instance_id="forward-1").context
        == expected.prepare(
            next_payload,
            instance_id="forward-1",
        ).context
    )


def test_verified_forward_history_round_trips_through_canonical_persistence_wire() -> None:
    manifest = _manifest()
    history = ForwardStrategyContextHistory(
        "forward-1",
        manifest.fingerprint,
        content_digest("checkpoint"),
        content_digest("warmup-receipt"),
        (_payload(event_id="event-1", sequence=1, event_time=NOW),),
    )

    encoded = canonical_json(history)
    restored = decode_canonical_contract(encoded, ForwardStrategyContextHistory)

    assert restored == history
    assert restored.fingerprint == history.fingerprint


@pytest.mark.parametrize(
    ("checkpoint", "warmup", "expected_error"),
    [
        (content_digest("wrong-checkpoint"), content_digest("warmup-receipt"), "checkpoint"),
        (content_digest("checkpoint-1"), content_digest("wrong-warmup"), "warm-up"),
    ],
)
def test_verified_history_replay_rejects_other_durable_checkpoints(
    checkpoint: str,
    warmup: str,
    expected_error: str,
) -> None:
    manifest = _manifest()
    history = ForwardStrategyContextHistory(
        "forward-1",
        manifest.fingerprint,
        content_digest("checkpoint-1"),
        content_digest("warmup-receipt"),
        (),
    )

    with pytest.raises(ValueError, match=expected_error):
        ForwardStrategyContextWindow.replay_verified_history(
            history,
            manifest,
            parameters={},
            random_seed=17,
            expected_pre_event_checkpoint_fingerprint=checkpoint,
            expected_warmup_receipt_fingerprint=warmup,
        )


def test_verified_history_rejects_duplicate_or_non_monotonic_event_tape() -> None:
    manifest = _manifest()
    first = _payload(event_id="event-1", sequence=1, event_time=NOW)
    second = _payload(event_id="event-2", sequence=2, event_time=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="strictly by time"):
        ForwardStrategyContextHistory(
            "forward-1",
            manifest.fingerprint,
            content_digest("checkpoint"),
            content_digest("warmup"),
            (second, first),
        )
    with pytest.raises(ValueError, match="ids must be unique"):
        ForwardStrategyContextHistory(
            "forward-1",
            manifest.fingerprint,
            content_digest("checkpoint"),
            content_digest("warmup"),
            (first, first),
        )


def test_invalid_or_out_of_order_event_does_not_mutate_context_window() -> None:
    window = ForwardStrategyContextWindow("forward-1", _manifest(), parameters={}, random_seed=17)
    accepted = _payload(event_id="aapl-2", sequence=2, event_time=NOW)
    window.append(accepted, instance_id="forward-1")
    fingerprint = window.window_fingerprint

    invalid = (
        _payload(
            event_id="aapl-extra-field",
            sequence=3,
            event_time=NOW + timedelta(minutes=1),
            values={"close": Decimal("3"), "volume": 100},
        ),
        _payload(
            event_id="unknown-dependency",
            sequence=3,
            event_time=NOW + timedelta(minutes=1),
            dependency_id="unknown",
        ),
        _payload(
            event_id="wrong-instance-sequence",
            sequence=1,
            event_time=NOW - timedelta(minutes=1),
        ),
    )
    for payload in invalid:
        with pytest.raises(ValueError):
            window.append(payload, instance_id="forward-1")
        assert window.window_fingerprint == fingerprint

    with pytest.raises(ValueError, match="different instance"):
        window.append(
            _payload(
                event_id="wrong-instance",
                sequence=3,
                event_time=NOW + timedelta(minutes=1),
            ),
            instance_id="forward-2",
        )
    assert window.window_fingerprint == fingerprint


def test_staged_context_advances_only_after_explicit_commit() -> None:
    window = ForwardStrategyContextWindow("forward-1", _manifest(), parameters={}, random_seed=17)
    payload = _payload(event_id="aapl-staged", sequence=1, event_time=NOW)
    initial_fingerprint = window.window_fingerprint

    preparation = window.prepare(payload, instance_id="forward-1")

    assert preparation.base_window_fingerprint == initial_fingerprint
    assert preparation.context.market_events["daily-bars"] == (payload.market_event,)
    assert window.window_fingerprint == initial_fingerprint
    assert window.last_event_key is None
    assert window.prepare(payload, instance_id="forward-1") == preparation
    with pytest.raises(ValueError, match="already awaiting settlement"):
        window.prepare(
            _payload(
                event_id="aapl-next",
                sequence=2,
                event_time=NOW + timedelta(minutes=1),
            ),
            instance_id="forward-1",
        )

    committed_fingerprint = window.commit(preparation)

    assert committed_fingerprint == preparation.next_window_fingerprint
    assert window.last_event_key == (NOW, 1)
    assert window.commit(preparation) == committed_fingerprint


def test_staged_context_can_be_discarded_after_failed_native_execution() -> None:
    window = ForwardStrategyContextWindow("forward-1", _manifest(), parameters={}, random_seed=17)
    initial_fingerprint = window.window_fingerprint
    preparation = window.prepare(
        _payload(event_id="aapl-failed", sequence=1, event_time=NOW),
        instance_id="forward-1",
    )

    window.discard(preparation)

    assert window.window_fingerprint == initial_fingerprint
    assert window.last_event_key is None
