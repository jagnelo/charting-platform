from __future__ import annotations

import asyncio
from datetime import date

from app.config import settings
from app.services.top_down_taxonomy import benchmark_family_proxy_symbols
from app.tasks import etf_holdings_tasks


def test_sec_backfill_task_prioritizes_configured_family_proxies(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            return None

    calls: list[dict] = []

    async def fake_backfill(_db, **kwargs):
        calls.append(kwargs)
        return {"status": "completed", "profiles": 0}

    monkeypatch.setattr(settings, "ETF_HOLDINGS_SEC_BACKFILL_ENABLED", True)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(
        "app.services.etf_holdings_edgar.backfill_all_sec_nport_holdings",
        fake_backfill,
    )

    result = asyncio.run(etf_holdings_tasks.backfill_sec_nport_holdings_task({}))

    assert result["status"] == "completed"
    assert calls == [
        {
            "priority_symbols": list(benchmark_family_proxy_symbols()),
            "max_profiles": settings.ETF_HOLDINGS_SEC_BACKFILL_MAX_PROFILES,
            "max_filings_per_etf": settings.ETF_HOLDINGS_SEC_BACKFILL_MAX_FILINGS_PER_ETF,
        }
    ]


def test_benchmark_family_dated_refresh_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED", False)

    result = asyncio.run(etf_holdings_tasks.refresh_benchmark_family_holdings_task({}))

    assert result == {"skipped": True, "reason": "benchmark family refresh disabled"}


def test_benchmark_family_dated_refresh_queues_member_history(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            return None

    calls: list[dict] = []
    queue_calls: list[tuple[object, list[int]]] = []

    async def fake_refresh(_db, **kwargs):
        calls.append(kwargs)
        return {
            "requested_dates": [kwargs["requested_dates"][0]],
            "family_keys": ["sp500"],
            "roles": ["cap_weight"],
            "refreshed": 1,
            "unavailable": 0,
            "failed": 0,
            "runs": [
                {
                    "families": [
                        {"legs": [{"status": "refreshed", "snapshot_id": 91}]}
                    ]
                }
            ],
        }

    async def fake_queue(_db, redis, snapshot_ids):
        queue_calls.append((redis, snapshot_ids))
        return {"status": "queued", "queued": 2, "already_queued": 0}

    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_LOOKBACK_DATES", 1)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.refresh_all_benchmark_family_holdings_for_dates",
        fake_refresh,
    )
    monkeypatch.setattr(
        "app.services.benchmark_family_history.queue_snapshot_member_history",
        fake_queue,
    )
    monkeypatch.setattr(
        "app.services.benchmark_family_holdings_runs.completed_month_end_dates",
        lambda *, count: [date(2026, 7, 31)],
    )

    result = asyncio.run(etf_holdings_tasks.refresh_benchmark_family_holdings_task({"redis": "r"}))

    assert calls == [{"requested_dates": [date(2026, 7, 31)]}]
    assert queue_calls == [("r", [91])]
    assert result["snapshot_ids"] == [91]
    assert result["history_queue"]["queued"] == 2
