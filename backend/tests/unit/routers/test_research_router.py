import asyncio
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.instrument import Instrument
from app.models.market_data_foundation import AdjustmentBasis, MarketSeries, MarketSeriesDefault
from app.models.ohlcv import OHLCVBar, Timeframe
from app.routers.research import (
    _dataset_manifest_fields,
    _dataset_options,
    _instrument_metadata,
    _load_bars_for_ids,
    _load_instrument_bars,
    _materialize_instrument_dataset,
    _parse_dataset_bound,
    _research_coverage_calendars,
    _research_manifest_fingerprint,
    _wire_timestamps,
)


class _AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session
        self.execute_count = 0

    async def execute(self, statement):
        self.execute_count += 1
        return self.session.execute(statement)


def _series(instrument_id: int, *, feed: str, canonical: bool = True) -> MarketSeries:
    return MarketSeries(
        instrument_id=instrument_id,
        feed_scope=feed,
        session_code="regular",
        timeframe="D1",
        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
        adjustment_version="research-series-test",
        is_canonical=canonical,
        is_active=True,
    )


def _bar(
    instrument_id: int,
    ts: datetime,
    *,
    series_id: int | None,
    close: str,
    session: str = "regular",
) -> OHLCVBar:
    return OHLCVBar(
        instrument_id=instrument_id,
        market_series_id=series_id,
        timeframe=Timeframe.D1,
        ts=ts,
        session=session,
        open=Decimal(close),
        high=Decimal(close) + Decimal("1"),
        low=Decimal(close) - Decimal("1"),
        close=Decimal(close),
        volume=Decimal("100"),
        is_adjusted=True,
        adjustment_basis="split_adjusted",
        adjustment_version="research-series-test",
        scope_key=f"series:{series_id}:regular" if series_id is not None else "legacy:regular",
    )


def _daily_options(*, start=None, end=None):
    return {
        "timeframe": Timeframe.D1,
        "is_adjusted": True,
        "session": "regular",
        "start": start,
        "end": end,
        "adjustment": "split_adjusted",
        "benchmark": None,
        "as_of": None,
    }


def test_research_dataset_as_of_clamps_future_bars_and_is_retained_as_metadata():
    options = _dataset_options(
        {"timeframe": "D1", "as_of": "2024-02-01T15:30:00Z"},
        {},
    )

    assert options["as_of"].tzinfo == UTC
    assert options["end"] == options["as_of"]


def test_date_only_research_bounds_cover_the_full_utc_dates_inclusively():
    options = _dataset_options(
        {"timeframe": "D1", "start_date": "2024-11-22", "end_date": "2026-10-22"},
        {},
    )

    assert options["start"] == datetime(2024, 11, 22, tzinfo=UTC)
    assert options["end"] == datetime(2026, 10, 22, 23, 59, 59, 999999, tzinfo=UTC)
    assert options["date_only_bounds"] == {"start": True, "end": True}

    with pytest.raises(HTTPException) as error:
        _parse_dataset_bound("2024-02-30", end=True)
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "invalid_dataset_date"


