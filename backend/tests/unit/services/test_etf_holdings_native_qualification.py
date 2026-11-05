import base64
import hashlib
import inspect
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsRawArtifact, ETFProfile
from app.models.instrument import Instrument
from app.models.provider_runtime import ProviderCapability
from app.services import etf_holdings_adapters as adapters_module
from app.services.etf_holdings import _hash_payload
from app.services.etf_holdings_adapters import (
    ETFNativeSourceEvidenceError,
    _table_to_text,
    get_holdings_adapter,
    parse_xlsx_table,
)
from app.services.etf_holdings_native_qualification import (
    NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE,
    _attempt_scope,
    _issuer_catalog_identity_claim,
    _native_provider_contract,
    _native_review_snapshot_still_matches,
    _reparse_retained_native_failure,
    _require_one_shot_available,
    _reviewed_native_route,
    _verify_invesco_catalog_identity_evidence,
    _verify_issuer_catalog_identity_evidence,
    _verify_persisted_qualification_adapter_state,
    _verify_retained_evidence_body_log_link,
)
from app.services.etf_holdings_provider_bridge import (
    ETF_NATIVE_INITIAL_QUALIFICATION_DEADLINE_SECONDS,
    ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS,
    ETFHoldingsRouteHeldError,
    bind_etf_holdings_request_context,
)
from app.services.etf_holdings_refresh import (
    _native_adapter_fetch_evidence,
    _native_artifact_identity_validation,
    _native_initial_qualification_fetch_evidence,
    _validate_artifact_identity,
)
from app.services.etf_issuer_catalog import (
    ISHARES_US_CATALOG_KEY,
    ISHARES_US_CATALOG_URL,
    parse_ishares_us_product_catalog,
)


def _native_fetch_fixture(*, raw_text=None, raw_json=None, metadata=None, symbol="TST"):
    instrument = Instrument(id=824, symbol=symbol, name="Test Issuer Broad Market ETF")
    profile = ETFProfile(
        id=53,
        instrument_id=instrument.id,
        instrument=instrument,
        adapter_key="test_native",
        provider_aliases={"holdings_source_provider": "test_issuer"},
    )
    adapter = SimpleNamespace(adapter_key="test_native", source_provider="test_issuer")
    legal_metadata = {
        "source_provider": "test_issuer",
        "adapter_key": "test_native",
        "source_format": "csv",
        "parser_version": "test-native-csv-v1",
        "composition_date": "2026-10-30",
        **(metadata or {}),
    }
    fetch_result = SimpleNamespace(
        rows=[{"symbol": "ABC"}],
        raw_text=raw_text,
        raw_json=raw_json,
        source_url="https://issuer.example.test/holdings.csv",
        source_identifier="TST-product-824",
        legal_metadata=legal_metadata,
    )
    from app.services.etf_holdings_provider_bridge import _canonical_request_url

    parser_body = (
        raw_text.encode("utf-8") if raw_text is not None else json.dumps(raw_json).encode()
    )
    artifact_payload = raw_json if raw_json is not None else raw_text
    artifact_text = json.dumps(artifact_payload, sort_keys=True, separators=(",", ":"), default=str)
    body_hash = hashlib.sha256(parser_body).hexdigest()
    fetch_result.legal_metadata["native_holdings_response_witness"] = {
        "provider_capture": {
            "request_log_id": 91,
            "physical_request_url_sha256": hashlib.sha256(
                _canonical_request_url(fetch_result.source_url).encode("utf-8")
            ).hexdigest(),
            "response_body_sha256": body_hash,
            "response_body_bytes": len(parser_body),
            "content_type": "text/csv",
            "binary_body": False,
            "status_code": 200,
            "attempt_id": 44,
            "provider": "test_issuer",
            "data_source_id": 61,
            "capability": ProviderCapability.ETF_HOLDINGS.value,
            "operation": "fetch_etf_holdings_latest",
            "profile_id": profile.id,
            "instrument_id": profile.instrument_id,
            "provider_symbol": symbol,
            "account_scope": "test_issuer:offline-fixture",
            "review_revision": 7,
            "provider_review_fingerprint": "a" * 64,
        },
        "parser": "test-native-csv-v1",
        "parser_input_sha256": body_hash,
        "parser_input_bytes": len(parser_body),
        "normalized_payload_sha256": hashlib.sha256(artifact_text.encode()).hexdigest(),
        "normalized_payload_kind": "json" if isinstance(artifact_payload, dict) else "text",
    }
    return profile, adapter, fetch_result


def test_native_qualification_requires_the_exact_published_provider_contract():
    try:
        binder, fingerprint = _native_provider_contract()
    except ETFHoldingsRouteHeldError as exc:
        pytest.skip(str(exc))

    assert callable(binder)
    assert callable(fingerprint)
    required_binder_parameters = {
        "attempt_id",
        "provider_name",
        "data_source_id",
        "fund_profile_id",
        "instrument_id",
        "provider_symbol",
        "operation",
        "account_scope",
        "entitlement_revision",
        "provider_review_fingerprint",
        "expires_at",
        "max_physical_requests",
    }
    assert required_binder_parameters <= set(inspect.signature(binder).parameters)
    from app.services.provider_runtime import (
        native_etf_initial_qualification_allows_disabled_policy,
    )

    assert callable(native_etf_initial_qualification_allows_disabled_policy)


def test_one_shot_latch_rejects_every_prior_attempt_status():
    _require_one_shot_available([])

    for status in ("running", "failed", "cancelled", "completed"):
        prior = ETFHoldingsBackfillJob(
            id=9,
            etf_profile_id=53,
            source_provider="test_issuer",
            job_type=NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE,
            status=status,
        )
        with pytest.raises(ETFHoldingsRouteHeldError, match="already latched"):
            _require_one_shot_available([prior])


def test_native_attempt_scope_binds_every_persisted_authority_dimension():
    profile, _, _ = _native_fetch_fixture(raw_text="Fund Ticker,TST\n")
    from datetime import UTC, datetime, timedelta

    expiry = datetime.now(UTC) + timedelta(seconds=120)
    scope = _attempt_scope(
        attempt_id=44,
        provider_name="test_issuer",
        data_source_id=81,
        profile=profile,
        account_scope="test_issuer:shared-ip",
        entitlement_revision=7,
        review_fingerprint="a" * 64,
        expires_at=expiry,
    )

    assert scope == {
        "attempt_id": 44,
        "provider": "test_issuer",
        "data_source_id": 81,
        "capability": "etf_holdings",
        "profile_id": 53,
        "instrument_id": 824,
        "provider_symbol": "TST",
        "operation": "fetch_etf_holdings_latest",
        "account_scope": "test_issuer:shared-ip",
        "review_revision": 7,
        "provider_review_fingerprint": "a" * 64,
        "expires_at": expiry.isoformat(),
        "max_physical_requests": 3,
    }


def test_native_bridge_binding_requires_exact_bounded_scope_and_cannot_overlap_special_route():
    from datetime import UTC, datetime, timedelta

    profile, adapter, _ = _native_fetch_fixture(raw_text="Fund Ticker,TST\n")
    expires_at = datetime.now(UTC) + timedelta(
        seconds=ETF_NATIVE_INITIAL_QUALIFICATION_DEADLINE_SECONDS
    )
    scope = _attempt_scope(
        attempt_id=44,
        provider_name="test_issuer",
        data_source_id=81,
        profile=profile,
        account_scope="test_issuer:shared-ip",
        entitlement_revision=7,
        review_fingerprint="a" * 64,
        expires_at=expires_at,
    )
    kwargs = {
        "db": object(),
        "adapter": adapter,
        "profile_id": profile.id,
        "instrument_id": profile.instrument_id,
        "provider_symbol": "TST",
        "operation": "fetch_etf_holdings_latest",
        "native_initial_qualification_job_id": 44,
        "native_initial_qualification_scope": scope,
    }

    with bind_etf_holdings_request_context(**kwargs) as binding:
        assert binding.native_initial_qualification_scope == scope

    oversized = {
        **scope,
        "max_physical_requests": ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS + 1,
    }
    with pytest.raises(ETFHoldingsRouteHeldError, match="exact committed scope"):
        with bind_etf_holdings_request_context(
            **{**kwargs, "native_initial_qualification_scope": oversized}
        ):
            pytest.fail("oversized native request scope must not bind")

    vaneck_profile, _, _ = _native_fetch_fixture(raw_text="Fund Ticker,OIH\n", symbol="OIH")
    vaneck_adapter = SimpleNamespace(adapter_key="vaneck", source_provider="vaneck")
    vaneck_scope = _attempt_scope(
        attempt_id=45,
        provider_name="vaneck",
        data_source_id=82,
        profile=vaneck_profile,
        account_scope="vaneck:shared-ip",
        entitlement_revision=2,
        review_fingerprint="b" * 64,
        expires_at=expires_at,
    )
    with pytest.raises(ETFHoldingsRouteHeldError, match="cannot overlap SEC or VanEck"):
        with bind_etf_holdings_request_context(
            **{
                **kwargs,
                "adapter": vaneck_adapter,
                "profile_id": vaneck_profile.id,
                "instrument_id": vaneck_profile.instrument_id,
                "provider_symbol": "OIH",
                "native_initial_qualification_job_id": 45,
                "vaneck_initial_qualification_budget": object(),
                "native_initial_qualification_scope": vaneck_scope,
            }
        ):
            pytest.fail("native scope must not borrow a special-source context")


