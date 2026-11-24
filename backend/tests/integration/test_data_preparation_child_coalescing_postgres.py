"""Child coalescing lookups against real PostgreSQL/asyncpg.

The identity lookup filters a JSON (not JSONB) payload by path, and both
lookups use FOR UPDATE SKIP LOCKED so a request never joins a child that a
drain is claiming in another transaction. SQLite unit tests exercise neither.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime(2026, 11, 20, 10, 5, tzinfo=UTC)


def _async_database_url(raw_url: str) -> str:
    return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    )


@pytest_asyncio.fixture
async def coalescing_sessions(request, test_database_url):
    raw_url = test_database_url
    if not raw_url:
        raw_url = request.getfixturevalue("pg_container").get_connection_url()
    schema = f"child_coalescing_{uuid4().hex}"
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


async def _seed(session):
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument
    from app.models.market_data_foundation import MarketRefreshJob

    asset_class = AssetClass(name="Equity", description="Equity")
    session.add(asset_class)
    await session.flush()
    instrument_type = InstrumentType(name="Stock", asset_class_id=asset_class.id)
    session.add(instrument_type)
    await session.flush()
    instrument = Instrument(symbol="ACME", name="Acme", instrument_type_id=instrument_type.id)
    session.add(instrument)
    await session.flush()
    parents = []
    for name in ("a", "b", "c"):
        parent = MarketRefreshJob(
            request_key=f"data-preparation:maintenance:{name}",
            capability="data_preparation_request",
            priority=100,
            status="tracking",
            attempts=0,
            next_attempt_at=NOW,
            metadata_payload={},
        )
        session.add(parent)
        parents.append(parent)
    await session.flush()
    return instrument, parents


def _refs(job) -> set[int]:
    refs = job.metadata_payload["data_preparation_child"].get("parent_refs") or []
    return {int(ref["parent_job_id"]) for ref in refs}


async def test_symbol_only_identity_join_filters_the_json_payload(coalescing_sessions):
    from app.services.data_preparation import _enqueue_identity_profile_job

    async with coalescing_sessions() as session:
        _instrument, (first, second, third) = await _seed(session)

        async def ensure(parent, symbol, now):
            return await _enqueue_identity_profile_job(
                session,
                parent_job_id=parent.id,
                request_id=f"request-{parent.id}",
                symbol=symbol,
                instrument_id=None,
                owner_user_id=None,
                priority=100,
                now=now,
            )

        waiting = await ensure(first, "newco", NOW)
        joined = await ensure(second, "NEWCO", NOW + timedelta(hours=1))
        other = await ensure(third, "OTHERCO", NOW + timedelta(hours=1))
        await session.commit()

        assert joined.id == waiting.id
        assert _refs(joined) == {first.id, second.id}
        assert other.id != waiting.id


async def test_history_join_skips_a_child_locked_by_a_concurrent_claim(coalescing_sessions):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.models.ohlcv import Timeframe
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import _enqueue_history_dependency

    session_end_1 = datetime(2026, 11, 18, 21, tzinfo=UTC)
    session_end_2 = datetime(2026, 11, 19, 21, tzinfo=UTC)
    session_end_3 = datetime(2026, 11, 20, 21, tzinfo=UTC)

    async with coalescing_sessions() as session:
        instrument, parents = await _seed(session)
        await session.commit()

    async def ensure(session, parent, end_at):
        request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": instrument.id},
                "datasets": ["history"],
                "timeframe": "D1",
                "adjusted": True,
                "end_at": end_at.isoformat(),
            }
        )
        return await _enqueue_history_dependency(
            session,
            parent_job_id=parent.id,
            request_id=f"request-{parent.id}",
            dependency_id=f"dependency-{parent.id}",
            instrument_id=instrument.id,
            request=request,
            priority=100,
            timeframe=Timeframe.D1,
            now=NOW,
        )

    async with coalescing_sessions() as session:
        waiting = await ensure(session, parents[0], session_end_1)
        await session.commit()
        waiting_id = waiting.id

    async with coalescing_sessions() as claimer, coalescing_sessions() as planner:
        # A drain holds the row lock between claim and commit.
        await claimer.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.id == waiting_id).with_for_update()
        )
        forked = await ensure(planner, parents[1], session_end_2)
        await planner.commit()
        await claimer.rollback()
        assert forked.id != waiting_id

    async with coalescing_sessions() as session:
        joined = await ensure(session, parents[2], session_end_3)
        await session.commit()
        # Once unlocked, the earlier child is again the oldest waiting sibling.
        assert joined.id == waiting_id
        assert joined.end_at == session_end_3
        assert _refs(joined) == {parents[0].id, parents[2].id}


async def _deepest_child(session, instrument, key, parent, *, status):
    from app.models.market_data_foundation import MarketRefreshJob

    job = MarketRefreshJob(
        request_key=f"prep-history:{key}",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe="D1",
        priority=100,
        status=status,
        attempts=0,
        next_attempt_at=NOW,
        lease_token=f"lease-{key}" if status == "leased" else None,
        metadata_payload={
            "data_preparation_child": {
                "dataset": "history",
                "instrument_id": instrument.id,
                "adjusted": True,
                "range_mode": "deepest_admitted",
                "wait_for_job_ids": [],
                "derived_only": False,
                "parent_refs": [{"parent_job_id": parent.id, "dependency_id": key}],
            }
        },
    )
    session.add(job)
    await session.flush()
    parent.metadata_payload = {
        "data_preparation": {
            "role": "system_maintenance_tracking",
            "version": 1,
            "dependencies": [{"dependency_id": key, "dataset": "history", "job_ids": [job.id]}],
        }
    }
    await session.flush()
    return job


async def test_drain_folds_a_legacy_duplicate_and_repoints_its_parent(coalescing_sessions):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.services.data_preparation import coalesce_history_duplicate

    async with coalescing_sessions() as session:
        instrument, parents = await _seed(session)
        survivor = await _deepest_child(session, instrument, "s", parents[0], status="deferred")
        duplicate = await _deepest_child(session, instrument, "d", parents[1], status="leased")
        await session.commit()
        survivor_id, duplicate_id = survivor.id, duplicate.id

    async with coalescing_sessions() as session:
        duplicate = await session.get(MarketRefreshJob, duplicate_id)
        folded = await coalesce_history_duplicate(session, job=duplicate, now=NOW)
        await session.commit()
        assert folded is not None and folded.id == survivor_id

    async with coalescing_sessions() as session:
        survivor = await session.get(MarketRefreshJob, survivor_id)
        duplicate = await session.get(MarketRefreshJob, duplicate_id)
        parent = await session.get(MarketRefreshJob, parents[1].id)
        assert _refs(survivor) == {parents[0].id, parents[1].id}
        assert _refs(duplicate) == set()
        child = duplicate.metadata_payload["data_preparation_child"]
        assert child["coalesced_into"] == survivor_id
        assert child["wait_for_job_ids"] == [survivor_id]
        dependency = parent.metadata_payload["data_preparation"]["dependencies"][0]
        assert dependency["job_ids"] == [survivor_id]


async def test_drain_does_not_fold_into_a_sibling_another_drain_is_claiming(
    coalescing_sessions,
):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.services.data_preparation import coalesce_history_duplicate

    async with coalescing_sessions() as session:
        instrument, parents = await _seed(session)
        survivor = await _deepest_child(session, instrument, "s", parents[0], status="queued")
        duplicate = await _deepest_child(session, instrument, "d", parents[1], status="leased")
        await session.commit()
        survivor_id, duplicate_id = survivor.id, duplicate.id

    async with coalescing_sessions() as claimer, coalescing_sessions() as drain:
        await claimer.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.id == survivor_id).with_for_update()
        )
        duplicate = await drain.get(MarketRefreshJob, duplicate_id)
        folded = await coalesce_history_duplicate(drain, job=duplicate, now=NOW)
        await drain.commit()
        await claimer.rollback()

        assert folded is None
        assert "coalesced_into" not in duplicate.metadata_payload["data_preparation_child"]
        assert _refs(duplicate) == {parents[1].id}


async def test_drain_fold_and_enqueue_join_share_a_parent_without_deadlock(
    coalescing_sessions,
):
    """An enqueue join holds the survivor's key, then locks a parent the fold also needs."""

    import asyncio

    from app.models.market_data_foundation import MarketRefreshJob
    from app.services.data_preparation import (
        _acquire_enqueue_lock,
        _lock_parent_for_update,
        coalesce_history_duplicate,
    )

    async with coalescing_sessions() as session:
        instrument, parents = await _seed(session)
        survivor = await _deepest_child(session, instrument, "s", parents[0], status="queued")
        duplicate = await _deepest_child(session, instrument, "d", parents[1], status="leased")
        await session.commit()
        survivor_id, survivor_key, duplicate_id = survivor.id, survivor.request_key, duplicate.id

    async with coalescing_sessions() as enqueuer, coalescing_sessions() as drain:
        await enqueuer.execute(text("SET LOCAL lock_timeout = '10s'"))
        await drain.execute(text("SET LOCAL lock_timeout = '10s'"))
        await _acquire_enqueue_lock(enqueuer, survivor_key)
        duplicate = await drain.get(MarketRefreshJob, duplicate_id)
        fold = asyncio.create_task(coalesce_history_duplicate(drain, job=duplicate, now=NOW))
        await asyncio.sleep(0.5)  # let the fold reach its first blocked lock

        # Postgres aborts one side with DeadlockDetectedError if the fold holds
        # the parent while it waits for the survivor's key.
        await _lock_parent_for_update(enqueuer, parents[1].id)
        await enqueuer.commit()
        folded = await asyncio.wait_for(fold, timeout=15)
        await drain.commit()

        assert folded is not None and folded.id == survivor_id
