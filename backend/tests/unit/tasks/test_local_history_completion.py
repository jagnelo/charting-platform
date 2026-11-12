"""No-eligible-provider history plans complete from canonical local bars.

The helper must never call a provider: it reads local rows only. A window that
local bars fully cover is ready, a partly covered one is partial with gaps, and
only an instrument with no local bars at all keeps the provider-eligibility
failure (represented here by a None result).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.ohlcv import OHLCVBar, Timeframe
from app.tasks import data_tasks
from tests.unit.conftest import AsyncSessionAdapter

END = datetime(2026, 11, 10, tzinfo=UTC)


def _seed_daily(db, instrument, *, first: datetime, last: datetime, skip=()):
    """Seed one D1 bar per day from first to last inclusive, skipping given days."""
    day = first
    while day <= last:
        if day.date() not in skip:
            db.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=day,
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100.5"),
                    volume=Decimal("1000000"),
                    is_adjusted=True,
                )
            )
        day += timedelta(days=1)
    db.flush()


def _job(end_at=None):
    return SimpleNamespace(id=1, end_at=end_at)


async def _complete(db, instrument, preparation):
    return await data_tasks._local_history_completion(
        AsyncSessionAdapter(db),
        job=_job(),
        instrument=instrument,
        timeframe=Timeframe.D1,
        preparation=preparation,
    )


@pytest.mark.asyncio
async def test_default_window_covered_by_local_bars_is_ready_without_provider(db, instrument):
    max_bars = data_tasks.settings.PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS
    _seed_daily(
        db,
        instrument,
        first=END - timedelta(days=max_bars + 100),
        last=END,
    )

    outcome = await _complete(
        db,
        instrument,
        {"range_end": END.isoformat(), "adjusted": True},
    )

    assert outcome is not None
    assert outcome["preparation_status"] == "ready"
    assert outcome["reason_code"] is None
    assert outcome["local_only"] is True
    assert outcome["provider_plan_reason"] == "no_eligible_history_provider"
    assert outcome["missing_slices"] == []
    assert outcome["bars_observed"] > 0


@pytest.mark.asyncio
async def test_explicit_range_covered_by_local_bars_is_ready(db, instrument):
    _seed_daily(db, instrument, first=END - timedelta(days=400), last=END)
    start = END - timedelta(days=30)

    outcome = await _complete(
        db,
        instrument,
        {
            "range_start": start.isoformat(),
            "range_end": END.isoformat(),
            "adjusted": True,
        },
    )

    assert outcome is not None
    assert outcome["preparation_status"] == "ready"
    assert outcome["requested_start"] == start.isoformat()


@pytest.mark.asyncio
async def test_explicit_range_with_interior_gap_is_partial_with_gap_details(db, instrument):
    gap_day = (END - timedelta(days=15)).date()
    _seed_daily(
        db,
        instrument,
        first=END - timedelta(days=60),
        last=END,
        skip={gap_day + timedelta(days=offset) for offset in range(10)},
    )

    outcome = await _complete(
        db,
        instrument,
        {
            "range_start": (END - timedelta(days=30)).isoformat(),
            "range_end": END.isoformat(),
            "adjusted": True,
        },
    )

    assert outcome is not None
    assert outcome["preparation_status"] == "partial"
    assert outcome["reason_code"] == "history_coverage_partial"
    assert outcome["covered_start"] is not None
    assert outcome["covered_end"] is not None
    assert outcome["missing_slices"], "partial coverage must name its gaps"
    assert any(gap["start"].startswith(gap_day.isoformat()) for gap in outcome["missing_slices"])


@pytest.mark.asyncio
async def test_window_without_overlap_but_with_local_history_is_partial_not_failure(db, instrument):
    _seed_daily(db, instrument, first=END - timedelta(days=400), last=END - timedelta(days=300))
    start = END - timedelta(days=30)

    outcome = await _complete(
        db,
        instrument,
        {
            "range_start": start.isoformat(),
            "range_end": END.isoformat(),
            "adjusted": True,
        },
    )

    assert outcome is not None
    assert outcome["preparation_status"] == "partial"
    assert outcome["covered_start"] is None
    assert outcome["missing_slices"] == [{"start": start.isoformat(), "end": END.isoformat()}]


@pytest.mark.asyncio
async def test_symbol_without_any_local_data_still_fails(db, instrument):
    outcome = await _complete(
        db,
        instrument,
        {
            "range_start": (END - timedelta(days=30)).isoformat(),
            "range_end": END.isoformat(),
            "adjusted": True,
        },
    )

    assert outcome is None


def _no_provider_worker_job(now):
    return SimpleNamespace(
        id=77,
        capability="price_history",
        instrument_id=17,
        timeframe="D1",
        start_at=None,
        end_at=None,
        status="leased",
        next_attempt_at=now,
        lease_token="worker-lease",
        priority=10,
        request_key="data-preparation:test",
        metadata_payload={
            "data_preparation_child": {
                "range_mode": "deepest_admitted",
                "adjusted": True,
                "wait_for_job_ids": [],
            }
        },
    )


def _worker_session(job, instrument):
    from contextlib import nullcontext

    class Session:
        @property
        def no_autoflush(self):
            return nullcontext()

        async def execute(self, *_args, **_kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: job)

        async def flush(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _model, _instrument_id):
            return instrument

        async def refresh(self, _job):
            return None

        async def commit(self):
            return None

    return Session


async def _run_no_provider_worker(monkeypatch, local_outcome):
    from unittest.mock import AsyncMock

    from app.config import settings

    monkeypatch.setattr(
        data_tasks, "refresh_derived_timeframe_if_needed", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", False)
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    instrument = SimpleNamespace(id=17, symbol="SPY")
    job = _no_provider_worker_job(now)
    preparation = dict(job.metadata_payload["data_preparation_child"])
    chunk_plan = (None, None, None, None, None, "no_eligible_history_provider")
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", _worker_session(job, instrument))
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(side_effect=[[job], []]))
    monkeypatch.setattr(
        data_tasks,
        "_plan_and_fetch_history_chunk",
        AsyncMock(return_value=(chunk_plan, preparation, None, None, None, None)),
    )
    local = AsyncMock(return_value=local_outcome)
    monkeypatch.setattr(data_tasks, "_local_history_completion", local)
    complete = AsyncMock()
    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete)
    fetch = AsyncMock()
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", fetch)
    retry = AsyncMock()
    monkeypatch.setattr(data_tasks, "retry_refresh_job", retry)

    await data_tasks.process_refresh_jobs({})
    return complete, local, fetch, retry


@pytest.mark.asyncio
async def test_worker_completes_no_provider_plan_from_local_coverage(monkeypatch):
    ready = {"preparation_status": "ready", "reason_code": None, "local_only": True}
    complete, local, fetch, retry = await _run_no_provider_worker(monkeypatch, ready)

    local.assert_awaited_once()
    complete.assert_awaited_once()
    assert complete.await_args.kwargs["result_summary"] == ready
    fetch.assert_not_awaited()
    retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_keeps_provider_reason_when_no_local_data(monkeypatch):
    complete, local, _fetch, _retry = await _run_no_provider_worker(monkeypatch, None)

    local.assert_awaited_once()
    summary = complete.await_args.kwargs["result_summary"]
    assert summary["preparation_status"] == "waiting"
    assert summary["reason_code"] == "no_eligible_history_provider"
