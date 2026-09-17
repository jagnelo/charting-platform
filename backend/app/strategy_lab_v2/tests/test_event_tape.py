from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    DataSeriesManifest,
    DataSnapshot,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.event_tape import (
    EVENT_TAPE_DEFINITION_VERSION,
    EventTapeBatch,
    EventTapeBinding,
    FrozenEventTape,
    bind_event_tape,
)
from app.strategy_lab_v2.replay import (
    ReplayStatus,
    build_event_tape_contexts,
    replay_event_tape,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    StrategyDataDependency,
    StrategySdkManifest,
    TargetPositionIntent,
)
from strategy_runtime import InvocationStatus

SNAPSHOT = content_digest("snapshot")
BASE = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)


def _event(
    event_id: str,
    dependency_id: str,
    sequence: int,
    *,
    offset: int = 0,
    instrument_id: str | None = None,
) -> MarketEvent:
    return MarketEvent(
        dependency_id=dependency_id,
        event_id=event_id,
        instrument_id=instrument_id or dependency_id,
        event_time=BASE + timedelta(minutes=offset),
        sequence=sequence,
        values={"close": sequence + 1},
    )


def test_tape_canonicalizes_input_order_and_groups_same_time_batches() -> None:
    late = _event("b-1", "beta", 1, offset=1)
    first = _event("a-0", "alpha", 0)
    same_time = _event("b-0", "beta", 0)
    tape = FrozenEventTape(SNAPSHOT, (late, first, same_time))

    assert tape.events == (first, same_time, late)
    assert tape.event_count == 3
    assert tape.start_time == BASE
    assert tape.end_time == BASE + timedelta(minutes=1)
    assert [batch.batch_sequence for batch in tape.batches()] == [0, 1]
    assert [len(batch.events) for batch in tape.batches()] == [2, 1]
    assert tape.batches()[0] == EventTapeBatch(0, BASE, (first, same_time))


def test_tape_fingerprint_is_stable_for_permuted_input() -> None:
    events = (
        _event("a-0", "alpha", 0),
        _event("a-1", "alpha", 1, offset=1),
        _event("b-0", "beta", 0),
    )
    assert FrozenEventTape(SNAPSHOT, events).fingerprint == FrozenEventTape(
        SNAPSHOT, tuple(reversed(events))
    ).fingerprint
    assert FrozenEventTape(SNAPSHOT, events).definition_version == EVENT_TAPE_DEFINITION_VERSION


def test_duplicate_ids_and_dependency_instrument_switch_fail_closed() -> None:
    with pytest.raises(ValueError, match="event ids must be unique"):
        FrozenEventTape(SNAPSHOT, (_event("same", "alpha", 0), _event("same", "beta", 0)))

    with pytest.raises(ValueError, match="multiple instruments"):
        FrozenEventTape(
            SNAPSHOT,
            (
                _event("a-0", "alpha", 0),
                _event("a-1", "alpha", 1, offset=1, instrument_id="US.MSFT"),
            ),
        )


def test_each_dependency_must_advance_sequence_and_time() -> None:
    with pytest.raises(ValueError, match="advance sequence and time"):
        FrozenEventTape(
            SNAPSHOT,
            (
                _event("a-0", "alpha", 0, offset=1),
                _event("a-1", "alpha", 1),
            ),
        )
    with pytest.raises(ValueError, match="advance sequence and time"):
        FrozenEventTape(
            SNAPSHOT,
            (
                _event("a-0", "alpha", 0),
                _event("a-dup", "alpha", 0, offset=1),
            ),
        )


