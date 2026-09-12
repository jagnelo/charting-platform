from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.market_data_foundation import MarketEvent
from app.models.provider_observation import LatestPriceSnapshot
from app.models.provider_runtime import ProviderCapability
from app.models.tokenized_asset import TokenizedAssetDetail
from app.providers.base import TokenizedAssetRecord
from app.services import tokenized_assets
from app.services.tokenized_assets import (
    refresh_tokenized_events,
    refresh_tokenized_prices,
    upsert_tokenized_asset,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_upsert_keeps_token_distinct_and_links_unambiguous_underlying(db, instrument):
    instrument.isin = "US0378331005"
    db.flush()
    record = TokenizedAssetRecord(
        provider="xstocks",
        asset_id="x:AAPL",
        symbol="xAAPL",
        name="Apple xStock",
        underlying_symbol=instrument.symbol,
        underlying_isin="US0378331005",
        network="solana",
        chain_id=101,
        contract_address="So111",
        price=Decimal("100.25"),
        multiplier=Decimal("0.98"),
        collateral={"deployments": [{"network": "solana", "address": "So111"}]},
        observed_at=datetime.now(UTC),
        raw_payload={"id": "x:AAPL"},
    )

    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    assert token.id != instrument.id
    assert token.domain_key == "tokenized:xstocks:" + token.domain_key.rsplit(":", 1)[1]

    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()
    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_isin"
    assert detail.multiplier == Decimal("0.98")
    assert detail.deployments[0]["address"] == "So111"

    snapshot = db.execute(
        select(LatestPriceSnapshot).where(LatestPriceSnapshot.instrument_id == token.id)
    ).scalar_one()
    assert snapshot.price == Decimal("100.25")


@pytest.mark.asyncio
async def test_upsert_does_not_guess_ambiguous_underlying(db, instrument_type, instrument):
    duplicate = Instrument(
        symbol="AAPL",
        name="Apple duplicate listing",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(duplicate)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPL",
        name="Apple Stock Token",
        underlying_symbol="AAPL",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()
    assert detail.underlying_instrument_id is None
    assert detail.provenance["underlying_link_status"] == "unresolved_or_ambiguous"


@pytest.mark.asyncio
async def test_upsert_prefers_underlying_isin_over_duplicate_ticker(db, instrument_type, instrument):
    instrument.isin = "US0378331005"
    duplicate = Instrument(
        symbol="AAPL",
        name="Apple duplicate listing",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(duplicate)
    db.flush()

    record = TokenizedAssetRecord(
        provider="dinari",
        asset_id="d-aapl",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_isin="US0378331005",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_isin"


@pytest.mark.asyncio
async def test_upsert_resolves_underlying_isin_from_canonical_identifier(db, instrument, instrument_type):
    identifier = InstrumentIdentifier(
        instrument_id=instrument.id,
        identifier_type=InstrumentIdentifierType.ISIN,
        identifier_value="US0378331005",
        is_active=True,
    )
    db.add(identifier)
    db.flush()

    record = TokenizedAssetRecord(
        provider="dinari",
        asset_id="d-aapl-identifier",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_isin="US0378331005",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_isin"


@pytest.mark.asyncio
async def test_upsert_does_not_fallback_to_ticker_when_underlying_isin_unresolved(db, instrument):
    record = TokenizedAssetRecord(
        provider="dinari",
        asset_id="d-aapl-unresolved",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_isin="US0000000000",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id is None
    assert detail.provenance["underlying_link_status"] == "unresolved_or_ambiguous_isin"


@pytest.mark.asyncio
async def test_refresh_tokenized_prices_routes_by_provider_asset_id_and_persists_quote(
    db, instrument, monkeypatch
):
    initial = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPLx",
        name="Apple Stock Token",
        underlying_symbol=instrument.symbol,
        raw_payload={"id": "rh-aapl"},
    )
    await upsert_tokenized_asset(AsyncSessionAdapter(db), initial)
    calls = []

    async def fake_execute(_db, _capability, operation, **kwargs):
        calls.append((operation, kwargs["provider_name"], kwargs["provider_symbol"], kwargs["usage_identity"]))
        return SimpleNamespace(
            provider_name="robinhood_tokens",
            result=TokenizedAssetRecord(
                provider="robinhood_tokens",
                asset_id="rh-aapl",
                symbol="AAPLx",
                name="Apple Stock Token",
                price=Decimal("123.45"),
                bid=Decimal("123.40"),
                ask=Decimal("123.50"),
                underlying_symbol=instrument.symbol,
                observed_at=datetime.now(UTC),
                raw_payload={"quote": {"bid": "123.40", "ask": "123.50"}},
            ),
        )

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=10)

    assert result["status"] == "refreshed"
    assert result["requested"] == 1
    assert result["refreshed"] == 1
    assert result["failed"] == 0
    assert calls == [("get_tokenized_price", "robinhood_tokens", "rh-aapl", "rh-aapl")]
    token_detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.provider_asset_id == "rh-aapl")
    ).scalar_one()
    snapshot = db.execute(
        select(LatestPriceSnapshot).where(
            LatestPriceSnapshot.instrument_id == token_detail.instrument_id
        )
    ).scalar_one()
    # The token has a distinct instrument ID from the underlying; locate the
    # quote through the token's provider symbol rather than the economic ticker.
    assert snapshot.provider_symbol == "AAPLx"
    assert snapshot.price == Decimal("123.45")


@pytest.mark.asyncio
async def test_refresh_tokenized_prices_keeps_per_asset_failure_evidence(db, instrument, monkeypatch):
    initial = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPLx",
        name="Apple Stock Token",
        raw_payload={},
    )
    await upsert_tokenized_asset(AsyncSessionAdapter(db), initial)

    async def fake_execute(*_args, **_kwargs):
        raise RuntimeError("provider unavailable https://api.example.test/?api_key=super-secret")

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=10)

    assert result["status"] == "failed"
    assert result["requested"] == 1
    assert result["refreshed"] == 0
    assert result["failed"] == 1
    assert result["failures"][0]["provider_asset_id"] == "rh-aapl"
    assert "super-secret" not in result["failures"][0]["error"]
    assert len(result["failures"][0]["error"]) <= 500


