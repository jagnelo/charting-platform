from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services import etf_holdings_refresh as refresh


@pytest.mark.parametrize(
    ("source_quality", "expected"),
    [
        ("filing_reconstructed_holdings", "filing_reconstructed"),
        ("issuer_reported_dated_complete_holdings", "complete"),
        ("issuer_reported_complete_daily_holdings_csv", "complete"),
        ("issuer_reported_full_investment_holdings", "complete"),
    ],
)
def test_declared_source_quality_provides_conservative_completeness_evidence(
    source_quality, expected
):
    assert refresh._holdings_completeness_status({"source_quality": source_quality}, {}) == expected


def test_ambiguous_source_quality_remains_unknown_without_explicit_status():
    assert (
        refresh._holdings_completeness_status(
            {"source_quality": "issuer_reported_current_holdings"}, {}
        )
        == "unknown"
    )
    assert (
        refresh._holdings_completeness_status(
            {
                "source_quality": "issuer_reported_dated_complete_holdings",
                "completeness_status": "partial",
            },
            {},
        )
        == "partial"
    )


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

    async def fake_refresh(_db, _profile, *, requested_date, record_failure):
        assert record_failure is False
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


@pytest.mark.asyncio
async def test_dated_family_refresh_isolates_role_transaction_failures(monkeypatch):
    class Savepoint:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, _exc, _tb):
            if exc_type is not None:
                self.session.closed = False
            return False

    class Session:
        closed = False

        def begin_nested(self):
            return Savepoint(self)

        async def flush(self):
            return None

    async def fake_instrument(db, *, symbol, name):
        if db.closed:
            raise RuntimeError("closed transaction")
        if symbol == "QQQ":
            db.closed = True
            raise RuntimeError("provider integrity failure")
        return SimpleNamespace(symbol=symbol, name=name)

    async def fake_profile(_db, instrument):
        return SimpleNamespace(instrument=instrument, adapter_key="invesco", provider_aliases={})

    async def fake_probe(_db, _profile):
        return SimpleNamespace(status="ready", reason=None)

    async def fake_refresh(_db, profile, *, requested_date, record_failure):
        assert record_failure is False
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
        roles=["cap_weight", "equal_weight"],
    )

    assert summary["failed"] == 1
    assert summary["refreshed"] == 1
    assert [leg["status"] for leg in summary["legs"]] == ["failed", "refreshed"]