def _reviewed_route_fixture():
    operation_review = {
        "evidence_source": "issuer terms and API documentation",
        "evidence_version": "2026-10",
        "reviewed_at": "2026-10-30T00:00:00Z",
    }
    source = SimpleNamespace(
        id=81,
        name="test_issuer",
        is_active=True,
        supported_capabilities=["etf_holdings"],
        config={
            "etf_holdings_review": {
                "https_hosts": ["issuer.example.test"],
                "account_scope": "test_issuer:shared-ip",
                "operations": {"fetch_etf_holdings_latest": operation_review},
            }
        },
    )
    policy = SimpleNamespace(
        data_source_id=81,
        capability=ProviderCapability.ETF_HOLDINGS,
        is_enabled=False,
        quota_scope="ip",
    )
    entitlement = SimpleNamespace(
        data_source_id=81,
        capability=ProviderCapability.ETF_HOLDINGS,
        configured_plan="reviewed-public-download",
        is_free=True,
        authentication_required=False,
        usage_terms="public download terms reviewed",
        redistribution_allowed=False,
        quota_policy={"requests": "bounded"},
        enabled_environments=["test"],
        review_due_at=None,
        live_probe_status="not_run",
        revision=4,
    )
    adapter = SimpleNamespace(
        source_provider="test_issuer",
        adapter_key="test_native",
        fetch_latest=lambda **_: None,
        fetch_for_date=lambda **_: None,
    )
    profile = SimpleNamespace(
        adapter_key="test_native",
        provider_aliases={"holdings_source_provider": "test_issuer"},
    )
    return profile, source, policy, entitlement, adapter


def test_native_route_requires_current_disabled_reviewed_free_rows(monkeypatch):
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"test_issuer:ip": "test_issuer:shared-ip"},
    )
    profile, source, policy, entitlement, adapter = _reviewed_route_fixture()

    assert _reviewed_native_route(
        profile=profile,
        source=source,
        policy=policy,
        entitlement=entitlement,
        adapter=adapter,
    ) == ("test_issuer", "test_issuer:shared-ip")

    policy.is_enabled = True
    with pytest.raises(ETFHoldingsRouteHeldError, match="disabled ETF adapter"):
        _reviewed_native_route(
            profile=profile,
            source=source,
            policy=policy,
            entitlement=entitlement,
            adapter=adapter,
        )


def test_native_route_rejects_unreviewed_or_expired_entitlement(monkeypatch):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"test_issuer:ip": "test_issuer:shared-ip"},
    )
    profile, source, policy, entitlement, adapter = _reviewed_route_fixture()
    entitlement.configured_plan = "free-download"
    with pytest.raises(ETFHoldingsRouteHeldError, match="entitlement is held"):
        _reviewed_native_route(
            profile=profile,
            source=source,
            policy=policy,
            entitlement=entitlement,
            adapter=adapter,
        )
    entitlement.configured_plan = "reviewed-public-download"
    entitlement.review_due_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ETFHoldingsRouteHeldError, match="review has expired"):
        _reviewed_native_route(
            profile=profile,
            source=source,
            policy=policy,
            entitlement=entitlement,
            adapter=adapter,
        )


def test_native_postfetch_review_must_match_current_rows_before_positive_update():
    from datetime import timedelta

    def evaluate(change=None):
        profile, adapter, _ = _native_fetch_fixture(raw_text="Fund Ticker,TST\n")
        initial_adapter = adapter
        _, source, policy, entitlement, _ = _reviewed_route_fixture()
        expires_at = datetime.now(UTC) + timedelta(seconds=120)
        scope = _attempt_scope(
            attempt_id=44,
            provider_name="test_issuer",
            data_source_id=source.id,
            profile=profile,
            account_scope="test_issuer:shared-ip",
            entitlement_revision=entitlement.revision,
            review_fingerprint="a" * 64,
            expires_at=expires_at,
        )
        provider_name = "test_issuer"
        account_scope = "test_issuer:shared-ip"
        fingerprint = "a" * 64
        if change == "enabled":
            policy.is_enabled = True
        elif change == "probe":
            entitlement.live_probe_status = "passed"
        elif change == "revision":
            entitlement.revision += 1
        elif change == "fingerprint":
            fingerprint = "b" * 64
        elif change == "account_scope":
            account_scope = "other:account"
        elif change == "provider":
            provider_name = "other_issuer"
        elif change == "expired":
            scope["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        elif change == "adapter":
            adapter = SimpleNamespace(source_provider="test_issuer", adapter_key="test_native")
        return _native_review_snapshot_still_matches(
            scope=scope,
            profile=profile,
            source=source,
            policy=policy,
            entitlement=entitlement,
            adapter=adapter,
            initial_adapter=initial_adapter,
            provider_name=provider_name,
            account_scope=account_scope,
            review_fingerprint=fingerprint,
            now=datetime.now(UTC),
        )

    assert evaluate()
    for changed_state in (
        "enabled",
        "probe",
        "revision",
        "fingerprint",
        "account_scope",
        "provider",
        "expired",
        "adapter",
    ):
        assert not evaluate(changed_state), changed_state


def test_native_evidence_rejects_unknown_publisher_completeness_contract():
    profile, adapter, fetch_result = _native_fetch_fixture(
        raw_text=(
            "Fund Ticker,TST\n"
            "Composition Date,2026-10-30\n"
            "Ticker,Name,Weight\nABC,Example Corp,1.0\n"
        )
    )

    with pytest.raises(ValueError, match="composition completeness is not proven"):
        _native_initial_qualification_fetch_evidence(profile, adapter, fetch_result)


@pytest.mark.parametrize(
    ("raw_text", "metadata", "message"),
    [
        (
            "Fund Ticker,OTHER\nTicker,Name\nABC,Example Corp\n",
            {"composition_date": "2026-10-30"},
            "conflicts",
        ),
        (
            "Fund Ticker,TST\nTicker,Name\nABC,Example Corp\n",
            {"composition_date": None},
            "provider-reported composition date",
        ),
        (
            "Fund Ticker,TST\nTicker,Name\nABC,Example Corp\n",
            {"composition_date": "not-a-date"},
            "provider-reported composition date",
        ),
        (
            "Ticker,Name\nABC,Example Corp\n",
            {
                "composition_date": "2026-10-30",
                "fund_identity": {
                    "instrument_id": 824,
                    "symbol": "OTHER",
                    "name": "Test Issuer Broad Market ETF",
                },
            },
            "conflicts|does not prove",
        ),
    ],
)
def test_native_evidence_rejects_wrong_fund_or_missing_reported_date(raw_text, metadata, message):
    profile, adapter, fetch_result = _native_fetch_fixture(raw_text=raw_text, metadata=metadata)

    with pytest.raises(ValueError, match=message):
        _native_initial_qualification_fetch_evidence(profile, adapter, fetch_result)


def test_native_evidence_does_not_treat_adapter_identity_as_completeness_proof():
    profile, adapter, fetch_result = _native_fetch_fixture(
        raw_json={"holdings": [{"ticker": "ABC", "weight": 1.0}]},
        metadata={
            "fund_identity": {
                "instrument_id": 824,
                "symbol": "TST",
                "name": "Test Issuer Broad Market ETF",
            }
        },
    )

    with pytest.raises(ValueError, match="composition completeness is not proven"):
        _native_initial_qualification_fetch_evidence(profile, adapter, fetch_result)


class _OfflineAdapterResponse:
    def __init__(self, *, body: bytes, url: str, content_type: str):
        self.content = body
        self.text = (
            body.decode("utf-8", errors="strict")
            if "json" in content_type or "csv" in content_type or "html" in content_type
            else ""
        )
        self.url = url
        self.encoding = "utf-8"
        self.status_code = 200
        self.headers = {"content-type": content_type}
        self.extensions = {}

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self.content)


class _OfflineAdapterClient:
    responses: list[_OfflineAdapterResponse] = []
    requested: list[str] = []
    on_get = None
    last_binding = None
    captured_responses: list[tuple[str, bytes, dict[str, object]]] = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, **_kwargs):
        type(self).requested.append(url)
        if type(self).on_get is not None:
            type(self).on_get(url)
        if not type(self).responses:
            raise AssertionError(f"unexpected offline adapter URL: {url}")
        response = type(self).responses.pop(0)
        from app.services import etf_holdings_provider_bridge as bridge

        binding = bridge._REQUEST_BINDING.get()
        if binding is not None:
            type(self).last_binding = binding
            if type(self).on_get is None:
                request_id = len(binding.request_log_ids) + 1
                binding.request_log_ids.append(request_id)
                binding.request_urls_by_log_id[request_id] = url
        if binding is not None and binding.native_initial_qualification_job_id is not None:
            witness = bridge._capture_native_response_body_witness(
                response,
                body=bytes(response.content),
            )
            assert witness is not None
            binding.response_body_witnesses.append(witness)
            type(self).captured_responses.append((url, bytes(response.content), witness))
        return response


def _native_adapter_profile(adapter, symbol: str, name: str) -> ETFProfile:
    instrument = Instrument(id=824, symbol=symbol, name=name)
    return ETFProfile(
        id=53,
        instrument_id=instrument.id,
        instrument=instrument,
        adapter_key=adapter.adapter_key,
        provider_aliases={"holdings_source_provider": adapter.source_provider},
    )


def _native_adapter_request_context(profile: ETFProfile, adapter):
    expires_at = datetime.now(UTC) + timedelta(
        seconds=ETF_NATIVE_INITIAL_QUALIFICATION_DEADLINE_SECONDS
    )
    scope = _attempt_scope(
        attempt_id=44,
        provider_name=adapter.source_provider,
        data_source_id=61,
        profile=profile,
        account_scope=f"{adapter.source_provider}:offline-fixture",
        entitlement_revision=7,
        review_fingerprint="a" * 64,
        expires_at=expires_at,
    )
    return bind_etf_holdings_request_context(
        db=object(),
        adapter=adapter,
        profile_id=profile.id,
        instrument_id=profile.instrument_id,
        provider_symbol=profile.instrument.symbol,
        operation="fetch_etf_holdings_latest",
        native_initial_qualification_job_id=44,
        native_initial_qualification_scope=scope,
    )


