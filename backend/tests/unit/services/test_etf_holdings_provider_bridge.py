import asyncio
import threading

import httpx
import pytest

from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    LoopLocalHTTPXAttempt,
    _normalized_host,
    _sync_provider_invoke,
)


def test_publisher_host_requires_https_and_normalizes_idna():
    assert _normalized_host("https://WWW.Example.com:443/path") == "www.example.com"
    assert _normalized_host("https://münich.example/holdings") == "xn--mnich-kva.example"

    with pytest.raises(ETFHoldingsRouteHeldError):
        _normalized_host("http://example.com/holdings")
    with pytest.raises(ETFHoldingsRouteHeldError):
        _normalized_host("https://user:secret@example.com/holdings")


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