def test_slice_and_boundary_iteration_are_explicit_and_non_interpolating() -> None:
    events = tuple(_event(f"a-{index}", "alpha", index, offset=index) for index in range(3))
    tape = FrozenEventTape(SNAPSHOT, events)

    assert tuple(tape.iter_events_until(BASE + timedelta(minutes=1))) == events[:2]
    assert tuple(
        tape.iter_events_until(BASE + timedelta(minutes=1), include_boundary=False)
    ) == events[:1]
    assert tape.slice(BASE, BASE + timedelta(minutes=2), include_start=False, include_end=False) == (
        events[1],
    )
    assert tape.slice(BASE + timedelta(minutes=1), BASE + timedelta(minutes=1)) == (events[1],)
    assert tape.slice() == events


def test_empty_tape_is_a_valid_explicit_snapshot_bound_input() -> None:
    tape = FrozenEventTape(SNAPSHOT)
    assert tape.event_count == 0
    assert tape.start_time is None
    assert tape.end_time is None
    assert tape.batches() == ()
    assert tuple(tape.iter_events_until(BASE)) == ()


def test_invalid_time_range_and_definition_are_rejected() -> None:
    tape = FrozenEventTape(SNAPSHOT, (_event("a-0", "alpha", 0),))
    with pytest.raises(ValueError, match="start must not follow end"):
        tape.slice(BASE + timedelta(days=1), BASE)
    with pytest.raises(ValueError, match="definition version"):
        FrozenEventTape(SNAPSHOT, definition_version="event-tape.other.v1")


def _binding_inputs() -> tuple[FrozenEventTape, DataSnapshot, StrategySdkManifest]:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=BASE - timedelta(days=1),
        end=BASE + timedelta(days=4),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
        corporate_action_semantics="split-adjusted-v1",
    )
    cell = CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=BASE - timedelta(days=10),
        history_end=BASE + timedelta(days=10),
        evidence_digest=content_digest("capability"),
    )
    report = preflight_capabilities((requirement,), (cell,))
    series = DataSeriesManifest(
        instrument_id="US.AAPL",
        event_type="ohlcv",
        event_granularity=EventGranularity.BAR,
        timeframe="1d",
        session="regular",
        feed="consolidated",
        start=BASE - timedelta(days=1),
        end=BASE + timedelta(days=4),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        corporate_action_semantics="split-adjusted-v1",
        coverage_evidence_digest=content_digest("coverage"),
        content_digest=content_digest("series"),
        row_count=5,
    )
    snapshot = DataSnapshot("snapshot-1", "provider-snapshot-1", report, (series,), BASE)
    manifest = StrategySdkManifest(
        StrategyVersion("strategy-1", "v1", "2.0", content_digest("source")),
        (StrategyDataDependency("daily-bars", requirement, ("close",)),),
    )
    tape = FrozenEventTape(
        snapshot.fingerprint,
        (
            MarketEvent("daily-bars", "bar-1", "US.AAPL", BASE, 0, {"close": 100}),
            MarketEvent(
                "daily-bars",
                "bar-2",
                "US.AAPL",
                BASE + timedelta(days=1),
                1,
                {"close": 101},
            ),
        ),
    )
    return tape, snapshot, manifest


def test_binding_verifies_snapshot_manifest_fields_and_coverage() -> None:
    tape, snapshot, manifest = _binding_inputs()
    binding = bind_event_tape(tape, snapshot, manifest)

    assert isinstance(binding, EventTapeBinding)
    assert binding.event_tape_fingerprint == tape.fingerprint
    assert binding.snapshot_fingerprint == snapshot.fingerprint
    assert binding.manifest_fingerprint == manifest.fingerprint
    assert binding.dependency_event_counts == (("daily-bars", 2),)
    assert binding.fingerprint.startswith("sha256:")


