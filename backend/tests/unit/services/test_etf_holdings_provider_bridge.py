import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.services import etf_holdings_provider_bridge as bridge
from app.services.etf_holdings_adapters import httpx as adapter_httpx
from app.services.etf_holdings_adapters import requests as adapter_requests
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    LoopLocalHTTPXAttempt,
    _normalized_host,
    _sync_provider_invoke,
    bind_etf_holdings_request_context,
)


def test_publisher_host_requires_https_and_normalizes_idna():
    assert _normalized_host("https://WWW.Example.com:443/path") == "www.example.com"
    assert _normalized_host("https://münich.example/holdings") == "xn--mnich-kva.example"

    with pytest.raises(ETFHoldingsRouteHeldError):
        _normalized_host("http://example.com/holdings")
    with pytest.raises(ETFHoldingsRouteHeldError):
        _normalized_host("https://user:secret@example.com/holdings")


def _run_in_finite_worker(function, *args):
    results = []
    errors = []

    def run():
        try:
            results.append(function(*args))
        except BaseException as exc:  # propagate worker failures to the test loop
            errors.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "loop-local HTTPX attempt exceeded its five-second bound"
    if errors:
        raise errors[0]
    assert len(results) == 1
    return results[0]


def _run_sync_attempt_in_finite_worker(single_attempt):
    return _run_in_finite_worker(_sync_provider_invoke(single_attempt), None, "AAA")


def test_provider_sync_callback_rejects_raw_async_callable():
    calls = []

    async def one_attempt():
        calls.append("called")
        return "response"

    invoke = _sync_provider_invoke(one_attempt)
    with pytest.raises(TypeError, match="must use LoopLocalHTTPXAttempt"):
        invoke(object(), "SPY")
    assert calls == []


def test_provider_sync_callback_completes_one_httpx_attempt_without_following_redirect():
    requested_urls = []
    factory_loops = []

    def transport(request):
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://publisher.example/second"},
            request=request,
        )

    def transport_factory():
        factory_loops.append(asyncio.get_running_loop().is_running())
        return httpx.MockTransport(transport)

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://publisher.example/first",
        request_kwargs={},
        client_kwargs={},
        transport_factory=transport_factory,
    )
    invoke = _sync_provider_invoke(attempt)
    result = []
    worker = threading.Thread(target=lambda: result.append(invoke(object(), "SPY")))
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive(), "sync Provider callback did not finish HTTPX attempt"
    assert len(result) == 1
    assert result[0].status_code == 302
    assert requested_urls == ["https://publisher.example/first"]
    assert factory_loops == [True]


def test_provider_sync_callback_does_not_reinvoke_sync_attempt():
    calls = []

    def one_attempt():
        calls.append("called")
        return "response"

    invoke = _sync_provider_invoke(one_attempt)
    result = invoke(object(), "SPY")

    assert result == "response"
    assert calls == ["called"]


@pytest.mark.asyncio
async def test_adapter_httpx_redirects_are_dispatched_as_separate_shared_attempts(monkeypatch):
    urls = []
    db = object()
    adapter = SimpleNamespace(source_provider="publisher")

    async def fake_execute(db_arg, **kwargs):
        assert db_arg is db
        attempt = kwargs["single_attempt"]
        urls.append((kwargs["request_url"], attempt.method, attempt.request_kwargs))
        request = httpx.Request(attempt.method, kwargs["request_url"])
        if len(urls) == 1:
            response = httpx.Response(
                302,
                headers={"location": "/holdings.csv"},
                request=request,
            )
        else:
            response = httpx.Response(200, text="symbol,weight\nAAA,1\n", request=request)
        return SimpleNamespace(result=response, request_log_id=len(urls))

    monkeypatch.setattr(
        "app.services.etf_holdings_provider_bridge.execute_etf_holdings_request_attempt",
        fake_execute,
    )
    with bind_etf_holdings_request_context(
        db=db,
        adapter=adapter,
        instrument_id=7,
        provider_symbol="AAA",
        operation="fetch_etf_holdings_latest",
    ) as binding:
        async with adapter_httpx.AsyncClient(timeout=2) as client:
            response = await client.get(
                "https://publisher.example/product",
                follow_redirects=True,
            )

    assert response.status_code == 200
    assert [url for url, _method, _kwargs in urls] == [
        "https://publisher.example/product",
        "https://publisher.example/holdings.csv",
    ]
    assert all("follow_redirects" not in kwargs for _url, _method, kwargs in urls)
    assert binding.request_log_ids == [1, 2]


@pytest.mark.asyncio
async def test_bound_legacy_requests_fallback_is_denied_before_transport():
    db = object()
    adapter = SimpleNamespace(source_provider="publisher")
    with bind_etf_holdings_request_context(
        db=db,
        adapter=adapter,
        instrument_id=7,
        provider_symbol="AAA",
        operation="fetch_etf_holdings_latest",
    ):
        with pytest.raises(ETFHoldingsRouteHeldError, match="legacy requests transport"):
            await asyncio.to_thread(adapter_requests.get, "https://publisher.example/holdings")


