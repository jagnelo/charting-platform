from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.data_source import DataSource
from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketRefreshJob,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import (
    DatasetStatus,
    InstrumentDatasetState,
    InstrumentProfileSnapshot,
)
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.schemas.data_preparation import DataEnsureRequest
from app.services.data_preparation import (
    _analysis_required_start,
    _holdings_job_has_terminal_negative,
    _identity_job_has_terminal_negative,
    _profile_is_fresh,
    _resolve_requested_instruments,
    create_data_preparation_request,
    create_maintenance_data_preparation_request,
    expand_resolved_identity_dependency,
    get_data_preparation_response,
    load_owner_request,
)
from app.services.instrument_mastering import reconcile_instrument_profile
from app.services.market_refresh_queue import claim_refresh_jobs
from tests.unit.conftest import AsyncSessionAdapter


def _add_selected_cached_history(
    db, instrument, *, days, adjusted=True, currency="EUR", close_labelled=False
):
    instrument.currency = currency
    source = DataSource(name="retained-cache-test")
    db.add(source)
    db.flush()
    series = MarketSeries(
        instrument_id=instrument.id,
        data_source_id=source.id,
        feed_scope="retained-cache-test",
        session_code="regular",
        timeframe=Timeframe.D1.value,
        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED if adjusted else AdjustmentBasis.RAW,
        adjustment_version="retained-test-v1",
        is_canonical=True,
        is_active=True,
    )
    db.add(series)
    db.flush()
    db.add(
        MarketSeriesDefault(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            is_adjusted=adjusted,
            market_series_id=series.id,
            selection_reason="retained-cache-test",
        )
    )
    bars = []
    for day in days:
        bar = OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=source.id,
            market_series_id=series.id,
            timeframe=Timeframe.D1,
            ts=datetime(2026, 1, day, 21 if close_labelled else 0, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            volume=Decimal("100"),
            is_adjusted=adjusted,
            adjustment_basis="split_adjusted" if adjusted else "raw",
            adjustment_version="retained-test-v1",
            scope_key=f"series:{series.id}:regular",
        )
        bars.append(bar)
    db.add_all(bars)
    db.flush()
    return series, bars


def _history_request(instrument, *, start_day, end_day, adjusted=True):
    return DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "timeframe": "D1",
            "adjusted": adjusted,
            "start_at": f"2026-01-{start_day:02d}T00:00:00Z",
            "end_at": f"2026-01-{end_day:02d}T00:00:00Z",
        }
    )


def _qualify_test_instrument(instrument):
    instrument.identity_status = "resolved"
    instrument.domain_key = f"test:retained:{instrument.symbol}"
    instrument.primary_identifier_type = "figi"
    instrument.primary_identifier_value = "BBG000GENV001"


async def _create_previously_held_history_request(db, instrument):
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(
        async_db,
        owner_user_id=81,
        request=_history_request(instrument, start_day=1, end_day=5),
    )
    data = deepcopy(parent.metadata_payload["data_preparation"])
    dependency = data["dependencies"][0]
    child = db.get(MarketRefreshJob, dependency["job_ids"][0])
    child.status = "completed"
    child.result_summary = {
        "preparation_status": "held",
        "reason_code": "no_eligible_history_provider",
        "data_status": "empty",
    }
    dependency["status"] = "waiting"
    dependency["reason_code"] = "no_eligible_history_provider"
    data["status"] = "waiting"
    parent.metadata_payload = {"data_preparation": data}
    await async_db.commit()
    db.expire_all()
    return async_db, data["request_id"]


@pytest.mark.asyncio
async def test_fully_retained_selected_range_is_ready_without_provider_job(
    db, instrument, monkeypatch
):
    import app.services.data_preparation as preparation

    _qualify_test_instrument(instrument)
    selected, _ = _add_selected_cached_history(db, instrument, days=[1, 2, 3, 4, 5])

    async def no_external_dependency(*args, **kwargs):
        raise AssertionError("covered selected-series history must not enter provider admission")

    monkeypatch.setattr(preparation, "_enqueue_history_dependency", no_external_dependency)
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(
        async_db,
        owner_user_id=81,
        request=_history_request(instrument, start_day=1, end_day=5),
    )
    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)

    assert response.status == "ready"
    assert response.has_pending_work is False
    assert response.dependencies[0].status == "ready"
    assert response.dependencies[0].covered_start == datetime(2026, 1, 1, tzinfo=UTC)
    assert response.dependencies[0].covered_end == datetime(2026, 1, 5, tzinfo=UTC)
    assert response.dependencies[0].covered_ranges[0].market_series_id == selected.id
    assert response.dependencies[0].covered_ranges[0].data_source_id == selected.data_source_id
    assert response.dependencies[0].covered_ranges[0].adjustment_basis == "split_adjusted"
    assert parent.metadata_payload["data_preparation"]["dependencies"][0]["job_ids"] == []


