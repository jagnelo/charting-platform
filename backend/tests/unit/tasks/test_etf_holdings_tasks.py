from __future__ import annotations

import asyncio

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