@pytest.mark.asyncio
async def test_unbound_direct_adapter_httpx_and_sec_clients_fail_before_transport():
    async with adapter_httpx.AsyncClient(timeout=1) as client:
        with pytest.raises(ETFHoldingsRouteHeldError, match="without a bound shared-admission"):
            await client.get("https://publisher.example/holdings")

    from app.services import etf_holdings_refresh as refresh

    async with refresh.httpx.AsyncClient(timeout=1) as client:
        with pytest.raises(ETFHoldingsRouteHeldError, match="without a bound shared-admission"):
            await client.get("https://discovery.example/funds.csv")

    from app.services import etf_holdings_edgar as edgar

    with pytest.raises(ETFHoldingsRouteHeldError, match="dedicated reviewed ETF_HOLDINGS binding"):
        edgar.httpx.AsyncClient(timeout=1)


@pytest.mark.asyncio
async def test_bound_httpx_rejects_caller_loop_async_body_before_provider_dispatch(monkeypatch):
    dispatches = []
    db = object()
    adapter = SimpleNamespace(source_provider="publisher")

    async def forbidden_dispatch(*_args, **_kwargs):
        dispatches.append("called")
        raise AssertionError("loop-bound body must be rejected before provider dispatch")

    async def body_stream():
        yield b"payload"

    body = body_stream()
    monkeypatch.setattr(
        "app.services.etf_holdings_provider_bridge.execute_etf_holdings_request_attempt",
        forbidden_dispatch,
    )
    with bind_etf_holdings_request_context(
        db=db,
        adapter=adapter,
        instrument_id=7,
        provider_symbol="AAA",
        operation="fetch_etf_holdings_latest",
    ):
        async with adapter_httpx.AsyncClient(timeout=2) as client:
            with pytest.raises(ETFHoldingsRouteHeldError, match="caller-loop async state"):
                await client.post("https://publisher.example/holdings", content=body)
    await body.aclose()
    assert dispatches == []


@pytest.mark.asyncio
async def test_client_defaults_redirect_credentials_and_scoped_cookies_use_real_httpx_attempts(
    monkeypatch,
):
    observed = []

    def transport(request):
        observed.append((str(request.url), request.headers, request.content))
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={
                    "location": "/same-origin",
                    "set-cookie": "session=publisher; Path=/; Secure",
                },
                request=request,
            )
        if request.url.path == "/same-origin":
            return httpx.Response(
                302,
                headers={"location": "https://elsewhere.example/final"},
                request=request,
            )
        return httpx.Response(200, text="done", request=request)

    original_attempt_factory = bridge._make_loop_local_httpx_attempt

    def mock_attempt_factory(**kwargs):
        return original_attempt_factory(
            **kwargs,
            transport_factory=lambda: httpx.MockTransport(transport),
        )

    monkeypatch.setattr(bridge, "_make_loop_local_httpx_attempt", mock_attempt_factory)

    async def execute_attempt(_db, **kwargs):
        response = _run_sync_attempt_in_finite_worker(kwargs["single_attempt"])
        return SimpleNamespace(result=response, request_log_id=len(observed))

    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", execute_attempt)
    db = object()
    adapter = SimpleNamespace(source_provider="publisher")
    with bind_etf_holdings_request_context(
        db=db,
        adapter=adapter,
        instrument_id=7,
        provider_symbol="AAA",
        operation="fetch_etf_holdings_latest",
    ):
        # follow_redirects is a supported AsyncClient default, not only a
        # per-request option. Each hop still passes through a fresh admitted
        # worker-local HTTPX client.
        async with adapter_httpx.AsyncClient(
            follow_redirects=True,
            headers={
                "Authorization": "Bearer origin-secret",
                "Proxy-Authorization": "Basic origin-secret",
            },
        ) as client:
            response = await client.get(
                "https://publisher.example/start",
                headers={"Cookie": "explicit=origin-secret"},
            )
            scoped_cookie_response = await client.get("https://publisher.example/next")

    assert response.status_code == 200
    assert scoped_cookie_response.status_code == 200
    assert len(observed) == 4
    assert [str(item[0]) for item in observed] == [
        "https://publisher.example/start",
        "https://publisher.example/same-origin",
        "https://elsewhere.example/final",
        "https://publisher.example/next",
    ]
    same_origin_headers = observed[1][1]
    assert same_origin_headers["authorization"] == "Bearer origin-secret"
    assert same_origin_headers["cookie"] == "explicit=origin-secret"
    cross_origin_headers = observed[2][1]
    for name in ("authorization", "cookie", "proxy-authorization"):
        assert name not in cross_origin_headers
    assert "session=publisher" in observed[3][1]["cookie"]
    assert len(response.history) == 2


