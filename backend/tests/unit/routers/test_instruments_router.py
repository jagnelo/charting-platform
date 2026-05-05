import pytest

from app.models.instrument import Instrument
from app.providers.base import InstrumentProfile, ListingRecord
from app.routers.instruments import _create_from_provider
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