def _ordinary_adapter_request_context(profile: ETFProfile, adapter):
    return bind_etf_holdings_request_context(
        db=object(),
        adapter=adapter,
        profile_id=profile.id,
        instrument_id=profile.instrument_id,
        provider_symbol=profile.instrument.symbol,
        operation="fetch_etf_holdings_latest",
    )


def _xlsx_for_native_spdr(symbol: str, name: str) -> bytes:
    from tests.unit.services.test_etf_holdings_adapters import _xlsx_workbook

    return _xlsx_workbook(
        [
            ["Fund Name:", name],
            ["Ticker Symbol:", symbol],
            ["Holdings:", "As of 02-Nov-2026"],
            ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Shares Held", "Local Currency"],
            ["Microsoft Corp", "MSFT", "594918104", "2588173", "6.5", "100", "USD"],
        ]
    )


def _ishares_offline_catalog() -> str:
    return """<!doctype html><html><body><p>2 of 2 funds</p><table>
    <thead><tr><th>Ticker</th><th>Name</th><th>Asset Class</th></tr></thead><tbody>
    <tr><td><a href="/us/products/239771/ishares-expanded-tech-software-sector-etf">IGV</a></td>
    <td><a href="/us/products/239771/ishares-expanded-tech-software-sector-etf">iShares Expanded Tech-Software Sector ETF</a></td><td>Equity</td></tr>
    <tr><td><a href="/us/products/239726/">XLK</a></td>
    <td><a href="/us/products/239726/">iShares U.S. Technology ETF</a></td><td>Equity</td></tr>
    </tbody></table></body></html>"""


