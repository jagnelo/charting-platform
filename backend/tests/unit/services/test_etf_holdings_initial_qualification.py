from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.routers import etf_holdings
from app.services.etf_holdings_edgar import (
    _backfill_sec_holdings,
    _is_identified_non_target_fund,
    _validated_initial_qualification_filing_reference,
)
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    bind_etf_holdings_sec_request_context,
)
from app.services.provider_runtime import (
    _ETF_INITIAL_QUALIFICATION_OPERATIONS,
    _bind_etf_initial_qualification_authority,
    _etf_initial_qualification_matches,
    _new_etf_initial_qualification_authority,
)


def _authority(**overrides):
    values = {
        "attempt_id": 31,
        "provider_name": "edgar",
        "capability": ProviderCapability.ETF_HOLDINGS,
        "operations": _ETF_INITIAL_QUALIFICATION_OPERATIONS,
        "profile_id": 17,
        "instrument_id": 23,
        "provider_symbol": "IWM",
        "account_scope": "reviewed-edgar-ip",
        "expires_at": datetime.now(UTC) + timedelta(minutes=3),
    }
    values.update(overrides)
    return _new_etf_initial_qualification_authority(**values)


def _matches(**overrides):
    values = {
        "provider_name": "edgar",
        "capability": ProviderCapability.ETF_HOLDINGS,
        "operation": "fetch_etf_holdings_sec_filing",
        "instrument_id": 23,
        "provider_symbol": "IWM",
        "profile_id": 17,
        "policy": SimpleNamespace(quota_scope="ip"),
    }
    values.update(overrides)
    return _etf_initial_qualification_matches(**values)


def _committed_reference():
    return {
        "cik": "0001100663",
        "series_id": "S000004344",
        "class_id": "C000012074",
        "form": "NPORT-P",
        "accession_number": "0001234567-26-000001",
        "primary_document": "nport_primary.xml",
        "filing_date": "2026-10-20",
        "report_date": "2026-09-30",
        "acceptance_datetime": None,
        "review_provenance": "offline reviewed index fixture",
        "reviewed_at": datetime.now(UTC).isoformat(),
    }


def test_committed_filing_reference_constructs_fixed_archive_url_and_audit():
    profile = SimpleNamespace(
        sec_cik="0001100663",
        sec_series_id="S000004344",
        sec_class_id="C000012074",
        legal_metadata={
            "existing_provenance": {"owner": "preserved"},
            "sec_initial_qualification": {"filing_reference": _committed_reference()},
        },
    )

    filing, audit = _validated_initial_qualification_filing_reference(profile)

    assert filing is not None and audit is not None
    assert filing.filing_url == (
        "https://www.sec.gov/Archives/edgar/data/1100663/" "000123456726000001/nport_primary.xml"
    )
    assert filing.form == "NPORT-P"
    assert audit["selection_method"] == "committed_profile_reference"
    assert audit["reference"]["accession_number"] == filing.accession_number
    assert audit["reference"]["review_provenance"] == "offline reviewed index fixture"


def test_missing_committed_filing_reference_preserves_default_discovery():
    profile = SimpleNamespace(
        sec_cik="0001100663",
        sec_series_id="S000004344",
        sec_class_id="C000012074",
        legal_metadata={"existing_provenance": {"x": 1}},
    )

    assert _validated_initial_qualification_filing_reference(profile) == (None, None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cik", "0000000001"),
        ("series_id", "S000009999"),
        ("class_id", "C000099999"),
        ("form", "N-CSR"),
        ("accession_number", "../000123456726000001"),
        ("accession_number", "٠00123456726000001"),
        ("series_id", "S0000043٤4"),
        ("series_id", "*"),
        ("class_id", "C00001207*"),
        ("primary_document", "filing.htm"),
        ("primary_document", "*.xml"),
        ("primary_document", "nport_K.xml"),
        ("primary_document", "https://evil.invalid/filing.xml"),
        ("primary_document", "filing.xml?next=evil"),
        ("primary_document", "filing.xml#fragment"),
        ("primary_document", "filing%2f.xml"),
        ("primary_document", "../filing.xml"),
        ("filing_url", "https://evil.invalid/filing.xml"),
        ("review_provenance", "   "),
        ("reviewed_at", "2026-10-20T12:00:00"),
    ],
)
def test_committed_filing_reference_rejects_untrusted_or_cross_fund_values(field, value):
    reference = _committed_reference()
    reference[field] = value
    profile = SimpleNamespace(
        sec_cik="0001100663",
        sec_series_id="S000004344",
        sec_class_id="C000012074",
        legal_metadata={"sec_initial_qualification": {"filing_reference": reference}},
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="committed SEC filing reference"):
        _validated_initial_qualification_filing_reference(profile)