@pytest.mark.asyncio
async def test_monthly_preparation_repairs_pending_derived_state_before_cache_reuse(db, instrument):
    from app.services.derived_timeframes import materialize_derived_timeframes

    _qualify_test_instrument(instrument)
    _add_selected_cached_history(db, instrument, days=[1, 2, 3, 4, 5])
    async_db = AsyncSessionAdapter(db)
    await materialize_derived_timeframes(async_db, instrument.id, adjusted=True)
    monthly_state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "MN:adj",
        )
        .one()
    )
    monthly_state.status = DatasetStatus.PENDING
    monthly_state.coverage_start = None
    monthly_state.coverage_end = None
    monthly_state.extra_data = {"derived_bar_count": 0}
    db.flush()

    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "timeframe": "MN",
            "adjusted": True,
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-01-05T00:00:00Z",
        }
    )
    parent = await create_data_preparation_request(async_db, owner_user_id=81, request=request)
    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)

    assert response.dependencies[0].status in {"partial", "queued", "ready"}
    assert monthly_state.status == DatasetStatus.FRESH
    assert monthly_state.coverage_start is not None
    assert monthly_state.coverage_end is not None
    assert monthly_state.extra_data["derived_bar_count"] > 0
    assert (
        any(
            job_id
            for dependency in parent.metadata_payload["data_preparation"]["dependencies"]
            for job_id in dependency["job_ids"]
        )
        or response.dependencies[0].status == "ready"
    )


@pytest.mark.asyncio
async def test_close_labelled_retained_range_is_ready_at_exact_bounds(db, instrument, monkeypatch):
    import app.services.data_preparation as preparation

    _qualify_test_instrument(instrument)
    selected, _ = _add_selected_cached_history(
        db, instrument, days=[2, 3, 4, 5], currency="USD", close_labelled=True
    )

    async def no_external_dependency(*args, **kwargs):
        raise AssertionError("complete retained range must not enter provider admission")

    monkeypatch.setattr(preparation, "_enqueue_history_dependency", no_external_dependency)
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "timeframe": "D1",
            "adjusted": True,
            "start_at": "2026-01-02T21:00:00Z",
            "end_at": "2026-01-05T21:00:00Z",
        }
    )
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(async_db, owner_user_id=81, request=request)
    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)

    assert response.status == "ready"
    assert response.has_pending_work is False
    assert response.dependencies[0].covered_start == datetime(2026, 1, 2, 21, tzinfo=UTC)
    assert response.dependencies[0].covered_end == datetime(2026, 1, 5, 21, tzinfo=UTC)
    assert response.dependencies[0].covered_ranges[0].market_series_id == selected.id


@pytest.mark.asyncio
async def test_missing_close_labelled_first_session_is_not_treated_as_ready(db, instrument):
    _qualify_test_instrument(instrument)
    _add_selected_cached_history(
        db, instrument, days=[3, 4, 5], currency="USD", close_labelled=True
    )
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history"],
            "timeframe": "D1",
            "adjusted": True,
            "start_at": "2026-01-02T21:00:00Z",
            "end_at": "2026-01-05T21:00:00Z",
        }
    )
    parent = await create_data_preparation_request(
        AsyncSessionAdapter(db), owner_user_id=81, request=request
    )
    dependency = parent.metadata_payload["data_preparation"]["dependencies"][0]
    children = [db.get(MarketRefreshJob, value) for value in dependency["job_ids"]]
    assert dependency["status"] == "partial"
    assert len(children) == 1
    assert children[0].start_at == datetime(2026, 1, 2, 21)