def test_binding_rejects_snapshot_drift_and_dependency_or_field_mismatch() -> None:
    tape, snapshot, manifest = _binding_inputs()
    with pytest.raises(ValueError, match="does not belong"):
        bind_event_tape(FrozenEventTape(content_digest("other"), tape.events), snapshot, manifest)

    with pytest.raises(ValueError, match="dependency mismatch"):
        bind_event_tape(
            FrozenEventTape(
                snapshot.fingerprint,
                tuple(
                    MarketEvent("other", event.event_id, event.instrument_id, event.event_time, event.sequence, event.values)
                    for event in tape.events
                ),
            ),
            snapshot,
            manifest,
        )

    bad_fields = FrozenEventTape(
        snapshot.fingerprint,
        (
            MarketEvent("daily-bars", "bar-1", "US.AAPL", BASE, 0, {"open": 100}),
            MarketEvent(
                "daily-bars", "bar-2", "US.AAPL", BASE + timedelta(days=1), 1, {"close": 101}
            ),
        ),
    )
    with pytest.raises(ValueError, match="fields do not match"):
        bind_event_tape(bad_fields, snapshot, manifest)


def test_binding_rejects_instrument_or_interval_drift() -> None:
    tape, snapshot, manifest = _binding_inputs()
    wrong_instrument = FrozenEventTape(
        snapshot.fingerprint,
        (
            MarketEvent("daily-bars", "bar-1", "US.MSFT", BASE, 0, {"close": 100}),
            MarketEvent(
                "daily-bars", "bar-2", "US.MSFT", BASE + timedelta(days=1), 1, {"close": 101}
            ),
        ),
    )
    with pytest.raises(ValueError, match="undeclared instrument"):
        bind_event_tape(wrong_instrument, snapshot, manifest)

    outside_requirement = FrozenEventTape(
        snapshot.fingerprint,
        (
            MarketEvent(
                "daily-bars", "bar-1", "US.AAPL", BASE + timedelta(days=4), 0, {"close": 100}
            ),
        ),
    )
    with pytest.raises(ValueError, match="declared interval"):
        bind_event_tape(outside_requirement, snapshot, manifest)


def test_binding_rejects_empty_tape_and_unsupported_or_missing_snapshot_decision() -> None:
    tape, snapshot, manifest = _binding_inputs()
    with pytest.raises(ValueError, match="empty event set"):
        bind_event_tape(FrozenEventTape(snapshot.fingerprint), snapshot, manifest)

    valid_snapshot = DataSnapshot(
        snapshot.snapshot_id,
        snapshot.provider_snapshot_id,
        snapshot.preflight_report,
        snapshot.series,
        snapshot.created_at,
    )
    # A missing manifest dependency cannot be silently treated as a complete
    # tape even when the snapshot itself is otherwise valid.
    other_requirement = CapabilityRequirement(
        "US.MSFT",
        ProductClass.EQUITY,
        EventGranularity.BAR,
        "ohlcv",
        "1d",
        BASE - timedelta(days=1),
        BASE + timedelta(days=2),
        AdjustmentMode.SPLIT_ADJUSTED,
        "regular",
        "consolidated",
        "bar-close-v1",
        "cash-equity-v1",
        "split-adjusted-v1",
    )
    other_manifest = StrategySdkManifest(
        manifest.strategy,
        (StrategyDataDependency("other", other_requirement, ("close",)),),
    )
    with pytest.raises(ValueError, match="dependency mismatch"):
        bind_event_tape(tape, valid_snapshot, other_manifest)


def test_replay_contexts_group_same_time_events_and_bound_lookback() -> None:
    tape, snapshot, manifest = _binding_inputs()
    manifest = replace(
        manifest,
        data_dependencies=(replace(manifest.data_dependencies[0], lookback_periods=1),),
    )
    same_time = MarketEvent(
        "daily-bars",
        "bar-0b",
        "US.AAPL",
        BASE,
        1,
        {"close": 100.5},
    )
    tape = FrozenEventTape(
        snapshot.fingerprint,
        (tape.events[0], same_time, replace(tape.events[1], sequence=2)),
    )

    contexts = build_event_tape_contexts(
        tape,
        manifest,
        random_seed=19,
        parameters={"threshold": 1},
    )

    assert len(contexts) == 2
    assert contexts[0].event_time == BASE
    assert contexts[0].event_sequence == 1
    assert [event.event_id for event in contexts[0].market_events["daily-bars"]] == [
        "bar-1",
        "bar-0b",
    ]
    assert [event.event_id for event in contexts[1].market_events["daily-bars"]] == [
        "bar-0b",
        "bar-2",
    ]