async def _fetch_native_adapter_result(monkeypatch, provider: str, *, ordinary=False):
    _OfflineAdapterClient.responses = []
    _OfflineAdapterClient.requested = []
    _OfflineAdapterClient.on_get = None
    _OfflineAdapterClient.last_binding = None
    _OfflineAdapterClient.captured_responses = []
    monkeypatch.setattr(adapters_module.httpx, "AsyncClient", _OfflineAdapterClient)
    adapter = get_holdings_adapter(provider)
    assert adapter is not None
    if hasattr(adapter, "_cusip_cache"):
        monkeypatch.setattr(adapter, "_cusip_cache", {})
    request_context = (
        _ordinary_adapter_request_context if ordinary else _native_adapter_request_context
    )
    profile = None

    if provider == "spdr":
        symbol, name = "XES", "State Street SPDR S&P Oil & Gas Equipment & Services ETF"
        profile = _native_adapter_profile(adapter, symbol, name)
        url = adapter._workbook_url(symbol)
        _OfflineAdapterClient.responses = [
            _OfflineAdapterResponse(
                body=_xlsx_for_native_spdr(symbol, name),
                url=url,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ]
        with request_context(profile, adapter):
            result = await adapter.fetch_latest(symbol=symbol)
    elif provider == "invesco":
        symbol, name = "QQQ", "Invesco QQQ Trust"
        profile = _native_adapter_profile(adapter, symbol, name)
        catalog_body = json.dumps(
            {"response": {"docs": [{"ticker": "QQQ", "cusip": "46090E103", "accountName": name}]}},
            separators=(",", ":"),
        ).encode()
        holdings_url = adapter._holdings_url("46090E103")
        holdings_body = json.dumps(
            {
                "effectiveDate": "2026-11-03",
                "effectiveBusinessDate": "2026-11-02",
                "totalNumberOfHoldings": 1,
                "holdings": [
                    {
                        "ticker": "NVDA",
                        "issuerName": "NVIDIA Corp",
                        "cusip": "67066G104",
                        "percentageOfTotalNetAssets": 6.5,
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()
        _OfflineAdapterClient.responses = [
            _OfflineAdapterResponse(
                body=catalog_body,
                url=adapter._PRODUCT_CATALOG_URL,
                content_type="application/json",
            ),
            _OfflineAdapterResponse(
                body=holdings_body,
                url=holdings_url,
                content_type="application/json",
            ),
        ]
        adapter._cusip_cache["QQQ"] = "46090E103"  # qualification must still read the catalog.
        with request_context(profile, adapter):
            if ordinary:
                result = await adapter.fetch_latest(symbol=symbol)
            else:
                result = await adapter.fetch_latest(
                    symbol=symbol,
                    source_url="https://invalid.example/legacy-route",
                    identifiers={"cusip": "46090E103"},
                )
        assert _OfflineAdapterClient.requested == [adapter._PRODUCT_CATALOG_URL, holdings_url]
    elif provider == "ishares":
        symbol, name = "IGV", "iShares Expanded Tech-Software Sector ETF"
        profile = _native_adapter_profile(adapter, symbol, name)
        catalog_url = ISHARES_US_CATALOG_URL
        catalog_text = _ishares_offline_catalog()
        holdings_url = adapter.resolve_source_url(symbol=symbol, issuer_product_id="239771")
        holdings_payload = {
            "componentsByNameMap": {
                "holdings": {
                    "containersByNameMap": {
                        "all": {
                            "dataPointsByNameMap": {
                                "asOfDate": {"value": "20261102"},
                                "fundTicker": {"value": ["IGV"]},
                                "fundName": {
                                    "value": ["iShares Expanded Tech-Software Sector ETF"]
                                },
                                "dateList": {
                                    "fullName": "holdings.dateList",
                                    "value": [20261102, 20261030, 20260930, 20251231],
                                    "active": False,
                                    "visible": False,
                                },
                                "ticker": {"value": ["MSFT"]},
                                "issueName": {"value": ["Microsoft Corp"]},
                                "holdingPercent": {"value": [6.5]},
                            }
                        }
                    }
                }
            }
        }
        parsed_catalog = parse_ishares_us_product_catalog(catalog_text)

        async def no_cached_catalog(*_args, **_kwargs):
            return None

        async def store_catalog(_db, *, response, ticker, request_log_ids, request_urls):
            assert ticker == symbol
            assert request_urls == [catalog_url]
            body = bytes(response.content)
            return SimpleNamespace(
                cache_id=91,
                catalog=parsed_catalog,
                source_url=catalog_url,
                final_url=catalog_url,
                content_sha256=hashlib.sha256(body).hexdigest(),
                retrieved_at=datetime.now(UTC),
                request_log_ids=tuple(request_log_ids),
            )

        monkeypatch.setattr(adapters_module, "load_cached_ishares_catalog", no_cached_catalog)
        monkeypatch.setattr(adapters_module, "store_ishares_catalog_response", store_catalog)
        binding = None

        def append_log(url):
            assert binding is not None
            request_id = len(binding.request_log_ids) + 1
            binding.request_log_ids.append(request_id)
            binding.request_urls_by_log_id[request_id] = url

        _OfflineAdapterClient.on_get = append_log
        _OfflineAdapterClient.responses = [
            _OfflineAdapterResponse(
                body=catalog_text.encode(), url=catalog_url, content_type="text/html"
            ),
            _OfflineAdapterResponse(
                body=json.dumps(holdings_payload).encode(),
                url=holdings_url,
                content_type="application/json",
            ),
        ]
        with request_context(profile, adapter) as binding:
            result = await adapter.fetch_latest(
                symbol=symbol,
                identifiers={
                    "issuer_product_catalog_key": ISHARES_US_CATALOG_KEY,
                    "canonical_fund_name": name,
                },
            )
        assert _OfflineAdapterClient.requested == [catalog_url, holdings_url]
    elif provider == "amplify":
        symbol, name = "BWET", "Amplify Bitcoin product"
        source_url = adapter.config.url_templates[0]
        raw_csv = (
            "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets\n"
            "11/01/2026,OTHER,FOREIGN,123456789,Other fund holding,10,1,10,10%,100\n"
            "11/02/2026,BWET,NVDA,67066G104,NVIDIA Corp,10,100,1000,10%,10000\n"
        )
        _OfflineAdapterClient.responses = [
            _OfflineAdapterResponse(body=raw_csv.encode(), url=source_url, content_type="text/csv")
        ]
        profile = _native_adapter_profile(adapter, symbol, name)
        with request_context(profile, adapter):
            result = await adapter.fetch_latest(symbol=symbol, source_url=source_url)
    else:
        raise AssertionError(provider)

    if profile is None:
        profile = _native_adapter_profile(adapter, symbol, name)
    return profile, adapter, result


async def _retained_native_failure_fixture(monkeypatch, provider: str):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, provider)
    binding = _OfflineAdapterClient.last_binding
    now = datetime.now(UTC)
    request_ids = list(binding.request_log_ids)
    request_urls = [binding.request_urls_by_log_id[value] for value in request_ids]
    logs = []
    attempts = []
    for index, (request_id, url, captured) in enumerate(
        zip(request_ids, request_urls, _OfflineAdapterClient.captured_responses, strict=True)
    ):
        captured_url, body, capture = captured
        assert captured_url == url
        if provider == "spdr":
            response_payloads = [
                {
                    "kind": "etf_native_response_body",
                    "encoding": "base64",
                    "body_base64": base64.b64encode(body).decode("ascii"),
                    "bytes_received": len(body),
                    "complete": True,
                    "sha256": hashlib.sha256(body).hexdigest(),
                },
                {"kind": "etf_native_response_body_witness", "witness": capture},
            ]
        elif "etf-investments" in url:
            response_payloads = [
                body.decode("utf-8"),
                {"kind": "etf_native_response_body_witness", "witness": capture},
            ]
        else:
            response_payloads = [
                json.loads(body),
                {"kind": "etf_native_response_body_witness", "witness": capture},
            ]
        requested_at = now - timedelta(seconds=3 - index)
        log = SimpleNamespace(
            id=request_id,
            data_source_id=61,
            capability=ProviderCapability.ETF_HOLDINGS,
            operation="fetch_etf_holdings_latest",
            instrument_id=profile.instrument_id,
            provider_symbol=profile.instrument.symbol,
            requested_at=requested_at,
            completed_at=requested_at + timedelta(milliseconds=100),
            success=True,
            http_requests=1,
            settled_usage_units=Decimal("1"),
            response_bytes=len(body),
            response_payloads=response_payloads,
        )
        logs.append(log)
        attempts.append(
            {
                "request_log_id": request_id,
                "request_url": url,
                "success": True,
                "error_type": None,
                "error_message": None,
                "response_headers": {},
                "response_payloads": response_payloads,
            }
        )
    job = SimpleNamespace(
        id=44,
        etf_profile_id=profile.id,
        source_provider=provider,
        job_type=NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE,
        status="failed",
        started_at=now - timedelta(seconds=5),
        failure_reason=(
            "Native qualification source body does not prove the selected fund identity"
            if provider == "spdr"
            else "Native holdings composition completeness is not proven "
            "(provider=ishares, status=incomplete, reason=all-container row vectors are "
            "incomplete or misaligned)."
        ),
        extra_data={
            "qualification_scope": binding.native_initial_qualification_scope,
            "provider_request_log_ids": request_ids,
            "request_urls": request_urls,
        },
    )
    raw_payload = result.raw_json if result.raw_json is not None else result.raw_text
    artifact = ETFHoldingsRawArtifact(
        id=5,
        etf_profile_id=profile.id,
        data_source_id=61,
        source_kind="issuer_adapter_rejected_fetch",
        source_url=result.source_url,
        source_identifier=result.source_identifier,
        content_hash=_hash_payload(raw_payload),
        payload_text=result.raw_text,
        payload_json=result.raw_json,
        legal_metadata={
            "provider_request_log_ids": request_ids,
            "request_urls": request_urls,
            "request_attempts": attempts,
        },
    )
    hostnames = list(dict.fromkeys(url.split("/", 3)[2] for url in request_urls))
    source = SimpleNamespace(
        id=61,
        name=provider,
        config={"etf_holdings_review": {"https_hosts": hostnames}},
    )
    catalog_identity = None
    if provider == "ishares":
        catalog_identity = _issuer_catalog_identity_claim(
            profile, result.legal_metadata["issuer_product_catalog"]
        )
        assert catalog_identity is not None
    return profile, adapter, result, binding, job, artifact, source, logs, catalog_identity


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["spdr", "ishares"])
async def test_retained_native_failure_reparse_uses_exact_settled_evidence_without_transport(
    monkeypatch, provider
):
    fixture = await _retained_native_failure_fixture(monkeypatch, provider)
    profile, adapter, _result, binding, job, artifact, source, logs, catalog_identity = fixture
    request_count = len(_OfflineAdapterClient.requested)
    rebuilt, evidence, continuation = _reparse_retained_native_failure(
        profile=profile,
        adapter=adapter,
        predecessor=job,
        rejected_artifact=artifact,
        source=source,
        request_logs=logs,
        request_urls=list(binding.request_urls_by_log_id.values()),
        catalog_identity=catalog_identity,
    )

    assert rebuilt.rows
    assert evidence["composition_completeness"]["status"] == "complete"
    assert evidence["raw_payload_hash"] == artifact.content_hash
    assert continuation["physical_http_requests"] == 0
    assert continuation["quota_reservations"] == 0
    assert len(_OfflineAdapterClient.requested) == request_count
    if provider == "spdr":
        assert (
            continuation["recovery_input"]["representation"] == "provider_request_log_binary_body"
        )
        assert (
            continuation["recovery_input"]["input_sha256"]
            == continuation["physical_body_capture"]["response_body_sha256"]
        )
    else:
        recovery_input = continuation["recovery_input"]
        assert recovery_input["representation"] == "provider_request_log_normalized_json_object"
        assert recovery_input["normalized_payload_sha256"] == evidence["raw_payload_hash"]
        assert (
            recovery_input["normalized_payload_sha256"]
            != recovery_input["physical_response_sha256"]
        )
        assert "parser_input_sha256" not in recovery_input

    evidence_artifact = SimpleNamespace(
        legal_metadata={
            "retained_evidence_continuation": continuation,
            "provider_request_log_ids": job.extra_data["provider_request_log_ids"],
        },
        payload_json=rebuilt.raw_json,
    )
    _verify_retained_evidence_body_log_link(
        evidence=evidence,
        profile=profile,
        source=source,
        snapshot=SimpleNamespace(source_url=rebuilt.source_url),
        job=job,
        artifact=evidence_artifact,
        request_ids=job.extra_data["provider_request_log_ids"],
        request_urls=job.extra_data["request_urls"],
        logs_by_id={log.id: log for log in logs},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["artifact_hash", "account_scope", "provider_payload"])
async def test_retained_native_failure_reparse_rejects_swapped_or_incomplete_evidence(
    monkeypatch, mutation
):
    fixture = await _retained_native_failure_fixture(monkeypatch, "ishares")
    profile, adapter, _result, binding, job, artifact, source, logs, catalog_identity = fixture
    if mutation == "artifact_hash":
        artifact.content_hash = "f" * 64
    elif mutation == "account_scope":
        capture_payload = next(
            item
            for item in logs[-1].response_payloads
            if item.get("kind") == "etf_native_response_body_witness"
        )
        capture_payload["witness"]["account_scope"] = "foreign:account"
    else:
        artifact.payload_json = {**artifact.payload_json, "fundName": "Foreign Fund"}
        artifact.content_hash = _hash_payload(artifact.payload_json)

    with pytest.raises((ETFNativeSourceEvidenceError, ETFHoldingsRouteHeldError)):
        _reparse_retained_native_failure(
            profile=profile,
            adapter=adapter,
            predecessor=job,
            rejected_artifact=artifact,
            source=source,
            request_logs=logs,
            request_urls=list(binding.request_urls_by_log_id.values()),
            catalog_identity=catalog_identity,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_basis", "expected_date_field"),
    [
        ("spdr", "spdr_fund_workbook_preamble", "composition_date"),
        ("invesco", "invesco_product_catalog", "effective_business_date"),
        ("ishares", "issuer_product_catalog", "composition_date"),
        ("amplify", "amplify_selected_account_csv", "selected_account_rows.date"),
    ],
)
async def test_native_qualification_accepts_actual_offline_adapter_result_and_keeps_schema(
    monkeypatch, provider, expected_basis, expected_date_field
):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, provider)
    initial_binding = _OfflineAdapterClient.last_binding
    assert initial_binding.native_initial_qualification_job_id == 44
    assert initial_binding.native_initial_qualification_scope is not None

    evidence = _native_initial_qualification_fetch_evidence(
        profile,
        adapter,
        result,
        request_binding=initial_binding,
    )
    initial_captured_responses = list(_OfflineAdapterClient.captured_responses)

    ordinary_profile, ordinary_adapter, ordinary_result = await _fetch_native_adapter_result(
        monkeypatch, provider, ordinary=True
    )
    ordinary_binding = _OfflineAdapterClient.last_binding
    assert ordinary_binding.native_initial_qualification_job_id is None
    assert ordinary_binding.native_initial_qualification_scope is None
    assert ordinary_binding.request_log_ids
    assert [
        ordinary_binding.request_urls_by_log_id[request_id]
        for request_id in ordinary_binding.request_log_ids
    ] == _OfflineAdapterClient.requested
    ordinary_evidence = _native_adapter_fetch_evidence(
        ordinary_profile,
        ordinary_adapter,
        ordinary_result,
        request_binding=ordinary_binding,
        require_body_witness=False,
    )

    assert evidence["fund_identity"]["basis"] == expected_basis
    assert {
        key: value
        for key, value in ordinary_evidence["fund_identity"].items()
        if key != "retrieved_at"
    } == {key: value for key, value in evidence["fund_identity"].items() if key != "retrieved_at"}
    assert evidence["composition_date"] == "2026-11-02"
    assert ordinary_evidence["composition_date"] == "2026-11-02"
    assert evidence["composition_date_source_field"] == expected_date_field
    assert ordinary_evidence["composition_date_source_field"] == expected_date_field
    if provider in {"invesco", "ishares"}:
        catalog_url = ordinary_evidence["fund_identity"].get(
            "catalog_request_url", ordinary_evidence["fund_identity"].get("source_url")
        )
        assert catalog_url in (
            ordinary_binding.request_urls_by_log_id[request_id]
            for request_id in ordinary_binding.request_log_ids
        )
    initial_identity_validation = _native_artifact_identity_validation(
        profile,
        _validate_artifact_identity(profile, result.raw_text),
        evidence,
    )
    assert initial_identity_validation["status"] == "matched"
    assert initial_identity_validation["native_fund_identity_evidence"] == evidence["fund_identity"]
    identity_validation = _native_artifact_identity_validation(
        ordinary_profile,
        _validate_artifact_identity(ordinary_profile, ordinary_result.raw_text),
        ordinary_evidence,
    )
    assert identity_validation["status"] == "matched"
    assert (
        identity_validation["native_fund_identity_evidence"] == ordinary_evidence["fund_identity"]
    )
    # This is the same identity/date metadata consumed by capability evaluation
    # after snapshot/state persistence. Neutralize only the static symbol audit;
    # the test is asserting that a fresh, complete native snapshot with these
    # persisted fields is current/cache-eligible.
    from app.services import etf_holdings_capability as capability_module

    monkeypatch.setattr(
        capability_module,
        "symbol_audit_for_profile",
        lambda _profile: SimpleNamespace(tier=None, outcome="current", evidence_state="test"),
    )
    from app.services.etf_holdings_capability import CURRENT, evaluate_capability

    persisted_validation = identity_validation
    snapshot = SimpleNamespace(
        composition_date=date.fromisoformat(ordinary_evidence["composition_date"]),
        as_of_date=None,
        known_at=datetime(2026, 11, 2, 12, tzinfo=UTC),
        published_at=datetime(2026, 11, 2, 12, tzinfo=UTC),
        provenance="issuer_self_snapshotted_holdings",
        source_provider=provider,
        completeness_status="complete",
        row_count=len(result.rows),
        resolved_count=len(result.rows),
        unresolved_count=0,
        extra_data={"artifact_identity_validation": persisted_validation},
        source_url=result.source_url,
    )
    state = SimpleNamespace(
        status="success",
        last_checked_at=datetime(2026, 11, 3, 12, tzinfo=UTC),
        last_success_at=datetime(2026, 11, 3, 12, tzinfo=UTC),
        last_failure_at=None,
        failure_reason=None,
        extra_data={"expected_cadence": "weekly"},
    )
    capability = evaluate_capability(
        profile,
        snapshot,
        state,
        now=datetime(2026, 11, 3, 12, tzinfo=UTC),
    )
    assert capability.identity_verified is True
    assert capability.availability == CURRENT
    assert capability.usable_for_current_analysis is True
    assert evidence["schema_fingerprint"] == _schema_fingerprint_for_adapter_result(result)
    body_witness = evidence["holdings_response_body_witness"]
    provider_capture = body_witness["provider_capture"]
    captured_url, captured_body, actual_capture = initial_captured_responses[-1]
    assert provider_capture == actual_capture
    assert provider_capture["request_log_id"] in initial_binding.request_log_ids
    assert hashlib.sha256(captured_body).hexdigest() == provider_capture["response_body_sha256"]
    assert provider_capture["response_body_bytes"] == len(captured_body)
    assert captured_url == result.source_url
    assert body_witness["parser_input_sha256"] == provider_capture["response_body_sha256"]
    assert body_witness["normalized_payload_sha256"] == evidence["raw_payload_hash"]
    if provider == "spdr":
        assert evidence["raw_payload_hash"] != provider_capture["response_body_sha256"]
    assert "holdings_response_body_witness" not in ordinary_evidence
    if provider == "spdr":
        assert result.source_identifier is None
        assert evidence["source_identifier"] is None
        assert evidence["source_identifier_basis"] == "fund_scoped_spdr_workbook_route"
    elif provider == "invesco":
        assert evidence["fund_identity"]["ticker"] == "QQQ"
        assert evidence["fund_identity"]["cusip"] == "46090E103"
        assert evidence["fund_identity"]["account_name"] == "Invesco QQQ Trust"
        assert evidence["fund_identity"]["catalog_response_sha256"]
    elif provider == "amplify":
        assert evidence["fund_identity"]["account"] == "BWET"
        assert evidence["fund_identity"]["source_url"] == result.source_url
        assert evidence["fund_identity"]["source_date"] == "2026-11-02"
        assert evidence["fund_identity"]["row_count"] == len(result.rows) == 1
        assert [row.symbol for row in result.rows] == ["NVDA"]
        assert "11/01/2026,OTHER,FOREIGN" in result.raw_text
        assert "11/02/2026,BWET,NVDA" in result.raw_text

    # `ingest_holdings_snapshot` writes these adapter-state fields. The
    # qualification verifier must require that durable state before marking
    # the reviewed publisher probe passed.
    from app.services.etf_holdings_refresh import _ensure_schema_fingerprint_is_stable

    composition_date = date.fromisoformat(evidence["composition_date"])
    internal_source_id = 93
    state = SimpleNamespace(
        etf_profile_id=profile.id,
        adapter_key=profile.adapter_key,
        status="success",
        data_source_id=internal_source_id,
        source_url=result.source_url,
        source_identifier=result.source_identifier,
        parser_version=evidence["parser_version"],
        composition_date=composition_date,
        row_count=len(result.rows),
        last_success_at=datetime.now(UTC),
        extra_data={"schema_fingerprint": evidence["schema_fingerprint"]},
    )
    snapshot = SimpleNamespace(
        data_source_id=internal_source_id,
        source_url=result.source_url,
        source_identifier=result.source_identifier,
        parser_version=evidence["parser_version"],
        composition_date=composition_date,
        row_count=len(result.rows),
        extra_data={"schema_fingerprint": evidence["schema_fingerprint"]},
    )
    _verify_persisted_qualification_adapter_state(
        state,
        profile=profile,
        source=SimpleNamespace(name=adapter.source_provider),
        snapshot=snapshot,
        evidence=evidence,
    )
    for invalid_state in (
        None,
        SimpleNamespace(**{**state.__dict__, "extra_data": {"schema_fingerprint": "old"}}),
    ):
        with pytest.raises(ETFHoldingsRouteHeldError, match="persisted adapter schema state"):
            _verify_persisted_qualification_adapter_state(
                invalid_state,
                profile=profile,
                source=SimpleNamespace(name=adapter.source_provider),
                snapshot=snapshot,
                evidence=evidence,
            )

    class _ExistingStateDB:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: state)

    await _ensure_schema_fingerprint_is_stable(
        _ExistingStateDB(),
        ordinary_profile,
        parser_version=evidence["parser_version"],
        raw_payload_text=ordinary_result.raw_text,
        raw_payload_json=ordinary_result.raw_json,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("url_case", ["recorded_redirect", "unbound_redirect", "foreign_host"])
async def test_spdr_native_identity_accepts_only_the_bound_same_fund_redirect(url_case):
    adapter = get_holdings_adapter("spdr")
    assert adapter is not None
    profile = _native_adapter_profile(adapter, "SPY", "State Street SPDR S&P 500 ETF Trust")
    requested_url = adapter._workbook_url("SPY")
    final_url = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
    workbook = _xlsx_for_native_spdr("SPY", "State Street SPDR S&P 500 ETF Trust")
    workbook_rows = parse_xlsx_table(workbook)
    rows, composition_date, fund_symbol = adapter._parse_workbook(workbook, symbol="SPY")
    result = SimpleNamespace(
        rows=rows,
        raw_text=_table_to_text(workbook_rows),
        raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
        source_url=final_url,
        source_identifier=None,
        legal_metadata={
            "source_provider": "spdr",
            "adapter_key": adapter.adapter_key,
            "source_format": "xlsx",
            "composition_date": composition_date.isoformat(),
            "native_composition_completeness": adapter._workbook_completeness(
                workbook_rows,
                rows=rows,
                fund_symbol=fund_symbol,
                composition_date=composition_date,
            ),
        },
    )
    request_urls = {1: requested_url}
    if url_case != "unbound_redirect":
        request_urls[2] = (
            final_url
            if url_case == "recorded_redirect"
            else final_url.replace("www.ssga.com", "attacker.example")
        )
    binding = SimpleNamespace(
        request_log_ids=list(request_urls),
        request_urls_by_log_id=request_urls,
    )
    if url_case == "foreign_host":
        result.source_url = request_urls[2]

    if url_case == "recorded_redirect":
        evidence = _native_adapter_fetch_evidence(
            profile,
            adapter,
            result,
            request_binding=binding,
            require_body_witness=False,
        )
        assert evidence["fund_identity"]["symbol"] == "SPY"
        assert evidence["fund_identity"]["source_url"] == final_url
        assert evidence["composition_date"] == "2026-11-02"
    else:
        with pytest.raises(ETFNativeSourceEvidenceError, match="does not prove the selected fund"):
            _native_adapter_fetch_evidence(
                profile,
                adapter,
                result,
                request_binding=binding,
                require_body_witness=False,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["misaligned_holdings_vector", "active_date_selector"])
async def test_ishares_native_completeness_ignores_only_inactive_date_selector(
    monkeypatch, mutation
):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "ishares")
    points = adapter._blackrock_holdings_data_points(result.raw_json)
    assert points["dateList"]["active"] is False
    completeness = adapter._holdings_all_completeness(result.raw_json, rows=result.rows)
    assert completeness["status"] == "complete"
    assert completeness["reported_rows"] == completeness["parsed_rows"] == len(result.rows)
    assert completeness["all_list_columns_aligned"] is True

    mutated_payload = json.loads(json.dumps(result.raw_json))
    mutated_points = adapter._blackrock_holdings_data_points(mutated_payload)
    if mutation == "misaligned_holdings_vector":
        mutated_points["holdingPercent"]["value"] = []
    else:
        mutated_points["dateList"]["active"] = True
    mutated_evidence = adapter._holdings_all_completeness(mutated_payload, rows=result.rows)
    assert mutated_evidence["status"] == "incomplete"
    result.raw_json = mutated_payload
    result.legal_metadata["native_composition_completeness"] = mutated_evidence
    with pytest.raises(
        ETFNativeSourceEvidenceError,
        match="composition completeness is not proven",
    ):
        _native_adapter_fetch_evidence(
            profile,
            adapter,
            result,
            request_binding=_OfflineAdapterClient.last_binding,
            require_body_witness=False,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [None, "foreign_ticker", "foreign_name", "missing_ticker"])
async def test_ishares_direct_holdings_body_proves_exact_fund_without_catalog(
    monkeypatch, mutation
):
    profile, adapter, result = await _fetch_native_adapter_result(
        monkeypatch, "ishares", ordinary=True
    )
    binding = _OfflineAdapterClient.last_binding
    assert binding.native_initial_qualification_job_id is None
    assert binding.native_initial_qualification_scope is None
    result.legal_metadata.pop("issuer_product_catalog", None)
    points = adapter._blackrock_holdings_data_points(result.raw_json)
    if mutation == "foreign_ticker":
        points["fundTicker"]["value"] = ["XLK"]
    elif mutation == "foreign_name":
        points["fundName"]["value"] = ["iShares U.S. Technology ETF"]
    elif mutation == "missing_ticker":
        points.pop("fundTicker")

    if mutation is not None:
        with pytest.raises(ValueError, match="does not prove|conflicts with the selected iShares"):
            _native_adapter_fetch_evidence(
                profile,
                adapter,
                result,
                request_binding=binding,
                require_body_witness=False,
            )
        return

    evidence = _native_adapter_fetch_evidence(
        profile,
        adapter,
        result,
        request_binding=binding,
        require_body_witness=False,
    )
    assert evidence["fund_identity"]["basis"] == "ishares_holdings_response"
    assert evidence["fund_identity"]["fund_tickers"] == ["IGV"]
    assert evidence["composition_date"] == "2026-11-02"


@pytest.mark.asyncio
async def test_invesco_ordinary_fetch_revalidates_catalog_with_warm_cusip_hint(monkeypatch):
    _OfflineAdapterClient.responses = []
    _OfflineAdapterClient.requested = []
    _OfflineAdapterClient.on_get = None
    _OfflineAdapterClient.last_binding = None
    _OfflineAdapterClient.captured_responses = []
    monkeypatch.setattr(adapters_module.httpx, "AsyncClient", _OfflineAdapterClient)
    adapter = get_holdings_adapter("invesco")
    assert adapter is not None
    adapter._cusip_cache = {"QQQ": "46090E103"}
    profile = _native_adapter_profile(adapter, "QQQ", "Invesco QQQ Trust")
    ordinary_binding = None

    def record_binding():
        nonlocal ordinary_binding
        from app.services import etf_holdings_provider_bridge as bridge

        ordinary_binding = bridge._REQUEST_BINDING.get()

    _OfflineAdapterClient.on_get = lambda _url: record_binding()
    catalog_payload = {
        "response": {
            "docs": [
                {
                    "ticker": "QQQ",
                    "cusip": "46090E103",
                    "accountName": "Invesco QQQ Trust",
                }
            ]
        }
    }
    holdings_payload = {
        "effectiveBusinessDate": "2026-11-02",
        "effectiveDate": "2026-11-03",
        "totalNumberOfHoldings": 1,
        "holdings": [{"ticker": "NVDA", "issuerName": "NVIDIA Corp"}],
    }
    holdings_url = adapter._holdings_url("46090E103")
    _OfflineAdapterClient.responses = [
        _OfflineAdapterResponse(
            body=json.dumps(catalog_payload).encode(),
            url=adapter._PRODUCT_CATALOG_URL,
            content_type="application/json",
        ),
        _OfflineAdapterResponse(
            body=json.dumps(holdings_payload).encode(),
            url=holdings_url,
            content_type="application/json",
        ),
    ]
    with bind_etf_holdings_request_context(
        db=object(),
        adapter=adapter,
        profile_id=profile.id,
        instrument_id=profile.instrument_id,
        provider_symbol="QQQ",
        operation="fetch_etf_holdings_latest",
    ) as binding:
        result = await adapter.fetch_latest(
            symbol="QQQ",
            identifiers={
                "cusip": "46090E103",
            },
        )

    assert ordinary_binding is binding
    assert binding.native_initial_qualification_job_id is None
    assert binding.native_initial_qualification_scope is None
    assert _OfflineAdapterClient.requested == [adapter._PRODUCT_CATALOG_URL, holdings_url]
    catalog = result.legal_metadata["issuer_product_catalog"]
    assert catalog["matched_product"] == {
        "ticker": "QQQ",
        "cusip": "46090E103",
        "account_name": "Invesco QQQ Trust",
    }
    assert (
        hashlib.sha256(base64.b64decode(catalog["response_body_base64"], validate=True)).hexdigest()
        == catalog["response_sha256"]
    )
    assert result.legal_metadata["effective_business_date"] == "2026-11-02"
    ordinary_evidence = _native_adapter_fetch_evidence(
        profile,
        adapter,
        result,
        request_binding=binding,
        require_body_witness=False,
    )
    assert ordinary_evidence["fund_identity"] == {
        "basis": "invesco_product_catalog",
        "ticker": "QQQ",
        "cusip": "46090E103",
        "source_identifier": "46090E103",
        "account_name": "Invesco QQQ Trust",
        "catalog_request_url": adapter._PRODUCT_CATALOG_URL,
        "catalog_response_body_base64": catalog["response_body_base64"],
        "catalog_response_sha256": catalog["response_sha256"],
        "holdings_source_url": holdings_url,
    }
    assert ordinary_evidence["composition_date"] == "2026-11-02"
    assert ordinary_evidence["composition_date_source_field"] == "effective_business_date"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["spdr", "invesco", "ishares", "amplify"])