@pytest.mark.asyncio
async def test_existing_held_request_reprojects_ready_after_compatible_cache_arrives(
    db, instrument
):
    _qualify_test_instrument(instrument)
    async_db, request_id = await _create_previously_held_history_request(db, instrument)
    _add_selected_cached_history(db, instrument, days=[1, 2, 3, 4, 5])
    await async_db.commit()
    db.expire_all()

    parent = await load_owner_request(async_db, request_id=request_id, owner_user_id=81)
    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)

    assert response.status == "ready"
    assert response.has_pending_work is False
    assert response.dependencies[0].reason_code is None
    assert response.dependencies[0].covered_start == datetime(2026, 1, 1, tzinfo=UTC)
    assert response.dependencies[0].covered_end == datetime(2026, 1, 5, tzinfo=UTC)


@pytest.mark.asyncio
async def test_existing_held_request_keeps_partial_gaps_and_reason_after_cache_arrives(
    db, instrument
):
    _qualify_test_instrument(instrument)
    async_db, request_id = await _create_previously_held_history_request(db, instrument)
    _add_selected_cached_history(db, instrument, days=[3, 4, 5])
    await async_db.commit()
    db.expire_all()

    parent = await load_owner_request(async_db, request_id=request_id, owner_user_id=81)
    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)

    assert response.status == "partial"
    assert response.has_pending_work is False
    assert response.dependencies[0].status == "partial"
    assert response.dependencies[0].reason_code == "no_eligible_history_provider"
    assert response.dependencies[0].covered_start == datetime(2026, 1, 3, tzinfo=UTC)
    assert response.dependencies[0].covered_end == datetime(2026, 1, 5, tzinfo=UTC)


@pytest.mark.asyncio
async def test_zero_bar_no_transport_outcome_is_unavailable_with_admission_reason(db, instrument):
    async_db, request_id = await _create_previously_held_history_request(db, instrument)
    parent = await load_owner_request(async_db, request_id=request_id, owner_user_id=81)
    dependency = parent.metadata_payload["data_preparation"]["dependencies"][0]
    child = await async_db.get(MarketRefreshJob, dependency["job_ids"][0])
    child.status = "completed"
    child.result_summary = {
        "bars_observed": 0,
        "data_status": "empty",
        "chunk_coverage_status": None,
        "range_coverage_status": "missing",
        "reason_code": "no_eligible_history_provider",
    }
    await async_db.commit()

    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)

    assert response.status == "unavailable"
    assert response.has_pending_work is False
    assert response.dependencies[0].status == "unavailable"
    assert response.dependencies[0].reason_code == "no_eligible_history_provider"


@pytest.mark.asyncio
async def test_partial_retained_range_queues_only_missing_edge_and_reports_cache(db, instrument):
    _qualify_test_instrument(instrument)
    _add_selected_cached_history(db, instrument, days=[3, 4, 5])
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(
        async_db,
        owner_user_id=81,
        request=_history_request(instrument, start_day=1, end_day=5),
    )
    dependency = parent.metadata_payload["data_preparation"]["dependencies"][0]
    children = [db.get(MarketRefreshJob, value) for value in dependency["job_ids"]]
    assert dependency["status"] == "partial"
    assert len(children) == 1
    assert children[0].start_at == datetime(2026, 1, 1)
    assert children[0].end_at == datetime(2026, 1, 2)

    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)
    assert response.dependencies[0].status == "partial"
    assert response.has_pending_work is True
    assert response.dependencies[0].covered_start == datetime(2026, 1, 3, tzinfo=UTC)
    assert response.dependencies[0].covered_end == datetime(2026, 1, 5, tzinfo=UTC)


@pytest.mark.asyncio
async def test_retained_internal_gap_is_reported_and_only_gap_is_queued(db, instrument):
    _qualify_test_instrument(instrument)
    selected, _ = _add_selected_cached_history(db, instrument, days=[1, 2, 8, 9])
    alternate = MarketSeries(
        instrument_id=instrument.id,
        data_source_id=selected.data_source_id,
        feed_scope="alternate-cache-test",
        session_code="regular",
        timeframe=Timeframe.D1.value,
        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
        adjustment_version="alternate-test-v1",
        is_canonical=True,
        is_active=True,
    )
    db.add(alternate)
    db.flush()
    db.add_all(
        [
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=selected.data_source_id,
                market_series_id=alternate.id,
                timeframe=Timeframe.D1,
                ts=datetime(2026, 1, day, tzinfo=UTC),
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                volume=Decimal("100"),
                is_adjusted=True,
                adjustment_basis="split_adjusted",
                adjustment_version="alternate-test-v1",
                scope_key=f"series:{alternate.id}:regular",
            )
            for day in range(3, 8)
        ]
    )
    db.flush()
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(
        async_db,
        owner_user_id=81,
        request=_history_request(instrument, start_day=1, end_day=9),
    )
    dependency = parent.metadata_payload["data_preparation"]["dependencies"][0]
    children = [db.get(MarketRefreshJob, value) for value in dependency["job_ids"]]
    assert len(children) == 1
    assert children[0].start_at == datetime(2026, 1, 3)
    assert children[0].end_at == datetime(2026, 1, 7)
    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=81)
    assert response.dependencies[0].status == "partial"
    assert len(response.dependencies[0].covered_ranges) == 2
    assert response.dependencies[0].covered_start is None
    assert response.dependencies[0].covered_end is None


