from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.routers import baskets as baskets_router


def test_user_can_create_update_and_delete_manual_basket(
    client,
    auth_headers,
    instrument,
    instrument_b,
):
    created = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Mega-cap pair",
            "description": "Two-stock research basket",
            "weighting_scheme": "custom",
            "members": [
                {"instrument_id": instrument.id, "weight": "0.60"},
                {"symbol": instrument_b.symbol, "weight": "0.40"},
            ],
        },
    )

    assert created.status_code == 200
    basket = created.json()
    assert basket["name"] == "Mega-cap pair"
    assert basket["source_type"] == "manual"
    assert basket["is_read_only"] is False
    assert basket["snapshot_count"] == 1
    assert basket["latest_snapshot_date"] is not None
    assert [member["symbol"] for member in basket["members"]] == ["AAPL", "MSFT"]
    assert basket["members"][0]["weight"] == "0.60000000"

    listed = client.get("/api/v1/baskets", headers=auth_headers)
    assert listed.status_code == 200
    assert any(row["id"] == basket["id"] for row in listed.json())

    updated = client.patch(
        f"/api/v1/baskets/{basket['id']}",
        headers=auth_headers,
        json={
            "name": "Equal-weight pair",
            "weighting_scheme": "equal",
            "members": [
                {"instrument_id": instrument_b.id},
                {"instrument_id": instrument.id},
            ],
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["weighting_scheme"] == "equal"
    assert updated_body["snapshot_count"] == 2
    assert [member["symbol"] for member in updated_body["members"]] == ["MSFT", "AAPL"]
    assert updated_body["members"][0]["weight"] is None

    snapshots = client.get(f"/api/v1/baskets/{basket['id']}/snapshots", headers=auth_headers)
    assert snapshots.status_code == 200
    snapshot_body = snapshots.json()
    assert len(snapshot_body) == 2
    assert [row["member_count"] for row in snapshot_body] == [2, 2]
    assert {row["source_type"] for row in snapshot_body} == {"manual"}

    deleted = client.delete(f"/api/v1/baskets/{basket['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    missing = client.get(f"/api/v1/baskets/{basket['id']}", headers=auth_headers)
    assert missing.status_code == 404


def test_historical_etf_basket_materializes_and_reuses_loaded_members(
    client, admin_headers, auth_headers
):
    composition_date = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    ingest = client.post(
        "/api/v1/etf-holdings/DIA/ingest",
        headers=admin_headers,
        json={
            "composition_date": composition_date,
            "source_provider": "basket-async-regression",
            "rows": [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.60"},
                {"symbol": "MSFT", "name": "Microsoft Corporation", "weight": "0.40"},
            ],
        },
    )
    assert ingest.status_code == 200, ingest.text
    snapshot_id = ingest.json()["id"]

    materialized = client.get(
        f"/api/v1/etf-holdings/DIA/basket?snapshot_id={snapshot_id}",
        headers=auth_headers,
    )
    assert materialized.status_code == 200, materialized.text
    first = materialized.json()
    assert first["is_system_managed"] is True
    assert first["is_read_only"] is True
    assert first["source_snapshot_id"] == snapshot_id
    assert first["metadata"]["source_provider"] == "basket-async-regression"
    assert [member["symbol"] for member in first["members"]] == ["AAPL", "MSFT"]

    repeated = client.get(
        f"/api/v1/etf-holdings/DIA/basket?snapshot_id={snapshot_id}",
        headers=auth_headers,
    )
    assert repeated.status_code == 200, repeated.text
    second = repeated.json()
    assert second["id"] == first["id"]
    assert second["source_snapshot_id"] == snapshot_id
    assert [member["symbol"] for member in second["members"]] == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_manual_basket_crud_uses_real_async_session(db_engine):
    """Exercise the normal basket endpoints with PostgreSQL-backed AsyncSessions."""
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument
    from app.models.user import User

    suffix = uuid4().hex[:10]
    async_url = db_engine.url.set(drivername="postgresql+asyncpg")
    async_engine = create_async_engine(async_url, poolclass=NullPool)
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async with session_factory() as session, session.begin():
        user = User(
            username=f"basket-{suffix}",
            email=f"basket-{suffix}@example.test",
            hashed_password="test-only-not-authenticated",
            is_active=True,
        )
        asset_class = AssetClass(name=f"Basket Equity {suffix}")
        instrument_type = InstrumentType(name=f"Basket Stock {suffix}", asset_class=asset_class)
        instruments = [
            Instrument(
                symbol=f"BA{suffix[:4]}A",
                name="Basket test instrument A",
                currency="USD",
                instrument_type=instrument_type,
                is_active=True,
            ),
            Instrument(
                symbol=f"BA{suffix[:4]}B",
                name="Basket test instrument B",
                currency="USD",
                instrument_type=instrument_type,
                is_active=True,
            ),
        ]
        session.add_all([user, asset_class, instrument_type, *instruments])
        await session.flush()
        user_id = user.id
        instrument_a_id, instrument_b_id = (item.id for item in instruments)

    app = FastAPI()
    app.include_router(baskets_router.router, prefix="/api/v1")

    async def override_db():
        async with session_factory() as session:
            yield session

    async def override_user():
        return SimpleNamespace(id=user_id)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/v1/baskets",
                json={
                    "name": f"Async basket {suffix}",
                    "weighting_scheme": "custom",
                    "members": [
                        {"instrument_id": instrument_a_id, "weight": "0.60"},
                        {"instrument_id": instrument_b_id, "weight": "0.40"},
                    ],
                },
            )
            assert created.status_code == 200, created.text
            basket = created.json()
            basket_id = basket["id"]
            assert [member["instrument_id"] for member in basket["members"]] == [
                instrument_a_id,
                instrument_b_id,
            ]
            assert basket["snapshot_count"] == 1

            updated = await client.patch(
                f"/api/v1/baskets/{basket_id}",
                json={
                    "name": f"Updated async basket {suffix}",
                    "weighting_scheme": "equal",
                    "members": [
                        {"instrument_id": instrument_b_id},
                        {"instrument_id": instrument_a_id},
                    ],
                },
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["name"] == f"Updated async basket {suffix}"
            assert [member["instrument_id"] for member in updated.json()["members"]] == [
                instrument_b_id,
                instrument_a_id,
            ]
            assert updated.json()["snapshot_count"] == 2

            read = await client.get(f"/api/v1/baskets/{basket_id}")
            assert read.status_code == 200
            assert read.json()["id"] == basket_id
            snapshots = await client.get(f"/api/v1/baskets/{basket_id}/snapshots")
            assert snapshots.status_code == 200
            assert len(snapshots.json()) == 2

            deleted = await client.delete(f"/api/v1/baskets/{basket_id}")
            assert deleted.status_code == 204
            missing = await client.get(f"/api/v1/baskets/{basket_id}")
            assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
        async with session_factory() as session, session.begin():
            remaining_user = await session.get(User, user_id)
            if remaining_user is not None:
                await session.delete(remaining_user)
        await async_engine.dispose()


def test_custom_basket_rejects_unknown_duplicate_and_unbalanced_members(
    client,
    auth_headers,
    instrument,
):
    unknown = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Unknown member",
            "members": [{"symbol": "NOTREAL"}],
        },
    )
    assert unknown.status_code == 400
    assert "unknown instruments" in unknown.text

    duplicate = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Duplicate member",
            "members": [
                {"instrument_id": instrument.id},
                {"symbol": instrument.symbol},
            ],
        },
    )
    assert duplicate.status_code == 400
    assert "duplicate instrument" in duplicate.text

    unbalanced = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Bad weights",
            "weighting_scheme": "custom",
            "members": [{"instrument_id": instrument.id, "weight": "0.75"}],
        },
    )
    assert unbalanced.status_code == 400
    assert "sum to 1.0" in unbalanced.text