async def test_ordinary_native_identity_rejects_foreign_fund_or_account(monkeypatch, provider):
    profile, adapter, result = await _fetch_native_adapter_result(
        monkeypatch, provider, ordinary=True
    )
    if provider == "spdr":
        result.raw_text = result.raw_text.replace("Ticker Symbol:,XES", "Ticker Symbol:,OTHER")
    elif provider == "invesco":
        # NVDA occurs in the holdings, but the catalog proves the selected fund is QQQ.
        profile.instrument.symbol = "NVDA"
        profile.instrument.name = "NVIDIA Corp"
    elif provider == "ishares":
        result.legal_metadata.pop("issuer_product_catalog", None)
        adapter._blackrock_holdings_data_points(result.raw_json)["fundTicker"]["value"] = ["OTHER"]
    else:
        result.legal_metadata["selected_account"] = "OTHER"

    with pytest.raises(
        ValueError,
        match="conflicts with the selected fund|conflicts with the selected iShares|does not prove",
    ):
        _native_adapter_fetch_evidence(
            profile,
            adapter,
            result,
            request_binding=_OfflineAdapterClient.last_binding,
            require_body_witness=False,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_witness",
        "wrong_body_hash",
        "swapped_parser_hash",
        "wrong_artifact_hash",
        "wrong_log_id",
        "wrong_scope",
        "catalog_only",
    ],
)
async def test_native_qualification_rejects_unlinked_or_mismatched_response_body(
    monkeypatch, mutation
):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "ishares")
    binding = _OfflineAdapterClient.last_binding
    evidence = result.legal_metadata["native_holdings_response_witness"]
    capture = dict(evidence["provider_capture"])
    evidence["provider_capture"] = capture

    if mutation == "missing_witness":
        result.legal_metadata.pop("native_holdings_response_witness")
    elif mutation == "wrong_body_hash":
        capture["response_body_sha256"] = "f" * 64
    elif mutation == "swapped_parser_hash":
        evidence["parser_input_sha256"] = "e" * 64
    elif mutation == "wrong_artifact_hash":
        evidence["normalized_payload_sha256"] = "d" * 64
    elif mutation == "wrong_log_id":
        capture["request_log_id"] = 9999
    elif mutation == "wrong_scope":
        capture["account_scope"] = "another:account"
    elif mutation == "catalog_only":
        catalog_capture = _OfflineAdapterClient.captured_responses[0][2]
        evidence["provider_capture"] = dict(catalog_capture)
        evidence["parser_input_sha256"] = catalog_capture["response_body_sha256"]
        evidence["parser_input_bytes"] = catalog_capture["response_body_bytes"]

    with pytest.raises((ValueError, ETFHoldingsRouteHeldError), match="Native|native"):
        _native_initial_qualification_fetch_evidence(
            profile,
            adapter,
            result,
            request_binding=binding,
        )