@pytest.mark.asyncio
async def test_incompatible_adjustment_basis_does_not_satisfy_retained_history(db, instrument):
    _qualify_test_instrument(instrument)
    _add_selected_cached_history(db, instrument, days=[1, 2, 3], adjusted=True)
    async_db = AsyncSessionAdapter(db)
    parent = await create_data_preparation_request(
        async_db,
        owner_user_id=81,
        request=_history_request(instrument, start_day=1, end_day=3, adjusted=False),
    )
    dependency = parent.metadata_payload["data_preparation"]["dependencies"][0]
    children = [db.get(MarketRefreshJob, value) for value in dependency["job_ids"]]
    assert dependency["status"] == "queued"
    assert dependency["covered_ranges"] == []
    assert len(children) == 1
    assert (children[0].start_at, children[0].end_at) == (
        datetime(2026, 1, 1),
        datetime(2026, 1, 3),
    )


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
async def test_screener_universe_reuses_engine_membership_without_scope_widening(
    db, user, instrument, instrument_type, screener
):
    from app.models.basket import Basket, BasketMember
    from app.models.screener import ScreenerDefinition
    from app.models.user import User
    from app.models.watchlist import Watchlist, WatchlistItem
    from app.services.screener_engine import _resolve_universe_members

    async_db = AsyncSessionAdapter(db)
    ids, reason = await _resolve_universe_members(async_db, screener)
    assert ids == [instrument.id]
    assert reason is None

    owned_watchlist = Watchlist(user_id=user.id, name="Owned")
    owned_basket = Basket(user_id=user.id, name="Owned basket")
    db.add_all([owned_watchlist, owned_basket])
    db.flush()
    db.add_all(
        [
            WatchlistItem(watchlist_id=owned_watchlist.id, instrument_id=instrument.id),
            BasketMember(basket_id=owned_basket.id, instrument_id=instrument.id),
        ]
    )
    db.flush()
    valid_screens = [
        ScreenerDefinition(
            user_id=user.id,
            name="Custom member",
            conditions={},
            universe_type="custom",
            universe_instrument_ids=[instrument.id],
            timeframe="D1",
        ),
        ScreenerDefinition(
            user_id=user.id,
            name="Owned watchlist",
            conditions={},
            universe_type="watchlist",
            universe_watchlist_id=owned_watchlist.id,
            timeframe="D1",
        ),
        ScreenerDefinition(
            user_id=user.id,
            name="Owned basket",
            conditions={},
            universe_type="basket",
            universe_basket_id=owned_basket.id,
            timeframe="D1",
        ),
        ScreenerDefinition(
            user_id=user.id,
            name="Owned asset class",
            conditions={},
            universe_type="asset_class",
            universe_asset_class_id=instrument_type.asset_class_id,
            timeframe="D1",
        ),
    ]
    db.add_all(valid_screens)
    db.flush()
    for valid in valid_screens:
        ids, reason = await _resolve_universe_members(async_db, valid)
        assert ids == [instrument.id]
        assert reason is None

    foreign = User(
        username="foreign-screener-owner",
        email="foreign-screener-owner@example.com",
        hashed_password="test-only",
        is_active=True,
    )
    db.add(foreign)
    db.flush()
    private_watchlist = Watchlist(user_id=foreign.id, name="Private")
    private_basket = Basket(user_id=foreign.id, name="Private basket")
    db.add_all([private_watchlist, private_basket])
    db.flush()
    db.add_all(
        [
            WatchlistItem(watchlist_id=private_watchlist.id, instrument_id=instrument.id),
            BasketMember(basket_id=private_basket.id, instrument_id=instrument.id),
        ]
    )
    db.flush()

    empty_custom = ScreenerDefinition(
        user_id=user.id,
        name="Empty custom",
        conditions={},
        universe_type="custom",
        universe_instrument_ids=[],
        timeframe="D1",
    )
    missing_watchlist = ScreenerDefinition(
        user_id=user.id,
        name="Missing watchlist",
        conditions={},
        universe_type="watchlist",
        universe_watchlist_id=None,
        timeframe="D1",
    )
    foreign_watchlist = ScreenerDefinition(
        user_id=user.id,
        name="Foreign watchlist",
        conditions={},
        universe_type="watchlist",
        universe_watchlist_id=private_watchlist.id,
        timeframe="D1",
    )
    foreign_basket = ScreenerDefinition(
        user_id=user.id,
        name="Foreign basket",
        conditions={},
        universe_type="basket",
        universe_basket_id=private_basket.id,
        timeframe="D1",
    )
    db.add_all([empty_custom, missing_watchlist, foreign_watchlist, foreign_basket])
    db.flush()

    for invalid, expected_reason in (
        (empty_custom, "empty_custom_universe"),
        (missing_watchlist, "watchlist_unavailable"),
        (foreign_watchlist, "watchlist_unavailable"),
        (foreign_basket, "basket_unavailable"),
    ):
        ids, reason = await _resolve_universe_members(async_db, invalid)
        assert ids == []
        assert reason == expected_reason


