"""Tokenized quote refresh against real PostgreSQL/asyncpg.

Production regression (2026-11-20): a gate_tradfi order-book quote carried
``Decimal`` values into the JSON observation payload.  The flush failed, the
shared session was left in a failed transaction, and every quarter-hour
``scheduled_tokenized_asset_refresh`` tick raised ``PendingRollbackError`` on
the same asset without advancing its cursor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _async_database_url(raw_url: str) -> str:
    return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    )


@pytest_asyncio.fixture
async def tokenized_sessions(request, test_database_url):
    raw_url = test_database_url
    if not raw_url:
        raw_url = request.getfixturevalue("pg_container").get_connection_url()
    schema = f"tokenized_refresh_{uuid4().hex}"
    import app.models  # noqa: F401
    from app.database import Base

    bootstrap_engine = create_async_engine(_async_database_url(raw_url))
    scoped_engine = None
    created = False
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema})
                )
            )
        scoped_engine = create_async_engine(
            _async_database_url(raw_url),
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield async_sessionmaker(scoped_engine, expire_on_commit=False)
    finally:
        if scoped_engine is not None:
            await scoped_engine.dispose()
        if created:
            async with bootstrap_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap_engine.dispose()


async def test_refresh_persists_decimal_quotes_and_survives_one_failing_asset(
    tokenized_sessions, monkeypatch
):
    from app.models.instrument import Instrument
    from app.models.provider_observation import LatestPriceSnapshot
    from app.models.tokenized_asset import TokenizedAssetDetail, TokenizedAssetObservation
    from app.providers.base import TokenizedAssetRecord
    from app.services import tokenized_assets

    async with tokenized_sessions() as session:
        for asset_id in ("pg-bad", "pg-dec"):
            await tokenized_assets.upsert_tokenized_asset(
                session,
                TokenizedAssetRecord(
                    provider="gate_tradfi",
                    asset_id=asset_id,
                    symbol=asset_id,
                    name=asset_id,
                    underlying_symbol="NOTLISTED",
                    raw_payload={"instrument": {"symbol": asset_id}, "quote": {}},
                ),
            )
        await session.commit()

    async def fake_execute(_db, _capability, _operation, **kwargs):
        identifier = kwargs["provider_symbol"]
        orderbook = {"bid": Decimal("38.07"), "ask": Decimal("38.12"), "price": Decimal("38.095")}
        return SimpleNamespace(
            provider_name="gate_tradfi",
            result=TokenizedAssetRecord(
                provider="gate_tradfi",
                asset_id=identifier,
                symbol=identifier,
                name=identifier,
                price=Decimal("38.095"),
                bid=Decimal("38.07"),
                ask=Decimal("38.12"),
                underlying_symbol="NOTLISTED",
                observed_at=datetime.now(UTC),
                raw_payload={"asset": {"symbol": identifier}, "orderbook": orderbook},
            ),
        )

    real_upsert = tokenized_assets.upsert_tokenized_asset

    async def failing_upsert(db, record, **kwargs):
        persisted = await real_upsert(db, record, **kwargs)
        if record.asset_id == "pg-bad":
            # A write PostgreSQL rejects at flush time (NOT NULL type).
            db.add(Instrument(symbol="BROKEN", name="broken", instrument_type_id=None))
            await db.flush()
        return persisted

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    monkeypatch.setattr(tokenized_assets, "upsert_tokenized_asset", failing_upsert)

    async with tokenized_sessions() as session:
        result = await tokenized_assets.refresh_tokenized_prices(session, max_assets=10)

    assert (result["status"], result["requested"]) == ("refreshed", 2)
    assert [quote["provider_asset_id"] for quote in result["quotes"]] == ["pg-dec"]
    assert [failure["provider_asset_id"] for failure in result["failures"]] == ["pg-bad"]

    async with tokenized_sessions() as session:
        details = {
            row.provider_asset_id: row.instrument_id
            for row in (await session.execute(select(TokenizedAssetDetail))).scalars()
        }
        snapshots = {
            row.instrument_id: row
            for row in (await session.execute(select(LatestPriceSnapshot))).scalars()
        }
        assert details["pg-bad"] not in snapshots
        snapshot = snapshots[details["pg-dec"]]
        assert snapshot.price == Decimal("38.095")
        assert snapshot.payload["orderbook"] == {
            "bid": "38.07",
            "ask": "38.12",
            "price": "38.095",
        }
        observation_payloads = (
            (
                await session.execute(
                    select(TokenizedAssetObservation.payload).where(
                        TokenizedAssetObservation.instrument_id == details["pg-dec"]
                    )
                )
            )
            .scalars()
            .all()
        )
        assert snapshot.payload in observation_payloads
        broken = await session.execute(select(Instrument).where(Instrument.symbol == "BROKEN"))
        assert broken.first() is None
