from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.data_source import DataSource
from app.models.market_data_foundation import MarketRefreshJob
from app.models.provider_observation import InstrumentProfileSnapshot
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.schemas.data_preparation import DataEnsureRequest
from app.services.data_preparation import (
    _analysis_required_start,
    _profile_is_fresh,
    _resolve_requested_instruments,
    create_data_preparation_request,
    create_maintenance_data_preparation_request,
    expand_resolved_identity_dependency,
    get_data_preparation_response,
)
from app.services.instrument_mastering import reconcile_instrument_profile
from app.services.market_refresh_queue import claim_refresh_jobs
from tests.unit.conftest import AsyncSessionAdapter


def test_monthly_rrg_priority_floor_includes_both_lookbacks_and_result_tail():
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": 1},
            "timeframe": "MN",
            "analysis": {"kind": "rrg"},
        }
    )
    assert request.analysis.required_raw_bars == 50
    assert _analysis_required_start(request, now=datetime(2026, 11, 6, tzinfo=UTC)) == datetime(
        2022, 10, 1, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_preparation_request_uses_tracking_parent_and_shared_history_children(db, instrument):
    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "timeframe": "MN",
            "adjusted": True,
            "start_at": "2024-01-01T00:00:00Z",
            "end_at": "2026-11-01T00:00:00Z",
        }
    )
    plan = await _resolve_requested_instruments(async_db, request)
    assert plan.instrument_ids == [instrument.id]
    assert plan.unresolved_symbols == []
    assert plan.reason_code is None
    parent = await create_data_preparation_request(
        async_db, owner_user_id=81, request=request, priority="visible"
    )
    assert parent.metadata_payload["data_preparation"]["dependencies"], parent.metadata_payload
    await async_db.commit()

    metadata = parent.metadata_payload["data_preparation"]
    assert (
        metadata["reason_code"] is None
    ), f"reason={metadata['reason_code']} target={request.target!r}"
    assert parent.capability == "data_preparation_request"
    assert parent.status == "tracking"
    assert metadata["owner_user_id"] == 81
    assert len(metadata["dependencies"]) == 1, metadata
    dependency = metadata["dependencies"][0]
    assert dependency["dataset"] == "history"
    assert dependency["job_ids"] == sorted(dependency["job_ids"])
    child_jobs = list(
        (
            await async_db.execute(
                select(MarketRefreshJob).where(MarketRefreshJob.id.in_(dependency["job_ids"]))
            )
        ).scalars()
    )
    assert {job.timeframe for job in child_jobs} == {"D1", "MN"}
    assert all(job.capability == "price_history" for job in child_jobs)
    monthly = next(job for job in child_jobs if job.timeframe == "MN")
    assert monthly.metadata_payload["data_preparation_child"]["derived_only"] is True
    assert monthly.metadata_payload["data_preparation_child"]["wait_for_job_ids"]
    claimed = await claim_refresh_jobs(async_db, now=datetime.now(UTC))
    claimed_ids = {job.id for job in claimed}
    assert set(dependency["job_ids"]).issubset(claimed_ids)
    assert parent.id not in claimed_ids


@pytest.mark.asyncio
async def test_required_industry_is_field_sensitive_and_accepts_only_sourced_sic_fallback(
    db, instrument
):
    async_db = AsyncSessionAdapter(db)
    now = datetime.now(UTC)
    generic = DataSource(name="alpaca")
    massive = DataSource(name="massive")
    db.add_all([generic, massive])
    db.flush()
    for source in (generic, massive):
        db.add(
            ProviderPolicy(
                data_source_id=source.id,
                capability=ProviderCapability.INSTRUMENT_METADATA,
                is_enabled=True,
                freshness_seconds=3600,
            )
        )
    db.add_all(
        [
            InstrumentProfileSnapshot(
                instrument_id=instrument.id,
                data_source_id=generic.id,
                provider_symbol=instrument.symbol,
                observed_at=now,
                fetched_at=now,
                profile_hash="generic-profile",
                payload={"provider": "alpaca", "extra": {"sector": "Technology"}},
            ),
            InstrumentProfileSnapshot(
                instrument_id=instrument.id,
                data_source_id=massive.id,
                provider_symbol=instrument.symbol,
                observed_at=now,
                fetched_at=now,
                profile_hash="massive-sic-profile",
                payload={
                    "provider": "massive",
                    "extra": {"sic_code": 3571, "sic_description": "Electronic computers"},
                },
            ),
        ]
    )
    await async_db.flush()

    assert await _profile_is_fresh(async_db, instrument.id, now=now)
    # A fresh generic snapshot with no industry is not sufficient.
    db.delete(
        db.execute(
            select(InstrumentProfileSnapshot).where(
                InstrumentProfileSnapshot.data_source_id == massive.id
            )
        ).scalar_one()
    )
    await async_db.flush()
    assert not await _profile_is_fresh(
        async_db, instrument.id, now=now, required_profile_fields=["industry"]
    )
    # The exact Massive SIC pair is a valid SEC_SIC industry source; a sector
    # label alone and a SIC description without its code are not.
    db.add(
        InstrumentProfileSnapshot(
            instrument_id=instrument.id,
            data_source_id=massive.id,
            provider_symbol=instrument.symbol,
            observed_at=now,
            fetched_at=now,
            profile_hash="massive-valid-sic-profile",
            payload={
                "provider": "massive",
                "extra": {"sic_code": 3571, "sic_description": "Electronic computers"},
            },
        )
    )
    await async_db.flush()
    assert await _profile_is_fresh(
        async_db, instrument.id, now=now, required_profile_fields=["industry"]
    )