@pytest.mark.asyncio
async def test_screener_ensure_uses_saved_timeframe_and_returns_bounded_snapshot_parent(
    db, user, screener, instrument
):
    from app.schemas.data_preparation import DataEnsureRequest

    async_db = AsyncSessionAdapter(db)
    screener.timeframe = "W1"
    await async_db.flush()
    request = DataEnsureRequest.model_validate(
        {"target": {"kind": "screener", "screener_id": screener.id}, "datasets": ["history"]}
    )
    parent = await create_data_preparation_request(async_db, owner_user_id=user.id, request=request)
    data = parent.metadata_payload["data_preparation"]
    assert data["normalized_request"]["timeframe"] == "W1"
    assert data["target"].get("snapshot_id"), data
    assert data["target"]["snapshot_id"] == data["screener_snapshot"]["snapshot_id"]
    assert data["screener_snapshot"]["member_count"] == 1
    assert len(data["dependencies"]) == 1
    assert data["dependencies"][0]["reason_code"] == "screener_universe_expansion_pending"

    response = await get_data_preparation_response(async_db, parent=parent, owner_user_id=user.id)
    assert response.status == "queued"
    assert response.has_pending_work is True
    assert response.target["snapshot_id"] == data["screener_snapshot"]["snapshot_id"]

    explicit_mismatch = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "screener", "screener_id": screener.id},
            "datasets": ["history"],
            "timeframe": "D1",
        }
    )
    with pytest.raises(HTTPException) as mismatch:
        await create_data_preparation_request(
            async_db, owner_user_id=user.id, request=explicit_mismatch
        )
    assert mismatch.value.status_code == 422