@pytest.mark.parametrize(
    ("status", "expected_method", "expected_body"),
    [
        (301, "GET", b""),
        (302, "GET", b""),
        (303, "GET", b""),
        (307, "POST", b'{"symbol":"AAA"}'),
        (308, "POST", b'{"symbol":"AAA"}'),
    ],
)
@pytest.mark.asyncio
async def test_post_redirect_body_semantics_are_httpx_compatible(
    monkeypatch, status, expected_method, expected_body
):
    observed = []

    def transport(request):
        observed.append((request.method, request.content, request.headers))
        if len(observed) == 1:
            return httpx.Response(
                status,
                headers={"location": "/after-redirect"},
                request=request,
            )
        return httpx.Response(200, text="ok", request=request)

    original_attempt_factory = bridge._make_loop_local_httpx_attempt
    monkeypatch.setattr(
        bridge,
        "_make_loop_local_httpx_attempt",
        lambda **kwargs: original_attempt_factory(
            **kwargs,
            transport_factory=lambda: httpx.MockTransport(transport),
        ),
    )

    async def execute_attempt(_db, **kwargs):
        response = _run_sync_attempt_in_finite_worker(kwargs["single_attempt"])
        return SimpleNamespace(result=response, request_log_id=len(observed))

    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", execute_attempt)
    with bind_etf_holdings_request_context(
        db=object(),
        adapter=SimpleNamespace(source_provider="publisher"),
        instrument_id=7,
        provider_symbol="AAA",
        operation="fetch_etf_holdings_latest",
    ):
        async with adapter_httpx.AsyncClient(follow_redirects=True) as client:
            result = await client.post("https://publisher.example/submit", json={"symbol": "AAA"})

    assert result.status_code == 200
    assert observed[1][0] == expected_method
    assert observed[1][1] == expected_body
    if expected_method == "GET":
        assert "content-type" not in observed[1][2]
        assert "content-length" not in observed[1][2]


@pytest.mark.asyncio
async def test_real_issuer_adapter_through_refresh_uses_worker_local_mocktransport(monkeypatch):
    from app.services import etf_holdings_refresh as refresh
    from app.services.etf_holdings_adapters import (
        IssuerCsvAdapterConfig,
        IssuerCsvHoldingsAdapter,
    )

    observed = []

    def transport(request):
        observed.append(str(request.url))
        if request.url.path == "/DXJ.csv":
            return httpx.Response(
                302,
                headers={"location": "/funds/DXJ.csv"},
                request=request,
            )
        return httpx.Response(
            200,
            text="Symbol,Weight\nDXJ,1.0\n",
            headers={"content-type": "text/csv"},
            request=request,
        )

    original_attempt_factory = bridge._make_loop_local_httpx_attempt
    monkeypatch.setattr(
        bridge,
        "_make_loop_local_httpx_attempt",
        lambda **kwargs: original_attempt_factory(
            **kwargs,
            transport_factory=lambda: httpx.MockTransport(transport),
        ),
    )
    dispatches = []

    async def reviewed_offline_attempt(
        _db, _capability, operation, *, instrument_id, provider_symbol, invoke, **kwargs
    ):
        assert operation == "fetch_etf_holdings_latest"
        assert instrument_id == 42
        assert provider_symbol == "DXJ"
        provider_adapter = kwargs["etf_holdings_adapters"]["fixture"]
        response = _run_in_finite_worker(invoke, provider_adapter, provider_symbol)
        dispatches.append(response.status_code)
        return SimpleNamespace(result=response, request_log_id=len(dispatches))

    async def reviewed_policy_context(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bridge, "_review_attempt_context", reviewed_policy_context)
    monkeypatch.setattr(bridge, "execute_provider_call", reviewed_offline_attempt)

    adapter = IssuerCsvHoldingsAdapter(
        IssuerCsvAdapterConfig(
            adapter_key="fixture",
            source_provider="fixture",
            url_templates=("https://publisher.example/{symbol}.csv",),
            supports_sec_filing_fallback=False,
        )
    )
    profile = SimpleNamespace(
        id=12,
        adapter_key="fixture",
        instrument=SimpleNamespace(id=42, symbol="DXJ", name="fixture DXJ"),
        provider_aliases={},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
    )
    monkeypatch.setattr(refresh, "get_holdings_adapter", lambda _key: adapter)
    monkeypatch.setattr(
        refresh,
        "_validate_artifact_identity",
        lambda *_args, **_kwargs: {"status": "matched"},
    )
    ingested = {}

    async def capture_ingestion(_db, **kwargs):
        ingested.update(kwargs)
        return SimpleNamespace(id=99, source_provider=kwargs["source_provider"])

    async def accept_schema(*_args, **_kwargs):
        return None

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", capture_ingestion)
    monkeypatch.setattr(refresh, "_ensure_schema_fingerprint_is_stable", accept_schema)

    result = await refresh._refresh_adapter_route(object(), profile)

    assert result.source_provider == "fixture"
    assert ingested["legal_metadata"]["provider_request_log_ids"] == [1, 2]
    assert dispatches == [302, 200]
    assert observed == [
        "https://publisher.example/DXJ.csv",
        "https://publisher.example/funds/DXJ.csv",
    ]
