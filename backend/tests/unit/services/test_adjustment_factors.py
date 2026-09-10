from datetime import UTC, datetime
from decimal import Decimal

from app.models.instrument_event import EventTimeHint, InstrumentEvent, InstrumentEventType
from app.services.adjustment_factors import build_adjustment_factor_snapshot


def _event(
    event_type: InstrumentEventType,
    event_time: datetime,
    *,
    source_event_key: str,
    split_ratio: Decimal | None = None,
    dividend_amount: Decimal | None = None,
) -> InstrumentEvent:
    return InstrumentEvent(
        instrument_id=1,
        event_type=event_type,
        event_time=event_time,
        time_hint=EventTimeHint.UNKNOWN,
        title="fixture event",
        source="fixture-provider",
        source_event_key=source_event_key,
        fetched_at=event_time,
        split_ratio=split_ratio,
        dividend_amount=dividend_amount,
    )


def test_split_factor_snapshot_is_stable_and_order_independent():
    events = [
        _event(
            InstrumentEventType.SPLIT,
            datetime(2024, 6, 10, tzinfo=UTC),
            source_event_key="split:2024-06-10",
            split_ratio=Decimal("2"),
        ),
        _event(
            InstrumentEventType.SPLIT,
            datetime(2020, 1, 2, tzinfo=UTC),
            source_event_key="split:2020-01-02",
            split_ratio=Decimal("1.5"),
        ),
    ]

    first = build_adjustment_factor_snapshot(events)
    second = build_adjustment_factor_snapshot(reversed(events))

    assert first == second
    assert first.status == "rebuildable_split_factors"
    assert first.event_count == 2
    assert first.version is not None and first.version.startswith("afv1-")


def test_dividend_event_keeps_adjustment_factors_explicitly_opaque():
    snapshot = build_adjustment_factor_snapshot(
        [
            _event(
                InstrumentEventType.DIVIDEND,
                datetime(2024, 6, 10, tzinfo=UTC),
                source_event_key="dividend:2024-06-10",
                dividend_amount=Decimal("0.25"),
            )
        ]
    )

    assert snapshot.version is None
    assert snapshot.status == "provider_native_opaque_incomplete_factor_set"
    assert snapshot.event_count == 1


def test_missing_split_ratio_does_not_create_a_rebuildable_version():
    snapshot = build_adjustment_factor_snapshot(
        [
            _event(
                InstrumentEventType.SPLIT,
                datetime(2024, 6, 10, tzinfo=UTC),
                source_event_key="split:2024-06-10",
            )
        ]
    )

    assert snapshot.version is None
    assert snapshot.status == "provider_native_opaque_incomplete_factor_set"