@pytest.mark.asyncio
async def test_native_qualification_persisted_body_link_rejects_wrong_log_or_scope(monkeypatch):
    from app.services.etf_holdings_native_qualification import (
        _verify_native_holdings_body_log_link,
    )

    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "invesco")
    binding = _OfflineAdapterClient.last_binding
    evidence = _native_initial_qualification_fetch_evidence(
        profile, adapter, result, request_binding=binding
    )
    body_witness = evidence["holdings_response_body_witness"]
    capture = body_witness["provider_capture"]
    request_ids = list(binding.request_log_ids)
    request_urls = [binding.request_urls_by_log_id[value] for value in request_ids]
    logs = {
        request_id: SimpleNamespace(
            id=request_id,
            response_bytes=(
                capture["response_body_bytes"] if request_id == capture["request_log_id"] else 0
            ),
            response_payloads=(
                [{"kind": "etf_native_response_body_witness", "witness": capture}]
                if request_id == capture["request_log_id"]
                else []
            ),
        )
        for request_id in request_ids
    }
    source = SimpleNamespace(id=61, name="invesco")
    snapshot = SimpleNamespace(source_url=result.source_url)
    job = SimpleNamespace(
        id=44, extra_data={"qualification_scope": binding.native_initial_qualification_scope}
    )

    _verify_native_holdings_body_log_link(
        evidence=evidence,
        profile=profile,
        source=source,
        snapshot=snapshot,
        job=job,
        request_ids=request_ids,
        request_urls=request_urls,
        logs_by_id=logs,
    )

    wrong_log_evidence = {
        **evidence,
        "holdings_response_body_witness": {
            **body_witness,
            "provider_capture": {
                **capture,
                "request_log_id": request_ids[0],
            },
        },
    }
    with pytest.raises(ETFHoldingsRouteHeldError, match="scope or URL"):
        _verify_native_holdings_body_log_link(
            evidence=wrong_log_evidence,
            profile=profile,
            source=source,
            snapshot=snapshot,
            job=job,
            request_ids=request_ids,
            request_urls=request_urls,
            logs_by_id=logs,
        )