def test_legacy_massive_sic_fallback_keeps_its_native_classification():
    from app.services.instrument_mastering import _value_from_snapshot

    payload = {
        "provider": "massive",
        "classification_system": "GICS",
        "extra": {
            "sic_code": "3571",
            "sic_description": "Electronic computers",
            # A stale generic classification label cannot relabel the native
            # SIC source as GICS when no explicit industry value was stored.
            "classification_system": "GICS",
        },
    }

    assert _value_from_snapshot(payload, "industry") == "Electronic computers"
    assert _value_from_snapshot(payload, "classification_system") == "SEC_SIC"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "massive_extra",
    [
        {"sic_code": "3571", "sic_description": "Electronic computers"},
        {
            "sic_code": "3571",
            "sic_description": "Electronic computers",
            "industry": "Electronic computers",
            "classification_system": "SEC_SIC",
            "industry_evidence": {
                "provider": "massive",
                "source_field": "sic_description",
                "sic_code": "3571",
                "classification_system": "SEC_SIC",
            },
        },
    ],
)
async def test_reconciled_sic_industry_keeps_its_snapshot_provider_and_timing(
    db, instrument, monkeypatch, massive_extra
):
    async_db = AsyncSessionAdapter(db)
    massive = DataSource(name="massive")
    alpaca = DataSource(name="alpaca")
    db.add_all([massive, alpaca])
    db.flush()
    observed_at = datetime(2026, 11, 6, 14)
    fetched_at = datetime(2026, 11, 6, 14, 1)
    db.add_all(
        [
            InstrumentProfileSnapshot(
                instrument_id=instrument.id,
                data_source_id=massive.id,
                provider_symbol=instrument.symbol,
                observed_at=observed_at,
                fetched_at=fetched_at,
                profile_hash="massive-sic",
                payload={
                    "provider": "massive",
                    "symbol": instrument.symbol,
                    "extra": massive_extra,
                },
            ),
            InstrumentProfileSnapshot(
                instrument_id=instrument.id,
                data_source_id=alpaca.id,
                provider_symbol=instrument.symbol,
                observed_at=datetime(2026, 11, 6, 15),
                fetched_at=datetime(2026, 11, 6, 15, 1),
                profile_hash="newer-alpaca",
                payload={
                    "provider": "alpaca",
                    "symbol": instrument.symbol,
                    "extra": {"sector": "Technology"},
                },
            ),
        ]
    )
    await async_db.flush()
    monkeypatch.setattr(
        "app.services.instrument_mastering.resolve_provider_chain",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    provider_name="massive",
                    policy=SimpleNamespace(effective_score=1.0),
                ),
                SimpleNamespace(
                    provider_name="alpaca",
                    policy=SimpleNamespace(effective_score=0.5),
                ),
            ]
        ),
    )

    profile = await reconcile_instrument_profile(async_db, instrument)

    assert profile is not None
    assert profile.provider == "alpaca"
    assert profile.extra["industry"] == "Electronic computers"
    assert profile.extra["classification_system"] == "SEC_SIC"
    assert profile.extra["industry_evidence"] == {
        "provider": "massive",
        "source_field": "sic_description",
        "classification_system": "SEC_SIC",
        "observed_at": observed_at.isoformat(),
        "fetched_at": fetched_at.isoformat(),
        "sic_code": "3571",
    }


