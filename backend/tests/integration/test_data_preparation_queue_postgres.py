"""Focused real-PostgreSQL coverage for durable data-preparation graphs."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio


@pytest.fixture
def preparation_database_urls(pg_container, test_database_url):
    raw_url = test_database_url or pg_container.get_connection_url()
    async_url = raw_url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )
    schema = f"provider_prep_{uuid4().hex}"
    return raw_url, async_url, schema


@pytest_asyncio.fixture
async def preparation_sessions(preparation_database_urls):
    raw_url, async_url, schema = preparation_database_urls
    import app.models  # noqa: F401
    from app.database import Base

    sync_engine = create_engine(raw_url, pool_pre_ping=True)
    with sync_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_sync_engine = sync_engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(scoped_sync_engine)

    async_engine = create_async_engine(
        async_url,
        pool_size=6,
        max_overflow=0,
        connect_args={"server_settings": {"search_path": schema}},
    )
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    yield factory
    await async_engine.dispose()
    with sync_engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    sync_engine.dispose()


def _canonical_instrument(symbol: str, instrument_type_id: int, *, domain_prefix: str):
    from app.models.instrument import Instrument

    return Instrument(
        symbol=symbol,
        name=f"{symbol} test instrument",
        currency="USD",
        instrument_type_id=instrument_type_id,
        is_active=True,
        identity_status="resolved",
        domain_key=f"{domain_prefix}:{symbol.lower()}",
        primary_identifier_type="figi",
        primary_identifier_value=f"BBG000{domain_prefix[-4:].upper()}{symbol.upper()}",
    )


async def _create_instrument_types(session):
    from app.models.asset_class import AssetClass, InstrumentType

    equity = AssetClass(name=f"Equity-{uuid4().hex[:8]}")
    etp = AssetClass(name=f"ETP-{uuid4().hex[:8]}")
    session.add_all([equity, etp])
    await session.flush()
    stock = InstrumentType(asset_class_id=equity.id, name="Stock")
    etf = InstrumentType(asset_class_id=equity.id, name="ETF")
    session.add_all([stock, etf])
    await session.flush()
    return stock.id, etf.id


async def test_rrg_ratio_and_concurrent_identity_children_preserve_each_parent_leg(
    preparation_sessions, monkeypatch
):
    from fastapi import HTTPException

    from app.models.instrument import Instrument
    from app.models.market_data_foundation import MarketRefreshJob
    from app.models.workstation import MarketGroup, MarketGroupMember
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import (
        create_data_preparation_request,
        expand_resolved_identity_dependency,
        get_data_preparation_response,
        load_owner_request,
        record_identity_preparation_outcome,
    )

    async with preparation_sessions() as session:
        _, etf_type_id = await _create_instrument_types(session)
        sector_symbols = [
            "XLK",
            "XLY",
            "XLC",
            "XLF",
            "XLV",
            "XLI",
            "XLP",
            "XLE",
            "XLU",
            "XLRE",
            "XLB",
        ]
        sectors = [
            _canonical_instrument(symbol, etf_type_id, domain_prefix="rrg-sector")
            for symbol in sector_symbols
        ]
        spy = _canonical_instrument("SPY", etf_type_id, domain_prefix="rrg-benchmark")
        sector_group = MarketGroup(
            stable_key="sp500-sectors",
            group_type="sector",
            name="S&P 500 sectors",
        )
        family = MarketGroup(
            stable_key=f"sp500-family-{uuid4().hex[:8]}",
            group_type="benchmark_family",
            name="S&P 500 family",
            provenance={"proxy_mappings": {"cap_weight": {"symbol": "SPY"}}},
        )
        session.add_all([*sectors, spy, sector_group, family])
        await session.flush()
        session.add_all(
            [
                MarketGroupMember(
                    market_group_id=sector_group.id,
                    instrument_id=instrument.id,
                    position=position,
                )
                for position, instrument in enumerate(sectors)
            ]
            + [
                MarketGroupMember(
                    market_group_id=family.id,
                    instrument_id=spy.id,
                    position=0,
                )
            ]
        )
        await session.flush()

        rrg_request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "market_group", "group_key": "sp500-sectors"},
                "datasets": ["history"],
                "analysis": {"kind": "rrg", "benchmark_symbol": "SPY"},
            }
        )
        rrg_parent = await create_data_preparation_request(
            session, owner_user_id=701, request=rrg_request
        )
        rrg_deps = rrg_parent.metadata_payload["data_preparation"]["dependencies"]
        rrg_history = [item for item in rrg_deps if item["dataset"] == "history"]
        assert len(rrg_history) == 12
        assert {item["instrument_id"] for item in rrg_history} == {
            instrument.id for instrument in [*sectors, spy]
        }

        family_request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "family", "family_key": family.stable_key},
                "datasets": ["history"],
                "analysis": {"kind": "rrg"},
            }
        )
        family_parent = await create_data_preparation_request(
            session, owner_user_id=702, request=family_request
        )
        family_history = [
            item
            for item in family_parent.metadata_payload["data_preparation"]["dependencies"]
            if item["dataset"] == "history"
        ]
        assert {item["instrument_id"] for item in family_history} == {spy.id}

        custom_request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": sectors[-1].id},
                "datasets": ["history"],
                "analysis": {"kind": "rrg", "benchmark_symbol": "CUSRR"},
            }
        )
        custom_parent = await create_data_preparation_request(
            session, owner_user_id=703, request=custom_request
        )
        custom_data = custom_parent.metadata_payload["data_preparation"]
        custom_identity = next(
            item for item in custom_data["dependencies"] if item["dataset"] == "identity"
        )
        custom_history = next(
            item
            for item in custom_data["dependencies"]
            if item["dataset"] == "history" and item.get("symbol") == "CUSRR"
        )
        assert custom_history["depends_on"] == [custom_identity["dependency_id"]]
        custom_id = custom_identity["job_ids"][0]
        custom_canonical = _canonical_instrument("CUSRR", etf_type_id, domain_prefix="rrg-custom")
        session.add(custom_canonical)
        await session.flush()
        custom_canonical_id = custom_canonical.id
        custom_parent_id = custom_parent.id
        await session.commit()

    async with preparation_sessions() as session:
        identity_job = await session.get(MarketRefreshJob, custom_id)
        await expand_resolved_identity_dependency(
            session, identity_job=identity_job, instrument_id=custom_canonical_id
        )
        await session.commit()
    async with preparation_sessions() as session:
        persisted_custom = await session.get(MarketRefreshJob, custom_parent_id)
        custom_dependencies = persisted_custom.metadata_payload["data_preparation"]["dependencies"]
        custom_history = next(
            item
            for item in custom_dependencies
            if item["dataset"] == "history" and item.get("symbol") == "CUSRR"
        )
        assert custom_history["instrument_id"] == custom_canonical_id
        assert custom_history["status"] == "queued"

    # The target/numerator remains known while only its uncached denominator
    # receives an identity job and subsequent history dependency.
    async with preparation_sessions() as session:
        xlb = await session.scalar(select(Instrument).where(Instrument.symbol == "XLB"))
        ratio_request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": xlb.id},
                "datasets": ["history"],
                "analysis": {
                    "kind": "ratio",
                    "legs": [{"symbol": "XLB"}, {"symbol": "DENOM"}],
                },
            }
        )
        ratio_parent = await create_data_preparation_request(
            session, owner_user_id=704, request=ratio_request
        )
        ratio_data = ratio_parent.metadata_payload["data_preparation"]
        ratio_identity = next(
            item for item in ratio_data["dependencies"] if item["dataset"] == "identity"
        )
        assert ratio_identity["symbol"] == "DENOM"
        assert sum(item["dataset"] == "identity" for item in ratio_data["dependencies"]) == 1
        denominator = _canonical_instrument("DENOM", etf_type_id, domain_prefix="ratio-denom")
        session.add(denominator)
        await session.flush()
        denominator_id = denominator.id
        ratio_parent_id = ratio_parent.id
        ratio_identity_id = ratio_identity["job_ids"][0]
        await session.commit()
    async with preparation_sessions() as session:
        identity_job = await session.get(MarketRefreshJob, ratio_identity_id)
        await expand_resolved_identity_dependency(
            session, identity_job=identity_job, instrument_id=denominator_id
        )
        await session.commit()
    async with preparation_sessions() as session:
        persisted_ratio = await session.get(MarketRefreshJob, ratio_parent_id)
        history = [
            item
            for item in persisted_ratio.metadata_payload["data_preparation"]["dependencies"]
            if item["dataset"] == "history"
        ]
        assert {item["instrument_id"] for item in history} == {xlb.id, denominator_id}

    # Two ETF ratio legs resolve concurrently in independent real sessions.
    async with preparation_sessions() as session:
        xlb = await session.scalar(select(Instrument).where(Instrument.symbol == "XLB"))
        request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": xlb.id},
                "datasets": ["history", "holdings"],
                "analysis": {
                    "kind": "ratio",
                    "legs": [{"symbol": "LEFTETF"}, {"symbol": "RIGHTETF"}],
                },
            }
        )
        parent = await create_data_preparation_request(session, owner_user_id=705, request=request)
        data = deepcopy(parent.metadata_payload["data_preparation"])
        identity_jobs = {
            item["symbol"]: item["job_ids"][0]
            for item in data["dependencies"]
            if item["dataset"] == "identity"
        }
        assert set(identity_jobs) == {"LEFTETF", "RIGHTETF"}
        left = _canonical_instrument("LEFTETF", etf_type_id, domain_prefix="ratio-etf")
        right = _canonical_instrument("RIGHTETF", etf_type_id, domain_prefix="ratio-etf")
        session.add_all([left, right])
        await session.flush()
        parent_id = parent.id
        left_id, right_id = left.id, right.id
        left_job_id, right_job_id = identity_jobs["LEFTETF"], identity_jobs["RIGHTETF"]
        await session.commit()

    original_enqueue = __import__(
        "app.services.data_preparation", fromlist=["_enqueue_history_dependency"]
    )._enqueue_history_dependency
    arrived = 0
    both_arrived = asyncio.Event()

    async def synchronized_enqueue(*args, **kwargs):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both_arrived.set()
        await asyncio.wait_for(both_arrived.wait(), timeout=10)
        return await original_enqueue(*args, **kwargs)

    from app.services import data_preparation

    monkeypatch.setattr(data_preparation, "_enqueue_history_dependency", synchronized_enqueue)

    async def expand_in_new_session(job_id: int, instrument_id: int) -> None:
        async with preparation_sessions() as session:
            identity_job = await session.get(MarketRefreshJob, job_id)
            await expand_resolved_identity_dependency(
                session, identity_job=identity_job, instrument_id=instrument_id
            )
            await session.commit()

    await asyncio.gather(
        expand_in_new_session(left_job_id, left_id),
        expand_in_new_session(right_job_id, right_id),
    )
    async with preparation_sessions() as session:
        persisted = await session.get(MarketRefreshJob, parent_id)
        dependencies = persisted.metadata_payload["data_preparation"]["dependencies"]
        histories = {item["symbol"]: item for item in dependencies if item["dataset"] == "history"}
        holdings = {item["instrument_id"] for item in dependencies if item["dataset"] == "holdings"}
        assert histories["LEFTETF"]["instrument_id"] == left_id
        assert histories["RIGHTETF"]["instrument_id"] == right_id
        assert {left_id, right_id}.issubset(holdings)
        with pytest.raises(HTTPException) as denied:
            await load_owner_request(
                session,
                request_id=persisted.metadata_payload["data_preparation"]["request_id"],
                owner_user_id=999,
            )
        assert denied.value.status_code == 404
        owner_view = await get_data_preparation_response(
            session, parent=persisted, owner_user_id=705
        )
        assert {
            item.instrument_id
            for item in owner_view.dependencies
            if item.dataset.value == "history"
        } >= {
            xlb.id,
            left_id,
            right_id,
        }

    # An unavailable leg changes only its own dependent history, leaving the
    # second unknown leg independently waiting for identity resolution.
    async with preparation_sessions() as session:
        xlb = await session.scalar(select(Instrument).where(Instrument.symbol == "XLB"))
        fail_request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": xlb.id},
                "datasets": ["history"],
                "analysis": {
                    "kind": "ratio",
                    "legs": [{"symbol": "FAILLEG"}, {"symbol": "WAITLEG"}],
                },
            }
        )
        fail_parent = await create_data_preparation_request(
            session, owner_user_id=706, request=fail_request
        )
        fail_data = fail_parent.metadata_payload["data_preparation"]
        fail_job_id = next(
            item["job_ids"][0]
            for item in fail_data["dependencies"]
            if item["dataset"] == "identity" and item["symbol"] == "FAILLEG"
        )
        fail_job = await session.get(MarketRefreshJob, fail_job_id)
        await record_identity_preparation_outcome(
            session,
            identity_job=fail_job,
            status="unavailable",
            reason_code="provider_no_match",
        )
        await session.commit()
        fail_parent_id = fail_parent.id
    async with preparation_sessions() as session:
        failed = await session.get(MarketRefreshJob, fail_parent_id)
        histories = {
            item["symbol"]: item
            for item in failed.metadata_payload["data_preparation"]["dependencies"]
            if item["dataset"] == "history"
        }
        assert histories["FAILLEG"]["status"] == "unavailable"
        assert histories["WAITLEG"]["status"] == "waiting"

    # Concurrent equivalent owners join one history child; visible demand
    # promotes the shared queue row without losing either parent reference.
    async with preparation_sessions() as session:
        xlb = await session.scalar(select(Instrument).where(Instrument.symbol == "XLB"))
        shared_request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": xlb.id},
                "datasets": ["history"],
                "start_at": "2024-01-01T00:00:00Z",
                "end_at": "2024-02-01T00:00:00Z",
            }
        )

    async def create_for_owner(owner: int, priority: str):
        async with preparation_sessions() as session:
            parent = await create_data_preparation_request(
                session,
                owner_user_id=owner,
                request=shared_request,
                priority=priority,
            )
            await session.commit()
            return parent.id, parent.metadata_payload["data_preparation"]["dependencies"][0][
                "job_ids"
            ][0]

    first, second = await asyncio.gather(
        create_for_owner(707, "background"), create_for_owner(708, "visible")
    )
    assert first[1] == second[1]
    async with preparation_sessions() as session:
        shared_job = await session.get(MarketRefreshJob, first[1])
        assert shared_job.priority == 10
        assert {
            item["parent_job_id"]
            for item in shared_job.metadata_payload["data_preparation_child"]["parent_refs"]
        } == {first[0], second[0]}


async def test_actual_etf_hook_runs_in_worker_without_source_transport(
    preparation_sessions, monkeypatch
):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.models.ohlcv import Timeframe
    from app.tasks import data_tasks

    async with preparation_sessions() as session:
        _, etf_type_id = await _create_instrument_types(session)
        instrument = _canonical_instrument("HOOKETF", etf_type_id, domain_prefix="hook")
        session.add(instrument)
        await session.flush()
        job = MarketRefreshJob(
            request_key=f"prep-hook:{uuid4()}",
            capability="etf_holdings_preparation",
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            priority=0,
            status="queued",
            attempts=0,
            next_attempt_at=datetime.now(UTC),
            metadata_payload={
                "data_preparation_child": {
                    "request_id": f"hook:{uuid4()}",
                    "dependency_id": "hook-dependency",
                }
            },
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    from app.services import etf_holdings_refresh

    calls = []

    async def held_issuer_attempt(*args, **kwargs):
        calls.append(kwargs["symbol"])
        return SimpleNamespace(
            outcome="unavailable", reason_code="issuer_route_unavailable", retry_at=None
        )

    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", held_issuer_attempt)
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", preparation_sessions)
    result = await data_tasks.process_refresh_jobs({"redis": None}, limit=1)
    assert result["completed"] == 1
    assert calls == ["HOOKETF"]
    async with preparation_sessions() as session:
        job = await session.get(MarketRefreshJob, job_id)
        assert job.status == "completed"
        assert job.result_summary["preparation_status"] == "unavailable"
        assert job.result_summary["reason_code"] == "issuer_route_unavailable"


async def test_committed_history_chunks_project_only_contiguous_same_scope_coverage(
    preparation_sessions,
):
    from app.models.data_source import DataSource
    from app.models.market_data_foundation import AdjustmentBasis, MarketRefreshJob, MarketSeries
    from app.models.ohlcv import OHLCVBar, Timeframe
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import (
        create_data_preparation_request,
        get_data_preparation_response,
    )

    async with preparation_sessions() as session:
        stock_type_id, _ = await _create_instrument_types(session)
        instrument = _canonical_instrument("COVERAGE", stock_type_id, domain_prefix="coverage")
        source = DataSource(name=f"prep-source-{uuid4().hex[:8]}", is_active=True)
        session.add_all([instrument, source])
        await session.flush()
        series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=source.id,
            feed_scope="coverage-test",
            session_code="regular",
            timeframe=Timeframe.D1.value,
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="test-split-v1",
            is_canonical=True,
            is_active=True,
        )
        session.add(series)
        await session.flush()
        request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": instrument.id},
                "datasets": ["history"],
                "timeframe": "D1",
                "start_at": "2025-01-02T00:00:00Z",
                "end_at": "2025-01-03T23:59:59Z",
            }
        )
        parent = await create_data_preparation_request(session, owner_user_id=811, request=request)
        data = deepcopy(parent.metadata_payload["data_preparation"])
        dependency = next(item for item in data["dependencies"] if item["dataset"] == "history")
        first = await session.get(MarketRefreshJob, dependency["job_ids"][0])
        second = MarketRefreshJob(
            request_key=f"prep-coverage-continuation:{uuid4()}",
            capability="price_history",
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            status="completed",
            attempts=1,
            next_attempt_at=datetime.now(UTC),
            result_summary={
                "data_status": "ready",
                "chunk_coverage_status": "ready",
                "range_coverage_status": "ready",
                "bars_observed": 1,
                "requested_start": "2025-01-03T00:00:00+00:00",
                "requested_end": "2025-01-03T23:59:59.999999+00:00",
                "covered_start": "2025-01-03T14:30:00+00:00",
                "covered_end": "2025-01-03T14:30:00+00:00",
                "coverage_scopes": [
                    {
                        "data_source_id": source.id,
                        "market_series_id": series.id,
                        "adjustment_basis": "split_adjusted",
                        "adjustment_version": "test-split-v1",
                        "is_adjusted": True,
                    }
                ],
            },
            metadata_payload={"data_preparation_child": {"chunk": True}},
        )
        first.status = "completed"
        first.result_summary = {
            # The interval itself is complete even though deeper history is
            # still pending for the whole preparation request.
            "data_status": "partial",
            "chunk_coverage_status": "ready",
            "range_coverage_status": "partial",
            "bars_observed": 1,
            "requested_start": "2025-01-02T00:00:00+00:00",
            "requested_end": "2025-01-02T23:59:59.999999+00:00",
            "covered_start": "2025-01-02T14:30:00+00:00",
            "covered_end": "2025-01-02T14:30:00+00:00",
            "coverage_scopes": [
                {
                    "data_source_id": source.id,
                    "market_series_id": series.id,
                    "adjustment_basis": "split_adjusted",
                    "adjustment_version": "test-split-v1",
                    "is_adjusted": True,
                }
            ],
        }
        session.add(second)
        await session.flush()
        dependency["job_ids"] = [first.id]
        dependency["background_job_ids"] = [second.id]
        parent.metadata_payload = {"data_preparation": data}
        for day in (2, 3):
            ts = datetime(2025, 1, day, 14, 30, tzinfo=UTC)
            session.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=source.id,
                    market_series_id=series.id,
                    timeframe=Timeframe.D1,
                    ts=ts,
                    session="regular",
                    scope_key="test:coverage",
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10.5"),
                    is_adjusted=True,
                    adjustment_basis="split_adjusted",
                    adjustment_version="test-split-v1",
                )
            )
        parent_id = parent.id
        await session.commit()

    async with preparation_sessions() as session:
        parent = await session.get(MarketRefreshJob, parent_id)
        response = await get_data_preparation_response(session, parent=parent, owner_user_id=811)
        history = next(item for item in response.dependencies if item.dataset.value == "history")
        assert history.status == "ready"
        assert history.covered_start == datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
        assert history.covered_end == datetime(2025, 1, 3, 14, 30, tzinfo=UTC)
        assert len(history.covered_ranges) == 1
        assert history.covered_ranges[0].market_series_id is not None


async def test_worker_chunk_result_projects_while_older_continuation_is_queued(
    preparation_sessions, monkeypatch
):
    from app.models.data_source import DataSource
    from app.models.market_data_foundation import AdjustmentBasis, MarketRefreshJob, MarketSeries
    from app.models.ohlcv import OHLCVBar, Timeframe
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import (
        create_data_preparation_request,
        get_data_preparation_response,
    )
    from app.tasks import data_tasks

    planned_start = datetime(2025, 1, 3, 5, 0, tzinfo=UTC)
    planned_end = datetime(2025, 1, 4, 4, 59, 59, 999999, tzinfo=UTC)
    full_start = datetime(2025, 1, 2, 5, 0, tzinfo=UTC)
    full_end = planned_end
    async with preparation_sessions() as session:
        stock_type_id, _ = await _create_instrument_types(session)
        instrument = _canonical_instrument(
            "WORKER-COVERAGE", stock_type_id, domain_prefix="worker-coverage"
        )
        source = DataSource(name=f"prep-worker-source-{uuid4().hex[:8]}", is_active=True)
        session.add_all([instrument, source])
        await session.flush()
        series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=source.id,
            feed_scope="worker-coverage-test",
            session_code="regular",
            timeframe=Timeframe.D1.value,
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="worker-split-v1",
            is_canonical=True,
            is_active=True,
        )
        session.add(series)
        await session.flush()
        bar = OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=source.id,
            market_series_id=series.id,
            timeframe=Timeframe.D1,
            ts=datetime(2025, 1, 3, 14, 30, tzinfo=UTC),
            session="regular",
            scope_key="test:worker-coverage",
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10.5"),
            is_adjusted=True,
            adjustment_basis="split_adjusted",
            adjustment_version="worker-split-v1",
        )
        session.add(bar)
        await session.flush()
        request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": instrument.id},
                "datasets": ["history"],
                "timeframe": "D1",
                "start_at": full_start.isoformat(),
                "end_at": full_end.isoformat(),
            }
        )
        parent = await create_data_preparation_request(session, owner_user_id=812, request=request)
        data = deepcopy(parent.metadata_payload["data_preparation"])
        dependency = next(item for item in data["dependencies"] if item["dataset"] == "history")
        parent.status = "completed"
        parent_id = parent.id
        await session.commit()

    async def fixed_chunk_plan(db, job, instrument, timeframe, preparation):
        return planned_start, planned_end, full_start, full_end, "massive", None

    async def local_fetch(db, instrument, timeframe, start, *, end=None, **kwargs):
        statement = select(OHLCVBar).where(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.ts >= start,
        )
        if end is not None:
            statement = statement.where(OHLCVBar.ts <= end)
        return list((await db.execute(statement.order_by(OHLCVBar.ts))).scalars())

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", preparation_sessions)
    monkeypatch.setattr(data_tasks, "_history_chunk_plan", fixed_chunk_plan)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", local_fetch)
    result = await data_tasks.process_refresh_jobs({"redis": None}, limit=1)
    assert result["completed"] == 1

    async with preparation_sessions() as session:
        parent = await session.get(MarketRefreshJob, parent_id)
        data = parent.metadata_payload["data_preparation"]
        dependency = next(item for item in data["dependencies"] if item["dataset"] == "history")
        foreground = await session.get(MarketRefreshJob, dependency["job_ids"][0])
        continuation_ids = dependency["background_job_ids"]
        assert continuation_ids
        assert foreground.status == "completed"
        assert foreground.result_summary["data_status"] == "partial"
        assert foreground.result_summary["chunk_coverage_status"] == "ready"
        assert foreground.result_summary["coverage_scopes"][0]["market_series_id"] == series.id
        response = await get_data_preparation_response(session, parent=parent, owner_user_id=812)
        history = next(item for item in response.dependencies if item.dataset.value == "history")
        assert history.status == "partial"
        assert history.covered_start == bar.ts
        assert history.covered_end == bar.ts
        assert history.covered_ranges[0].is_adjusted is True
        assert history.covered_ranges[0].market_series_id == series.id


async def test_weekly_and_monthly_coverage_tracks_rematerialized_derived_series(
    preparation_sessions, monkeypatch
):
    from app.models.data_source import DataSource
    from app.models.instrument import Instrument
    from app.models.market_data_foundation import (
        AdjustmentBasis,
        MarketRefreshJob,
        MarketSeries,
        MarketSeriesDefault,
    )
    from app.models.ohlcv import OHLCVBar, Timeframe
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import (
        create_data_preparation_request,
        get_data_preparation_response,
    )
    from app.services.derived_timeframes import materialize_derived_timeframes
    from app.tasks import data_tasks

    async with preparation_sessions() as session:
        stock_type_id, _ = await _create_instrument_types(session)
        instrument = _canonical_instrument(
            "DERIVED-COVERAGE", stock_type_id, domain_prefix="derived-coverage"
        )
        source = DataSource(name=f"prep-derived-source-{uuid4().hex[:8]}", is_active=True)
        session.add_all([instrument, source])
        await session.flush()
        daily = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=source.id,
            feed_scope="derived-coverage-source",
            session_code="regular",
            timeframe=Timeframe.D1.value,
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="derived-split-v1",
            is_canonical=True,
            is_active=True,
        )
        session.add(daily)
        await session.flush()
        session.add(
            MarketSeriesDefault(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1.value,
                is_adjusted=True,
                market_series_id=daily.id,
                selection_reason="test_selected_source",
            )
        )
        for day in (
            datetime(2025, 1, 3, 14, 30, tzinfo=UTC),
            datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
        ):
            session.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=source.id,
                    market_series_id=daily.id,
                    timeframe=Timeframe.D1,
                    ts=day,
                    session="regular",
                    scope_key="test:derived-source",
                    open=Decimal("20"),
                    high=Decimal("22"),
                    low=Decimal("19"),
                    close=Decimal("21"),
                    is_adjusted=True,
                    adjustment_basis="split_adjusted",
                    adjustment_version="derived-split-v1",
                )
            )
        await session.flush()
        weekly_request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": instrument.id},
                "datasets": ["history"],
                "timeframe": "W1",
            }
        )
        monthly_request = weekly_request.model_copy(update={"timeframe": Timeframe.MN})
        weekly_parent = await create_data_preparation_request(
            session, owner_user_id=813, request=weekly_request
        )
        monthly_parent = await create_data_preparation_request(
            session, owner_user_id=814, request=monthly_request
        )
        weekly_parent_id, monthly_parent_id, instrument_id = (
            weekly_parent.id,
            monthly_parent.id,
            instrument.id,
        )
        await materialize_derived_timeframes(session, instrument.id, adjusted=True)
        for parent_id in (weekly_parent_id, monthly_parent_id):
            parent = await session.get(MarketRefreshJob, parent_id)
            dependency = next(
                item
                for item in parent.metadata_payload["data_preparation"]["dependencies"]
                if item["dataset"] == "history"
            )
            for child_id in dependency["job_ids"]:
                child = await session.get(MarketRefreshJob, child_id)
                child.status = "completed"
                child.result_summary = {"data_status": "ready", "bars_observed": 1}
        await session.commit()

    async with preparation_sessions() as session:
        weekly_parent = await session.get(MarketRefreshJob, weekly_parent_id)
        monthly_parent = await session.get(MarketRefreshJob, monthly_parent_id)
        weekly_first = await get_data_preparation_response(
            session, parent=weekly_parent, owner_user_id=813
        )
        monthly_first = await get_data_preparation_response(
            session, parent=monthly_parent, owner_user_id=814
        )
        weekly_dep = next(
            item for item in weekly_first.dependencies if item.dataset.value == "history"
        )
        monthly_dep = next(
            item for item in monthly_first.dependencies if item.dataset.value == "history"
        )
        assert weekly_dep.covered_ranges and monthly_dep.covered_ranges
        old_weekly_start = min(item.start_at for item in weekly_dep.covered_ranges)
        old_monthly_start = monthly_dep.covered_start
        assert weekly_dep.covered_ranges[0].market_series_id != daily.id
        assert monthly_dep.covered_ranges[0].market_series_id != daily.id
        await session.commit()

    async with preparation_sessions() as session:
        instrument = await session.get(Instrument, instrument_id)
        source_series = await session.get(MarketSeries, daily.id)
        for day in (
            datetime(2024, 12, 2, 14, 30, tzinfo=UTC),
            datetime(2024, 12, 3, 14, 30, tzinfo=UTC),
        ):
            session.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=source_series.data_source_id,
                    market_series_id=source_series.id,
                    timeframe=Timeframe.D1,
                    ts=day,
                    session="regular",
                    scope_key="test:derived-source-older",
                    open=Decimal("18"),
                    high=Decimal("19"),
                    low=Decimal("17"),
                    close=Decimal("18.5"),
                    is_adjusted=True,
                    adjustment_basis="split_adjusted",
                    adjustment_version="derived-split-v1",
                )
            )
        older_start = datetime(2024, 12, 2, 0, 0, tzinfo=UTC)
        older_end = datetime(2024, 12, 4, 4, 59, 59, 999999, tzinfo=UTC)
        daily_chunk = MarketRefreshJob(
            request_key=f"prep-derived-daily-continuation:{uuid4()}",
            capability="price_history",
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            start_at=older_start,
            end_at=older_end,
            status="queued",
            attempts=0,
            priority=10,
            next_attempt_at=datetime.now(UTC),
            metadata_payload={
                "data_preparation_child": {
                    "range_mode": "bounded",
                    "range_start": older_start.isoformat(),
                    "range_end": older_end.isoformat(),
                    "adjusted": True,
                    "derive_coarse_timeframes": True,
                    "source_provider": "massive",
                    "parent_refs": [],
                }
            },
        )
        session.add(daily_chunk)
        await session.flush()
        daily_chunk_id = daily_chunk.id
        await session.commit()

    async def fixed_chunk_plan(db, job, instrument, timeframe, preparation):
        return older_start, older_end, older_start, older_end, "massive", None

    async def local_fetch(db, instrument, timeframe, start, *, end=None, **kwargs):
        statement = select(OHLCVBar).where(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.ts >= start,
        )
        if end is not None:
            statement = statement.where(OHLCVBar.ts <= end)
        return list((await db.execute(statement.order_by(OHLCVBar.ts))).scalars())

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", preparation_sessions)
    monkeypatch.setattr(data_tasks, "_history_chunk_plan", fixed_chunk_plan)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", local_fetch)
    worker_result = await data_tasks.process_refresh_jobs({"redis": None}, limit=1)
    assert worker_result["completed"] == 1

    async with preparation_sessions() as session:
        completed_chunk = await session.get(MarketRefreshJob, daily_chunk_id)
        assert completed_chunk.status == "completed"
        assert completed_chunk.result_summary["data_status"] == "ready"
        weekly_parent = await session.get(MarketRefreshJob, weekly_parent_id)
        monthly_parent = await session.get(MarketRefreshJob, monthly_parent_id)
        weekly_second = await get_data_preparation_response(
            session, parent=weekly_parent, owner_user_id=813
        )
        monthly_second = await get_data_preparation_response(
            session, parent=monthly_parent, owner_user_id=814
        )
        weekly_dep = next(
            item for item in weekly_second.dependencies if item.dataset.value == "history"
        )
        monthly_dep = next(
            item for item in monthly_second.dependencies if item.dataset.value == "history"
        )
        assert min(item.start_at for item in weekly_dep.covered_ranges) < old_weekly_start
        assert monthly_dep.covered_start < old_monthly_start


async def test_opposite_ratio_requests_lock_shared_children_in_one_order(
    preparation_sessions, monkeypatch
):
    """Opposite leg and dataset order still coalesce without a PG deadlock."""
    from app.models.market_data_foundation import MarketRefreshJob
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services import data_preparation
    from app.services.data_preparation import create_data_preparation_request

    async with preparation_sessions() as session:
        stock_type_id, _ = await _create_instrument_types(session)
        xlb = _canonical_instrument("XLB", stock_type_id, domain_prefix="ratio-lock")
        spy = _canonical_instrument("SPY", stock_type_id, domain_prefix="ratio-lock")
        session.add_all([xlb, spy])
        await session.flush()
        xlb_id, spy_id = xlb.id, spy.id
        await session.commit()

    original_lock = data_preparation._acquire_enqueue_lock
    first_tasks: set[asyncio.Task] = set()
    first_keys: list[str] = []
    both_ready = asyncio.Event()

    async def synchronized_first_child_lock(db, request_key):
        task = asyncio.current_task()
        if task not in first_tasks and request_key.startswith(("prep-identity:", "prep-history:")):
            first_tasks.add(task)
            first_keys.append(request_key)
            if len(first_tasks) == 2:
                both_ready.set()
            await asyncio.wait_for(both_ready.wait(), timeout=15)
        return await original_lock(db, request_key)

    monkeypatch.setattr(data_preparation, "_acquire_enqueue_lock", synchronized_first_child_lock)
    requests = [
        (9101, xlb_id, ["history", "profile"], [xlb_id, spy_id]),
        (9102, spy_id, ["profile", "history"], [spy_id, xlb_id]),
    ]

    async def create_in_session(owner_id, target_id, datasets, legs):
        async with preparation_sessions() as session:
            request = DataEnsureRequest.model_validate(
                {
                    "target": {"kind": "instrument", "instrument_id": target_id},
                    "datasets": datasets,
                    "analysis": {
                        "kind": "ratio",
                        "legs": [{"instrument_id": value} for value in legs],
                    },
                }
            )
            parent = await create_data_preparation_request(
                session, owner_user_id=owner_id, request=request
            )
            await session.commit()
            return parent.id

    parent_ids = await asyncio.wait_for(
        asyncio.gather(*(create_in_session(*item) for item in requests)), timeout=45
    )
    assert len(first_keys) == 2
    assert first_keys[0] == first_keys[1]

    shared_parent_ids = set(parent_ids)
    history_maps, profile_maps = [], []
    async with preparation_sessions() as session:
        for parent_id, (_owner, _target, datasets, legs) in zip(parent_ids, requests, strict=True):
            parent = await session.get(MarketRefreshJob, parent_id)
            data = parent.metadata_payload["data_preparation"]
            assert data["normalized_request"]["datasets"] == datasets
            assert [
                leg["instrument_id"] for leg in data["normalized_request"]["analysis"]["legs"]
            ] == legs
            dependencies = data["dependencies"]
            assert {
                item["instrument_id"] for item in dependencies if item["dataset"] == "history"
            } == {xlb_id, spy_id}
            history_maps.append(
                {
                    item["instrument_id"]: item["job_ids"][0]
                    for item in dependencies
                    if item["dataset"] == "history"
                }
            )
            profile_maps.append(
                {
                    item["instrument_id"]: item["job_ids"][0]
                    for item in dependencies
                    if item["dataset"] == "profile"
                }
            )
        assert history_maps[0] == history_maps[1]
        assert profile_maps[0] == profile_maps[1]
        child_ids = set(history_maps[0].values()) | set(profile_maps[0].values())
        children = (
            await session.execute(
                select(MarketRefreshJob).where(MarketRefreshJob.id.in_(child_ids))
            )
        ).scalars()
        for child in children:
            refs = (child.metadata_payload.get("data_preparation_child") or {}).get(
                "parent_refs", []
            )
            assert shared_parent_ids.issubset({int(ref["parent_job_id"]) for ref in refs})


async def test_joined_deferred_history_keeps_native_retry_for_both_owners(
    preparation_sessions,
):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import (
        create_data_preparation_request,
        get_data_preparation_response,
    )
    from app.services.market_refresh_queue import claim_refresh_jobs, retry_refresh_job

    async with preparation_sessions() as session:
        stock_type_id, _ = await _create_instrument_types(session)
        instrument = _canonical_instrument("DEFER", stock_type_id, domain_prefix="deferred-join")
        session.add(instrument)
        await session.flush()
        instrument_id = instrument.id
        request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": instrument_id},
                "datasets": ["history"],
            }
        )
        first = await create_data_preparation_request(
            session, owner_user_id=9201, request=request, priority="background"
        )
        first_id = first.id
        child_id = next(
            item["job_ids"][0]
            for item in first.metadata_payload["data_preparation"]["dependencies"]
            if item["dataset"] == "history"
        )
        await session.commit()

    deferred_at = datetime.now(UTC)
    provider_retry_at = deferred_at + timedelta(minutes=20)
    async with preparation_sessions() as session:
        child = next(
            job for job in await claim_refresh_jobs(session, now=deferred_at) if job.id == child_id
        )
        await retry_refresh_job(
            session,
            child,
            "provider native window is full",
            now=deferred_at,
            retry_at=provider_retry_at,
        )
        await session.commit()

    async with preparation_sessions() as session:
        second = await create_data_preparation_request(
            session,
            owner_user_id=9202,
            request=DataEnsureRequest.model_validate(
                {
                    "target": {"kind": "instrument", "instrument_id": instrument_id},
                    "datasets": ["history"],
                }
            ),
            priority="visible",
        )
        second_id = second.id
        history = next(
            item
            for item in second.metadata_payload["data_preparation"]["dependencies"]
            if item["dataset"] == "history"
        )
        assert history["job_ids"] == [child_id]
        await session.commit()

    async with preparation_sessions() as session:
        child = await session.get(MarketRefreshJob, child_id)
        assert child.status == "deferred"
        assert child.priority == 10
        assert child.next_attempt_at == provider_retry_at
        assert child.metadata_payload["defer_reason"] == "provider_reset"
        assert child.metadata_payload["provider_retry_at"] == provider_retry_at.isoformat()
        refs = (child.metadata_payload.get("data_preparation_child") or {}).get("parent_refs", [])
        assert {first_id, second_id}.issubset({int(ref["parent_job_id"]) for ref in refs})
        for parent_id, owner_id in ((first_id, 9201), (second_id, 9202)):
            parent = await session.get(MarketRefreshJob, parent_id)
            response = await get_data_preparation_response(
                session, parent=parent, owner_user_id=owner_id
            )
            history = next(
                item for item in response.dependencies if item.dataset.value == "history"
            )
            assert response.has_pending_work is True
            assert history.status == "waiting"
            assert history.reason_code == "provider_reset"
            assert history.retry_at == provider_retry_at
        not_due = await claim_refresh_jobs(session, now=provider_retry_at - timedelta(minutes=1))
        assert all(job.id != child_id for job in not_due)


async def test_startup_maintenance_uses_shared_planner_and_catalogue_defaults(
    preparation_sessions, monkeypatch
):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.models.user import User
    from app.models.watchlist import Watchlist, WatchlistItem
    from app.models.workstation import Workspace, WorkspaceTab, WorkspaceWindow
    from app.services.data_preparation import _TRACKING_CAPABILITY
    from app.tasks import data_tasks

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", preparation_sessions)
    monkeypatch.setattr(data_tasks.settings, "E2E_SEED_MARKET_DATA", False)

    async with preparation_sessions() as session:
        stock_type_id, _ = await _create_instrument_types(session)
        saved = _canonical_instrument("SAVEDX", stock_type_id, domain_prefix="saved-list")
        panel = _canonical_instrument("PANELX", stock_type_id, domain_prefix="saved-panel")
        discovered = _canonical_instrument("DISCOVX", stock_type_id, domain_prefix="discovered")
        user = User(
            username=f"maintenance-{uuid4().hex[:8]}",
            email=f"maintenance-{uuid4().hex[:8]}@example.test",
            hashed_password="test-only",
        )
        session.add_all([saved, panel, discovered, user])
        await session.flush()
        watchlist = Watchlist(user_id=user.id, name="Saved", position=0)
        workspace = Workspace(
            user_id=user.id,
            name="Saved analysis",
            is_default=True,
            position=0,
            tabs=[
                WorkspaceTab(
                    stable_key="saved-analysis",
                    name="Saved analysis",
                    position=0,
                    windows=[
                        WorkspaceWindow(
                            instance_key="saved-panel",
                            tool_type="chart",
                            title="Saved panel",
                            configuration={"symbol": "PANELX", "timeframe": "D1"},
                            position=0,
                        )
                    ],
                )
            ],
        )
        session.add_all(
            [
                watchlist,
                workspace,
                WatchlistItem(watchlist=watchlist, instrument=saved, position=0),
            ]
        )
        saved_id, discovered_id = saved.id, discovered.id
        await session.commit()

    result = await data_tasks.enqueue_workstation_maintenance({}, include_discovered=True)
    assert result["mode"] == "shared_preparation_queue"
    assert result["default"] > 0
    assert result["background"] > 0

    async with preparation_sessions() as session:
        parents = list(
            (
                await session.execute(
                    select(MarketRefreshJob).where(
                        MarketRefreshJob.capability == _TRACKING_CAPABILITY
                    )
                )
            ).scalars()
        )
        assert parents
        assert all(
            (job.metadata_payload or {}).get("data_preparation", {}).get("role")
            == "system_maintenance_tracking"
            for job in parents
        )
        requests = [
            (job.metadata_payload or {}).get("data_preparation", {}).get("normalized_request", {})
            for job in parents
        ]
        assert any(
            request.get("target") == {"kind": "market_group", "group_key": "sp500-sectors"}
            and (request.get("analysis") or {}).get("kind") == "rrg"
            and (request.get("analysis") or {}).get("benchmark_symbol") == "SPY"
            for request in requests
        )
        assert any(
            (request.get("analysis") or {}).get("kind") == "ratio"
            and [leg.get("symbol") for leg in request["analysis"]["legs"]] == ["SPY", "RSP"]
            for request in requests
        )
        assert any(
            request.get("target", {}).get("kind") == "instrument"
            and request["target"].get("instrument_id") == saved_id
            and job.priority == 50
            for job in parents
            for request in [
                (job.metadata_payload or {})
                .get("data_preparation", {})
                .get("normalized_request", {})
            ]
        )
        assert any(
            request.get("target", {}).get("kind") == "instrument"
            and request["target"].get("symbol") == "PANELX"
            and job.priority == 50
            for job in parents
            for request in [
                (job.metadata_payload or {})
                .get("data_preparation", {})
                .get("normalized_request", {})
            ]
        )
        assert any(
            request.get("target", {}).get("kind") == "instrument"
            and request["target"].get("instrument_id") == discovered_id
            and request.get("datasets") == ["history"]
            and job.priority == 100
            for job in parents
            for request in [
                (job.metadata_payload or {})
                .get("data_preparation", {})
                .get("normalized_request", {})
            ]
        )


async def test_system_maintenance_identity_job_runs_without_an_owner_user(
    preparation_sessions, monkeypatch
):
    from app.routers import instruments as instruments_router
    from app.schemas.data_preparation import DataEnsureRequest
    from app.schemas.instrument_acquisition import (
        InstrumentAcquireResponse,
        QualifiedInstrumentIdentity,
    )
    from app.services.data_preparation import (
        create_maintenance_data_preparation_request,
    )
    from app.tasks import data_tasks

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", preparation_sessions)
    async with preparation_sessions() as session:
        parent = await create_maintenance_data_preparation_request(
            session,
            request=DataEnsureRequest.model_validate(
                {
                    "target": {"kind": "instrument", "symbol": "MNTNEW"},
                    "datasets": ["history"],
                }
            ),
            idempotency_key="test-system-identity-mntnew",
        )
        parent_id = parent.id
        identity_job_id = next(
            dependency["job_ids"][0]
            for dependency in parent.metadata_payload["data_preparation"]["dependencies"]
            if dependency["dataset"] == "identity"
        )
        await session.commit()

    async with preparation_sessions() as session:
        _, stock_type_id = await _create_instrument_types(session)
        canonical = _canonical_instrument("MNTNEW", stock_type_id, domain_prefix="maintenance")
        session.add(canonical)
        await session.flush()
        instrument_id = canonical.id
        await session.commit()

    calls = []

    async def fake_acquire(body, *, db, current_user):
        calls.append((body.symbol, current_user))
        return InstrumentAcquireResponse(
            request_id=body.request_id,
            status="resolved",
            instrument=QualifiedInstrumentIdentity(
                instrument_id=instrument_id,
                symbol="MNTNEW",
                identity_status="resolved",
                domain_key="maintenance:mntnew",
                primary_identifier_type="figi",
                primary_identifier_value="BBG000TESTMNTNEW",
            ),
        )

    monkeypatch.setattr(instruments_router, "acquire_instrument", fake_acquire)
    result = await data_tasks.process_refresh_jobs({}, limit=1)
    assert result["completed"] == 1
    assert calls == [("MNTNEW", None)]

    async with preparation_sessions() as session:
        from app.models.market_data_foundation import MarketRefreshJob

        parent = await session.get(MarketRefreshJob, parent_id)
        identity_job = await session.get(MarketRefreshJob, identity_job_id)
        assert identity_job.status == "completed"
        dependencies = parent.metadata_payload["data_preparation"]["dependencies"]
        identity = next(item for item in dependencies if item["dataset"] == "identity")
        history = next(item for item in dependencies if item["dataset"] == "history")
        assert identity["status"] == "queued"
        assert identity["instrument_id"] == instrument_id
        assert history["status"] == "queued"
        assert history["instrument_id"] == instrument_id
        assert history["job_ids"]


async def test_system_maintenance_reenters_shared_preparation_for_later_observation(
    preparation_sessions,
):
    from app.models.exchange import Exchange
    from app.models.listing import InstrumentListing
    from app.models.market_data_foundation import ExchangeSessionRule, MarketRefreshJob
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import create_maintenance_data_preparation_request
    from app.tasks.data_tasks import _maintenance_history_end_at

    first_observation = datetime(2026, 11, 6, 14, 5, tzinfo=UTC)
    same_observation = datetime(2026, 11, 6, 14, 55, tzinfo=UTC)
    later_observation = datetime(2026, 11, 6, 21, 5, tzinfo=UTC)
    closed_session_observation = datetime(2026, 11, 7, 14, 5, tzinfo=UTC)

    async with preparation_sessions() as session:
        stock_type_id, _ = await _create_instrument_types(session)
        exchange = Exchange(
            mic=f"XNAS{uuid4().hex[:4]}",
            name="Test Nasdaq",
            country_code="USA",
            timezone="America/New_York",
            market_open="09:30",
            market_close="16:00",
        )
        session.add(exchange)
        await session.flush()
        session.add_all(
            [
                ExchangeSessionRule(
                    exchange_id=exchange.id,
                    session_code="regular",
                    weekday=weekday,
                    opens_at=time(9, 30),
                    closes_at=time(16, 0),
                    crosses_midnight=False,
                    trade_date_rule="local_open_date",
                    valid_from=date(2020, 1, 1),
                    provenance={"test": True},
                )
                for weekday in range(5)
            ]
        )
        instrument = _canonical_instrument(
            "MAINTX", stock_type_id, domain_prefix="maintenance-refresh"
        )
        instrument.listings.append(
            InstrumentListing(
                exchange_id=exchange.id,
                ticker="MAINTX",
                currency="USD",
                is_primary=True,
                is_active=True,
            )
        )
        session.add(instrument)
        await session.flush()
        instrument_id = instrument.id
        exchange_id = exchange.id
        await session.commit()

    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument_id},
            "timeframe": "D1",
            "datasets": ["history"],
        }
    )

    async def create_at(observed_at):
        async with preparation_sessions() as session:
            published_end = await _maintenance_history_end_at(
                session,
                instrument_ids={instrument_id},
                timeframe=request.timeframe,
                observed_at=observed_at,
                primary_exchange_ids={instrument_id: {exchange_id}},
            )
            assert published_end is not None
            bounded_request = request.model_copy(update={"end_at": published_end})
            parent = await create_maintenance_data_preparation_request(
                session,
                request=bounded_request,
                idempotency_key=f"workstation:{published_end.isoformat()}:maintenancex-history",
                now=observed_at,
            )
            parent_id = parent.id
            child_id = parent.metadata_payload["data_preparation"]["dependencies"][0]["job_ids"][0]
            await session.commit()
        return parent_id, child_id

    first_parent, first_child = await create_at(first_observation)
    same_parent, same_child = await create_at(same_observation)
    later_parent, later_child = await create_at(later_observation)
    closed_parent, closed_child = await create_at(closed_session_observation)

    assert (same_parent, same_child) == (first_parent, first_child)
    assert later_parent != first_parent
    assert later_child != first_child
    assert (closed_parent, closed_child) == (later_parent, later_child)

    async with preparation_sessions() as session:
        parents = list(
            (
                await session.execute(
                    select(MarketRefreshJob).where(
                        MarketRefreshJob.id.in_([first_parent, later_parent])
                    )
                )
            ).scalars()
        )
        children = list(
            (
                await session.execute(
                    select(MarketRefreshJob).where(
                        MarketRefreshJob.id.in_([first_child, later_child])
                    )
                )
            ).scalars()
        )
        assert len(parents) == 2
        assert len(children) == 2
        assert all(job.capability == "price_history" for job in children)
        assert len({job.request_key for job in children}) == 2