def test_explicit_research_timestamps_keep_their_instants_and_do_not_become_date_bounds():
    options = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22T05:00:00Z",
            "end_date": "2024-11-22T21:00:00Z",
        },
        {},
    )

    assert options["start"] == datetime(2024, 11, 22, 5, tzinfo=UTC)
    assert options["end"] == datetime(2024, 11, 22, 21, tzinfo=UTC)
    assert options["date_only_bounds"] == {"start": False, "end": False}

    mixed = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22T05:00:00Z",
            "end_date": "2024-11-25",
        },
        {},
    )
    assert mixed["start"] == datetime(2024, 11, 22, 5, tzinfo=UTC)
    assert mixed["end"] == datetime(2024, 11, 25, 23, 59, 59, 999999, tzinfo=UTC)
    assert mixed["date_only_bounds"] == {"start": False, "end": True}
    assert (
        _research_coverage_calendars(
            {"timeframe": mixed["timeframe"], "date_only_bounds": mixed["date_only_bounds"]},
            [],
        )
        is None
    )

    reverse_mixed = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22",
            "end_date": "2024-11-25T21:00:00Z",
        },
        {},
    )
    assert reverse_mixed["start"] == datetime(2024, 11, 22, tzinfo=UTC)
    assert reverse_mixed["end"] == datetime(2024, 11, 25, 21, tzinfo=UTC)
    assert reverse_mixed["date_only_bounds"] == {"start": True, "end": False}
    assert (
        _research_coverage_calendars(
            {
                "timeframe": reverse_mixed["timeframe"],
                "date_only_bounds": reverse_mixed["date_only_bounds"],
            },
            [
                cast(
                    Instrument,
                    SimpleNamespace(id=1, listings=[]),
                )
            ],
        )
        is None
    )

    date_range_with_exact_as_of = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22",
            "end_date": "2024-11-25",
            "as_of": "2024-11-25T15:00:00Z",
        },
        {},
    )
    assert date_range_with_exact_as_of["end"] == datetime(2024, 11, 25, 15, tzinfo=UTC)
    assert date_range_with_exact_as_of["date_only_bounds"] == {"start": True, "end": False}


def test_date_granular_daily_coverage_uses_only_the_exact_supported_instrument_venue():
    options = {
        "timeframe": Timeframe.D1,
        "date_only_bounds": {"start": True, "end": True},
    }

    def instrument_with_listings(instrument_id: int, *listings: SimpleNamespace) -> Instrument:
        return cast(Instrument, SimpleNamespace(id=instrument_id, listings=list(listings)))

    def primary_listing(mic: str, *, active: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            is_primary=True,
            is_active=active,
            exchange=SimpleNamespace(mic=mic),
        )

    xnys_equity = instrument_with_listings(1, primary_listing("XNYS"))
    canonical_xnys_without_equity_detail_mic = cast(
        Instrument,
        SimpleNamespace(
            id=8,
            listings=[primary_listing("XNYS")],
            equity_detail=SimpleNamespace(exchange_mic=None),
        ),
    )
    other_us_equity = instrument_with_listings(2, primary_listing("ARCX"))
    unknown_venue = instrument_with_listings(3, primary_listing("UNLISTED"))
    no_primary_listing = instrument_with_listings(
        4,
        SimpleNamespace(
            is_primary=False,
            is_active=True,
            exchange=SimpleNamespace(mic="XNYS"),
        ),
    )
    ambiguous_primary_listings = instrument_with_listings(
        5, primary_listing("XNYS"), primary_listing("XNYS")
    )
    inactive_xnys = instrument_with_listings(6, primary_listing("XNYS", active=False))
    detail_only_xnys = cast(
        Instrument,
        SimpleNamespace(
            id=7,
            listings=[],
            equity_detail=SimpleNamespace(exchange_mic="XNYS"),
        ),
    )

    assert _research_coverage_calendars(options, [xnys_equity]) == {1: "XNYS"}
    assert _research_coverage_calendars(options, [canonical_xnys_without_equity_detail_mic]) == {
        8: "XNYS"
    }
    assert _research_coverage_calendars(options, [other_us_equity]) == {2: None}
    assert _research_coverage_calendars(options, [unknown_venue]) == {3: None}
    assert _research_coverage_calendars(options, [no_primary_listing]) == {4: None}
    assert _research_coverage_calendars(options, [ambiguous_primary_listings]) == {5: None}
    assert _research_coverage_calendars(options, [inactive_xnys]) == {6: None}
    assert _research_coverage_calendars(options, [detail_only_xnys]) == {7: None}
    assert (
        _research_coverage_calendars({**options, "timeframe": Timeframe.H1}, [xnys_equity]) is None
    )
    assert (
        _research_coverage_calendars(
            {**options, "date_only_bounds": {"start": True, "end": False}}, [xnys_equity]
        )
        is None
    )
    assert (
        _research_coverage_calendars(
            {**options, "date_only_bounds": {"start": False, "end": True}}, [xnys_equity]
        )
        is None
    )