@pytest.mark.asyncio
async def test_required_profile_fields_are_durable_and_part_of_shared_job_dedupe(db, instrument):
    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["profile"],
            "required_profile_fields": ["industry"],
        }
    )
    first = await create_data_preparation_request(
        async_db, owner_user_id=91, request=request, priority="visible"
    )
    second = await create_data_preparation_request(
        async_db, owner_user_id=92, request=request, priority="default"
    )
    first_profile_dependency = next(
        item
        for item in first.metadata_payload["data_preparation"]["dependencies"]
        if item["dataset"] == "profile"
    )
    second_profile_dependency = next(
        item
        for item in second.metadata_payload["data_preparation"]["dependencies"]
        if item["dataset"] == "profile"
    )
    first_job = await async_db.get(MarketRefreshJob, first_profile_dependency["job_ids"][0])
    second_job = await async_db.get(MarketRefreshJob, second_profile_dependency["job_ids"][0])
    assert first_job.id == second_job.id
    assert first_job.metadata_payload["data_preparation_child"]["required_profile_fields"] == [
        "industry"
    ]
    assert first_job.metadata_payload["data_preparation_child"]["refresh_profile"] is True


@pytest.mark.asyncio
async def test_shared_parent_refs_are_read_only_after_the_dataset_advisory_lock(
    db, instrument, monkeypatch
):
    from app.services import data_preparation

    events: list[tuple[str, str]] = []
    real_lock = data_preparation._acquire_enqueue_lock
    real_read = data_preparation._existing_parent_refs

    async def record_lock(session, request_key):
        events.append(("lock", request_key))
        await real_lock(session, request_key)

    async def record_read(session, request_key):
        events.append(("read", request_key))
        return await real_read(session, request_key)

    monkeypatch.setattr(data_preparation, "_acquire_enqueue_lock", record_lock)
    monkeypatch.setattr(data_preparation, "_existing_parent_refs", record_read)
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
        }
    )
    await create_data_preparation_request(
        AsyncSessionAdapter(db), owner_user_id=901, request=request
    )

    for index, event in enumerate(events):
        if event[0] == "read":
            assert events[index - 1] == ("lock", event[1])


@pytest.mark.asyncio
async def test_background_history_is_partial_until_durable_backfill_finishes(db, instrument):
    now = datetime.now(UTC)
    parent = MarketRefreshJob(
        request_key="tracking-background-history-test",
        capability="data_preparation_request",
        status="tracking",
        next_attempt_at=now,
        metadata_payload={
            "data_preparation": {
                "role": "owner_request_tracking",
                "request_id": "background-history-request",
                "owner_user_id": 902,
                "target": {"kind": "instrument", "instrument_id": instrument.id},
                "version": 1,
                "last_progress_at": now.isoformat(),
                "dependencies": [
                    {
                        "dependency_id": "history-dependency",
                        "dataset": "history",
                        "instrument_id": instrument.id,
                        "status": "partial",
                        "updated_at": now.isoformat(),
                        "job_ids": [501],
                        "background_job_ids": [502],
                    }
                ],
            }
        },
    )
    foreground = MarketRefreshJob(
        id=501,
        request_key="foreground-history-test",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe="D1",
        status="completed",
        next_attempt_at=now,
        result_summary={
            "data_status": "partial",
            "chunk_coverage_status": "ready",
            "bars_observed": 10,
            "requested_start": "2026-10-01T00:00:00+00:00",
            "requested_end": "2026-10-15T00:00:00+00:00",
            "covered_start": "2026-10-01T04:00:00+00:00",
            "covered_end": "2026-10-14T04:00:00+00:00",
            "coverage_scopes": [
                {
                    "data_source_id": 1,
                    "market_series_id": 11,
                    "adjustment_basis": "split_adjusted",
                    "adjustment_version": "v1",
                    "is_adjusted": True,
                }
            ],
        },
        metadata_payload={},
    )
    background = MarketRefreshJob(
        id=502,
        request_key="background-history-test",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe="D1",
        status="queued",
        next_attempt_at=now,
        metadata_payload={},
    )
    db.add_all([parent, foreground, background])
    db.flush()
    async_db = AsyncSessionAdapter(db)

    partial = await get_data_preparation_response(async_db, parent=parent, owner_user_id=902)
    assert partial.dependencies[0].status == "partial"
    assert partial.dependencies[0].reason_code == "history_backfill_pending"
    assert partial.has_pending_work is True
    assert partial.dependencies[0].covered_ranges[0].market_series_id == 11

    background.status = "completed"
    background.result_summary = {"range_coverage_status": "ready", "data_status": "ready"}
    db.flush()
    complete = await get_data_preparation_response(async_db, parent=parent, owner_user_id=902)
    assert complete.dependencies[0].status == "ready"
    assert complete.has_pending_work is False

    # A provider wait remains real work, but the owner response exposes its
    # actual deadline so the shared client can stop short polling.
    retry_at = now + timedelta(minutes=20)
    background.status = "deferred"
    background.next_attempt_at = retry_at
    background.metadata_payload = {"defer_reason": "provider_reset"}
    db.flush()
    deferred = await get_data_preparation_response(async_db, parent=parent, owner_user_id=902)
    assert deferred.status == "partial"
    assert deferred.has_pending_work is True
    assert deferred.dependencies[0].reason_code == "provider_reset"
    assert deferred.dependencies[0].retry_at == retry_at

    # A runnable sibling continuation must not be hidden behind the deferred
    # job's deadline; the shared client should continue ordinary progress polls.
    runnable = MarketRefreshJob(
        id=503,
        request_key="runnable-background-history-test",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe="D1",
        status="queued",
        next_attempt_at=now,
        metadata_payload={},
    )
    db.add(runnable)
    payload = dict(parent.metadata_payload)
    data = dict(payload["data_preparation"])
    dependency = dict(data["dependencies"][0])
    dependency["background_job_ids"] = [502, 503]
    data["dependencies"] = [dependency]
    payload["data_preparation"] = data
    parent.metadata_payload = payload
    db.flush()

    mixed = await get_data_preparation_response(async_db, parent=parent, owner_user_id=902)
    assert mixed.dependencies[0].status == "partial"
    assert mixed.dependencies[0].reason_code == "history_backfill_pending"
    assert mixed.dependencies[0].retry_at is None
    assert mixed.has_pending_work is True

    # Older stored/fixture response payloads remain valid without the additive
    # lifecycle bit and default fail-safe to no known pending queue work.
    from app.schemas.data_preparation import DataEnsureResponse

    legacy_response = DataEnsureResponse.model_validate(
        complete.model_dump(exclude={"has_pending_work"})
    )
    assert legacy_response.has_pending_work is False