def test_basket_auto_classification_uses_shared_equity_metadata(
    client,
    auth_headers,
    db,
    instrument,
    instrument_b,
):
    from app.models.instrument import EquityDetail

    db.add(
        EquityDetail(
            instrument_id=instrument.id,
            sector="Technology",
            industry="Consumer Electronics",
        )
    )
    db.add(
        EquityDetail(
            instrument_id=instrument_b.id,
            sector="Technology",
            industry="Software",
        )
    )
    db.commit()

    response = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Tech basket",
            "classification_mode": "auto",
            "members": [
                {"instrument_id": instrument.id},
                {"instrument_id": instrument_b.id},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sector"] == "Technology"
    assert body["industry"] is None


def test_basket_ohlcv_returns_rebased_weighted_series(
    client,
    auth_headers,
    db,
    instrument,
    instrument_b,
):
    from app.models.ohlcv import OHLCVBar, Timeframe

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset, (aapl_close, msft_close) in enumerate([(100, 200), (110, 220), (121, 198)]):
        ts = base + timedelta(days=offset)
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=ts,
                open=Decimal(str(aapl_close)),
                high=Decimal(str(aapl_close)),
                low=Decimal(str(aapl_close)),
                close=Decimal(str(aapl_close)),
                volume=Decimal("1000"),
                is_adjusted=True,
            )
        )
        db.add(
            OHLCVBar(
                instrument_id=instrument_b.id,
                timeframe=Timeframe.D1,
                ts=ts,
                open=Decimal(str(msft_close)),
                high=Decimal(str(msft_close)),
                low=Decimal(str(msft_close)),
                close=Decimal(str(msft_close)),
                volume=Decimal("2000"),
                is_adjusted=True,
            )
        )
    db.flush()

    created = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Equal pair",
            "members": [
                {"instrument_id": instrument.id},
                {"instrument_id": instrument_b.id},
            ],
        },
    )
    assert created.status_code == 200
    basket_id = created.json()["id"]

    response = client.get(f"/api/v1/baskets/{basket_id}/ohlcv/D1", headers=auth_headers)

    assert response.status_code == 200
    bars = response.json()
    assert len(bars) == 3
    assert bars[0]["close"] == 100
    assert bars[1]["close"] == 110
    # AAPL +21% and MSFT -1%, equal weighted from the first aligned bar.
    assert bars[2]["close"] == 110
    assert bars[2]["volume"] == 3000

    offset_range = client.get(
        f"/api/v1/baskets/{basket_id}/ohlcv/D1",
        params={
            "start": "2026-01-01T02:00:00+02:00",
            "end": "2026-01-02T02:00:00+02:00",
        },
        headers=auth_headers,
    )

    assert offset_range.status_code == 200
    assert [bar["close"] for bar in offset_range.json()] == [100, 110]