@pytest.mark.parametrize(
    ("provider_exchange", "expected_calendar"),
    [("XNYS", "XNYS"), ("UNVERIFIED-VENUE", None)],
)
@pytest.mark.asyncio
async def test_massive_listing_venue_flows_through_reconciliation_to_research_calendar(
    db, instrument, provider_exchange: str, expected_calendar: str | None
):
    """Only persisted canonical listing evidence can enable Research's date calendar."""
    from sqlalchemy.orm import selectinload

    from app.models.data_source import DataSource
    from app.models.instrument_identity import InstrumentProviderSymbol
    from app.models.listing import InstrumentListing
    from app.models.market_data_foundation import MarketUniverseReconciliationRun
    from app.providers.massive import MassiveProvider
    from app.services.instrument_mastering import register_provider_symbol
    from app.services.market_universe import _reconcile_rows
    from tests.unit.conftest import AsyncSessionAdapter

    db_session = AsyncSessionAdapter(db)
    instrument.symbol = "SPY"
    instrument.name = "SPDR S&P 500 ETF Trust"
    source = DataSource(name="massive", base_url="https://massive.example.test")
    db.add(source)
    db.flush()

    # Model the already-persisted provider identity and a locally supplied
    # discovery row; no provider transport or quota admission is involved.
    await register_provider_symbol(
        db_session,
        instrument,
        "massive",
        "SPY",
        provider_exchange_code=provider_exchange,
        provider_instrument_type="ETF",
        is_primary=True,
    )
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 10, 23, tzinfo=UTC),
    )
    db.add(run)
    db.flush()

    parsed = MassiveProvider._result(
        {"ticker": "SPY", "name": instrument.name, "primary_exchange": provider_exchange}
    )
    assert parsed is not None
    await _reconcile_rows(
        db_session,
        run=run,
        provider_name="massive",
        rows=[
            {
                "symbol": parsed.symbol,
                "name": parsed.name,
                "exchange": parsed.exchange,
                "instrument_type": parsed.instrument_type,
                "raw_payload": parsed.raw_payload,
            }
        ],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )
    db.flush()

    persisted = (
        db.query(Instrument)
        .options(selectinload(Instrument.listings).selectinload(InstrumentListing.exchange))
        .filter(Instrument.id == instrument.id)
        .one()
    )
    calendars = _research_coverage_calendars(
        {"timeframe": Timeframe.D1, "date_only_bounds": {"start": True, "end": True}},
        [persisted],
    )
    assert calendars == {instrument.id: expected_calendar}
    provider_binding = (
        db.query(InstrumentProviderSymbol)
        .filter(InstrumentProviderSymbol.instrument_id == instrument.id)
        .one()
    )
    assert provider_binding.provider_exchange_code == provider_exchange
    assert len(persisted.listings) == 1
    assert persisted.listings[0].is_primary is True
    if expected_calendar is None:
        assert persisted.listings[0].exchange is None
    else:
        assert persisted.listings[0].exchange.mic == expected_calendar