@pytest.mark.asyncio
async def test_partial_history_and_unavailable_holdings_have_no_pending_work(db, instrument):
    now = datetime.now(UTC)
    parent = MarketRefreshJob(
        request_key="tracking-independent-datasets-test",
        capability="data_preparation_request",
        status="tracking",
        next_attempt_at=now,
        metadata_payload={
            "data_preparation": {
                "role": "owner_request_tracking",
                "request_id": "independent-dataset-request",
                "owner_user_id": 903,
                "target": {"kind": "instrument", "instrument_id": instrument.id},
                "version": 1,
                "last_progress_at": now.isoformat(),
                "dependencies": [
                    {
                        "dependency_id": "history-dependency",
                        "dataset": "history",
                        "instrument_id": instrument.id,
                        "status": "queued",
                        "updated_at": now.isoformat(),
                        "job_ids": [601],
                    },
                    {
                        "dependency_id": "holdings-dependency",
                        "dataset": "holdings",
                        "instrument_id": instrument.id,
                        "status": "queued",
                        "updated_at": now.isoformat(),
                        "job_ids": [602],
                    },
                    {
                        "dependency_id": "final-partial-history-dependency",
                        "dataset": "history",
                        "instrument_id": instrument.id,
                        "status": "partial",
                        "reason_code": "history_coverage_partial",
                        "updated_at": now.isoformat(),
                        "job_ids": [],
                    },
                ],
            }
        },
    )
    history = MarketRefreshJob(
        id=601,
        request_key="history-independent-dataset-test",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe="D1",
        status="completed",
        next_attempt_at=now,
        result_summary={"data_status": "ready"},
        metadata_payload={},
    )
    holdings = MarketRefreshJob(
        id=602,
        request_key="holdings-independent-dataset-test",
        instrument_id=instrument.id,
        capability="etf_holdings_preparation",
        status="completed",
        next_attempt_at=now,
        result_summary={
            "preparation_status": "unavailable",
            "reason_code": "holdings_issuer_not_supported",
        },
        metadata_payload={},
    )
    db.add_all([parent, history, holdings])
    db.flush()

    async_db = AsyncSessionAdapter(db)
    retry_at = now + timedelta(minutes=35)
    holdings.status = "deferred"
    holdings.next_attempt_at = retry_at
    holdings.metadata_payload = {"defer_reason": "provider_reset"}
    deferred_holdings = await get_data_preparation_response(
        async_db, parent=parent, owner_user_id=903
    )
    assert deferred_holdings.status == "partial"
    assert deferred_holdings.has_pending_work is True
    holdings_outcome = next(
        item for item in deferred_holdings.dependencies if item.dataset.value == "holdings"
    )
    assert holdings_outcome.status == "waiting"
    assert holdings_outcome.retry_at == retry_at

    holdings.status = "completed"
    holdings.next_attempt_at = now
    holdings.result_summary = {
        "preparation_status": "unavailable",
        "reason_code": "holdings_issuer_not_supported",
    }
    holdings.metadata_payload = {}
    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=903)

    assert response.status == "partial"
    assert response.has_pending_work is False
    assert {item.dependency_id: item.status for item in response.dependencies} == {
        "history-dependency": "ready",
        "holdings-dependency": "unavailable",
        "final-partial-history-dependency": "partial",
    }
    final_history = next(
        item
        for item in response.dependencies
        if item.dependency_id == "final-partial-history-dependency"
    )
    assert final_history.status == "partial"
    assert final_history.reason_code == "history_coverage_partial"
    assert sum(item.status == "ready" for item in response.dependencies) == 1


