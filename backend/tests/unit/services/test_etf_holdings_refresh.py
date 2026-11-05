from __future__ import annotations

import asyncio
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
        instrument_id=42,
        adapter_key="wisdomtree",
        instrument=SimpleNamespace(id=42, symbol=symbol, name=f"{symbol} fixture"),
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
    observed_at = datetime.now(UTC)
    return SimpleNamespace(
        composition_date=observed_at.date(),
        published_at=observed_at,
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


async def _no_prior_snapshot(*_args, **_kwargs):
    return None


@pytest.mark.parametrize(
    ("raw_text", "expected_status"),
    [
        ("Daily Holdings (%) 10/29/2026\nTicker,Weight,Name\nSLB,1.0%,SLB Ltd", "matched"),
        ("Fund Ticker,SMH\nTicker,Weight\nSLB,1.0%", "mismatch"),
        (
            "Fund Name,VanEck Semiconductor ETF (SMH)\nTicker,Weight\nSLB,1.0%",
            "mismatch",
        ),
    ],
)
def test_verified_oih_worksheet_identity_fills_missing_table_identity_but_not_conflicts(
    raw_text, expected_status
):
    profile_value = _profile("OIH")
    profile_value.adapter_key = "vaneck"
    profile_value.instrument.name = "VanEck Oil Services ETF"
    profile_value.provider_aliases = {
        "product_slug": "oil-services-etf-oih",
        "expected_etf_symbol": "OIH",
        "expected_etf_name": "VanEck Oil Services ETF",
    }

    result = refresh._validate_artifact_identity(
        profile_value,
        raw_text,
        verified_body_identity=["worksheet:OIH_asof_20261029"],
    )

    assert result["status"] == expected_status
    if expected_status == "matched":
        assert result["matched"] == [
            {
                "type": "verified_body_identity",
                "value": "worksheet:OIH_asof_20261029",
            }
        ]
    else:
        assert result["matched"] == []


def test_curated_spdr_route_metadata_binds_adapter_and_publisher_identity():
    profile_value = _profile("SPY")
    profile_value.provider_aliases = {"operator_review_ref": "retained-review-record"}

    assert refresh._apply_known_route_metadata(profile_value) is True

    assert profile_value.issuer == "State Street Global Advisors"
    assert profile_value.adapter_key == "spdr"
    assert profile_value.provider_aliases == {
        "operator_review_ref": "retained-review-record",
        "holdings_adapter": "spdr",
        "holdings_source_provider": "spdr",
    }


def test_curated_iwm_route_metadata_hydrates_fund_scoped_sec_identity():
    profile_value = _profile("IWM")

    assert refresh._apply_known_route_metadata(profile_value) is True

    assert profile_value.adapter_key == "ishares"
    assert profile_value.sec_cik == "0001100663"
    assert profile_value.sec_series_id == "S000004344"
    assert profile_value.sec_class_id == "C000012074"
    assert profile_value.provider_aliases["sec_fund_tickers_symbol"] == "IWM"


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
    # The verified WisdomTree route now unlocks the current Tier 0 capability.
    assert report["availability"] == "current"
    assert report["recovered"] is True
    assert report["circuit_state"] == "closed"
    assert report["latency_ms"] >= 0
    assert state.extra_data["last_canary_status"] == "success"
    assert (
        state.extra_data["symbol_audit_revalidated_at"]
        == state.extra_data["canary_history"][0]["observed_at"]
    )
    assert state.extra_data["last_canary_failure_class"] is None
    assert len(state.extra_data["canary_history"]) == 1
    assert state.extra_data["canary_history"][0]["status"] == "success"
    assert state.extra_data["canary_history"][0]["availability"] == "current"
    assert state.extra_data["canary_history"][0]["symbol_audit_outcome"] == "current"
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

    retained = []

    async def capture_rejected_artifact(*args, **kwargs):
        retained.append((args, kwargs))
        return None

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", unexpected_ingest)
    monkeypatch.setattr(refresh, "_retain_rejected_fetch_artifact", capture_rejected_artifact)

    with pytest.raises(ValueError, match="future composition date"):
        await refresh._refresh_adapter_route(None, profile)
    assert retained[0][1]["validation"] == {"status": "future_dated"}
    assert retained[0][1]["fetch_result"].raw_text == "DXJ fixture"


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


def _vaneck_schema_result(payload):
    profile = _profile("OIH")
    profile.adapter_key = "vaneck"
    profile.provider_aliases = {"product_slug": "oil-services-etf-oih"}
    adapter = SimpleNamespace(adapter_key="vaneck", source_provider="vaneck")
    fetch_result = SimpleNamespace(
        source_identifier="oil-services-etf-oih",
        raw_json=payload,
        legal_metadata={
            "source_provider": "vaneck",
            "adapter_key": "vaneck",
            "source_format": "xlsx",
            "product_slug": "oil-services-etf-oih",
            "body_identity_status": "matched",
            "body_identity_evidence": ["OIH"],
            "composition_date": "2026-10-29",
        },
    )
    return profile, adapter, fetch_result


@pytest.mark.asyncio
async def test_vaneck_qualification_diagnostics_share_ordinary_schema_and_migrate_exact_legacy_state():
    ordinary_payload = {
        "source_format": "xlsx",
        "workbook_rows": [
            ["Daily Holdings (%)  10/29/2026"],
            [],
            [
                "Number",
                "Ticker",
                "Holding Name",
                "Identifier (FIGI)",
                "Shares",
                "Asset Class",
                "Market Value (US$)",
                "Notional Value",
                "% of Net Assets",
            ],
            ["1", "SLB", "SLB", "FIGI", "1", "Equity", "1", "1", "0.1"],
        ],
    }
    qualification_payload = {
        **ordinary_payload,
        "raw_workbook_base64": "cHJvb2Y=",
        "raw_workbook_sha256": "a" * 64,
        "raw_workbook_bytes": 5,
    }
    profile, adapter, qualification_result = _vaneck_schema_result(qualification_payload)
    qualification_fingerprint, no_legacy = refresh._vaneck_oih_schema_fingerprints(
        profile,
        adapter,
        qualification_result,
        parser_version="vaneck-xlsx-v1",
        verified_body_identity=["OIH"],
    )
    assert no_legacy is None

    _, _, ordinary_result = _vaneck_schema_result(ordinary_payload)
    ordinary_fingerprint, legacy_fingerprint = refresh._vaneck_oih_schema_fingerprints(
        profile,
        adapter,
        ordinary_result,
        parser_version="vaneck-xlsx-v1",
        verified_body_identity=["OIH"],
    )
    assert ordinary_fingerprint == qualification_fingerprint
    assert legacy_fingerprint == refresh._schema_fingerprint(raw_payload_json=qualification_payload)

    state = _state(extra_data={"schema_fingerprint": legacy_fingerprint})
    state.parser_version = "vaneck-xlsx-v1"
    await refresh._ensure_schema_fingerprint_is_stable(
        _Session([_Result(scalar=state)]),
        profile,
        parser_version="vaneck-xlsx-v1",
        raw_payload_json=ordinary_payload,
        schema_fingerprint_override=ordinary_fingerprint,
        legacy_qualification_fingerprint=legacy_fingerprint,
    )


def test_authentic_oih_workbook_qualification_and_ordinary_payloads_share_schema_fingerprint():
    import base64
    import hashlib
    from pathlib import Path

    from app.services.etf_holdings_adapters import get_holdings_adapter, parse_xlsx_table

    workbook = (
        Path(__file__).resolve().parents[2] / "fixtures/vaneck/oih_schema_continuity.xlsx"
    ).read_bytes()
    assert len(workbook) == 5396
    raw_sha256 = hashlib.sha256(workbook).hexdigest()
    assert raw_sha256 == "11deec5585455293657854b25a8fc04e3e8c6d50cb35f5f759c6a58c4aae4653"
    adapter = get_holdings_adapter("vaneck")
    assert adapter is not None
    _, composition_date = adapter._parse_workbook(workbook)
    assert composition_date is not None
    workbook_rows = parse_xlsx_table(workbook)
    identity_status, identity_evidence = adapter._initial_workbook_identity(
        workbook,
        workbook_rows,
        composition_date=composition_date,
    )
    assert identity_status == "matched"
    ordinary_payload = {"source_format": "xlsx", "workbook_rows": workbook_rows}
    qualification_payload = {
        **ordinary_payload,
        "raw_workbook_base64": base64.b64encode(workbook).decode("ascii"),
        "raw_workbook_sha256": raw_sha256,
        "raw_workbook_bytes": len(workbook),
    }
    profile = _profile("OIH")
    profile.adapter_key = "vaneck"
    profile.provider_aliases = {"product_slug": "oil-services-etf-oih"}

    fingerprints = []
    for payload in (qualification_payload, ordinary_payload):
        fetch_result = SimpleNamespace(
            source_identifier="oil-services-etf-oih",
            raw_json=payload,
            legal_metadata={
                "source_provider": "vaneck",
                "adapter_key": "vaneck",
                "source_format": "xlsx",
                "product_slug": "oil-services-etf-oih",
                "body_identity_status": identity_status,
                "body_identity_evidence": identity_evidence,
                "composition_date": composition_date.isoformat(),
            },
        )
        fingerprint, _legacy = refresh._vaneck_oih_schema_fingerprints(
            profile,
            adapter,
            fetch_result,
            parser_version="vaneck-xlsx-v1",
            verified_body_identity=identity_evidence,
        )
        fingerprints.append(fingerprint)
    assert fingerprints[0] is not None and fingerprints[0] == fingerprints[1]
    assert "raw_workbook_base64" in qualification_payload
    assert "raw_workbook_base64" not in ordinary_payload


@pytest.mark.asyncio
async def test_authentic_oih_workbook_header_change_still_fails_legacy_schema_check():
    import base64
    import hashlib
    import io
    import zipfile
    from pathlib import Path

    from app.services.etf_holdings_adapters import get_holdings_adapter, parse_xlsx_table

    workbook = (
        Path(__file__).resolve().parents[2] / "fixtures/vaneck/oih_schema_continuity.xlsx"
    ).read_bytes()
    assert len(workbook) == 5396
    raw_sha256 = hashlib.sha256(workbook).hexdigest()
    assert raw_sha256 == "11deec5585455293657854b25a8fc04e3e8c6d50cb35f5f759c6a58c4aae4653"

    output = io.BytesIO()
    replacement_count = 0
    with zipfile.ZipFile(io.BytesIO(workbook)) as source:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as changed:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "xl/sharedStrings.xml":
                    replacement_count = content.count(b"Notional Value")
                    content = content.replace(b"Notional Value", b"Notional Field")
                changed.writestr(info, content)
    assert replacement_count == 1
    changed_workbook = output.getvalue()
    assert hashlib.sha256(changed_workbook).hexdigest() != raw_sha256

    adapter = get_holdings_adapter("vaneck")
    assert adapter is not None
    original_rows, original_date = adapter._parse_workbook(workbook)
    changed_rows, changed_date = adapter._parse_workbook(changed_workbook)
    assert original_rows and changed_rows and changed_date == original_date
    ordinary_rows = parse_xlsx_table(changed_workbook)
    assert ordinary_rows[2][7] == "Notional Field"
    identity_status, identity_evidence = adapter._initial_workbook_identity(
        changed_workbook,
        ordinary_rows,
        composition_date=changed_date,
    )
    assert identity_status == "matched"

    qualification_payload = {
        "source_format": "xlsx",
        "workbook_rows": parse_xlsx_table(workbook),
        "raw_workbook_base64": base64.b64encode(workbook).decode("ascii"),
        "raw_workbook_sha256": raw_sha256,
        "raw_workbook_bytes": len(workbook),
    }
    legacy_fingerprint = refresh._schema_fingerprint(raw_payload_json=qualification_payload)
    changed_payload = {"source_format": "xlsx", "workbook_rows": ordinary_rows}
    profile = _profile("OIH")
    profile.adapter_key = "vaneck"
    profile.provider_aliases = {"product_slug": "oil-services-etf-oih"}
    fetch_result = SimpleNamespace(
        source_identifier="oil-services-etf-oih",
        raw_json=changed_payload,
        legal_metadata={
            "source_provider": "vaneck",
            "adapter_key": "vaneck",
            "source_format": "xlsx",
            "product_slug": "oil-services-etf-oih",
            "body_identity_status": identity_status,
            "body_identity_evidence": identity_evidence,
            "composition_date": changed_date.isoformat(),
        },
    )
    observed, legacy_candidate = refresh._vaneck_oih_schema_fingerprints(
        profile,
        adapter,
        fetch_result,
        parser_version="vaneck-xlsx-v1",
        verified_body_identity=identity_evidence,
    )
    assert observed is not None and observed != legacy_fingerprint
    assert legacy_candidate is None

    state = _state(extra_data={"schema_fingerprint": legacy_fingerprint})
    state.parser_version = "vaneck-xlsx-v1"
    with pytest.raises(refresh.ETFHoldingsSchemaDriftError, match="schema fingerprint drift"):
        await refresh._ensure_schema_fingerprint_is_stable(
            _Session([_Result(scalar=state)]),
            profile,
            parser_version="vaneck-xlsx-v1",
            raw_payload_json=changed_payload,
            schema_fingerprint_override=observed,
            legacy_qualification_fingerprint=legacy_candidate,
        )


@pytest.mark.asyncio
async def test_vaneck_legacy_schema_compatibility_does_not_accept_changed_workbook_rows():
    ordinary_payload = {
        "source_format": "xlsx",
        "workbook_rows": [
            ["Daily Holdings (%)  10/29/2026"],
            [],
            [
                "Number",
                "Ticker",
                "Holding Name",
                "Identifier (FIGI)",
                "Shares",
                "Asset Class",
                "Market Value (US$)",
                "Notional Value",
                "% of Net Assets",
            ],
            ["1", "SLB", "SLB", "FIGI", "1", "Equity", "1", "1", "0.1"],
        ],
    }
    profile, adapter, result = _vaneck_schema_result(ordinary_payload)
    observed, legacy = refresh._vaneck_oih_schema_fingerprints(
        profile,
        adapter,
        result,
        parser_version="vaneck-xlsx-v1",
        verified_body_identity=["OIH"],
    )
    changed_payload = {
        "source_format": "xlsx",
        "workbook_rows": [
            ordinary_payload["workbook_rows"][0],
            ordinary_payload["workbook_rows"][1],
            [
                "Number",
                "Ticker",
                "Holding Name",
                "Identifier (FIGI)",
                "Shares renamed",
                "Asset Class",
                "Market Value (US$)",
                "Notional Value",
                "% of Net Assets",
            ],
            ordinary_payload["workbook_rows"][3],
        ],
    }
    _, _, changed_result = _vaneck_schema_result(changed_payload)
    changed, changed_legacy = refresh._vaneck_oih_schema_fingerprints(
        profile,
        adapter,
        changed_result,
        parser_version="vaneck-xlsx-v1",
        verified_body_identity=["OIH"],
    )
    assert changed != observed and changed_legacy is None and legacy is not None

    state = _state(extra_data={"schema_fingerprint": legacy})
    state.parser_version = "vaneck-xlsx-v1"
    with pytest.raises(refresh.ETFHoldingsSchemaDriftError, match="schema fingerprint drift"):
        await refresh._ensure_schema_fingerprint_is_stable(
            _Session([_Result(scalar=state)]),
            profile,
            parser_version="vaneck-xlsx-v1",
            raw_payload_json=changed_payload,
            schema_fingerprint_override=changed,
            legacy_qualification_fingerprint=changed_legacy,
        )


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
                "composition_date": datetime.now(UTC).date().isoformat(),
            },
        )

    adapter.fetch_latest = fetch_latest
    monkeypatch.setattr(refresh, "get_holdings_adapter", lambda _key: adapter)

    async def unexpected_ingest(*_args, **_kwargs):
        raise AssertionError("schema-drift artifacts must be rejected before ingestion")

    retained = []

    async def capture_rejected_artifact(*args, **kwargs):
        retained.append((args, kwargs))
        return None

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", unexpected_ingest)
    monkeypatch.setattr(refresh, "_retain_rejected_fetch_artifact", capture_rejected_artifact)

    with pytest.raises(refresh.ETFHoldingsSchemaDriftError, match="schema fingerprint drift"):
        await refresh._refresh_adapter_route(db, profile)
    assert retained[0][1]["validation"] == {"status": "schema_drift"}
    assert retained[0][1]["fetch_result"].raw_json == {"holdings": [{"ticker": "DXJ", "weight": 1}]}


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
    monkeypatch.setattr(refresh, "get_latest_snapshot", _no_prior_snapshot)

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
async def test_canary_enforces_per_symbol_timeout_and_records_transport_failure(monkeypatch):
    profile = _profile()
    state = _state(status="success")
    db = _Session(
        [
            _Result(rows=[profile]),
            _Result(scalar=state),
            _Result(scalar=state),
        ]
    )

    async def slow_refresh(_db, _profile):
        await asyncio.sleep(1)

    async def fake_failure(_db, _profile, failure):
        state.status = "failure"
        state.failure_reason = str(failure)
        state.extra_data = {"consecutive_failures": 1}

    monkeypatch.setattr(refresh, "_refresh_adapter_route", slow_refresh)
    monkeypatch.setattr(refresh, "_record_failure", fake_failure)
    monkeypatch.setattr(refresh, "get_latest_snapshot", _no_prior_snapshot)

    result = await refresh.run_etf_holdings_capability_canaries(
        db,
        symbols=["DXJ"],
        max_symbols=1,
        timeout_seconds=0.01,
        failure_threshold=1,
    )

    assert result["failed"] == 1
    assert result["reports"][0]["failure_class"] == "transport_error"
    assert state.extra_data["last_canary_failure_class"] == "transport_error"


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
    monkeypatch.setattr(refresh, "get_latest_snapshot", _no_prior_snapshot)

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

    with pytest.raises(ValueError, match="future known-at timestamp"):
        refresh._ensure_holdings_dates_are_not_future(
            date(2026, 9, 5),
            date(2026, 9, 5),
            now=datetime(2026, 9, 5, 12, tzinfo=UTC),
            known_at=datetime(2026, 9, 5, 12, 1, tzinfo=UTC),
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


@pytest.mark.parametrize(
    ("status_code", "expected_class"),
    [(403, "access_denied"), (429, "quota_rate_limited")],
)
def test_access_and_quota_failures_have_explicit_failure_classes(status_code, expected_class):
    response = httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://issuer.example/holdings.csv"),
    )
    failure = httpx.HTTPStatusError(
        f"HTTP {status_code}", request=response.request, response=response
    )

    assert refresh._canary_failure_class(failure) == expected_class
