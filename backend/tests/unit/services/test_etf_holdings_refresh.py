from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import etf_holdings_refresh as refresh


class _Result:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.flushes = 0

    async def execute(self, _statement):
        return next(self.responses)

    async def flush(self):
        self.flushes += 1


def _profile(symbol="DXJ"):
    return SimpleNamespace(
        id=7,
        adapter_key="wisdomtree",
        instrument=SimpleNamespace(symbol=symbol),
    )


def _state(*, status="failure", extra_data=None):
    return SimpleNamespace(
        status=status,
        extra_data=extra_data or {},
        last_checked_at=None,
        last_success_at=None,
        last_failure_at=None,
        failure_reason=None,
        row_count=None,
        resolved_count=None,
        unresolved_count=None,
        completeness_status=None,
    )


def _snapshot():
    return SimpleNamespace(
        composition_date=date(2026, 9, 3),
        published_at=datetime(2026, 9, 3, tzinfo=UTC),
        provenance="issuer_current_holdings",
        source_provider="wisdomtree",
        source_url="https://issuer.example/DXJ.csv",
        source_identifier="DXJ",
        completeness_status="complete",
        row_count=12,
        resolved_count=12,
        unresolved_count=0,
        extra_data={
            "artifact_identity_validation": {"status": "matched"},
            "source_tier": "issuer_native",
            "transport_kind": "file_export",
            "expected_cadence": "daily",
            "schema_fingerprint": "schema-v1",
        },
        parser_version="wisdomtree-csv-v1",
    )


@pytest.mark.asyncio
async def test_canary_success_records_latency_recovery_and_symbol_gated_capability(monkeypatch):
    profile = _profile()
    state = _state(status="failure", extra_data={"consecutive_failures": 2})
    db = _Session(
        [
            _Result(rows=[profile]),
            _Result(scalar=state),
            _Result(scalar=state),
        ]
    )

    async def fake_refresh(_db, _profile):
        return _snapshot()

    async def fake_success(_db, _profile, snapshot=None):
        assert snapshot is not None
        state.status = "success"
        state.last_checked_at = datetime.now(UTC)
        state.last_success_at = state.last_checked_at
        state.extra_data = {"consecutive_failures": 0}

    monkeypatch.setattr(refresh, "_refresh_adapter_route", fake_refresh)
    monkeypatch.setattr(refresh, "_record_success", fake_success)

    result = await refresh.run_etf_holdings_capability_canaries(
        db,
        symbols=["dxj", "DXJ", "NTSX"],
        max_symbols=1,
    )

    assert result["requested"] == 1
    assert result["checked"] == 1
    assert result["recovered"] == 1
    assert result["failed"] == 0
    report = result["reports"][0]
    assert report["status"] == "success"
    # A successful fetch cannot override the unresolved Tier 0 source audit.
    assert report["availability"] == "unavailable"
    assert report["recovered"] is True
    assert report["circuit_state"] == "closed"
    assert report["latency_ms"] >= 0
    assert state.extra_data["last_canary_status"] == "success"
    assert state.extra_data["last_canary_failure_class"] is None
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_canary_failure_persists_class_and_opens_circuit_at_threshold(monkeypatch):
    profile = _profile()
    state = _state(status="success")
    db = _Session([_Result(rows=[profile]), _Result(scalar=state), _Result(scalar=state)])

    async def failing_refresh(_db, _profile):
        raise ValueError("Issuer holdings route returned no parseable rows.")

    async def fake_failure(_db, _profile, failure):
        state.status = "failure"
        state.failure_reason = str(failure)
        state.extra_data = {"consecutive_failures": 1}

    monkeypatch.setattr(refresh, "_refresh_adapter_route", failing_refresh)
    monkeypatch.setattr(refresh, "_record_failure", fake_failure)

    result = await refresh.run_etf_holdings_capability_canaries(
        db,
        symbols=["DXJ"],
        max_symbols=1,
        failure_threshold=1,
        cooldown_seconds=600,
    )

    assert result["failed"] == 1
    report = result["reports"][0]
    assert report["status"] == "failure"
    assert report["failure_class"] == "empty_or_partial_source"
    assert report["circuit_state"] == "open"
    assert state.extra_data["last_canary_failure_class"] == "empty_or_partial_source"
    assert state.extra_data["circuit_open_until"] is not None


@pytest.mark.asyncio
async def test_canary_honors_open_circuit_without_fetching(monkeypatch):
    profile = _profile()
    open_until = datetime.now(UTC) + timedelta(hours=1)
    state = _state(extra_data={"circuit_open_until": open_until.isoformat()})
    db = _Session([_Result(rows=[profile]), _Result(scalar=state)])

    async def unexpected_refresh(_db, _profile):
        raise AssertionError("open-circuit canary must not fetch")

    monkeypatch.setattr(refresh, "_refresh_adapter_route", unexpected_refresh)

    result = await refresh.run_etf_holdings_capability_canaries(
        db,
        symbols=["DXJ"],
        max_symbols=1,
    )

    assert result["skipped"] == 1
    assert result["checked"] == 0
    assert result["reports"] == [
        {
            "symbol": "DXJ",
            "status": "circuit_open",
            "circuit_open_until": open_until.isoformat(),
        }
    ]
    assert state.status == "circuit_open"
    assert state.extra_data["last_canary_status"] == "circuit_open"


@pytest.mark.asyncio
async def test_canary_reports_missing_profiles_without_creating_generic_runtime_rows():
    db = _Session([_Result(rows=[])])

    result = await refresh.run_etf_holdings_capability_canaries(
        db,
        symbols=["DXJ"],
        max_symbols=1,
    )

    assert result["missing_profiles"] == 1
    assert result["reports"] == [{"symbol": "DXJ", "status": "missing_profile"}]
    assert db.flushes == 1