@pytest.mark.asyncio
async def test_data_preparation_idempotency_is_owner_scoped_and_payload_bound(db, instrument):
    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {"target": {"kind": "instrument", "instrument_id": instrument.id}, "datasets": ["history"]}
    )
    first = await create_data_preparation_request(
        async_db,
        owner_user_id=81,
        request=request,
        idempotency_key="same-request",
    )
    second = await create_data_preparation_request(
        async_db,
        owner_user_id=81,
        request=request,
        idempotency_key="same-request",
    )
    assert first.id == second.id

    different = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "timeframe": "W1",
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_data_preparation_request(
            async_db,
            owner_user_id=81,
            request=different,
            idempotency_key="same-request",
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_system_maintenance_uses_shared_planner_without_owner_status_access(db, instrument):
    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {"target": {"kind": "instrument", "instrument_id": instrument.id}, "datasets": ["history"]}
    )
    first = await create_maintenance_data_preparation_request(
        async_db,
        request=request,
        idempotency_key="daily-core:2026-11-06:instrument-1",
        priority="background",
    )
    second = await create_maintenance_data_preparation_request(
        async_db,
        request=request,
        idempotency_key="daily-core:2026-11-06:instrument-1",
        priority="background",
    )

    assert first.id == second.id
    data = first.metadata_payload["data_preparation"]
    assert data["role"] == "system_maintenance_tracking"
    assert data["owner_user_id"] is None
    assert data["dependencies"][0]["dataset"] == "history"
    with pytest.raises(HTTPException) as exc_info:
        await get_data_preparation_response(async_db, parent=first, owner_user_id=1)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_poll_hides_tracking_job_from_a_different_owner(db, instrument):
    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {"target": {"kind": "instrument", "instrument_id": instrument.id}, "datasets": ["history"]}
    )
    parent = await create_data_preparation_request(async_db, owner_user_id=81, request=request)
    with pytest.raises(HTTPException) as exc_info:
        await get_data_preparation_response(async_db, parent=parent, owner_user_id=82)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_parent_dependencies_survive_commit_and_fresh_session_reload():
    """Nested JSON is replaced, not mutated through SQLAlchemy's old value."""
    from app.database import Base
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=True)
    try:
        with sessions() as seed:
            asset_class = AssetClass(name="Equity", description="Equity instruments")
            seed.add(asset_class)
            seed.flush()
            stock_type = InstrumentType(name="Stock", asset_class_id=asset_class.id)
            seed.add(stock_type)
            seed.flush()
            selected = Instrument(
                symbol="PERSIST",
                name="Persistence fixture",
                currency="USD",
                instrument_type_id=stock_type.id,
                is_active=True,
            )
            seed.add(selected)
            seed.commit()
            selected_id = selected.id

        with sessions() as writer:
            request = DataEnsureRequest.model_validate(
                {
                    "target": {"kind": "instrument", "instrument_id": selected_id},
                    "datasets": ["history"],
                }
            )
            parent = await create_data_preparation_request(
                AsyncSessionAdapter(writer), owner_user_id=91, request=request
            )
            parent_id = parent.id
            await AsyncSessionAdapter(writer).commit()

        with sessions() as reader:
            persisted = reader.get(MarketRefreshJob, parent_id)
            assert persisted is not None
            preparation = persisted.metadata_payload["data_preparation"]
            assert len(preparation["dependencies"]) == 1
            assert preparation["dependencies"][0]["dataset"] == "history"
            assert preparation["dependencies"][0]["job_ids"]
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.asyncio
async def test_unknown_symbol_late_expands_history_after_acquisition_resolution(
    db, instrument_type
):
    from app.models.asset_class import InstrumentType
    from app.models.instrument import Instrument

    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate({"target": {"kind": "instrument", "symbol": "LATE"}})
    parent = await create_data_preparation_request(async_db, owner_user_id=93, request=request)
    second_parent = await create_data_preparation_request(
        async_db, owner_user_id=94, request=request
    )
    dependencies = parent.metadata_payload["data_preparation"]["dependencies"]
    identity = next(item for item in dependencies if item["dataset"] == "identity")
    history = next(item for item in dependencies if item["dataset"] == "history")
    assert history["status"] == "waiting"
    assert history["reason_code"] == "identity_dependency_pending"
    identity_job = db.get(MarketRefreshJob, identity["job_ids"][0])
    second_identity = next(
        item
        for item in second_parent.metadata_payload["data_preparation"]["dependencies"]
        if item["dataset"] == "identity"
    )
    assert second_identity["job_ids"] == identity["job_ids"]
    assert len(identity_job.metadata_payload["data_preparation_child"]["parent_refs"]) == 2
    assert identity_job.capability == "instrument_metadata"
    assert identity_job.metadata_payload["data_preparation_child"]["symbol"] == "LATE"

    etf_type = InstrumentType(name="ETF", asset_class_id=instrument_type.asset_class_id)
    db.add(etf_type)
    await async_db.flush()
    canonical = Instrument(
        symbol="LATE",
        name="Late canonical identity",
        currency="USD",
        instrument_type_id=etf_type.id,
        is_active=True,
        identity_status="resolved",
        domain_key="test:late-identity",
        primary_identifier_type="figi",
        primary_identifier_value="BBG000LATE00",
    )
    db.add(canonical)
    await async_db.flush()
    await expand_resolved_identity_dependency(
        async_db, identity_job=identity_job, instrument_id=canonical.id
    )
    await async_db.flush()

    persisted_parent = db.get(MarketRefreshJob, parent.id)
    expanded = persisted_parent.metadata_payload["data_preparation"]["dependencies"]
    history = next(item for item in expanded if item["dataset"] == "history")
    assert history["status"] == "queued"
    assert history["instrument_id"] == canonical.id
    child_jobs = [db.get(MarketRefreshJob, job_id) for job_id in history["job_ids"]]
    assert child_jobs
    assert all(job.instrument_id == canonical.id for job in child_jobs)
    assert all(job.capability == "price_history" for job in child_jobs)
    holdings = next(item for item in expanded if item["dataset"] == "holdings")
    assert holdings["instrument_id"] == canonical.id
    assert holdings["status"] == "queued"
    holdings_job = db.get(MarketRefreshJob, holdings["job_ids"][0])
    assert holdings_job.capability == "etf_holdings_preparation"
    assert holdings_job.metadata_payload["data_preparation_child"]["kind"] == "etf_holdings"
    second_expanded = db.get(MarketRefreshJob, second_parent.id).metadata_payload[
        "data_preparation"
    ]["dependencies"]
    second_history = next(item for item in second_expanded if item["dataset"] == "history")
    second_holdings = next(item for item in second_expanded if item["dataset"] == "holdings")
    assert second_history["job_ids"] == history["job_ids"]
    assert second_holdings["job_ids"] == holdings["job_ids"]