@pytest.mark.asyncio
async def test_screener_idempotency_fingerprint_changes_with_saved_membership(
    db, user, screener, instrument, instrument_type
):
    from app.models.instrument import Instrument
    from app.schemas.data_preparation import DataEnsureRequest

    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "screener", "screener_id": screener.id},
            "datasets": ["history"],
        }
    )
    await create_data_preparation_request(
        async_db,
        owner_user_id=user.id,
        request=request,
        idempotency_key="saved-screener-view",
    )
    second = Instrument(
        symbol="MSFT",
        name="Microsoft",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(second)
    db.flush()
    screener.universe_type = "custom"
    screener.universe_instrument_ids = [instrument.id, second.id]
    db.flush()

    with pytest.raises(HTTPException) as conflict:
        await create_data_preparation_request(
            async_db,
            owner_user_id=user.id,
            request=request,
            idempotency_key="saved-screener-view",
        )
    assert conflict.value.status_code == 409


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
async def test_canonical_etv_without_profile_gets_independent_holdings_preparation(db):
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.etf_holdings import ETFProfile
    from app.models.instrument import Instrument

    asset_class = AssetClass(name="Exchange Traded Product", description="ETP fixtures")
    db.add(asset_class)
    db.flush()
    instrument_type = InstrumentType(name="Exchange Traded Vehicle", asset_class_id=asset_class.id)
    db.add(instrument_type)
    db.flush()
    instrument = Instrument(
        symbol="ETVTEST",
        name="Canonical exchange traded vehicle",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        is_synthetic=False,
        identity_status="resolved",
        domain_key="test:etv:canonical",
        primary_identifier_type="figi",
        primary_identifier_value="BBG000ETV001",
    )
    db.add(instrument)
    db.flush()

    request = DataEnsureRequest.model_validate(
        {"target": {"kind": "instrument", "instrument_id": instrument.id}}
    )
    parent = await create_data_preparation_request(
        AsyncSessionAdapter(db), owner_user_id=81, request=request
    )
    dependencies = parent.metadata_payload["data_preparation"]["dependencies"]
    holdings = next(item for item in dependencies if item["dataset"] == "holdings")
    assert holdings["status"] == "queued"
    assert db.query(ETFProfile).filter(ETFProfile.instrument_id == instrument.id).first() is None
    holdings_job = db.get(MarketRefreshJob, holdings["job_ids"][0])
    assert holdings_job.capability == "etf_holdings_preparation"


@pytest.mark.asyncio
async def test_synthetic_etv_holdings_stay_unavailable_without_blocking_history(db):
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument

    asset_class = AssetClass(name="Exchange Traded Product", description="ETP fixtures")
    db.add(asset_class)
    db.flush()
    instrument_type = InstrumentType(name="Exchange Traded Vehicle", asset_class_id=asset_class.id)
    db.add(instrument_type)
    db.flush()
    instrument = Instrument(
        symbol="SYNTHETV",
        name="Synthetic exchange traded vehicle",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        is_synthetic=True,
        identity_status="resolved",
        domain_key="test:etv:synthetic",
        primary_identifier_type="internal",
        primary_identifier_value="synthetic:etv",
    )
    db.add(instrument)
    db.flush()

    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["history", "holdings"],
        }
    )
    parent = await create_data_preparation_request(
        AsyncSessionAdapter(db), owner_user_id=81, request=request
    )
    dependencies = parent.metadata_payload["data_preparation"]["dependencies"]
    history = next(item for item in dependencies if item["dataset"] == "history")
    holdings = next(item for item in dependencies if item["dataset"] == "holdings")
    assert history["status"] == "queued"
    assert holdings["status"] == "unavailable"
    assert holdings["reason_code"] == "synthetic_instrument_not_supported"
    assert holdings["job_ids"] == []


