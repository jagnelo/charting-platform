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


def test_etf_classification_refresh_passes_snapshot_cap(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            return None

    calls: list[dict] = []

    async def fake_reconcile(_db, **kwargs):
        calls.append(kwargs)
        return {"processed": 0, "enriched": 0, "remaining": 0}

    monkeypatch.setattr(settings, "ETF_HOLDINGS_CLASSIFICATION_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CLASSIFICATION_MAX_PROFILES", 3)
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CLASSIFICATION_MAX_ENRICHMENTS_PER_PROFILE", 9)
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CLASSIFICATION_MAX_SNAPSHOTS_PER_PROFILE", 4)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.reconcile_all_etf_holdings_classifications",
        fake_reconcile,
    )

    result = asyncio.run(etf_holdings_tasks.reconcile_etf_holdings_classifications_task({}))

    assert result == {"processed": 0, "enriched": 0, "remaining": 0}
    assert calls == [
        {
            "max_profiles": 3,
            "max_enrichments_per_profile": 9,
            "max_snapshots_per_profile": 4,
        }
    ]


def test_benchmark_family_dated_refresh_fans_out_idempotent_units(monkeypatch):
    calls: list[tuple[str, tuple[object, ...], dict]] = []

    class Redis:
        async def enqueue_job(self, function, *args, **kwargs):
            calls.append((function, args, kwargs))
            return object()

    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_LOOKBACK_DATES", 1)
    monkeypatch.setattr(
        "app.services.benchmark_family_holdings_runs.completed_month_end_dates",
        lambda *, count: [date(2026, 7, 31)],
    )

    result = asyncio.run(
        etf_holdings_tasks.refresh_benchmark_family_holdings_task({"redis": Redis()})
    )

    assert result["queued"] == len(result["family_keys"])
    assert result["already_queued"] == 0
    assert all(call[0] == "task_refresh_scheduled_benchmark_family_holdings_unit" for call in calls)
    assert all(call[1][1] == "2026-07-31" for call in calls)
    assert all(call[1][2] == result["roles"] for call in calls)
    assert all(call[2]["_expires"] == 86_400 for call in calls)


def test_benchmark_family_dated_refresh_retains_per_root_queue_failures(monkeypatch):
    calls: list[tuple[str, tuple[object, ...], dict]] = []

    class Redis:
        async def enqueue_job(self, function, *args, **kwargs):
            calls.append((function, args, kwargs))
            if args[0] == "sp500":
                raise RuntimeError("redis queue unavailable for sp500")
            return object()

    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_LOOKBACK_DATES", 1)
    monkeypatch.setattr(
        "app.services.benchmark_family_holdings_runs.completed_month_end_dates",
        lambda *, count: [date(2026, 7, 31)],
    )

    result = asyncio.run(
        etf_holdings_tasks.refresh_benchmark_family_holdings_task({"redis": Redis()})
    )

    assert result["queue_error_count"] == 1
    assert result["queue_errors"] == [
        {
            "status": "queue_error",
            "family_key": "sp500",
            "requested_date": "2026-07-31",
            "error": "redis queue unavailable for sp500",
        }
    ]
    assert result["queued"] == len(result["family_keys"]) - 1
    assert len(calls) == len(result["family_keys"])


def test_benchmark_family_member_history_backfill_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_MEMBER_HISTORY_BACKFILL_ENABLED", False)

    result = asyncio.run(etf_holdings_tasks.backfill_benchmark_family_member_history_task({}))

    assert result == {
        "skipped": True,
        "reason": "benchmark family member-history backfill disabled",
    }


def test_benchmark_family_member_history_backfill_queues_existing_snapshots(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    queued: list[tuple[int, str]] = []

    async def fake_plan(_db, **kwargs):
        assert kwargs["max_snapshots"] == 2
        return {
            "family_keys": ["sp500"],
            "roles": ["cap_weight", "equal_weight", "value", "growth"],
            "max_snapshots": 2,
            "limited": True,
            "available_snapshot_count": 3,
            "selected_snapshot_count": 2,
            "undated_snapshot_count": 1,
            "continuity_by_symbol": {
                "SPY": {
                    "status": "gapped",
                    "gap_count": 1,
                }
            },
            "snapshots": [
                {"snapshot_id": 10, "composition_date": date(2026, 7, 31)},
                {"snapshot_id": 11, "composition_date": date(2026, 6, 30)},
            ],
        }

    async def fake_queue(_db, _redis, snapshot_ids, *, max_instruments, end):
        assert max_instruments == 5000
        queued.append((snapshot_ids[0], end.isoformat()))
        return {
            "queued": 2,
            "already_queued": 1,
            "unresolved_count": 3,
            "queue_error_count": 0,
            "queue_errors": [],
        }

    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_MEMBER_HISTORY_BACKFILL_ENABLED", True)
    monkeypatch.setattr(settings, "BENCHMARK_FAMILY_MEMBER_HISTORY_BACKFILL_MAX_SNAPSHOTS", 2)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(
        "app.services.benchmark_family_history.plan_benchmark_family_snapshot_history_refresh",
        fake_plan,
    )
    monkeypatch.setattr(
        "app.services.benchmark_family_history.queue_snapshot_member_history",
        fake_queue,
    )

    result = asyncio.run(
        etf_holdings_tasks.backfill_benchmark_family_member_history_task({"redis": object()})
    )

    assert result["selected_snapshot_count"] == 2
    assert result["available_snapshot_count"] == 3
    assert result["undated_snapshot_count"] == 1
    assert result["continuity_by_symbol"] == {
        "SPY": {
            "status": "gapped",
            "gap_count": 1,
        }
    }
    assert result["queued"] == 4
    assert result["already_queued"] == 2
    assert result["unresolved_count"] == 6
    assert [item["snapshot_id"] for item in result["snapshot_results"]] == [10, 11]
    assert [item["queued"] for item in result["snapshot_results"]] == [2, 2]
    assert queued == [
        (10, "2026-07-31T23:59:59.999999+00:00"),
        (11, "2026-06-30T23:59:59.999999+00:00"),
    ]