@pytest.mark.asyncio
async def test_group_and_ratio_requests_expand_each_canonical_member_and_leg(
    db, instrument, instrument_type
):
    from app.models.instrument import Instrument
    from app.models.workstation import MarketGroup, MarketGroupMember

    second = Instrument(
        symbol="MSFT",
        name="Microsoft Corporation",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    group = MarketGroup(stable_key="preparation-test-group", group_type="watchlist", name="Test")
    db.add_all([second, group])
    db.flush()
    db.add_all(
        [
            MarketGroupMember(market_group_id=group.id, instrument_id=instrument.id, position=0),
            MarketGroupMember(market_group_id=group.id, instrument_id=second.id, position=1),
        ]
    )
    db.flush()
    async_db = AsyncSessionAdapter(db)

    group_request = DataEnsureRequest.model_validate(
        {"target": {"kind": "market_group", "group_key": group.stable_key}, "datasets": ["history"]}
    )
    group_parent = await create_data_preparation_request(
        async_db, owner_user_id=101, request=group_request
    )
    group_dependencies = group_parent.metadata_payload["data_preparation"]["dependencies"]
    assert {item["instrument_id"] for item in group_dependencies} == {instrument.id, second.id}

    ratio_request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "analysis": {
                "kind": "ratio",
                "legs": [{"instrument_id": instrument.id}, {"symbol": "MSFT"}],
            },
        }
    )
    ratio_parent = await create_data_preparation_request(
        async_db, owner_user_id=102, request=ratio_request
    )
    ratio_dependencies = ratio_parent.metadata_payload["data_preparation"]["dependencies"]
    assert {item["instrument_id"] for item in ratio_dependencies} == {instrument.id, second.id}


