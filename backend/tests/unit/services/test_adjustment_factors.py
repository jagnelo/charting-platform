from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.adjustment_factor import AdjustmentFactorObservation
from app.models.data_source import DataSource
from app.models.instrument_event import EventTimeHint, InstrumentEvent, InstrumentEventType
from app.services.adjustment_factors import (
    build_adjustment_factor_snapshot,
    persist_adjustment_factor_observations,
)
from tests.unit.conftest import AsyncSessionAdapter


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


@pytest.mark.asyncio
async def test_persist_normalizes_factor_events_and_reuses_the_natural_key(db, instrument):
    source = DataSource(name="factor-observation-provider")
    db.add(source)
    db.flush()
    event_time = datetime(2024, 6, 10, tzinfo=UTC)
    event = _event(
        InstrumentEventType.SPLIT,
        event_time,
        source_event_key="split:2024-06-10",
        split_ratio=Decimal("2"),
    )
    event.instrument_id = instrument.id
    event.source = source.name

    session = AsyncSessionAdapter(db)
    assert (
        await persist_adjustment_factor_observations(
            session,
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="TEST",
            events=[event],
        )
        == 1
    )
    event.raw_payload = '{"ratio": 2}'
    assert (
        await persist_adjustment_factor_observations(
            session,
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="TEST",
            events=[event],
        )
        == 1
    )

    rows = db.query(AdjustmentFactorObservation).all()
    assert len(rows) == 1
    assert rows[0].factor_type == "split"
    assert rows[0].factor == Decimal("2.000000000000")
    assert rows[0].factor_version.startswith("afv1-")
    assert rows[0].raw_payload == '{"ratio": 2}'
