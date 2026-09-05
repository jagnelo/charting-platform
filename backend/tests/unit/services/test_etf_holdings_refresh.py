from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import httpx
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
        instrument=SimpleNamespace(symbol=symbol, name=f"{symbol} fixture"),
        provider_aliases={},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
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
    assert len(state.extra_data["canary_history"]) == 1
    assert state.extra_data["canary_history"][0]["status"] == "success"
    assert state.extra_data["canary_history"][0]["availability"] == "unavailable"
    assert state.extra_data["canary_history"][0]["symbol_audit_outcome"] == "unavailable"
    assert state.extra_data["canary_history"][0]["source_provider"] == "wisdomtree"
    assert state.extra_data["canary_history"][0]["source_url"].endswith("DXJ.csv")
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_refresh_route_rejects_future_metadata_before_snapshot_ingestion(monkeypatch):
    profile = _profile()
    profile.adapter_key = "fixture"
    probe = SimpleNamespace(status="ready", confidence=1)
    adapter = SimpleNamespace(
        source_provider="fixture",
        config=SimpleNamespace(source_access="issuer_public_holdings_csv"),
        probe=lambda **_: probe,
        fetch_latest=lambda **_: None,
    )

    async def fetch_latest(**_kwargs):
        return SimpleNamespace(
            rows=[SimpleNamespace()],
            raw_text="DXJ fixture",
            raw_json={},
            source_url="https://issuer.example/DXJ.csv",
            source_identifier="DXJ",
            legal_metadata={
                "source_provider": "fixture",
                "composition_date": "2099-01-01",
                "as_of_date": "2099-01-01",
            },
        )

    adapter.fetch_latest = fetch_latest
    monkeypatch.setattr(refresh, "get_holdings_adapter", lambda _key: adapter)

    async def unexpected_ingest(*_args, **_kwargs):
        raise AssertionError("future-dated artifacts must be rejected before ingestion")

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", unexpected_ingest)

    with pytest.raises(ValueError, match="future composition date"):
        await refresh._refresh_adapter_route(None, profile)


@pytest.mark.asyncio
async def test_schema_drift_is_rejected_for_an_unchanged_parser():
    profile = _profile()
    state = _state(
        extra_data={
            "schema_fingerprint": refresh._schema_fingerprint(
                raw_payload_json={"holdings": [{"ticker": "DXJ"}]}
            )
        }
    )
    state.parser_version = "fixture-json-v1"
    db = _Session([_Result(scalar=state)])

    with pytest.raises(refresh.ETFHoldingsSchemaDriftError) as error:
        await refresh._ensure_schema_fingerprint_is_stable(
            db,
            profile,
            parser_version="fixture-json-v1",
            raw_payload_json={"holdings": [{"ticker": "DXJ", "weight": 1}]},
        )

    assert error.value.previous_fingerprint != error.value.observed_fingerprint
    assert error.value.parser_version == "fixture-json-v1"


@pytest.mark.asyncio
async def test_refresh_route_rejects_schema_drift_before_snapshot_ingestion(monkeypatch):
    profile = _profile()
    profile.adapter_key = "fixture"
    state = _state(
        extra_data={
            "schema_fingerprint": refresh._schema_fingerprint(
                raw_payload_json={"holdings": [{"ticker": "DXJ"}]}
            )
        }
    )
    state.parser_version = "fixture-json-v1"
    db = _Session([_Result(scalar=state)])
    probe = SimpleNamespace(status="ready", confidence=1)
    adapter = SimpleNamespace(
        adapter_key="fixture",
        source_provider="fixture",
        config=SimpleNamespace(source_access="issuer_public_holdings_json"),
        probe=lambda **_: probe,
    )

    async def fetch_latest(**_kwargs):
        return SimpleNamespace(
            rows=[SimpleNamespace()],
            raw_text=None,
            raw_json={"holdings": [{"ticker": "DXJ", "weight": 1}]},
            source_url="https://issuer.example/DXJ.json",
            source_identifier="DXJ",
            legal_metadata={
                "source_provider": "fixture",
                "source_format": "json",
                "parser_version": "fixture-json-v1",
                "composition_date": "2026-09-03",
            },
        )

    adapter.fetch_latest = fetch_latest
    monkeypatch.setattr(refresh, "get_holdings_adapter", lambda _key: adapter)

    async def unexpected_ingest(*_args, **_kwargs):
        raise AssertionError("schema-drift artifacts must be rejected before ingestion")

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", unexpected_ingest)

    with pytest.raises(refresh.ETFHoldingsSchemaDriftError, match="schema fingerprint drift"):
        await refresh._refresh_adapter_route(db, profile)


@pytest.mark.asyncio
async def test_schema_drift_can_recover_with_an_explicit_parser_version():
    profile = _profile()
    state = _state(
        extra_data={
            "schema_fingerprint": refresh._schema_fingerprint(
                raw_payload_json={"holdings": [{"ticker": "DXJ"}]}
            )
        }
    )
    state.parser_version = "fixture-json-v0"
    db = _Session([_Result(scalar=state)])

    await refresh._ensure_schema_fingerprint_is_stable(
        db,
        profile,
        parser_version="fixture-json-v1",
        raw_payload_json={"holdings": [{"ticker": "DXJ", "weight": 1}]},
    )