@pytest.mark.asyncio
async def test_rrg_market_group_plans_all_sectors_and_explicit_spy_benchmark(db, instrument_type):
    from app.models.instrument import Instrument
    from app.models.workstation import MarketGroup, MarketGroupMember

    symbols = ["XLK", "XLY", "XLC", "XLF", "XLV", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB", "SPY"]
    instruments = [
        Instrument(
            symbol=symbol,
            name=symbol,
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        for symbol in symbols
    ]
    group = MarketGroup(
        stable_key="sp500-sectors",
        group_type="sector",
        name="S&P 500 Select Sector ETF proxies",
    )
    db.add_all([*instruments, group])
    db.flush()
    db.add_all(
        [
            MarketGroupMember(
                market_group_id=group.id,
                instrument_id=member.id,
                position=position,
            )
            for position, member in enumerate(instruments[:11])
        ]
    )
    db.flush()

    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "market_group", "group_key": "sp500-sectors"},
            "datasets": ["history"],
            "analysis": {"kind": "rrg", "benchmark_symbol": "SPY"},
        }
    )
    parent = await create_data_preparation_request(
        AsyncSessionAdapter(db), owner_user_id=901, request=request
    )
    history = [
        dependency
        for dependency in parent.metadata_payload["data_preparation"]["dependencies"]
        if dependency["dataset"] == "history"
    ]
    assert len(history) == 12
    assert {item["instrument_id"] for item in history} == {item.id for item in instruments}

    dedup_request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "market_group", "group_key": "sp500-sectors"},
            "datasets": ["history"],
            "analysis": {"kind": "rrg", "benchmark_symbol": "XLK"},
        }
    )
    dedup_parent = await create_data_preparation_request(
        AsyncSessionAdapter(db), owner_user_id=902, request=dedup_request
    )
    dedup_history = [
        dependency
        for dependency in dedup_parent.metadata_payload["data_preparation"]["dependencies"]
        if dependency["dataset"] == "history"
    ]
    assert len(dedup_history) == 11
    assert len({item["instrument_id"] for item in dedup_history}) == 11


@pytest.mark.asyncio
async def test_rrg_family_default_and_custom_uncached_benchmark_have_own_identity_chain(
    db, instrument, instrument_type
):
    from app.models.instrument import Instrument
    from app.models.workstation import MarketGroup

    family = MarketGroup(
        stable_key="sp500-family-preparation-test",
        group_type="benchmark_family",
        name="S&P 500 family",
        provenance={"proxy_mappings": {"cap_weight": {"symbol": "SPY"}}},
    )
    spy = Instrument(
        symbol="SPY",
        name="S&P 500 ETF",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add_all([family, spy])
    db.flush()
    async_db = AsyncSessionAdapter(db)

    family_request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "family", "family_key": family.stable_key},
            "datasets": ["history"],
            "analysis": {"kind": "rrg"},
        }
    )
    family_parent = await create_data_preparation_request(
        async_db, owner_user_id=910, request=family_request
    )
    family_history = [
        dependency
        for dependency in family_parent.metadata_payload["data_preparation"]["dependencies"]
        if dependency["dataset"] == "history"
    ]
    assert {item["instrument_id"] for item in family_history} == {spy.id}

    custom_request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "analysis": {"kind": "rrg", "benchmark_symbol": "CUSTOM"},
        }
    )
    custom_parent = await create_data_preparation_request(
        async_db, owner_user_id=911, request=custom_request
    )
    custom_dependencies = custom_parent.metadata_payload["data_preparation"]["dependencies"]
    identity = next(item for item in custom_dependencies if item["dataset"] == "identity")
    pending_history = next(
        item
        for item in custom_dependencies
        if item["dataset"] == "history" and item.get("symbol") == "CUSTOM"
    )
    assert identity["symbol"] == "CUSTOM"
    assert pending_history["status"] == "waiting"
    assert pending_history["depends_on"] == [identity["dependency_id"]]

    canonical = Instrument(
        symbol="CUSTOM",
        name="Custom RRG benchmark",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        identity_status="resolved",
        domain_key="test:custom-benchmark",
        primary_identifier_type="figi",
        primary_identifier_value="BBG000CUSTOM",
    )
    db.add(canonical)
    db.flush()
    identity_job = db.get(MarketRefreshJob, identity["job_ids"][0])
    await expand_resolved_identity_dependency(
        async_db, identity_job=identity_job, instrument_id=canonical.id
    )
    expanded = db.get(MarketRefreshJob, custom_parent.id).metadata_payload["data_preparation"][
        "dependencies"
    ]
    benchmark_history = next(
        item for item in expanded if item["dataset"] == "history" and item.get("symbol") == "CUSTOM"
    )
    target_history = next(
        item
        for item in expanded
        if item["dataset"] == "history" and item["instrument_id"] == instrument.id
    )
    assert benchmark_history["instrument_id"] == canonical.id
    assert benchmark_history["status"] == "queued"
    assert target_history["instrument_id"] == instrument.id