def test_research_dataset_rejects_as_of_before_requested_start():
    with pytest.raises(HTTPException) as error:
        _dataset_options(
            {"timeframe": "D1", "start_date": "2024-03-01", "as_of": "2024-02-01"},
            {},
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "dataset_as_of_before_start"


def test_research_dataset_payload_timestamps_use_canonical_utc_z():
    offset = datetime(2024, 2, 1, 15, 30, tzinfo=timezone(timedelta(hours=2)))

    assert _wire_timestamps([offset, datetime(2024, 2, 1, 14, 30)]) == [
        "2024-02-01T13:30:00Z",
        "2024-02-01T14:30:00Z",
    ]
    fields = _dataset_manifest_fields(
        {"name": "canonical"},
        {
            "timeframe": Timeframe.D1,
            "adjustment": "split_adjusted",
            "session": "regular",
            "start": None,
            "end": None,
            "as_of": offset,
            "benchmark": None,
        },
    )
    assert fields["as_of"] == "2024-02-01T13:30:00Z"


def test_research_single_read_uses_mapped_series_before_limit_and_keeps_rows_immutable(
    db, instrument
):
    selected = _series(instrument.id, feed="research-selected")
    alternate = _series(instrument.id, feed="research-alternate")
    db.add_all([selected, alternate])
    db.flush()
    mapping = MarketSeriesDefault(
        instrument_id=instrument.id,
        timeframe="D1",
        is_adjusted=True,
        market_series_id=selected.id,
        selection_reason="research-series-regression",
    )
    db.add(mapping)
    selected_dates = [datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 4, tzinfo=UTC)]
    alternate_date = datetime(2026, 1, 5, tzinfo=UTC)
    db.add_all(
        [
            _bar(instrument.id, selected_dates[0], series_id=selected.id, close="10"),
            _bar(
                instrument.id,
                datetime(2026, 1, 3, tzinfo=UTC),
                series_id=selected.id,
                close="11",
                session="extended",
            ),
            _bar(instrument.id, selected_dates[1], series_id=selected.id, close="12"),
            _bar(instrument.id, alternate_date, series_id=alternate.id, close="99"),
        ]
    )
    db.flush()
    original_mapping_id = mapping.id
    original_bar_ids = set(db.scalars(select(OHLCVBar.id)).all())

    adapter = _AsyncSessionAdapter(db)
    bars = asyncio.run(
        _load_instrument_bars(
            adapter,
            instrument,
            _daily_options(start=selected_dates[0], end=alternate_date),
            limit=2,
        )
    )

    assert adapter.execute_count == 1
    assert [bar.market_series_id for bar in bars] == [selected.id, selected.id]
    assert [bar.ts.date() for bar in bars] == [value.date() for value in selected_dates]
    assert [bar.close for bar in bars] == [Decimal("10"), Decimal("12")]
    assert db.get(MarketSeriesDefault, original_mapping_id).market_series_id == selected.id
    assert set(db.scalars(select(OHLCVBar.id)).all()) == original_bar_ids
    dataset = asyncio.run(
        _materialize_instrument_dataset(
            adapter,
            instrument,
            {},
            _daily_options(start=selected_dates[0], end=alternate_date),
            history_limit=2,
        )
    )
    expected_selected_dataset = {
        "source": "canonical_database",
        "timeframe": "D1",
        "adjustment": "split_adjusted",
        "session": "regular",
        "start_date": "2026-01-02",
        "end_date": "2026-01-05",
        "symbol": instrument.symbol,
        "instrument_id": instrument.id,
        "metadata": _instrument_metadata(instrument),
        "timestamps": _wire_timestamps(selected_dates),
        "opens": [10.0, 12.0],
        "highs": [11.0, 13.0],
        "lows": [9.0, 11.0],
        "closes": [10.0, 12.0],
        "volumes": [100.0, 100.0],
        "vwaps": [None, None],
        "sessions": ["regular", "regular"],
    }
    assert dataset == expected_selected_dataset
    assert _research_manifest_fingerprint(dataset) == _research_manifest_fingerprint(
        expected_selected_dataset
    )


def test_research_batched_reads_apply_each_instruments_default_in_one_query(
    db, instrument, instrument_b
):
    selected_a = _series(instrument.id, feed="research-a-selected")
    alternate_a = _series(instrument.id, feed="research-a-alternate")
    selected_b = _series(instrument_b.id, feed="research-b-selected")
    alternate_b = _series(instrument_b.id, feed="research-b-alternate")
    db.add_all([selected_a, alternate_a, selected_b, alternate_b])
    db.flush()
    db.add_all(
        [
            MarketSeriesDefault(
                instrument_id=instrument.id,
                timeframe="D1",
                is_adjusted=True,
                market_series_id=selected_a.id,
                selection_reason="research-series-regression",
            ),
            MarketSeriesDefault(
                instrument_id=instrument_b.id,
                timeframe="D1",
                is_adjusted=True,
                market_series_id=selected_b.id,
                selection_reason="research-series-regression",
            ),
            _bar(
                instrument.id,
                datetime(2026, 1, 2, tzinfo=UTC),
                series_id=selected_a.id,
                close="10",
            ),
            _bar(
                instrument.id,
                datetime(2026, 1, 6, tzinfo=UTC),
                series_id=alternate_a.id,
                close="99",
            ),
            _bar(
                instrument_b.id,
                datetime(2026, 1, 3, tzinfo=UTC),
                series_id=selected_b.id,
                close="20",
            ),
            _bar(
                instrument_b.id,
                datetime(2026, 1, 7, tzinfo=UTC),
                series_id=alternate_b.id,
                close="199",
            ),
        ]
    )
    db.flush()

    adapter = _AsyncSessionAdapter(db)
    bars_by_id = asyncio.run(
        _load_bars_for_ids(
            adapter,
            [instrument.id, instrument_b.id],
            _daily_options(),
            limit=1,
        )
    )

    assert adapter.execute_count == 1
    assert {key: [bar.market_series_id for bar in rows] for key, rows in bars_by_id.items()} == {
        instrument.id: [selected_a.id],
        instrument_b.id: [selected_b.id],
    }
    assert {key: [bar.close for bar in rows] for key, rows in bars_by_id.items()} == {
        instrument.id: [Decimal("10")],
        instrument_b.id: [Decimal("20")],
    }


