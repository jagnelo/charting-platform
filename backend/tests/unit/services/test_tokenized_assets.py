from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.instrument import Instrument
from app.models.provider_observation import LatestPriceSnapshot
from app.models.tokenized_asset import TokenizedAssetDetail
from app.providers.base import TokenizedAssetRecord
from app.services.tokenized_assets import upsert_tokenized_asset
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_upsert_keeps_token_distinct_and_links_unambiguous_underlying(db, instrument):
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
