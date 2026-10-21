from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.adjustment_factor import AdjustmentFactorObservation
from app.models.data_source import DataSource
from app.models.instrument_event import (
    EventTimeHint,
    InstrumentEvent,
    InstrumentEventType,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.alpaca import _parse_corporate_action_events
from app.providers.base import InstrumentEventRecord
from app.services import instrument_events
from app.services.instrument_events import fetch_and_store_instrument_events
from app.services.provider_runtime import ProviderExecutionResult
from tests.unit.conftest import AsyncSessionAdapter


def _event_record(
    *, adjustment_factor: Decimal | None, raw_payload: str | None
) -> InstrumentEventRecord:
    return InstrumentEventRecord(
        event_type=InstrumentEventType.DIVIDEND,
        event_time=datetime(2025, 2, 3, tzinfo=UTC),
        time_hint=EventTimeHint.UNKNOWN,
        title="Explicit provider factor fixture",
        source_event_key="factor-fixture-1",
        fetched_at=datetime(2025, 2, 4, tzinfo=UTC),
        dividend_amount=Decimal("0.25"),
        adjustment_factor=adjustment_factor,
        raw_payload=raw_payload,
    )


@pytest.mark.parametrize(
    "factor",
    [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")],
)
def test_provider_event_factor_input_rejects_nonpositive_or_nonfinite_values(factor):
    with pytest.raises(ValueError, match="finite positive Decimal"):
        _event_record(adjustment_factor=factor, raw_payload=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("explicit_factor", "raw_payload", "expected_factor", "expected_kind"),
    [
        (
            Decimal("0.9975"),
            '{"adjustment_factor":0.5}',
            Decimal("0.9975"),
            "provider_supplied",
        ),
        (None, '{"adjustment_factor":0.5}', None, None),
    ],
)
async def test_typed_factor_persists_to_event_and_existing_observation(
    db,
    instrument,
    monkeypatch,
    explicit_factor,
    raw_payload,
    expected_factor,
    expected_kind,
):
    async_db = AsyncSessionAdapter(db)
    # Synthetic typed-record persistence coverage, not native provider evidence.
    source = DataSource(name="factor-fixture", is_active=True)
    db.add(source)
    db.flush()
    event_record = _event_record(
        adjustment_factor=explicit_factor,
        raw_payload=raw_payload,
    )

    class _Provider:
        name = "factor-fixture"

        def fetch_instrument_events(self, _symbol):
            return [event_record]

    async def _execute(_db, _capability, _operation, **kwargs):
        result = kwargs["invoke"](_Provider(), instrument.symbol)
        return ProviderExecutionResult(
            provider_name="factor-fixture",
            data_source=source,
            policy=object(),
            health=object(),
            result=result,
        )

    monkeypatch.setattr(instrument_events, "execute_provider_call", _execute)
    await fetch_and_store_instrument_events(async_db, instrument)
    db.expire_all()

    persisted_event = db.query(InstrumentEvent).one()
    observation = db.query(AdjustmentFactorObservation).one()
    assert persisted_event.adjustment_factor == expected_factor
    assert observation.factor == expected_factor
    assert observation.factor_kind == expected_kind
    assert observation.amount == Decimal("0.25")


@pytest.mark.asyncio
async def test_alpaca_explicit_factor_flows_from_parser_to_persisted_observation(
    db, instrument, monkeypatch
):
    source = DataSource(name="alpaca", is_active=True)
    db.add(source)
    db.flush()
    parsed = _parse_corporate_action_events(
        {
            "cash_dividends": [
                {
                    "id": "parsed-dividend",
                    "ex_date": "2025-02-03",
                    "payable_date": "2025-02-10",
                    "rate": "0.25",
                    "adjustment_factor": "0.9975",
                }
            ]
        },
        instrument.symbol,
        datetime(2025, 2, 11, tzinfo=UTC),
    )

    class _AlpacaPageProvider:
        name = "alpaca"

        def fetch_instrument_events(self, _symbol):
            return parsed

    async def _execute(_db, _capability, _operation, **kwargs):
        return ProviderExecutionResult(
            provider_name="alpaca",
            data_source=source,
            policy=object(),
            health=object(),
            result=kwargs["invoke"](_AlpacaPageProvider(), instrument.symbol),
        )

    monkeypatch.setattr(instrument_events, "execute_provider_call", _execute)
    await fetch_and_store_instrument_events(AsyncSessionAdapter(db), instrument)
    db.expire_all()

    assert db.query(InstrumentEvent).count() == 2
    assert db.query(InstrumentEvent).filter_by(adjustment_factor=Decimal("0.9975")).count() == 2
    assert (
        db.query(AdjustmentFactorObservation)
        .filter_by(factor=Decimal("0.9975"), factor_kind="provider_supplied")
        .count()
        == 1
    )


@pytest.mark.asyncio
async def test_alpaca_dividend_amount_without_explicit_factor_persists_unknown(
    db, instrument, monkeypatch
):
    source = DataSource(name="alpaca", is_active=True)
    db.add(source)
    db.flush()
    parsed = _parse_corporate_action_events(
        {"cash_dividends": [{"id": "no-factor", "ex_date": "2025-02-03", "rate": "0.25"}]},
        instrument.symbol,
        datetime(2025, 2, 11, tzinfo=UTC),
    )

    class _AlpacaPageProvider:
        name = "alpaca"

        def fetch_instrument_events(self, _symbol):
            return parsed

    async def _execute(_db, _capability, _operation, **kwargs):
        return ProviderExecutionResult(
            provider_name="alpaca",
            data_source=source,
            policy=object(),
            health=object(),
            result=kwargs["invoke"](_AlpacaPageProvider(), instrument.symbol),
        )

    monkeypatch.setattr(instrument_events, "execute_provider_call", _execute)
    await fetch_and_store_instrument_events(AsyncSessionAdapter(db), instrument)
    db.expire_all()

    assert db.query(InstrumentEvent).count() == 1
    event = db.query(InstrumentEvent).one()
    assert event.dividend_amount == Decimal("0.25")
    assert event.adjustment_factor is None
    assert db.query(AdjustmentFactorObservation).count() == 0


def test_ohlcv_lineage_fields_keep_both_populated_and_unknown_values(db, instrument):
    source = DataSource(name="lineage-fixture", is_active=True)
    db.add(source)
    db.flush()
    populated = OHLCVBar(
        instrument_id=instrument.id,
        data_source_id=source.id,
        timeframe=Timeframe.D1,
        ts=datetime(2025, 2, 3, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        is_adjusted=True,
        adjustment_basis="split_adjusted",
        adjustment_version="fixture-v1",
        is_derived=True,
        source_timeframe="D1",
        derivation_method="provider_adjustment_factor",
        derived_at=datetime(2025, 2, 4, tzinfo=UTC),
        source_bar_count=2,
        source_start=datetime(2025, 2, 1, tzinfo=UTC),
        source_end=datetime(2025, 2, 2, tzinfo=UTC),
    )
    unknown = OHLCVBar(
        instrument_id=instrument.id,
        data_source_id=source.id,
        timeframe=Timeframe.D1,
        ts=datetime(2025, 2, 3, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        is_adjusted=False,
        adjustment_basis="raw",
        adjustment_version="provider-native",
        provenance={"observed_at": "2025-02-04T00:00:00Z"},
    )

    db.add_all([populated, unknown])
    db.commit()
    db.expire_all()
    populated = db.query(OHLCVBar).filter(OHLCVBar.is_derived.is_(True)).one()
    unknown = db.query(OHLCVBar).filter(OHLCVBar.is_adjusted.is_(False)).one()

    assert populated.is_derived is True
    assert populated.derivation_method == "provider_adjustment_factor"
    assert populated.source_bar_count == 2
    assert populated.source_start.replace(tzinfo=UTC) == datetime(2025, 2, 1, tzinfo=UTC)
    assert populated.source_end.replace(tzinfo=UTC) == datetime(2025, 2, 2, tzinfo=UTC)
    assert unknown.is_derived is False
    assert unknown.source_timeframe is None
    assert unknown.derivation_method is None
    assert unknown.derived_at is None
    assert unknown.source_bar_count is None
    assert unknown.source_start is None
    assert unknown.source_end is None