def test_research_reads_keep_canonical_fallback_and_legacy_fail_closed_behavior(
    db, instrument, instrument_b, instrument_type
):
    no_default_mapping = _series(instrument.id, feed="unavailable-mapped", canonical=False)
    canonical = _series(instrument.id, feed="canonical-fallback", canonical=True)
    canonical_only_instrument = Instrument(
        symbol="CANONICAL-RESEARCH",
        name="Canonical research fixture",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    canonical_no_bars = _series(instrument_b.id, feed="canonical-empty", canonical=True)
    alternate = _series(instrument_b.id, feed="noncanonical-only", canonical=False)
    legacy_only = Instrument(
        symbol="LEGACY-RESEARCH",
        name="Legacy research fixture",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add_all(
        [
            no_default_mapping,
            canonical,
            canonical_no_bars,
            alternate,
            canonical_only_instrument,
            legacy_only,
        ]
    )
    db.flush()
    canonical_without_mapping = _series(
        canonical_only_instrument.id, feed="canonical-without-mapping", canonical=True
    )
    db.add(canonical_without_mapping)
    db.flush()
    # A selected target with no bars falls back to a populated canonical series.
    db.add(
        MarketSeriesDefault(
            instrument_id=instrument.id,
            timeframe="D1",
            is_adjusted=True,
            market_series_id=no_default_mapping.id,
            selection_reason="research-series-regression",
        )
    )
    # No selected/canonical series exists for instrument_b; alternate scoped bars
    # must not be guessed as default, while old nullable-series rows remain readable.
    db.add_all(
        [
            _bar(
                instrument.id,
                datetime(2026, 1, 2, tzinfo=UTC),
                series_id=canonical.id,
                close="10",
            ),
            _bar(
                instrument_b.id,
                datetime(2026, 1, 3, tzinfo=UTC),
                series_id=alternate.id,
                close="99",
            ),
            _bar(
                instrument_b.id,
                datetime(2026, 1, 2, tzinfo=UTC),
                series_id=None,
                close="20",
            ),
            _bar(
                canonical_only_instrument.id,
                datetime(2026, 1, 2, tzinfo=UTC),
                series_id=canonical_without_mapping.id,
                close="25",
            ),
            _bar(
                legacy_only.id,
                datetime(2026, 1, 2, tzinfo=UTC),
                series_id=None,
                close="30",
            ),
        ]
    )
    db.flush()

    adapter = _AsyncSessionAdapter(db)
    bars_by_id = asyncio.run(
        _load_bars_for_ids(
            adapter,
            [instrument.id, instrument_b.id, canonical_only_instrument.id, legacy_only.id],
            _daily_options(),
            limit=5,
        )
    )

    assert adapter.execute_count == 1
    assert {key: [bar.close for bar in rows] for key, rows in bars_by_id.items()} == {
        instrument.id: [Decimal("10")],
        instrument_b.id: [Decimal("20")],
        canonical_only_instrument.id: [Decimal("25")],
        legacy_only.id: [Decimal("30")],
    }