@pytest.mark.parametrize(
    "field,value",
    [
        ("filing_date", lambda: (datetime.now(UTC) + timedelta(days=1)).date().isoformat()),
        ("report_date", lambda: (datetime.now(UTC) + timedelta(days=1)).date().isoformat()),
        ("acceptance_datetime", lambda: (datetime.now(UTC) + timedelta(days=1)).isoformat()),
        ("acceptance_datetime", lambda: datetime.now(UTC).replace(tzinfo=None).isoformat()),
        ("reviewed_at", lambda: (datetime.now(UTC) + timedelta(days=1)).isoformat()),
    ],
)
def test_committed_filing_reference_rejects_future_or_timezone_ambiguous_dates(field, value):
    reference = _committed_reference()
    reference[field] = value()
    profile = SimpleNamespace(
        sec_cik="0001100663",
        sec_series_id="S000004344",
        sec_class_id="C000012074",
        legal_metadata={"sec_initial_qualification": {"filing_reference": reference}},
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="committed SEC filing reference"):
        _validated_initial_qualification_filing_reference(profile)


@pytest.mark.asyncio
@pytest.mark.parametrize("qualification_job", [None, SimpleNamespace(job_type="ordinary")])
async def test_committed_filing_reference_is_restricted_before_backfill_effects(
    monkeypatch, qualification_job
):
    async def unexpected_scope(*args, **kwargs):
        raise AssertionError("invalid committed-reference call entered the SEC execution scope")

    monkeypatch.setattr("app.services.etf_holdings_edgar._run_in_sec_fund_scope", unexpected_scope)
    with pytest.raises(ETFHoldingsRouteHeldError, match="active initial qualification job"):
        await _backfill_sec_holdings(
            object(),
            profile=SimpleNamespace(id=17),
            start_date=None,
            end_date=None,
            max_filings=1,
            requested_by_user_id=None,
            job_type="ordinary",
            discover_filings=unexpected_scope,
            parse_xml=unexpected_scope,
            provenance="test",
            parser_version="test",
            source_format="test",
            missing_date_reason="missing date",
            no_rows_reason="no rows",
            notes="test",
            qualification_job=qualification_job,
            committed_filing_reference=object(),
        )


def test_initial_qualification_authority_is_task_local_and_exactly_scoped(monkeypatch):
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"edgar:ip": "reviewed-edgar-ip"},
    )
    authority = _authority()

    assert _matches() is False
    with _bind_etf_initial_qualification_authority(authority):
        assert _matches() is True
        assert _matches(provider_name="other") is False
        assert _matches(capability=ProviderCapability.PRICE_HISTORY) is False
        assert _matches(operation="fetch_etf_holdings_latest") is False
        assert _matches(instrument_id=24) is False
        assert _matches(provider_symbol="SPY") is False
        assert _matches(profile_id=18) is False
        assert _matches(policy=SimpleNamespace(quota_scope="api_key")) is False

    assert _matches() is False


def test_initial_qualification_authority_rejects_expiry_and_wildcards():
    expired = _authority(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with _bind_etf_initial_qualification_authority(expired):
        assert _matches() is False

    with pytest.raises(ValueError, match="invalid ETF initial qualification scope"):
        _authority(provider_symbol="*")


def test_sec_request_binding_rejects_a_different_qualification_fund():
    authority = _authority()
    adapter = SimpleNamespace(source_provider="edgar", adapter_key="edgar_sec_holdings")

    with pytest.raises(ETFHoldingsRouteHeldError, match="does not match this fund"):
        with bind_etf_holdings_sec_request_context(
            db=object(),
            adapter=adapter,
            profile_id=17,
            instrument_id=24,
            provider_symbol="IWM",
            operation="fetch_etf_holdings_sec_filing",
            initial_qualification_authority=authority,
        ):
            pass


def test_only_explicit_series_or_class_mismatch_is_expected_candidate_discard():
    profile = SimpleNamespace(sec_series_id="S000004344", sec_class_id="C000012074")

    assert _is_identified_non_target_fund(
        identity_status="mismatch_series_id:S000009999!=S000004344",
        filing_identity={"series_id": "S000009999"},
        profile=profile,
    )
    assert _is_identified_non_target_fund(
        identity_status="mismatch_class_id:C000099999!=C000012074",
        filing_identity={"class_id": "C000099999"},
        profile=profile,
    )
    assert not _is_identified_non_target_fund(
        identity_status="missing_class_id",
        filing_identity={"series_id": "S000004344"},
        profile=profile,
    )
    assert not _is_identified_non_target_fund(
        identity_status="mismatch_ticker:ZZZ!=IWM",
        filing_identity={"class_ticker": "ZZZ"},
        profile=profile,
    )


def test_initial_qualification_router_is_admin_only(client, auth_headers, monkeypatch):
    called = []

    async def forbidden_service(*_args, **_kwargs):
        called.append(True)

    monkeypatch.setattr(etf_holdings, "qualify_sec_nport_fund", forbidden_service)
    path = "/api/v1/etf-holdings/IWM/sec-initial-qualification"

    assert client.post(path).status_code == 401
    assert client.post(path, headers=auth_headers).status_code == 403
    assert called == []
