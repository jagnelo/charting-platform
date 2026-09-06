from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services import etf_holdings_refresh as refresh


@pytest.mark.asyncio
async def test_dated_family_refresh_preserves_declared_history_route_evidence(monkeypatch):
    class Session:
        async def flush(self):
            return None

    async def fake_instrument(_db, *, symbol, name):
        return SimpleNamespace(symbol=symbol, name=name)

    async def fake_profile(_db, instrument):
        return SimpleNamespace(instrument=instrument, adapter_key="invesco", provider_aliases={})

    async def fake_probe(_db, _profile):
        return SimpleNamespace(status="ready", reason=None)

    async def fake_refresh(_db, _profile, *, requested_date):
        return SimpleNamespace(id=42, composition_date=requested_date)

    monkeypatch.setattr(refresh, "ensure_lightweight_etf_instrument", fake_instrument)
    monkeypatch.setattr(refresh, "ensure_etf_profile", fake_profile)
    monkeypatch.setattr(refresh, "_apply_known_route_metadata", lambda _profile: True)
    monkeypatch.setattr(refresh, "probe_etf_holdings_adapter_route", fake_probe)
    monkeypatch.setattr(refresh, "refresh_etf_holdings_for_date", fake_refresh)

    summary = await refresh.refresh_benchmark_family_holdings_for_date(
        Session(),
        family_key="nasdaq100",
        requested_date=date(2026, 6, 30),
        roles=["cap_weight"],
    )

    assert summary["legs"] == [
        {
            "role": "cap_weight",
            "symbol": "QQQ",
            "status": "refreshed",
            "snapshot_id": 42,
            "composition_date": date(2026, 6, 30),
            "history_route_status": "sec_filing_reconstruction",
            "history_route_provider": "sec",
            "history_route_policy": "latest_sec_filing_report_on_or_before_requested_date",
            "history_route_source_url": "https://data.sec.gov/submissions/CIK0001067839.json",
        }
    ]