@pytest.mark.asyncio
async def test_ratio_preserves_known_leg_and_expands_only_unknown_denominator(
    db, instrument, instrument_type
):
    from app.models.instrument import Instrument

    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "analysis": {
                "kind": "ratio",
                "legs": [{"symbol": instrument.symbol}, {"symbol": "DENOM"}],
            },
        }
    )
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(async_db, owner_user_id=920, request=request)
    data = parent.metadata_payload["data_preparation"]
    identity = next(item for item in data["dependencies"] if item["dataset"] == "identity")
    assert identity["symbol"] == "DENOM"
    assert all(
        not (item["dataset"] == "identity" and item["symbol"] == instrument.symbol)
        for item in data["dependencies"]
    )
    pending = next(
        item
        for item in data["dependencies"]
        if item["dataset"] == "history" and item.get("symbol") == "DENOM"
    )
    assert pending["status"] == "waiting"

    denominator = Instrument(
        symbol="DENOM",
        name="Ratio denominator",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        identity_status="resolved",
        domain_key="test:ratio-denominator",
        primary_identifier_type="figi",
        primary_identifier_value="BBG000DENOM",
    )
    db.add(denominator)
    db.flush()
    identity_job = db.get(MarketRefreshJob, identity["job_ids"][0])
    await expand_resolved_identity_dependency(
        async_db, identity_job=identity_job, instrument_id=denominator.id
    )
    expanded = db.get(MarketRefreshJob, parent.id).metadata_payload["data_preparation"][
        "dependencies"
    ]
    denominator_history = next(
        item for item in expanded if item["dataset"] == "history" and item.get("symbol") == "DENOM"
    )
    assert denominator_history["instrument_id"] == denominator.id
    assert denominator_history["status"] == "queued"
    assert (
        sum(
            item["dataset"] == "history" and item["instrument_id"] == instrument.id
            for item in expanded
        )
        == 1
    )


@pytest.mark.asyncio
async def test_two_unknown_ratio_legs_keep_independent_late_dependencies(
    db, instrument, instrument_type
):
    from app.models.instrument import Instrument

    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "analysis": {
                "kind": "ratio",
                "legs": [{"symbol": "LEFT"}, {"symbol": "RIGHT"}],
            },
        }
    )
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(async_db, owner_user_id=930, request=request)
    data = parent.metadata_payload["data_preparation"]
    identities = {
        item["symbol"]: item for item in data["dependencies"] if item["dataset"] == "identity"
    }
    assert set(identities) == {"LEFT", "RIGHT"}
    assert len({job_id for item in identities.values() for job_id in item["job_ids"]}) == 2
    owner_view = await get_data_preparation_response(async_db, parent=parent, owner_user_id=930)
    assert owner_view.has_pending_work is True
    assert {
        item.symbol for item in owner_view.dependencies if item.dataset.value == "identity"
    } == {"LEFT", "RIGHT"}
    pending_by_symbol = {
        item["symbol"]: item
        for item in data["dependencies"]
        if item["dataset"] == "history" and item["status"] == "waiting"
    }
    assert set(pending_by_symbol) == {"LEFT", "RIGHT"}

    left = Instrument(
        symbol="LEFT",
        name="Left ratio leg",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        identity_status="resolved",
        domain_key="test:left-ratio-leg",
        primary_identifier_type="figi",
        primary_identifier_value="BBG000LEFT",
    )
    db.add(left)
    db.flush()
    left_job = db.get(MarketRefreshJob, identities["LEFT"]["job_ids"][0])
    await expand_resolved_identity_dependency(
        async_db, identity_job=left_job, instrument_id=left.id
    )
    expanded = db.get(MarketRefreshJob, parent.id).metadata_payload["data_preparation"][
        "dependencies"
    ]
    left_history = next(
        item for item in expanded if item["dataset"] == "history" and item.get("symbol") == "LEFT"
    )
    right_history = next(
        item for item in expanded if item["dataset"] == "history" and item.get("symbol") == "RIGHT"
    )
    assert left_history["instrument_id"] == left.id
    assert left_history["status"] == "queued"
    assert right_history["instrument_id"] is None
    assert right_history["status"] == "waiting"

    right = Instrument(
        symbol="RIGHT",
        name="Right ratio leg",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        identity_status="resolved",
        domain_key="test:right-ratio-leg",
        primary_identifier_type="figi",
        primary_identifier_value="BBG000RIGHT",
    )
    db.add(right)
    db.flush()
    right_job = db.get(MarketRefreshJob, identities["RIGHT"]["job_ids"][0])
    await expand_resolved_identity_dependency(
        async_db, identity_job=right_job, instrument_id=right.id
    )
    final_dependencies = db.get(MarketRefreshJob, parent.id).metadata_payload["data_preparation"][
        "dependencies"
    ]
    assert {
        item["symbol"]: (item["instrument_id"], item["status"])
        for item in final_dependencies
        if item["dataset"] == "history"
    } == {
        instrument.symbol: (instrument.id, "queued"),
        "LEFT": (left.id, "queued"),
        "RIGHT": (right.id, "queued"),
    }