@pytest.mark.asyncio
async def test_native_spdr_persisted_witness_distinguishes_wire_and_normalized_hashes(
    monkeypatch,
):
    from app.services.etf_holdings_native_qualification import (
        _verify_native_holdings_body_log_link,
    )

    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "spdr")
    binding = _OfflineAdapterClient.last_binding
    evidence = _native_initial_qualification_fetch_evidence(
        profile, adapter, result, request_binding=binding
    )
    witness = evidence["holdings_response_body_witness"]
    capture = witness["provider_capture"]
    request_id = capture["request_log_id"]
    _url, body, _captured = _OfflineAdapterClient.captured_responses[-1]
    assert capture["binary_body"] is True
    assert hashlib.sha256(body).hexdigest() == capture["response_body_sha256"]
    assert witness["normalized_payload_sha256"] == evidence["raw_payload_hash"]
    assert witness["normalized_payload_sha256"] != capture["response_body_sha256"]

    binary_payload = {
        "kind": "etf_native_response_body",
        "encoding": "base64",
        "complete": True,
        "bytes_received": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "body_base64": base64.b64encode(body).decode("ascii"),
    }
    log = SimpleNamespace(
        response_bytes=len(body),
        response_payloads=[
            binary_payload,
            {"kind": "etf_native_response_body_witness", "witness": capture},
        ],
    )
    _verify_native_holdings_body_log_link(
        evidence=evidence,
        profile=profile,
        source=SimpleNamespace(id=61, name="spdr"),
        snapshot=SimpleNamespace(source_url=result.source_url),
        job=SimpleNamespace(
            id=44,
            extra_data={"qualification_scope": binding.native_initial_qualification_scope},
        ),
        request_ids=list(binding.request_log_ids),
        request_urls=[binding.request_urls_by_log_id[value] for value in binding.request_log_ids],
        logs_by_id={request_id: log},
    )

    log.response_payloads[0] = {
        **binary_payload,
        "body_base64": base64.b64encode(b"wrong").decode(),
    }
    with pytest.raises(ETFHoldingsRouteHeldError, match="binary response bytes"):
        _verify_native_holdings_body_log_link(
            evidence=evidence,
            profile=profile,
            source=SimpleNamespace(id=61, name="spdr"),
            snapshot=SimpleNamespace(source_url=result.source_url),
            job=SimpleNamespace(
                id=44,
                extra_data={"qualification_scope": binding.native_initial_qualification_scope},
            ),
            request_ids=list(binding.request_log_ids),
            request_urls=[
                binding.request_urls_by_log_id[value] for value in binding.request_log_ids
            ],
            logs_by_id={request_id: log},
        )

    wrong_scope_job = SimpleNamespace(
        id=44,
        extra_data={
            "qualification_scope": {
                **binding.native_initial_qualification_scope,
                "account_scope": "other:account",
            }
        },
    )
    with pytest.raises(ETFHoldingsRouteHeldError, match="scope or URL"):
        _verify_native_holdings_body_log_link(
            evidence=evidence,
            profile=profile,
            source=SimpleNamespace(id=61, name="spdr"),
            snapshot=SimpleNamespace(source_url=result.source_url),
            job=wrong_scope_job,
            request_ids=list(binding.request_log_ids),
            request_urls=[
                binding.request_urls_by_log_id[value] for value in binding.request_log_ids
            ],
            logs_by_id={request_id: log},
        )


def _schema_fingerprint_for_adapter_result(result):
    from app.services.etf_holdings_refresh import _schema_fingerprint

    return _schema_fingerprint(raw_payload_text=result.raw_text, raw_payload_json=result.raw_json)


@pytest.mark.asyncio
async def test_invesco_catalog_identity_is_bound_to_scoped_provider_body_log(monkeypatch):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "invesco")
    evidence = _native_initial_qualification_fetch_evidence(profile, adapter, result)[
        "fund_identity"
    ]
    catalog_payload = json.loads(
        base64.b64decode(evidence["catalog_response_body_base64"], validate=True)
    )
    catalog_url = evidence["catalog_request_url"]
    holdings_url = evidence["holdings_source_url"]
    provider_log = SimpleNamespace(
        id=71,
        data_source_id=61,
        capability=ProviderCapability.ETF_HOLDINGS,
        operation="fetch_etf_holdings_latest",
        instrument_id=profile.instrument_id,
        provider_symbol="QQQ",
        success=True,
        response_payloads=[catalog_payload],
    )

    class _CatalogEvidenceDB:
        async def get(self, model, object_id):
            assert model.__name__ == "ProviderRequestLog"
            assert object_id == 71
            return provider_log

    source = SimpleNamespace(id=61)
    job = SimpleNamespace(
        extra_data={
            "provider_request_log_ids": [71, 72],
            "request_urls": [catalog_url, holdings_url],
        }
    )
    await _verify_invesco_catalog_identity_evidence(
        _CatalogEvidenceDB(),
        evidence=evidence,
        profile=profile,
        source=source,
        job=job,
    )

    provider_log.response_payloads = [{"response": {"docs": []}}]
    with pytest.raises(ETFHoldingsRouteHeldError, match="do not match their settled Provider"):
        await _verify_invesco_catalog_identity_evidence(
            _CatalogEvidenceDB(),
            evidence=evidence,
            profile=profile,
            source=source,
            job=job,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["spdr", "invesco", "ishares", "amplify"])
async def test_native_adapter_results_reject_missing_reported_date_and_non_spdr_identifier(
    monkeypatch, provider
):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, provider)
    ordinary_profile, ordinary_adapter, ordinary_result = await _fetch_native_adapter_result(
        monkeypatch, provider, ordinary=True
    )
    ordinary_binding = _OfflineAdapterClient.last_binding
    assert ordinary_binding.native_initial_qualification_job_id is None
    assert ordinary_binding.native_initial_qualification_scope is None
    metadata = result.legal_metadata
    for field in ("composition_date", "effective_business_date", "effective_date", "as_of_date"):
        metadata.pop(field, None)
    ordinary_metadata = ordinary_result.legal_metadata
    for field in ("composition_date", "effective_business_date", "effective_date", "as_of_date"):
        ordinary_metadata.pop(field, None)
    if provider == "amplify":
        # Amplify's reported composition date is the date on the selected
        # account rows themselves, not a separate metadata field.
        result.raw_text = result.raw_text.replace("11/02/2026,BWET,", "not-a-date,BWET,")
        ordinary_result.raw_text = ordinary_result.raw_text.replace(
            "11/02/2026,BWET,", "not-a-date,BWET,"
        )
    with pytest.raises(ValueError, match="provider-reported composition date"):
        _native_initial_qualification_fetch_evidence(profile, adapter, result)
    with pytest.raises(ValueError, match="provider-reported composition date"):
        _native_adapter_fetch_evidence(
            ordinary_profile,
            ordinary_adapter,
            ordinary_result,
            request_binding=ordinary_binding,
            require_body_witness=False,
        )

    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, provider)
    result.source_identifier = None
    if provider in {"spdr", "amplify"}:
        evidence = _native_initial_qualification_fetch_evidence(profile, adapter, result)
        assert evidence["source_identifier"] is None
        assert evidence["fund_identity"]["basis"] == (
            "spdr_fund_workbook_preamble" if provider == "spdr" else "amplify_selected_account_csv"
        )
    else:
        with pytest.raises(ValueError, match="source identifier"):
            _native_initial_qualification_fetch_evidence(profile, adapter, result)


@pytest.mark.asyncio
async def test_native_spdr_preamble_rejects_foreign_fund_even_if_holdings_contain_target_symbol(
    monkeypatch,
):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "spdr")
    result.raw_text = result.raw_text.replace("Ticker Symbol:,XES", "Ticker Symbol:,OTHER")
    result.raw_text = result.raw_text.replace("Microsoft Corp,MSFT", "XES Common Stock,XES")
    assert "XES" in result.raw_text  # It remains present as the actual constituent symbol.
    with pytest.raises(ValueError, match="conflicts with the selected fund identity"):
        _native_initial_qualification_fetch_evidence(profile, adapter, result)


@pytest.mark.asyncio
async def test_native_amplify_account_filter_rejects_foreign_rows_and_stale_selected_account_date(
    monkeypatch,
):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "amplify")
    result.rows = []
    with pytest.raises(ValueError, match="does not prove the selected fund"):
        _native_initial_qualification_fetch_evidence(profile, adapter, result)

    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "invesco")
    stale_payload = dict(result.raw_json)
    stale_payload["effectiveBusinessDate"] = "2025-01-01"
    result.raw_json = stale_payload
    result.raw_text = json.dumps(stale_payload)
    result.legal_metadata["effective_business_date"] = "2025-01-01"
    result.legal_metadata["expected_cadence"] = "daily"
    with pytest.raises(ValueError, match="is stale"):
        _native_initial_qualification_fetch_evidence(profile, adapter, result)


@pytest.mark.asyncio
async def test_native_invesco_catalog_does_not_accept_requested_ticker_as_a_constituent(
    monkeypatch,
):
    profile, adapter, result = await _fetch_native_adapter_result(monkeypatch, "invesco")
    profile.instrument.symbol = "NVDA"
    profile.instrument.name = "NVIDIA Corp"
    assert result.raw_json["holdings"][0]["ticker"] == "NVDA"
    with pytest.raises(ValueError, match="does not prove the selected fund"):
        _native_initial_qualification_fetch_evidence(profile, adapter, result)


def test_native_evidence_rejects_wrong_adapter_publisher_binding():
    profile, adapter, fetch_result = _native_fetch_fixture(
        raw_text="Fund Ticker,TST\n", metadata={"composition_date": "2026-10-30"}
    )
    adapter.source_provider = "other_issuer"

    with pytest.raises(ValueError, match="does not match the ETF profile"):
        _native_initial_qualification_fetch_evidence(profile, adapter, fetch_result)