@pytest.mark.asyncio
async def test_unverified_etv_waits_for_identity_before_holdings_dispatch(db):
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument

    asset_class = AssetClass(name="Exchange Traded Product", description="ETP fixtures")
    db.add(asset_class)
    db.flush()
    instrument_type = InstrumentType(name="Exchange Traded Vehicle", asset_class_id=asset_class.id)
    db.add(instrument_type)
    db.flush()
    instrument = Instrument(
        symbol="UNVERIFETV",
        name="Unverified exchange traded vehicle",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        is_synthetic=False,
        identity_status="provisional",
        domain_key=None,
        primary_identifier_type="internal",
        primary_identifier_value="symbol:UNVERIFETV",
    )
    db.add(instrument)
    db.flush()

    request = DataEnsureRequest.model_validate(
        {"target": {"kind": "instrument", "instrument_id": instrument.id}}
    )
    parent = await create_data_preparation_request(
        AsyncSessionAdapter(db), owner_user_id=81, request=request
    )
    dependencies = parent.metadata_payload["data_preparation"]["dependencies"]
    identity = next(item for item in dependencies if item["dataset"] == "identity")
    holdings = next(item for item in dependencies if item["dataset"] == "holdings")
    assert identity["status"] == "queued"
    assert holdings["status"] == "waiting"
    assert holdings["reason_code"] == "canonical_etf_instrument_required"
    assert holdings["job_ids"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("negative_status", ["held", "identity_conflict", "no_match"])
async def test_new_ensure_retries_legacy_terminal_negative_identity_child_once_per_scope(
    db, instrument, negative_status
):
    now = datetime(2026, 11, 7, 18, 56, tzinfo=UTC)
    instrument.identity_status = "provisional"
    instrument.domain_key = None
    instrument.primary_identifier_type = "internal"
    instrument.primary_identifier_value = f"symbol:{instrument.symbol}"
    await AsyncSessionAdapter(db).flush()
    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["identity", "profile"],
        }
    )

    first_parent = await create_data_preparation_request(
        async_db, owner_user_id=81, request=request, now=now
    )
    first_data = first_parent.metadata_payload["data_preparation"]
    first_identity = db.get(
        MarketRefreshJob,
        first_data["dependencies"][0]["job_ids"][0],
    )
    assert first_identity is not None
    first_identity.status = "completed"
    first_identity.finished_at = now
    # Preserve the legacy producer shape observed in the retained native
    # runtime: the prerequisite is in result_summary and metadata has no
    # native_usage_hold field.
    negative_result = {
        "preparation_status": negative_status,
        "reason_code": (
            "native_usage_bootstrap_not_admitted"
            if negative_status == "held"
            else "stable_identity_or_listing_authority_missing"
        ),
        "symbol": instrument.symbol,
    }
    if negative_status == "held":
        negative_result["native_usage_prerequisite"] = {
            "provider_name": "finnhub",
            "capability": "instrument_search",
            "operation": "search_instruments",
            "reason_code": "native_usage_bootstrap_not_admitted",
        }
    first_identity.result_summary = negative_result
    first_child_metadata = first_identity.metadata_payload["data_preparation_child"]
    assert "native_usage_hold" not in first_child_metadata
    await async_db.flush()

    second_parent = await create_data_preparation_request(
        async_db, owner_user_id=82, request=request, now=now
    )
    second_dependency = second_parent.metadata_payload["data_preparation"]["dependencies"][0]
    retry_id = second_dependency["job_ids"][0]
    retry_job = db.get(MarketRefreshJob, retry_id)
    assert retry_id != first_identity.id
    assert retry_job is not None
    assert retry_job.status == "queued"
    assert retry_job.result_summary is None
    assert first_identity.status == "completed"
    if negative_status == "held":
        assert (
            first_identity.result_summary["native_usage_prerequisite"]["provider_name"] == "finnhub"
        )
    else:
        assert first_identity.result_summary["preparation_status"] == negative_status

    third_parent = await create_data_preparation_request(
        async_db, owner_user_id=83, request=request, now=now
    )
    third_dependency = third_parent.metadata_payload["data_preparation"]["dependencies"][0]
    assert third_dependency["job_ids"] == [retry_id]
    retry_refs = retry_job.metadata_payload["data_preparation_child"]["parent_refs"]
    assert {ref["parent_job_id"] for ref in retry_refs} == {
        second_parent.id,
        third_parent.id,
    }


@pytest.mark.asyncio
async def test_new_ensure_recovers_held_holdings_child_and_coalesces_same_scope(db):
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument

    now = datetime(2026, 11, 7, 20, 56, tzinfo=UTC)
    asset_class = AssetClass(name="Exchange Traded Product", description="ETP recovery fixtures")
    db.add(asset_class)
    db.flush()
    instrument_type = InstrumentType(name="Exchange Traded Vehicle", asset_class_id=asset_class.id)
    db.add(instrument_type)
    db.flush()
    instrument = Instrument(
        symbol="ETVRECOVERY",
        name="Canonical exchange traded vehicle",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        is_synthetic=False,
        identity_status="resolved",
        domain_key="test:etv:recovery",
        primary_identifier_type="figi",
        primary_identifier_value="BBG000ETVREC001",
    )
    db.add(instrument)
    db.flush()

    async_db = AsyncSessionAdapter(db)
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": instrument.id},
            "datasets": ["holdings"],
        }
    )
    first_parent = await create_data_preparation_request(
        async_db, owner_user_id=81, request=request, now=now
    )
    first_dependency = first_parent.metadata_payload["data_preparation"]["dependencies"][0]
    previous_job = db.get(MarketRefreshJob, first_dependency["job_ids"][0])
    assert previous_job is not None
    previous_child = deepcopy(previous_job.metadata_payload["data_preparation_child"])
    previous_job.status = "completed"
    previous_job.finished_at = now
    previous_job.result_summary = {
        "preparation_status": "waiting",
        "reason_code": "issuer_request_held",
        "retry_at": None,
    }
    await async_db.flush()

    second_parent = await create_data_preparation_request(
        async_db, owner_user_id=82, request=request, now=now
    )
    second_dependency = second_parent.metadata_payload["data_preparation"]["dependencies"][0]
    recovery_id = second_dependency["job_ids"][0]
    recovery_job = db.get(MarketRefreshJob, recovery_id)
    assert recovery_id != previous_job.id
    assert recovery_job is not None
    assert recovery_job.status == "queued"
    recovery_child = recovery_job.metadata_payload["data_preparation_child"]
    assert recovery_child["request_id"].endswith(":recovery")
    assert previous_job.status == "completed"
    assert previous_job.result_summary == {
        "preparation_status": "waiting",
        "reason_code": "issuer_request_held",
        "retry_at": None,
    }
    assert previous_job.metadata_payload["data_preparation_child"] == previous_child

    third_parent = await create_data_preparation_request(
        async_db, owner_user_id=83, request=request, now=now
    )
    third_dependency = third_parent.metadata_payload["data_preparation"]["dependencies"][0]
    assert third_dependency["job_ids"] == [recovery_id]
    recovery_child = db.get(MarketRefreshJob, recovery_id).metadata_payload[
        "data_preparation_child"
    ]
    recovery_refs = recovery_child["parent_refs"]
    assert {ref["parent_job_id"] for ref in recovery_refs} == {
        second_parent.id,
        third_parent.id,
    }