def test_replay_uses_one_stateful_strategy_and_returns_binding_provenance() -> None:
    source = """
class Strategy:
    def __init__(self):
        self.count = 0

    def on_event(self, context):
        self.count += 1
        return [TargetPositionIntent('US.AAPL', Decimal(self.count) / Decimal(10))]
"""
    tape, snapshot, manifest = _binding_inputs()
    manifest = replace(
        manifest,
        strategy=replace(manifest.strategy, source_digest=content_digest(source)),
    )

    replay = replay_event_tape(
        source,
        tape=tape,
        snapshot=snapshot,
        manifest=manifest,
        random_seed=17,
        parameters={"threshold": Decimal("1.5")},
        entrypoint="strategy.main:Strategy",
    )

    assert replay.status is ReplayStatus.SUCCEEDED
    assert replay.accepted
    assert replay.batch_count == replay.processed_batches == 2
    assert replay.stopped_batch_sequence is None
    assert all(item.status is InvocationStatus.SUCCEEDED for item in replay.invocations)
    first_intent = replay.invocations[0].intents[0]
    second_intent = replay.invocations[1].intents[0]
    assert isinstance(first_intent, TargetPositionIntent)
    assert isinstance(second_intent, TargetPositionIntent)
    assert first_intent.target_fraction == Decimal("0.1")
    assert second_intent.target_fraction == Decimal("0.2")
    assert replay.tape_fingerprint == tape.fingerprint
    assert replay.manifest_fingerprint == manifest.fingerprint
    assert replay.binding_fingerprint.startswith("sha256:")
    assert replay.fingerprint.startswith("sha256:")


def test_replay_stops_at_first_typed_failure_without_exposing_later_contexts() -> None:
    source = """
class Strategy:
    def on_event(self, context):
        if context.event_sequence > 0:
            raise RuntimeError('failure detail must remain private')
        return []
"""
    tape, snapshot, manifest = _binding_inputs()
    manifest = replace(
        manifest,
        strategy=replace(manifest.strategy, source_digest=content_digest(source)),
    )

    replay = replay_event_tape(
        source,
        tape=tape,
        snapshot=snapshot,
        manifest=manifest,
        random_seed=17,
        parameters={},
        entrypoint="strategy.main:Strategy",
    )

    assert replay.status is ReplayStatus.FAILED
    assert not replay.accepted
    assert replay.batch_count == 2
    assert replay.processed_batches == 2
    assert replay.stopped_batch_sequence == 1
    assert replay.invocations[0].status is InvocationStatus.SUCCEEDED
    assert replay.invocations[1].status is InvocationStatus.FAILED
    assert replay.invocations[1].error_digest is not None
    assert "failure detail" not in str(replay.invocations[1].error_digest)


def test_replay_requires_a_non_empty_bound_tape_and_rejects_unknown_positions() -> None:
    _, snapshot, manifest = _binding_inputs()
    with pytest.raises(ValueError, match="empty event set"):
        replay_event_tape(
            "class Strategy:\n    def on_event(self, context):\n        return []\n",
            tape=FrozenEventTape(snapshot.fingerprint),
            snapshot=snapshot,
            manifest=manifest,
            random_seed=1,
            parameters={},
            entrypoint="strategy.main:Strategy",
        )

    tape, _, manifest = _binding_inputs()
    with pytest.raises(ValueError, match="unknown batch sequence"):
        build_event_tape_contexts(
            tape,
            manifest,
            random_seed=1,
            parameters={},
            positions_by_batch={99: {}},
        )
