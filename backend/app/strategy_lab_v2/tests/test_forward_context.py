from __future__ import annotations

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
from app.strategy_lab_v2.forward_context import ForwardStrategyContextWindow
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import VerifiedForwardMarketPayload
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
