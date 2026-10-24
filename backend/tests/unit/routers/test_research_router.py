from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException

from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.routers.research import (
    _dataset_manifest_fields,
    _dataset_options,
    _parse_dataset_bound,
    _research_coverage_calendars,
    _wire_timestamps,
)


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