def _ishares_catalog_html():
    return """<!doctype html><html><body>
    <p>Showing 2 of 2 total funds</p><table>
    <tr><th>Ticker</th><th>Name</th></tr>
    <tr><td><a href="/us/products/239771/ishares-expanded-tech-software-sector-etf">IGV</a></td>
        <td><a href="/us/products/239771/ishares-expanded-tech-software-sector-etf">iShares Expanded Tech-Software Sector ETF</a></td></tr>
    <tr><td><a href="/us/products/239726">XLK</a></td>
        <td><a href="/us/products/239726">iShares Technology ETF</a></td></tr>
    </table></body></html>"""


def _ishares_catalog_evidence_fixture(*, cache_hit=False, cached_request_symbol="IGV"):
    profile, adapter, fetch_result = _native_fetch_fixture(
        raw_json={"holdings": [{"ticker": "MSFT", "weight": 1.0}]}, symbol="IGV"
    )
    profile.instrument.name = "iShares Expanded Tech-Software Sector ETF"
    profile.adapter_key = "ishares"
    profile.provider_aliases.update(
        {"holdings_adapter": "ishares", "holdings_source_provider": "ishares"}
    )
    adapter.adapter_key = "ishares"
    adapter.source_provider = "ishares"
    fetch_result.legal_metadata.update(
        {
            "source_provider": "ishares",
            "adapter_key": "ishares",
            "source_format": "json",
            "parser_version": "ishares-json-v1",
        }
    )
    fetch_result.legal_metadata["native_holdings_response_witness"]["provider_capture"][
        "provider"
    ] = "ishares"
    fetch_result.legal_metadata["native_composition_completeness"] = {
        "basis": "blackrock_holdings_all_container",
        "status": "complete",
        "all_reported_rows_parsed": True,
        "reported_rows": len(fetch_result.rows),
        "parsed_rows": len(fetch_result.rows),
        "core_columns_aligned": True,
        "all_list_columns_aligned": True,
        "authoritative_total_matches": True,
        "continuation_clear": True,
    }
    html = _ishares_catalog_html()
    body = html.encode()
    content_hash = hashlib.sha256(body).hexdigest()
    fetched_at = datetime.now(UTC)
    catalog = parse_ishares_us_product_catalog(html)
    product = catalog.product_for("IGV")
    assert product is not None
    catalog_log_symbol = cached_request_symbol
    catalog_metadata = {
        "catalog_key": ISHARES_US_CATALOG_KEY,
        "catalog_source_url": ISHARES_US_CATALOG_URL,
        "catalog_final_url": ISHARES_US_CATALOG_URL,
        "catalog_content_sha256": content_hash,
        "catalog_retrieved_at": fetched_at.isoformat(),
        "catalog_request_log_ids": [71],
        "catalog_cache_id": 91,
        "catalog_cache_hit": cache_hit,
        "ticker": product.ticker,
        "name": product.name,
        "issuer_product_id": product.product_id,
        "product_url": product.product_url,
        "catalog_complete": catalog.complete,
        "catalog_reported_total": catalog.reported_total,
    }
    fetch_result.legal_metadata["issuer_product_catalog"] = catalog_metadata
    cache = SimpleNamespace(
        id=91,
        provider_name="ishares",
        catalog_key=ISHARES_US_CATALOG_KEY,
        data_source_id=61,
        source_url=ISHARES_US_CATALOG_URL,
        final_url=ISHARES_US_CATALOG_URL,
        content_sha256=content_hash,
        response_bytes=len(body),
        response_encoding="utf-8",
        raw_body_base64=base64.b64encode(body).decode("ascii"),
        parsed_entries=[entry.as_json() for entry in catalog.entries],
        reported_total=catalog.reported_total,
        catalog_complete=catalog.complete,
        requested_symbol=catalog_log_symbol,
        provider_request_log_ids=[71],
        request_urls=[ISHARES_US_CATALOG_URL],
        fetched_at=fetched_at,
    )
    catalog_log = SimpleNamespace(
        id=71,
        data_source_id=61,
        capability=ProviderCapability.ETF_HOLDINGS,
        operation="fetch_etf_holdings_latest",
        instrument_id=824,
        provider_symbol=catalog_log_symbol,
        success=True,
        completed_at=fetched_at,
    )
    product_log = SimpleNamespace(
        id=72,
        data_source_id=61,
        capability=ProviderCapability.ETF_HOLDINGS,
        operation="fetch_etf_holdings_latest",
        instrument_id=profile.instrument_id,
        provider_symbol="IGV",
        success=True,
        completed_at=fetched_at,
    )
    source = SimpleNamespace(id=61, name="ishares")
    job = SimpleNamespace(
        extra_data={
            "provider_request_log_ids": [71, 72],
            "request_urls": [ISHARES_US_CATALOG_URL, "https://www.ishares.com/api/holdings"],
        }
    )

    class _ScalarRows:
        def all(self):
            return [catalog_log]

    class _ReadOnlyDB:
        async def get(self, model, object_id):
            assert object_id == 91
            return cache

        async def scalars(self, _statement):
            return _ScalarRows()

    return profile, adapter, fetch_result, source, job, _ReadOnlyDB(), cache, product_log


def test_native_evidence_accepts_exact_complete_ishares_catalog_identity():
    profile, adapter, fetch_result, *_ = _ishares_catalog_evidence_fixture()

    evidence = _native_initial_qualification_fetch_evidence(profile, adapter, fetch_result)

    assert evidence["fund_identity"] == {
        "basis": "issuer_product_catalog",
        "catalog_key": ISHARES_US_CATALOG_KEY,
        "cache_id": 91,
        "content_sha256": hashlib.sha256(_ishares_catalog_html().encode()).hexdigest(),
        "retrieved_at": fetch_result.legal_metadata["issuer_product_catalog"][
            "catalog_retrieved_at"
        ],
        "source_url": ISHARES_US_CATALOG_URL,
        "final_url": ISHARES_US_CATALOG_URL,
        "ticker": "IGV",
        "name": "iShares Expanded Tech-Software Sector ETF",
        "product_id": "239771",
        "product_url": "https://www.ishares.com/us/products/239771/ishares-expanded-tech-software-sector-etf",
        "catalog_complete": True,
        "catalog_reported_total": 2,
        "request_log_ids": [71],
        "cache_hit": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticker", "OTHER"),
        ("name", "iShares Different Fund"),
        ("issuer_product_id", "239726"),
        ("catalog_complete", False),
        ("catalog_content_sha256", "x" * 64),
        ("product_url", "https://elsewhere.example/products/239771"),
    ],
)
def test_native_catalog_identity_claim_rejects_conflicting_catalog_fields(field, value):
    profile, adapter, fetch_result, *_ = _ishares_catalog_evidence_fixture()
    fetch_result.legal_metadata["issuer_product_catalog"][field] = value

    with pytest.raises(ValueError, match="does not prove"):
        _native_initial_qualification_fetch_evidence(profile, adapter, fetch_result)


@pytest.mark.asyncio
async def test_native_catalog_identity_rechecks_cached_raw_bytes_and_request_lineage():
    from app.services.etf_holdings_native_qualification import _issuer_catalog_identity_claim

    profile, adapter, fetch_result, source, job, db, cache, _product_log = (
        _ishares_catalog_evidence_fixture()
    )
    identity = _issuer_catalog_identity_claim(
        profile, fetch_result.legal_metadata["issuer_product_catalog"]
    )
    assert identity is not None

    await _verify_issuer_catalog_identity_evidence(
        db, evidence=identity, profile=profile, source=source, job=job
    )

    cache.raw_body_base64 = base64.b64encode(b"different catalog bytes").decode("ascii")
    with pytest.raises(ETFHoldingsRouteHeldError, match="raw content failed verification"):
        await _verify_issuer_catalog_identity_evidence(
            db, evidence=identity, profile=profile, source=source, job=job
        )


@pytest.mark.asyncio
async def test_native_catalog_cache_hit_uses_its_original_scoped_lineage():
    from app.services.etf_holdings_native_qualification import _issuer_catalog_identity_claim

    profile, _adapter, fetch_result, source, _job, db, cache, _product_log = (
        _ishares_catalog_evidence_fixture(cache_hit=True, cached_request_symbol="XLK")
    )
    identity = _issuer_catalog_identity_claim(
        profile, fetch_result.legal_metadata["issuer_product_catalog"]
    )
    assert identity is not None
    job = SimpleNamespace(
        extra_data={
            "provider_request_log_ids": [72],
            "request_urls": ["https://www.ishares.com/api/holdings"],
        }
    )

    await _verify_issuer_catalog_identity_evidence(
        db, evidence=identity, profile=profile, source=source, job=job
    )

    cache.requested_symbol = "OTHER"
    with pytest.raises(ETFHoldingsRouteHeldError, match="Provider request lineage is invalid"):
        await _verify_issuer_catalog_identity_evidence(
            db, evidence=identity, profile=profile, source=source, job=job
        )


@pytest.mark.asyncio
async def test_native_catalog_identity_rejects_a_conflicting_reported_total():
    from app.services.etf_holdings_native_qualification import _issuer_catalog_identity_claim

    profile, _adapter, fetch_result, source, job, db, _cache, _product_log = (
        _ishares_catalog_evidence_fixture()
    )
    identity = _issuer_catalog_identity_claim(
        profile, fetch_result.legal_metadata["issuer_product_catalog"]
    )
    assert identity is not None
    identity["catalog_reported_total"] = 482

    with pytest.raises(ETFHoldingsRouteHeldError, match="row does not exactly identify"):
        await _verify_issuer_catalog_identity_evidence(
            db, evidence=identity, profile=profile, source=source, job=job
        )
