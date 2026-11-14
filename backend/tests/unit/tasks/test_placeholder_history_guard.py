"""Unresolved ETF-holding placeholders never reach a history provider.

ETF holdings without a ticker get a local ``HOLDING-<hash>`` symbol. Identity
resolution runs first and may replace it with a real ticker; if it does not,
the history child must end as a terminal ``unavailable`` outcome instead of
sending the invented symbol to a provider (a 400 that burns quota and retries).
"""

from datetime import UTC, datetime

import pytest

from app.models.market_data_foundation import MarketRefreshJob
from app.models.ohlcv import Timeframe
from app.tasks import data_tasks
from tests.unit.conftest import AsyncSessionAdapter


class _WorkerAdapter(AsyncSessionAdapter):
    def add(self, value):
        self._session.add(value)


class _WorkerSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_placeholder_symbol_history_child_is_unavailable_without_provider_call(
    db, instrument, monkeypatch
):
    instrument.symbol = "HOLDING-E1F6F0DFF8"
    instrument.identity_status = "provisional"
    end = datetime(2026, 11, 13, tzinfo=UTC)
    job = MarketRefreshJob(
        request_key="placeholder-history",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe=Timeframe.D1.value,
        start_at=None,
        end_at=end,
        priority=100,
        status="queued",
        attempts=0,
        next_attempt_at=end,
        metadata_payload={
            "data_preparation_child": {
                "dataset": "history",
                "instrument_id": instrument.id,
                "range_mode": "deepest_admitted",
                "range_end": end.isoformat(),
                "adjusted": True,
                "derive_coarse_timeframes": False,
            }
        },
    )
    db.add(job)
    db.commit()

    adapter = _WorkerAdapter(db)

    class _Context:
        def __call__(self):
            return _WorkerSessionContext(adapter)

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", _Context())

    async def must_not_plan(*_args, **_kwargs):
        raise AssertionError("placeholder symbol reached provider history planning")

    monkeypatch.setattr(data_tasks, "_plan_and_fetch_history_chunk", must_not_plan)

    claimed = False

    async def claim(_db, *, limit):
        nonlocal claimed
        if claimed:
            return []
        claimed = True
        job.status = "leased"
        job.lease_token = "placeholder-lease"
        job.leased_until = datetime(2026, 11, 14, tzinfo=UTC)
        return [job]

    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", claim)
    summaries = []

    async def complete(_db, completed_job, *, result_summary, **_kwargs):
        completed_job.status = "completed"
        summaries.append(result_summary)

    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete)

    result = await data_tasks.process_refresh_jobs({})

    assert result["completed"] == 1, result
    assert summaries == [
        {
            "preparation_status": "unavailable",
            "reason_code": "provider_symbol_unresolved",
            "instrument_id": instrument.id,
            "timeframe": "D1",
        }
    ]