@pytest.mark.asyncio
async def test_schema_drift_failure_persists_comparable_fingerprints():
    profile = _profile()
    state = _state()
    db = _Session([_Result(scalar=state)])
    failure = refresh.ETFHoldingsSchemaDriftError(
        previous="schema-old",
        observed="schema-new",
        parser_version="fixture-json-v1",
    )

    await refresh._record_failure(db, profile, failure)

    assert state.extra_data["last_error_class"] == "ETFHoldingsSchemaDriftError"
    assert state.extra_data["last_failure_class"] == "schema_drift"
    assert state.extra_data["last_schema_drift"] == {
        "previous_fingerprint": "schema-old",
        "observed_fingerprint": "schema-new",
        "parser_version": "fixture-json-v1",
        "observed_at": state.last_failure_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_canary_failure_persists_class_and_opens_circuit_at_threshold(monkeypatch):
    profile = _profile()
    state = _state(status="success")
    db = _Session(
        [
            _Result(rows=[profile]),
            _Result(scalar=state),
            _Result(scalar=state),
        ]
    )

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
    assert state.status == "circuit_open"
    assert state.extra_data["last_canary_failure_class"] == "empty_or_partial_source"
    assert state.extra_data["last_failure_class"] == "empty_or_partial_source"
    assert state.extra_data["circuit_open_until"] is not None


@pytest.mark.asyncio
async def test_canary_normalizes_malformed_persisted_failure_streak(monkeypatch):
    profile = _profile()
    state = _state(extra_data={"consecutive_failures": "legacy-corrupt-value"})
    db = _Session(
        [
            _Result(rows=[profile]),
            _Result(scalar=state),
            _Result(scalar=state),
            _Result(scalar=state),
        ]
    )

    async def failing_refresh(_db, _profile):
        raise TimeoutError("issuer route timed out")

    monkeypatch.setattr(refresh, "_refresh_adapter_route", failing_refresh)

    result = await refresh.run_etf_holdings_capability_canaries(
        db,
        symbols=["DXJ"],
        max_symbols=1,
        failure_threshold=3,
    )

    assert result["failed"] == 1
    assert result["reports"][0]["failure_class"] == "transport_error"
    assert result["reports"][0]["circuit_state"] == "closed"
    assert state.extra_data["consecutive_failures"] == 1


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


@pytest.mark.asyncio
async def test_route_skip_records_failure_time_for_capability_diagnostics():
    profile = _profile()
    state = _state(status="pending")
    db = _Session([_Result(scalar=state)])

    await refresh._record_skip(db, profile, "needs_issuer_route", "Cloudflare blocked route")

    assert state.status == "needs_issuer_route"
    assert state.last_checked_at is not None
    assert state.last_failure_at == state.last_checked_at
    assert state.failure_reason == "Cloudflare blocked route"


def test_canary_history_is_bounded_for_long_running_shadow_windows():
    metadata = {"canary_history": [{"sequence": index} for index in range(90)]}

    result = refresh._append_canary_observation(metadata, {"sequence": 90})

    assert len(result["canary_history"]) == 90
    assert result["canary_history"][0]["sequence"] == 1
    assert result["canary_history"][-1]["sequence"] == 90


def test_failure_streak_rejects_negative_and_non_numeric_persisted_values():
    assert refresh._failure_streak({"consecutive_failures": "not-a-number"}) == 0
    assert refresh._failure_streak({"consecutive_failures": -4}) == 0
    assert refresh._failure_streak(["legacy-metadata"]) == 0


def test_future_holdings_dates_are_rejected_at_ingestion_boundary():
    with pytest.raises(ValueError, match="future composition date"):
        refresh._ensure_holdings_dates_are_not_future(
            date(2026, 9, 8),
            date(2026, 9, 8),
            today=date(2026, 9, 5),
        )

    with pytest.raises(ValueError, match="future as-of date"):
        refresh._ensure_holdings_dates_are_not_future(
            date(2026, 9, 5),
            date(2026, 9, 8),
            today=date(2026, 9, 5),
        )

    with pytest.raises(ValueError, match="future published-at timestamp"):
        refresh._ensure_holdings_dates_are_not_future(
            date(2026, 9, 5),
            date(2026, 9, 5),
            now=datetime(2026, 9, 5, 12, tzinfo=UTC),
            published_at=datetime(2026, 9, 5, 12, 1, tzinfo=UTC),
        )


def test_future_dated_canary_failures_have_explicit_failure_class():
    assert (
        refresh._canary_failure_class(
            "Issuer holdings route returned a future composition date (2026-09-08 > 2026-09-05)."
        )
        == "future_dated_source"
    )
    assert (
        refresh._canary_failure_class(
            "Issuer holdings route returned a future published-at timestamp."
        )
        == "future_dated_source"
    )


def test_authentication_failures_have_explicit_failure_class():
    response = httpx.Response(
        401,
        request=httpx.Request("GET", "https://issuer.example/holdings.csv"),
    )
    failure = httpx.HTTPStatusError("401 Unauthorized", request=response.request, response=response)

    assert refresh._canary_failure_class(failure) == "authentication_required"
