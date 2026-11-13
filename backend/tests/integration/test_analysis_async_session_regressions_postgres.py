"""Real-asyncpg regressions for analysis routes that the sync test adapter cannot catch.

The shared ``client`` fixture runs the app on a synchronous session behind an
async facade, so lazy loads succeed and savepoint/unique-violation behaviour is
not representative.  These tests use a genuine ``AsyncSession`` on asyncpg.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import Instrument
from app.models.market_map import MarketMapCache
from app.models.ohlcv import Timeframe
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.workstation import MarketGroup, MarketGroupMember
from app.schemas.market_map import MarketMapRequest


def _async_sessions(db_engine):
    engine = create_async_engine(
        db_engine.url.set(drivername="postgresql+asyncpg"), poolclass=NullPool
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _make_user(db_engine, suffix: str) -> int:
    with Session(db_engine) as setup, setup.begin():
        user = User(
            username=f"async-reg-{suffix}",
            email=f"async-reg-{suffix}@example.test",
            hashed_password="test-only-not-authenticated",
        )
        setup.add(user)
        setup.flush()
        return user.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_market_map_duplicate_cache_insert_is_served_not_500(db_engine, monkeypatch):
    """Two identical requests that both miss the cache lookup must both succeed."""
    from app.services import market_map as market_map_service

    suffix = uuid4().hex[:12]
    user_id = _make_user(db_engine, suffix)
    with Session(db_engine) as setup, setup.begin():
        watchlist = Watchlist(user_id=user_id, name=f"race-{suffix}")
        setup.add(watchlist)
        setup.flush()
        source_id = f"watchlist:{watchlist.id}"

    request = MarketMapRequest(
        source_id=source_id,
        group_by="none",
        period="1D",
        area_metric="equal",
        color_metric="return",
    )
    engine, sessions = _async_sessions(db_engine)

    async def always_miss(db, user, key):
        return None

    monkeypatch.setattr(market_map_service, "read_market_map_cache", always_miss)
    try:
        async with sessions() as first:
            first_result = await market_map_service.build_market_map(first, user_id, request)
            await first.commit()

        # The row now exists, but this request's lookup still misses (the race).
        async with sessions() as second:
            second_result = await market_map_service.build_market_map(second, user_id, request)
            # The outer transaction must stay usable after the savepoint rollback.
            await second.commit()
            assert (await second.execute(select(1))).scalar_one() == 1

        assert second_result.cache_key == first_result.cache_key
        assert second_result.source.source_id == source_id
        async with sessions() as check:
            count = (
                await check.execute(
                    select(func.count())
                    .select_from(MarketMapCache)
                    .where(MarketMapCache.user_id == user_id)
                )
            ).scalar_one()
        assert count == 1
    finally:
        await engine.dispose()
        with Session(db_engine) as cleanup, cleanup.begin():
            cleanup.execute(delete(MarketMapCache).where(MarketMapCache.user_id == user_id))
            cleanup.execute(delete(Watchlist).where(Watchlist.user_id == user_id))
            cleanup.execute(delete(User).where(User.id == user_id))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_benchmark_family_breadth_loads_members_without_missing_greenlet(db_engine):
    """The family handler must eager-load ``members`` on a real async session."""
    from datetime import UTC, datetime

    from app.routers.analysis import benchmark_family_breadth

    suffix = uuid4().hex[:12]
    family_key = f"async-family-{suffix}"
    now = datetime(2024, 1, 1, tzinfo=UTC)
    with Session(db_engine) as setup, setup.begin():
        asset_class = AssetClass(name=f"AC-{suffix}")
        setup.add(asset_class)
        setup.flush()
        instrument_type = InstrumentType(name=f"IT-{suffix}", asset_class_id=asset_class.id)
        setup.add(instrument_type)
        setup.flush()
        instrument = Instrument(
            symbol=f"AF{suffix[:8]}".upper(),
            name="Async family member",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        setup.add(instrument)
        setup.flush()
        instrument_id = instrument.id
        asset_class_id = asset_class.id
        instrument_type_id = instrument_type.id
        group = MarketGroup(
            stable_key=family_key,
            group_type="benchmark_family",
            name="Async Family",
            source="controlled_fixture",
            effective_at=now,
            known_at=now,
            provenance={"official_index": {"name": "Async Index"}, "proxy_mappings": {}},
        )
        setup.add(group)
        setup.flush()
        setup.add(
            MarketGroupMember(
                market_group_id=group.id,
                instrument_id=instrument_id,
                position=0,
                relationship_type="constituent",
                source="controlled_fixture",
                verification_state="verified",
                effective_at=now,
                known_at=now,
            )
        )
        group_id = group.id

    engine, sessions = _async_sessions(db_engine)
    try:
        async with sessions() as session:
            response = await benchmark_family_breadth(
                family_key=family_key,
                timeframe=Timeframe.D1,
                adjusted=True,
                as_of=None,
                near_threshold=0.01,
                new_high_lookback=20,
                _=SimpleNamespace(id=1),
                db=session,
            )
        assert response.family_key == family_key
    finally:
        await engine.dispose()
        with Session(db_engine) as cleanup, cleanup.begin():
            cleanup.execute(
                delete(MarketGroupMember).where(MarketGroupMember.market_group_id == group_id)
            )
            cleanup.execute(delete(MarketGroup).where(MarketGroup.id == group_id))
            cleanup.execute(delete(Instrument).where(Instrument.id == instrument_id))
            cleanup.execute(delete(InstrumentType).where(InstrumentType.id == instrument_type_id))
            cleanup.execute(delete(AssetClass).where(AssetClass.id == asset_class_id))
