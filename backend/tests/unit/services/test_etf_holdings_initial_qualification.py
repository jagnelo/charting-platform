from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.routers import etf_holdings
from app.services.etf_holdings_edgar import _is_identified_non_target_fund
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