def test_completed_negative_holdings_wait_respects_a_future_retry_time():
    now = datetime(2026, 11, 7, 20, 56, tzinfo=UTC)
    job = MarketRefreshJob(
        request_key="prep-holdings:negative",
        capability="etf_holdings_preparation",
        priority=50,
        status="completed",
        attempts=1,
        next_attempt_at=now,
        result_summary={
            "preparation_status": "waiting",
            "reason_code": "provider_rate_limited",
            "retry_at": (now + timedelta(minutes=10)).isoformat(),
        },
        metadata_payload={},
    )

    assert _holdings_job_has_terminal_negative(job, now=now) is False
    assert _holdings_job_has_terminal_negative(job, now=now + timedelta(minutes=10)) is True


def test_successful_completed_identity_child_is_not_a_recovery_candidate():
    job = MarketRefreshJob(
        request_key="prep-identity:ready",
        capability="instrument_metadata",
        priority=50,
        status="completed",
        attempts=1,
        next_attempt_at=datetime(2026, 11, 7, tzinfo=UTC),
        result_summary={"preparation_status": "ready", "instrument_id": 10},
        metadata_payload={"data_preparation_child": {"kind": "identity_profile"}},
    )
    assert _identity_job_has_terminal_negative(job) is False


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
@pytest.mark.parametrize(
    ("asset_class_name", "instrument_type_name"),
    [
        ("Equity", "ETF"),
        ("Index", "Index ETF"),
        ("Equity", "Mutual Fund"),
        ("Equity", "Closed-End Fund"),
        ("Exchange Traded Product", "Exchange Traded Vehicle"),
    ],
)
async def test_canonical_fund_types_plan_holdings_without_profile(
    db, asset_class_name, instrument_type_name
):
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.etf_holdings import ETFProfile
    from app.models.instrument import Instrument

    asset_class = db.query(AssetClass).filter_by(name=asset_class_name).one_or_none()
    if asset_class is None:
        asset_class = AssetClass(name=asset_class_name, description="Canonical fund fixture")
        db.add(asset_class)
        db.flush()
    instrument_type = InstrumentType(name=instrument_type_name, asset_class_id=asset_class.id)
    db.add(instrument_type)
    db.flush()
    instrument = Instrument(
        symbol=f"FUND{instrument_type.id}",
        name=f"Canonical {instrument_type_name}",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        is_synthetic=False,
        identity_status="resolved",
        domain_key=f"test:canonical-fund:{instrument_type.id}",
        primary_identifier_type="figi",
        primary_identifier_value=f"BBG{instrument_type.id:09d}",
    )
    db.add(instrument)
    db.flush()

    parent = await create_data_preparation_request(
        AsyncSessionAdapter(db),
        owner_user_id=81,
        request=DataEnsureRequest.model_validate(
            {"target": {"kind": "instrument", "instrument_id": instrument.id}}
        ),
    )

    dependencies = parent.metadata_payload["data_preparation"]["dependencies"]
    holdings = next(item for item in dependencies if item["dataset"] == "holdings")
    history = next(item for item in dependencies if item["dataset"] == "history")
    assert holdings["status"] == "queued"
    assert holdings["job_ids"]
    assert history["status"] == "queued"
    assert db.query(ETFProfile).filter_by(instrument_id=instrument.id).one_or_none() is None


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