@pytest.mark.asyncio
async def test_refresh_tokenized_events_redacts_provider_failure_evidence(db, monkeypatch):
    provider = SimpleNamespace(
        name="xstocks", fetch_tokenized_corporate_actions=lambda **_kwargs: []
    )

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="xstocks", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    async def fake_execute(*_args, **_kwargs):
        raise RuntimeError("provider unavailable Authorization: Bearer event-secret")

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_events(AsyncSessionAdapter(db))

    assert result["status"] == "failed"
    assert result["failed"] == 2  # xStocks history and upcoming phases
    assert result["failures"]
    assert all("event-secret" not in item["error"] for item in result["failures"])
    assert all(len(item["error"]) <= 500 for item in result["failures"])


@pytest.mark.asyncio
async def test_refresh_tokenized_events_persists_and_links_explicit_action_identity(
    db, instrument, monkeypatch
):
    initial = TokenizedAssetRecord(
        provider="xstocks",
        asset_id="x:AAPL",
        symbol="xAAPL",
        name="Apple xStock",
        underlying_symbol=instrument.symbol,
        raw_payload={},
    )
    await upsert_tokenized_asset(AsyncSessionAdapter(db), initial)
    provider = SimpleNamespace(
        name="xstocks", fetch_tokenized_corporate_actions=lambda **_kwargs: []
    )
    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="xstocks", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.TOKENIZED_CORPORATE_ACTIONS
        assert operation == "fetch_tokenized_corporate_actions"
        assert kwargs["provider_name"] == "xstocks"
        return SimpleNamespace(
            provider_name="xstocks",
            result=[
                {
                    "id": "ca-1",
                    "assetId": "x:AAPL",
                    "actionType": "dividend",
                    "effectiveDate": "2026-09-11",
                    "announcedAt": "2026-09-10T10:15:00Z",
                    "amount": "0.25",
                },
                {"id": "malformed-but-valid", "symbol": "unlisted"},
            ],
        )

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_providers=2, page_size=25, include_upcoming=False
    )

    assert result["status"] == "refreshed"
    assert result["events"] == 2
    assert result["linked"] == 1
    assert result["unlinked"] == 1
    assert result["failed"] == 0
    events = db.execute(select(MarketEvent).order_by(MarketEvent.id)).scalars().all()
    assert len(events) == 2
    token_detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.provider_asset_id == "x:AAPL")
    ).scalar_one()
    assert events[0].instrument_id == token_detail.instrument_id
    assert events[0].effective_date.isoformat() == "2026-09-11"
    assert events[0].announced_at.isoformat().startswith("2026-09-10T10:15:00")
    assert events[0].payload["raw"]["actionType"] == "dividend"
    assert events[1].instrument_id is None


@pytest.mark.asyncio
async def test_refresh_tokenized_events_reports_adapters_without_action_surface(db, monkeypatch):
    provider = SimpleNamespace(name="bybit_xstocks")
    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="bybit_xstocks", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    result = await refresh_tokenized_events(AsyncSessionAdapter(db))

    assert result == {
        "status": "no_corporate_action_provider",
        "providers": [],
        "unsupported": ["bybit_xstocks"],
        "events": 0,
        "linked": 0,
        "unlinked": 0,
        "failed": 0,
    }
