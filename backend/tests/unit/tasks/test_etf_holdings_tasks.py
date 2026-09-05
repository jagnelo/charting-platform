from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.config import settings
from app.services.etf_holdings_capability import tier0_symbols
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


def test_etf_capability_canary_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_ENABLED", False)

    result = asyncio.run(etf_holdings_tasks.etf_holdings_capability_canary_task({}))

    assert result == {"skipped": True, "reason": "capability canary disabled"}


def test_default_capability_canary_covers_each_canonical_tier0_symbol_once():
    configured = [
        value.strip().upper()
        for value in str(settings.ETF_HOLDINGS_CAPABILITY_CANARY_SYMBOLS).split(",")
        if value.strip()
    ]

    assert configured
    assert len(configured) == len(set(configured))
    assert set(configured) == set(tier0_symbols())
    assert len(configured) == len(tier0_symbols())
    assert settings.ETF_HOLDINGS_CAPABILITY_CANARY_MAX_SYMBOLS >= len(tier0_symbols())


def test_etf_capability_canary_rejects_truncated_canonical_tier0_configuration(monkeypatch):
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_ENABLED", True)
    monkeypatch.setattr(
        settings, "ETF_HOLDINGS_CAPABILITY_CANARY_SYMBOLS", ",".join(tier0_symbols())
    )
    monkeypatch.setattr(
        settings,
        "ETF_HOLDINGS_CAPABILITY_CANARY_MAX_SYMBOLS",
        len(tier0_symbols()) - 1,
    )

    result = asyncio.run(etf_holdings_tasks.etf_holdings_capability_canary_task({}))

    assert result["skipped"] is True
    assert result["reason"] == "invalid canary configuration"
    assert result["requested"] == len(tier0_symbols())
    assert result["max_symbols"] == len(tier0_symbols()) - 1


@pytest.mark.parametrize(
    ("configured_symbols", "expected_requested"),
    [("", 0), ("DXJ,DXJ", 2)],
)
def test_etf_capability_canary_rejects_empty_or_duplicate_configuration(
    monkeypatch, configured_symbols, expected_requested
):
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_ENABLED", True)
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_SYMBOLS", configured_symbols)

    result = asyncio.run(etf_holdings_tasks.etf_holdings_capability_canary_task({}))

    assert result["skipped"] is True
    assert result["reason"] == "invalid canary configuration"
    assert result["requested"] == expected_requested
    assert "unique symbol" in result["configuration_error"]


def test_etf_capability_canary_passes_bounded_configuration(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            return None

    calls: list[dict] = []

    async def fake_canary(_db, **kwargs):
        calls.append(kwargs)
        return {"checked": 1}

    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_ENABLED", True)
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_SYMBOLS", "DXJ, NTSX")
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_MAX_SYMBOLS", 2)
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_FAILURE_THRESHOLD", 3)
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CAPABILITY_CANARY_COOLDOWN_SECONDS", 600)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.run_etf_holdings_capability_canaries", fake_canary
    )

    result = asyncio.run(etf_holdings_tasks.etf_holdings_capability_canary_task({}))

    assert result == {"checked": 1}
    assert calls == [
        {
            "symbols": ["DXJ", "NTSX"],
            "max_symbols": 2,
            "failure_threshold": 3,
            "cooldown_seconds": 600,
        }
    ]
