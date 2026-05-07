from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.instrument import Instrument
from app.models.instrument_stats import InstrumentStats
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import InstrumentProfile, ListingRecord
from app.routers.instruments import (
    _create_from_provider,
    _ensure_52w_stats,
    _needs_52w_stats_refresh,
)
from tests.unit.conftest import AsyncSessionAdapter


class TestInstrumentAutoCreate:
    @pytest.mark.asyncio
    async def test_rejects_non_exact_provider_match(self, db, monkeypatch):
        async_db = AsyncSessionAdapter(db)

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "CSCOII-USD",
                    "name": "Fake Coin",
                    "exchange": "CoinGecko",
                    "type": "CRYPTOCURRENCY",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="coingecko",
                symbol="CSCOII-USD",
                canonical_symbol="CSCOII-USD",
                name="Fake Coin",
                quote_type="CRYPTOCURRENCY",
                listings=[ListingRecord(provider_symbol="CSCOII-USD", is_primary=True)],
            )

        async def _ingest(*_args, **_kwargs):
            raise AssertionError(
                "ingest_provider_profile should not be called for non-exact matches"
            )

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _ingest)

        created = await _create_from_provider("CSCOII", async_db)

        assert created is None
        assert db.query(Instrument).filter(Instrument.symbol == "CSCOII").one_or_none() is None

    @pytest.mark.asyncio
    async def test_creates_from_exact_provider_match(self, db, instrument_type, monkeypatch):
        async_db = AsyncSessionAdapter(db)
        seen_provider_name = None

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "CSCO",
                    "name": "Cisco Systems",
                    "exchange": "NMS",
                    "type": "EQUITY",
                    "provider": "yfinance",
                }
            ]

        async def _profile(*_args, provider_name=None, **_kwargs):
            nonlocal seen_provider_name
            seen_provider_name = provider_name
            return InstrumentProfile(
                provider="yfinance",
                symbol="CSCO",
                canonical_symbol="CSCO",
                name="Cisco Systems",
                currency="USD",
                quote_type="EQUITY",
                exchange="NMS",
                listings=[
                    ListingRecord(provider_symbol="CSCO", exchange_code="NMS", is_primary=True)
                ],
            )

        async def _ingest(db_session, profile, **_kwargs):
            instrument = Instrument(
                symbol=profile.canonical_symbol,
                name=profile.name,
                currency=profile.currency,
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            db_session.add(instrument)
            await db_session.flush()
            return instrument

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _ingest)

        created = await _create_from_provider("CSCO", async_db)

        assert created is not None
        assert created.symbol == "CSCO"
        assert seen_provider_name == "yfinance"


class TestInstrument52WStats:
    @pytest.mark.asyncio
    async def test_refreshes_provider_sourced_52w_provenance_from_ohlcv(self, db, instrument):
        async_db = AsyncSessionAdapter(db)
        stats = InstrumentStats(
            instrument_id=instrument.id,
            week52_high=Decimal("222.00"),
            week52_low=Decimal("111.00"),
            field_provenance={
                "week52_high": {"source": "yfinance", "observed_at": datetime.now(UTC).isoformat()},
                "week52_low": {"source": "yfinance", "observed_at": datetime.now(UTC).isoformat()},
            },
        )
        db.add(stats)
        instrument.stats = stats

        base = datetime.now(UTC) - timedelta(days=90)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base,
                    open=Decimal("150"),
                    high=Decimal("200"),
                    low=Decimal("145"),
                    close=Decimal("190"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=30),
                    open=Decimal("140"),
                    high=Decimal("142"),
                    low=Decimal("120"),
                    close=Decimal("130"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
            ]
        )
        db.flush()

        assert _needs_52w_stats_refresh(instrument) is True

        refreshed = await _ensure_52w_stats(instrument, async_db)

        assert float(refreshed.stats.week52_high) == 200.0
        assert float(refreshed.stats.week52_low) == 120.0
        assert refreshed.stats.field_provenance["week52_high"]["source"] == "internal_ohlcv_52w"
        assert (
            refreshed.stats.field_provenance["week52_high"]["observed_at"]
            == base.date().isoformat()
        )
        assert (
            refreshed.stats.field_provenance["week52_low"]["observed_at"]
            == (base + timedelta(days=30)).date().isoformat()
        )

    def test_skips_52w_refresh_when_internal_provenance_already_has_occurrence_dates(
        self, instrument
    ):
        instrument.stats = InstrumentStats(
            instrument_id=instrument.id,
            week52_high=Decimal("222.00"),
            week52_low=Decimal("111.00"),
            field_provenance={
                "week52_high": {
                    "source": "internal_ohlcv_52w",
                    "observed_at": "2025-02-01T00:00:00+00:00",
                },
                "week52_low": {
                    "source": "internal_ohlcv_52w",
                    "observed_at": "2025-01-10T00:00:00+00:00",
                },
            },
        )

        assert _needs_52w_stats_refresh(instrument) is False
