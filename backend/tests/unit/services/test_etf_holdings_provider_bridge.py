import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.services import etf_holdings_provider_bridge as bridge
from app.services.etf_holdings_adapters import httpx as adapter_httpx
from app.services.etf_holdings_adapters import requests as adapter_requests
from app.services.etf_holdings_provider_bridge import (
    ETF_SEC_MAX_AGGREGATE_DECODED_BYTES,
    ETF_SEC_MAX_ARCHIVE_PAGE_BYTES,
    ETF_SEC_MAX_FILING_BYTES,
    ETF_SEC_MAX_PHYSICAL_ATTEMPTS,
    ETF_SEC_MAX_REDIRECTS_PER_GET,
    ETF_SEC_MAX_SUBMISSIONS_BYTES,
    ETFHoldingsRouteHeldError,
    ETFSECExecutionBudget,
    LoopLocalHTTPXAttempt,
    ProviderBackedHTTPXClient,
    _normalized_host,
    _sync_provider_invoke,
    bind_etf_holdings_request_context,
)


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        return None


def test_publisher_host_requires_https_and_normalizes_idna():
    assert _normalized_host("https://WWW.Example.com:443/path") == "www.example.com"
    assert _normalized_host("https://münich.example/holdings") == "xn--mnich-kva.example"

    with pytest.raises(ETFHoldingsRouteHeldError):
        _normalized_host("http://example.com/holdings")
    with pytest.raises(ETFHoldingsRouteHeldError):
        _normalized_host("https://user:secret@example.com/holdings")


def test_edgar_ip_scope_requires_namespaced_shared_account_mapping():
    assert not bridge._has_explicit_account_scope_mapping(
        "edgar", "ip", {"edgar": "incorrect-provider-level-alias"}
    )


@pytest.mark.asyncio
async def test_vaneck_initial_transport_streams_and_stops_at_cumulative_body_cap():
    body = _ChunkStream([b"abc", b"def", b"ghi"])
    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://www.vaneck.com/oih.xlsx",
        request_kwargs={},
        client_kwargs={},
        transport_factory=lambda: httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-length": "1"},
                stream=body,
                request=request,
            )
        ),
        max_response_bytes=5,
        deadline_monotonic=time.monotonic() + 2,
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="5 MiB response limit"):
        await attempt.execute()


@pytest.mark.asyncio
async def test_vaneck_initial_transport_refuses_send_after_slow_setup_crosses_deadline():
    sends = 0

    async def handler(request):
        nonlocal sends
        sends += 1
        return httpx.Response(200, content=b"ok", request=request)

    def slow_transport_factory():
        time.sleep(0.04)
        return httpx.MockTransport(handler)

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://www.vaneck.com/oih.xlsx",
        request_kwargs={},
        client_kwargs={},
        transport_factory=slow_transport_factory,
        max_response_bytes=1024,
        deadline_monotonic=time.monotonic() + 0.01,
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="expired before transport"):
        await attempt.execute()
    assert sends == 0


@pytest.mark.asyncio
async def test_vaneck_initial_transport_cancels_in_flight_send_at_deadline():
    cancelled = asyncio.Event()

    async def handler(request):
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(200, content=b"late", request=request)

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://www.vaneck.com/oih.xlsx",
        request_kwargs={},
        client_kwargs={},
        transport_factory=lambda: httpx.MockTransport(handler),
        max_response_bytes=1024,
        deadline_monotonic=time.monotonic() + 0.03,
    )

    with pytest.raises(TimeoutError):
        await attempt.execute()
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_sec_execution_budget_enforces_total_attempt_archive_page_and_deadline():
    assert ETF_SEC_MAX_REDIRECTS_PER_GET == 2
    budget = ETFSECExecutionBudget()
    assert (
        budget.response_limit("fetch_etf_holdings_sec_submissions") == ETF_SEC_MAX_SUBMISSIONS_BYTES
    )
    assert (
        budget.response_limit("fetch_etf_holdings_sec_submissions_file")
        == ETF_SEC_MAX_ARCHIVE_PAGE_BYTES
    )
    assert budget.response_limit("fetch_etf_holdings_sec_filing") == ETF_SEC_MAX_FILING_BYTES
    for _ in range(ETF_SEC_MAX_PHYSICAL_ATTEMPTS):
        await budget.start_attempt()
        # Simulate elapsed spacing without sleeping through the full envelope.
        budget.last_attempt_started_at -= 1.0
    assert budget.physical_attempts == 9
    with pytest.raises(ETFHoldingsRouteHeldError, match="attempt limit"):
        await budget.before_attempt()

    budget = ETFSECExecutionBudget()
    budget.begin_logical_request("fetch_etf_holdings_sec_submissions_file")
    with pytest.raises(ETFHoldingsRouteHeldError, match="page limit"):
        budget.begin_logical_request("fetch_etf_holdings_sec_submissions_file")

    budget = ETFSECExecutionBudget()
    budget.deadline_at = 0
    with pytest.raises(ETFHoldingsRouteHeldError, match="deadline"):
        await budget.before_attempt()


def test_sec_fund_deadline_wins_equal_attempt_timeout_bound(monkeypatch):
    monkeypatch.setattr(bridge, "ETF_SEC_ATTEMPT_TIMEOUT_SECONDS", 0.25)
    budget_clock = 123.0
    monkeypatch.setattr(bridge, "_sec_budget_monotonic", lambda: budget_clock)
    budget = ETFSECExecutionBudget()
    budget.deadline_at = budget_clock + 0.25

    timeout_seconds, fund_deadline_selected = budget.attempt_timeout_selection()

    assert timeout_seconds == 0.25
    assert fund_deadline_selected is True


def test_expired_sec_budget_refuses_worker_transport_before_factory_or_send():
    budget = ETFSECExecutionBudget()
    budget.deadline_at = time.monotonic() - 0.01
    factory_calls = []

    def transport_factory():
        factory_calls.append("created")
        return httpx.MockTransport(lambda request: httpx.Response(200, request=request))

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        request_kwargs={},
        client_kwargs={},
        transport_factory=transport_factory,
        sec_budget=budget,
        sec_operation="fetch_etf_holdings_sec_submissions",
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="deadline exceeded"):
        _run_sync_attempt_in_finite_worker(attempt)

    assert factory_calls == []
    assert budget.physical_attempts == 0
    assert budget._terminal_failure == "SEC one-fund execution deadline exceeded"


def test_initial_qualification_authority_expiry_clamps_whole_call_budget():
    from app.services.provider_runtime import (
        _ETF_INITIAL_QUALIFICATION_OPERATIONS,
        _new_etf_initial_qualification_authority,
    )

    authority = _new_etf_initial_qualification_authority(
        attempt_id=1,
        provider_name="edgar",
        capability=bridge.ProviderCapability.ETF_HOLDINGS,
        operations=_ETF_INITIAL_QUALIFICATION_OPERATIONS,
        profile_id=2,
        instrument_id=3,
        provider_symbol="IWM",
        account_scope="reviewed-edgar-ip",
        expires_at=datetime.now(UTC) + timedelta(seconds=0.2),
    )
    budget = ETFSECExecutionBudget(authority)

    assert budget.deadline_at - budget.started_at < bridge.ETF_SEC_FUND_DEADLINE_SECONDS
    assert 0 < budget.whole_call_timeout_seconds() <= 0.2


def test_qualification_authority_expiry_during_slow_factory_prevents_send():
    from app.services.provider_runtime import (
        _ETF_INITIAL_QUALIFICATION_OPERATIONS,
        _new_etf_initial_qualification_authority,
    )

    authority = _new_etf_initial_qualification_authority(
        attempt_id=1,
        provider_name="edgar",
        capability=bridge.ProviderCapability.ETF_HOLDINGS,
        operations=_ETF_INITIAL_QUALIFICATION_OPERATIONS,
        profile_id=2,
        instrument_id=3,
        provider_symbol="IWM",
        account_scope="reviewed-edgar-ip",
        expires_at=datetime.now(UTC) + timedelta(seconds=0.05),
    )
    budget = ETFSECExecutionBudget(authority)
    factory_calls = []
    send_calls = []

    def transport_factory():
        time.sleep(0.1)
        factory_calls.append("created")
        return httpx.MockTransport(
            lambda request: send_calls.append(str(request.url))
            or httpx.Response(200, request=request)
        )

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        request_kwargs={},
        client_kwargs={},
        transport_factory=transport_factory,
        sec_budget=budget,
        sec_operation="fetch_etf_holdings_sec_submissions",
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="deadline exceeded"):
        _run_sync_attempt_in_finite_worker(attempt)

    assert factory_calls == ["created"]
    assert send_calls == []
    assert budget.physical_attempts == 1
    assert budget._terminal_failure == "SEC one-fund execution deadline exceeded"


def test_qualification_authority_expiry_cancels_in_flight_httpx_transport():
    from app.services.provider_runtime import (
        _ETF_INITIAL_QUALIFICATION_OPERATIONS,
        _new_etf_initial_qualification_authority,
    )

    authority = _new_etf_initial_qualification_authority(
        attempt_id=1,
        provider_name="edgar",
        capability=bridge.ProviderCapability.ETF_HOLDINGS,
        operations=_ETF_INITIAL_QUALIFICATION_OPERATIONS,
        profile_id=2,
        instrument_id=3,
        provider_symbol="IWM",
        account_scope="reviewed-edgar-ip",
        expires_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    budget = ETFSECExecutionBudget(authority)
    transport_state = {"started": threading.Event(), "cancelled": threading.Event()}

    class WaitingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            transport_state["started"].set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                transport_state["cancelled"].set()
                raise

        async def aclose(self):
            return None

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        request_kwargs={},
        client_kwargs={},
        transport_factory=WaitingTransport,
        sec_budget=budget,
        sec_operation="fetch_etf_holdings_sec_submissions",
    )

    with pytest.raises(TimeoutError, match="SEC one-fund execution deadline exceeded"):
        _run_sync_attempt_in_finite_worker(attempt)

    assert transport_state["started"].is_set()
    assert transport_state["cancelled"].is_set()
    assert budget._terminal_failure == "SEC one-fund execution deadline exceeded"
    with pytest.raises(ETFHoldingsRouteHeldError, match="terminal response"):
        _run_sync_attempt_in_finite_worker(attempt)


def test_sec_worker_rechecks_deadline_after_slow_setup_before_send(monkeypatch):
    monkeypatch.setattr(bridge, "ETF_SEC_ATTEMPT_TIMEOUT_SECONDS", 0.75)
    budget = ETFSECExecutionBudget()
    budget.deadline_at = time.monotonic() + 0.05
    factory_calls = []
    send_calls = []

    def transport_factory():
        # Model loop-local client/transport setup that crosses the whole-fund
        # deadline after the early guard but before HTTPX can send.
        time.sleep(0.1)
        factory_calls.append("created")

        def handler(request):
            send_calls.append(str(request.url))
            return httpx.Response(200, request=request)

        return httpx.MockTransport(handler)

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        request_kwargs={},
        client_kwargs={},
        transport_factory=transport_factory,
        sec_budget=budget,
        sec_operation="fetch_etf_holdings_sec_submissions",
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="deadline exceeded"):
        _run_sync_attempt_in_finite_worker(attempt)

    assert factory_calls == ["created"]
    assert send_calls == []
    assert budget.physical_attempts == 1
    assert budget._terminal_failure == "SEC one-fund execution deadline exceeded"


def test_sec_worker_cancels_real_httpx_transport_at_remaining_fund_deadline(monkeypatch):
    # Bound a regression failure too: the old fixed-attempt behavior must not
    # leave a daemon worker alive for the production twenty-second timeout.
    monkeypatch.setattr(bridge, "ETF_SEC_ATTEMPT_TIMEOUT_SECONDS", 0.75)
    budget_clock = time.monotonic()
    # The loop's own timer still advances normally; only the SEC budget clock
    # is held just before expiry to reproduce timer/clock boundary skew.
    monkeypatch.setattr(bridge, "_sec_budget_monotonic", lambda: budget_clock)
    budget = ETFSECExecutionBudget()
    budget.deadline_at = budget_clock + 0.2
    transports = []

    class WaitingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.started = threading.Event()
            self.cancelled = threading.Event()

        async def handle_async_request(self, request):
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

        async def aclose(self):
            return None

    def transport_factory():
        transport = WaitingTransport()
        transports.append(transport)
        return transport

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        request_kwargs={},
        client_kwargs={},
        transport_factory=transport_factory,
        sec_budget=budget,
        sec_operation="fetch_etf_holdings_sec_submissions",
    )
    started_at = time.monotonic()

    with pytest.raises(TimeoutError, match="SEC one-fund execution deadline exceeded"):
        _run_sync_attempt_in_finite_worker(attempt)

    elapsed = time.monotonic() - started_at
    assert len(transports) == 1
    assert transports[0].started.is_set()
    assert transports[0].cancelled.is_set()
    assert elapsed < 0.6
    assert budget._terminal_failure == "SEC one-fund execution deadline exceeded"
    assert bridge._sec_budget_monotonic() < budget.deadline_at

    # A later physical attempt is refused before another transport is built.
    with pytest.raises(ETFHoldingsRouteHeldError, match="terminal response"):
        _run_sync_attempt_in_finite_worker(attempt)
    assert len(transports) == 1


def test_sec_worker_attempt_cap_timeout_does_not_latch_fund_deadline(monkeypatch):
    monkeypatch.setattr(bridge, "ETF_SEC_ATTEMPT_TIMEOUT_SECONDS", 0.05)
    budget_clock = time.monotonic()
    monkeypatch.setattr(bridge, "_sec_budget_monotonic", lambda: budget_clock)
    budget = ETFSECExecutionBudget()
    budget.deadline_at = budget_clock + 0.5
    transports = []

    class WaitingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.started = threading.Event()
            self.cancelled = threading.Event()

        async def handle_async_request(self, request):
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

        async def aclose(self):
            return None

    def transport_factory():
        transport = WaitingTransport()
        transports.append(transport)
        return transport

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        request_kwargs={},
        client_kwargs={},
        transport_factory=transport_factory,
        sec_budget=budget,
        sec_operation="fetch_etf_holdings_sec_submissions",
    )

    with pytest.raises(TimeoutError) as raised:
        _run_sync_attempt_in_finite_worker(attempt)

    assert str(raised.value) == ""
    assert len(transports) == 1
    assert transports[0].started.is_set()
    assert transports[0].cancelled.is_set()
    assert budget._terminal_failure is None
    assert bridge._sec_budget_monotonic() < budget.deadline_at


def test_transport_timeout_before_timer_does_not_latch_fund_deadline(monkeypatch):
    monkeypatch.setattr(bridge, "ETF_SEC_ATTEMPT_TIMEOUT_SECONDS", 0.5)
    budget_clock = time.monotonic()
    monkeypatch.setattr(bridge, "_sec_budget_monotonic", lambda: budget_clock)
    budget = ETFSECExecutionBudget()
    budget.deadline_at = budget_clock + 2.0
    transport_calls = []

    async def transport_handler(request):
        transport_calls.append(str(request.url))
        raise TimeoutError("transport timed out before selected timer")

    attempt = LoopLocalHTTPXAttempt(
        method="GET",
        url="https://data.sec.gov/submissions/CIK0000000001.json",
        request_kwargs={},
        client_kwargs={},
        transport_factory=lambda: httpx.MockTransport(transport_handler),
        sec_budget=budget,
        sec_operation="fetch_etf_holdings_sec_submissions",
    )

    with pytest.raises(TimeoutError, match="transport timed out before selected timer"):
        _run_sync_attempt_in_finite_worker(attempt)

    assert transport_calls == ["https://data.sec.gov/submissions/CIK0000000001.json"]
    assert budget._terminal_failure is None


@pytest.mark.asyncio
async def test_sec_physical_attempt_limit_denies_before_shared_admission_or_transport(monkeypatch):
    budget = ETFSECExecutionBudget()
    budget.physical_attempts = ETF_SEC_MAX_PHYSICAL_ATTEMPTS
    adapter = SimpleNamespace(adapter_key="edgar_sec_holdings", source_provider="edgar")
    execute_calls = []

    async def execute_attempt(*_args, **_kwargs):
        execute_calls.append("admission")
        raise AssertionError("capped request must be rejected before shared admission")

    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", execute_attempt)
    with bridge.bind_etf_holdings_sec_request_context(
        db=object(),
        adapter=adapter,
        profile_id=17,
        instrument_id=23,
        provider_symbol="IWM",
        operation="fetch_etf_holdings_sec_submissions",
        sec_budget=budget,
    ):
        async with ProviderBackedHTTPXClient(follow_redirects=True, max_redirects=20) as client:
            with pytest.raises(ETFHoldingsRouteHeldError, match="attempt limit"):
                await client.get("https://data.sec.gov/submissions/CIK0001100663.json")
    assert execute_calls == []


@pytest.mark.asyncio
async def test_sec_streaming_gzip_cap_stops_at_one_decoded_byte_over_limit():
    import gzip

    from app.services.etf_holdings_provider_bridge import (
        _ETF_SEC_RESPONSE_LIMIT_MARKER,
        _read_bounded_sec_response,
    )

    exact_budget = ETFSECExecutionBudget()
    exact_response = httpx.Response(
        200,
        stream=httpx.ByteStream(b"x" * ETF_SEC_MAX_SUBMISSIONS_BYTES),
        request=httpx.Request("GET", "https://data.sec.gov/submissions/CIK0001100663.json"),
    )
    exact_bounded = await _read_bounded_sec_response(
        exact_response,
        budget=exact_budget,
        operation="fetch_etf_holdings_sec_submissions",
    )
    await exact_response.aclose()
    assert len(exact_bounded.content) == ETF_SEC_MAX_SUBMISSIONS_BYTES
    assert _ETF_SEC_RESPONSE_LIMIT_MARKER not in exact_bounded.extensions

    expanded = b"x" * (ETF_SEC_MAX_SUBMISSIONS_BYTES + 9)
    response = httpx.Response(
        200,
        headers={"content-encoding": "gzip"},
        stream=httpx.ByteStream(gzip.compress(expanded)),
        request=httpx.Request("GET", "https://data.sec.gov/submissions/CIK0001100663.json"),
    )
    budget = ETFSECExecutionBudget()
    bounded = await _read_bounded_sec_response(
        response,
        budget=budget,
        operation="fetch_etf_holdings_sec_submissions",
    )
    await response.aclose()
    assert len(bounded.content) == ETF_SEC_MAX_SUBMISSIONS_BYTES + 1
    assert budget.aggregate_decoded_bytes == ETF_SEC_MAX_SUBMISSIONS_BYTES + 1
    assert "application byte cap" in bounded.extensions[_ETF_SEC_RESPONSE_LIMIT_MARKER]


@pytest.mark.asyncio
@pytest.mark.parametrize("trailing", [b"", b"trailing-bytes"])
async def test_sec_gzip_rejects_concatenated_members_and_trailing_bytes(trailing):
    import gzip

    from app.services.etf_holdings_provider_bridge import (
        _ETF_SEC_RESPONSE_LIMIT_MARKER,
        _read_bounded_sec_response,
    )

    compressed = gzip.compress(b'{"filings":[]}') + (
        gzip.compress(b'{"filings":["second-member"]}') if not trailing else trailing
    )
    response = httpx.Response(
        200,
        headers={"content-encoding": "gzip"},
        stream=httpx.ByteStream(compressed),
        request=httpx.Request("GET", "https://data.sec.gov/submissions/CIK0001100663.json"),
    )
    budget = ETFSECExecutionBudget()
    bounded = await _read_bounded_sec_response(
        response,
        budget=budget,
        operation="fetch_etf_holdings_sec_submissions",
    )
    await response.aclose()
    assert "trailing or concatenated" in bounded.extensions[_ETF_SEC_RESPONSE_LIMIT_MARKER]
    with pytest.raises(ETFHoldingsRouteHeldError, match="terminal response"):
        await budget.before_attempt()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", [403, 429, "body_limit"])
async def test_sec_terminal_response_denies_next_candidate_before_shared_admission(
    monkeypatch, terminal_status
):
    from app.services.etf_holdings_provider_bridge import _ETF_SEC_RESPONSE_LIMIT_MARKER

    execute_calls = []

    async def execute_attempt(_db, **_kwargs):
        execute_calls.append("admission")
        if terminal_status == "body_limit":
            response = httpx.Response(
                200,
                request=httpx.Request("GET", "https://archives.sec.gov/candidate-one.xml"),
                extensions={_ETF_SEC_RESPONSE_LIMIT_MARKER: "SEC response byte cap exceeded"},
            )
        else:
            response = httpx.Response(
                terminal_status,
                request=httpx.Request("GET", "https://archives.sec.gov/candidate-one.xml"),
            )
        return SimpleNamespace(result=response)

    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", execute_attempt)
    budget = ETFSECExecutionBudget()
    adapter = SimpleNamespace(adapter_key="edgar_sec_holdings", source_provider="edgar")
    with bridge.bind_etf_holdings_sec_request_context(
        db=object(),
        adapter=adapter,
        profile_id=17,
        instrument_id=23,
        provider_symbol="IWM",
        operation="fetch_etf_holdings_sec_filing",
        sec_budget=budget,
    ):
        async with ProviderBackedHTTPXClient() as client:
            if terminal_status == "body_limit":
                with pytest.raises(ETFHoldingsRouteHeldError, match="byte cap"):
                    await client.get("https://archives.sec.gov/candidate-one.xml")
            else:
                first = await client.get("https://archives.sec.gov/candidate-one.xml")
                assert first.status_code == terminal_status
            with pytest.raises(ETFHoldingsRouteHeldError, match="terminal response"):
                await client.get("https://archives.sec.gov/candidate-two.xml")

    assert execute_calls == ["admission"]


@pytest.mark.asyncio
async def test_sec_aggregate_decoded_cap_includes_each_response_body():
    from app.services.etf_holdings_provider_bridge import (
        _ETF_SEC_RESPONSE_LIMIT_MARKER,
        _read_bounded_sec_response,
    )

    budget = ETFSECExecutionBudget()
    budget.aggregate_decoded_bytes = ETF_SEC_MAX_AGGREGATE_DECODED_BYTES - 2
    response = httpx.Response(
        200,
        stream=httpx.ByteStream(b"body"),
        request=httpx.Request("GET", "https://data.sec.gov/submissions/CIK0001100663.json"),
    )
    bounded = await _read_bounded_sec_response(
        response,
        budget=budget,
        operation="fetch_etf_holdings_sec_submissions",
    )
    await response.aclose()
    assert bounded.content == b"bod"
    assert budget.aggregate_decoded_bytes == ETF_SEC_MAX_AGGREGATE_DECODED_BYTES + 1
    assert "aggregate decoded" in bounded.extensions[_ETF_SEC_RESPONSE_LIMIT_MARKER]


@pytest.mark.asyncio
async def test_sec_attempt_spacing_is_at_least_one_second():
    budget = ETFSECExecutionBudget()
    await budget.start_attempt()
    started = time.monotonic()
    await budget.before_attempt()
    assert time.monotonic() - started >= 0.95


@pytest.mark.asyncio
async def test_sec_logical_get_follows_at_most_two_redirects(monkeypatch):
    requests = []

    def transport(request):
        requests.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": f"/hop-{len(requests)}"},
            stream=httpx.ByteStream(b""),
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

    async def execute_attempt(_db, **kwargs):
        response = _run_sync_attempt_in_finite_worker(kwargs["single_attempt"])
        return SimpleNamespace(result=response)

    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", execute_attempt)
    budget = ETFSECExecutionBudget()
    adapter = SimpleNamespace(adapter_key="edgar_sec_holdings", source_provider="edgar")
    with bridge.bind_etf_holdings_sec_request_context(
        db=object(),
        adapter=adapter,
        profile_id=17,
        instrument_id=23,
        provider_symbol="IWM",
        operation="fetch_etf_holdings_sec_submissions",
        sec_budget=budget,
    ):
        async with ProviderBackedHTTPXClient(follow_redirects=True, max_redirects=20) as client:
            with pytest.raises(httpx.TooManyRedirects):
                await client.get("https://data.sec.gov/submissions/CIK0001100663.json")

    assert len(requests) == ETF_SEC_MAX_REDIRECTS_PER_GET + 1
    assert budget.physical_attempts == ETF_SEC_MAX_REDIRECTS_PER_GET + 1


@pytest.mark.asyncio
async def test_sec_logical_get_does_not_retry_transport_failures(monkeypatch):
    requests = []

    def transport(request):
        requests.append(str(request.url))
        raise httpx.ConnectError("synthetic transport failure", request=request)

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
        return SimpleNamespace(result=response)

    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", execute_attempt)
    budget = ETFSECExecutionBudget()
    adapter = SimpleNamespace(adapter_key="edgar_sec_holdings", source_provider="edgar")
    with bridge.bind_etf_holdings_sec_request_context(
        db=object(),
        adapter=adapter,
        profile_id=17,
        instrument_id=23,
        provider_symbol="IWM",
        operation="fetch_etf_holdings_sec_submissions",
        sec_budget=budget,
    ):
        async with ProviderBackedHTTPXClient(follow_redirects=True, max_redirects=20) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get("https://data.sec.gov/submissions/CIK0001100663.json")

    assert len(requests) == 1
    assert budget.physical_attempts == 1
    assert not bridge._has_explicit_account_scope_mapping("edgar", "ip", {"edgar:ip": ""})
    assert not bridge._has_explicit_account_scope_mapping("edgar", "ip", {"edgar:ip": "   "})
    assert bridge._has_explicit_account_scope_mapping(
        "EDGAR", "IP", {"edgar:ip": "reviewed-shared-egress-scope"}
    )
    assert bridge._has_explicit_account_scope_mapping(
        "other", "account", {"other": "existing-account-alias"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "account_scopes",
    [
        {"edgar": "ignored"},
        {"edgar:ip": ""},
        {"edgar:ip": "   "},
    ],
)
async def test_edgar_attempt_review_rejects_unbound_scope_before_cost_admission(
    monkeypatch, account_scopes
):
    profile = SimpleNamespace(
        id=17,
        instrument_id=23,
        adapter_key="edgar",
        provider_aliases={"holdings_source_provider": "edgar"},
    )
    instrument = SimpleNamespace(id=23, symbol="SPY")
    source = SimpleNamespace(
        id=31,
        name="edgar",
        config={
            "etf_holdings_review": {
                "https_hosts": ["data.sec.gov"],
                "account_scope": "edgar:shared-ip",
                "operations": {
                    "fetch_etf_holdings_latest": {
                        "evidence_source": "reviewed-test-contract",
                        "evidence_version": "test-v1",
                        "reviewed_at": "2026-10-23T00:00:00Z",
                    }
                },
            }
        },
    )
    policy = SimpleNamespace(is_enabled=True, quota_scope="ip")
    entitlement = SimpleNamespace(id=41)

    class ReviewSession:
        def __init__(self):
            self.scalar_results = iter((source, policy, entitlement))
            self.cost_checks = 0

        async def get(self, model, _identity):
            if model is bridge.ETFProfile:
                return profile
            if model is bridge.Instrument:
                return instrument
            raise AssertionError(f"unexpected identity model: {model}")

        async def scalar(self, _statement):
            return next(self.scalar_results)

        async def run_sync(self, _callback):
            self.cost_checks += 1
            raise AssertionError("scope denial must happen before recurring-cost admission")

    session = ReviewSession()
    monkeypatch.setattr(bridge.settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", account_scopes)

    with pytest.raises(
        ETFHoldingsRouteHeldError, match="account binding is not explicitly configured"
    ):
        await bridge._review_attempt_context(
            session,
            provider_name="edgar",
            profile_id=17,
            instrument_id=23,
            provider_symbol="SPY",
            adapter_key="edgar",
            operation="fetch_etf_holdings_latest",
            request_url="https://data.sec.gov/submissions/CIK0000000001.json",
        )

    assert session.cost_checks == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "account_scopes",
    [
        {"edgar": "ignored"},
        {"edgar:ip": ""},
        {"edgar:ip": "   "},
    ],
)
async def test_edgar_unbound_scope_never_reaches_shared_provider_attempt(
    monkeypatch, account_scopes
):
    source = SimpleNamespace(
        id=31,
        name="edgar",
        config={
            "etf_holdings_review": {
                "https_hosts": ["data.sec.gov"],
                "account_scope": "edgar:shared-ip",
                "operations": {
                    "fetch_etf_holdings_latest": {
                        "evidence_source": "reviewed-test-contract",
                        "evidence_version": "test-v1",
                        "reviewed_at": "2026-10-23T00:00:00Z",
                    }
                },
            }
        },
    )
    policy = SimpleNamespace(is_enabled=True, quota_scope="ip")
    entitlement = SimpleNamespace(id=41)
    profile = SimpleNamespace(
        instrument_id=23,
        adapter_key="edgar",
        provider_aliases={"holdings_source_provider": "edgar"},
    )
    instrument = SimpleNamespace(id=23, symbol="SPY")

    class AttemptSession:
        def __init__(self, *, bind, expire_on_commit):
            self.bind = bind
            self.expire_on_commit = expire_on_commit
            self.scalar_results = iter((source, policy, entitlement))
            self.cost_checks = 0
            self.commits = 0
            self.rollbacks = 0
            self.closed = False

        async def get(self, model, _identity):
            if model is bridge.ETFProfile:
                return profile
            if model is bridge.Instrument:
                return instrument
            raise AssertionError(f"unexpected identity model: {model}")

        async def scalar(self, _statement):
            return next(self.scalar_results)

        async def run_sync(self, _callback):
            self.cost_checks += 1
            raise AssertionError("scope denial must happen before recurring-cost admission")

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

        async def close(self):
            self.closed = True

    sessions = []

    def make_session(**kwargs):
        session = AttemptSession(**kwargs)
        sessions.append(session)
        return session

    provider_calls = []

    async def fake_execute_provider_call(*_args, **_kwargs):
        provider_calls.append("called")
        raise AssertionError("unbound scope must not reserve or dispatch")

    monkeypatch.setattr(bridge, "AsyncSession", make_session)
    monkeypatch.setattr(bridge, "execute_provider_call", fake_execute_provider_call)
    monkeypatch.setattr(bridge.settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", account_scopes)
    transport_calls = []

    def transport():
        transport_calls.append("called")
        return "response"

    adapter = SimpleNamespace(source_provider="edgar", adapter_key="edgar")
    with bind_etf_holdings_request_context(
        db=SimpleNamespace(bind=object()),
        adapter=adapter,
        profile_id=17,
        instrument_id=23,
        provider_symbol="SPY",
        operation="fetch_etf_holdings_latest",
    ):
        with pytest.raises(
            ETFHoldingsRouteHeldError, match="account binding is not explicitly configured"
        ):
            await bridge.execute_etf_holdings_request_attempt(
                SimpleNamespace(bind=object()),
                adapter=adapter,
                instrument_id=23,
                provider_symbol="SPY",
                operation="fetch_etf_holdings_latest",
                request_url="https://data.sec.gov/submissions/CIK0000000001.json",
                single_attempt=transport,
            )

    assert provider_calls == []
    assert transport_calls == []
    assert len(sessions) == 1
    assert sessions[0].cost_checks == 0
    assert sessions[0].commits == 0
    assert sessions[0].rollbacks == 1
    assert sessions[0].closed


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
        binding = bridge._REQUEST_BINDING.get()
        request_log_id = len(urls)
        binding.request_log_ids.append(request_log_id)
        binding.request_urls_by_log_id[request_log_id] = kwargs["request_url"]
        request = httpx.Request(attempt.method, kwargs["request_url"])
        if len(urls) == 1:
            response = httpx.Response(
                302,
                headers={"location": "/holdings.csv"},
                request=request,
            )
        else:
            response = httpx.Response(200, text="symbol,weight\nAAA,1\n", request=request)
        return SimpleNamespace(result=response, request_log_id=request_log_id)

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

    async with edgar.httpx.AsyncClient(timeout=1) as client:
        with pytest.raises(ETFHoldingsRouteHeldError, match="without a bound shared-admission"):
            await client.get("https://data.sec.gov/submissions/CIK0000000001.json")


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
        request_log_id = len(dispatches)
        kwargs["request_log_id_callback"](request_log_id)
        return SimpleNamespace(result=response, request_log_id=request_log_id)

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

    async def offline_execute_attempt(_db, **kwargs):
        invoke = _sync_provider_invoke(kwargs["single_attempt"])
        response = _run_in_finite_worker(invoke, None, None)
        dispatches.append(response.status_code)
        request_log_id = len(dispatches)
        binding = bridge._REQUEST_BINDING.get()
        binding.request_log_ids.append(request_log_id)
        binding.request_urls_by_log_id[request_log_id] = kwargs["request_url"]
        return SimpleNamespace(result=response, request_log_id=request_log_id)

    async def accept_schema(*_args, **_kwargs):
        return None

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", capture_ingestion)
    monkeypatch.setattr(refresh, "_ensure_schema_fingerprint_is_stable", accept_schema)
    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", offline_execute_attempt)

    result = await refresh._refresh_adapter_route(object(), profile)

    assert result.source_provider == "fixture"
    assert ingested["legal_metadata"]["provider_request_log_ids"] == [1, 2]
    assert dispatches == [302, 200]
    assert observed == [
        "https://publisher.example/DXJ.csv",
        "https://publisher.example/funds/DXJ.csv",
    ]


@pytest.mark.asyncio
async def test_issuer_refresh_sec_fallback_cannot_borrow_native_binding(monkeypatch):
    from app.services import etf_holdings_edgar as edgar
    from app.services import etf_holdings_refresh as refresh
    from app.services.etf_holdings_adapters import (
        IssuerCsvAdapterConfig,
        IssuerCsvHoldingsAdapter,
    )

    observed = []
    sec_client_attempts = []

    def transport(request):
        observed.append(str(request.url))
        return httpx.Response(503, request=request)

    original_attempt_factory = bridge._make_loop_local_httpx_attempt
    monkeypatch.setattr(
        bridge,
        "_make_loop_local_httpx_attempt",
        lambda **kwargs: original_attempt_factory(
            **kwargs,
            transport_factory=lambda: httpx.MockTransport(transport),
        ),
    )

    async def offline_native_attempt(_db, **kwargs):
        invoke = _sync_provider_invoke(kwargs["single_attempt"])
        response = _run_in_finite_worker(invoke, None, None)
        kwargs["request_log_id_callback"](1)
        return SimpleNamespace(result=response, request_log_id=1)

    def forbidden_sec_client(*_args, **_kwargs):
        sec_client_attempts.append("constructed")
        raise AssertionError("SEC client construction must be denied by the ambient guard")

    monkeypatch.setattr(bridge, "execute_etf_holdings_request_attempt", offline_native_attempt)
    monkeypatch.setattr(edgar.httpx, "AsyncClient", forbidden_sec_client)

    adapter = IssuerCsvHoldingsAdapter(
        IssuerCsvAdapterConfig(
            adapter_key="fixture",
            source_provider="fixture",
            url_templates=("https://publisher.example/{symbol}.csv",),
            supports_sec_filing_fallback=True,
        )
    )
    profile = SimpleNamespace(
        id=12,
        adapter_key="fixture",
        instrument=SimpleNamespace(id=42, symbol="DXJ", name="fixture DXJ"),
        provider_aliases={"sec_cik": "0000000001"},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik="0000000001",
        sec_series_id="S000000001",
        sec_class_id="C000000001",
    )
    monkeypatch.setattr(refresh, "get_holdings_adapter", lambda _key: adapter)

    async def ignore_rejected_artifact(*_args, **_kwargs):
        return None

    monkeypatch.setattr(refresh, "_retain_rejected_fetch_artifact", ignore_rejected_artifact)

    with pytest.raises(ValueError) as raised:
        await refresh._refresh_adapter_route(object(), profile)

    assert "503 Service Unavailable" in str(raised.value)
    assert "SEC filing fallback failed" in str(raised.value)
    assert "SEC request identity cannot be loaded from the caller database session" in str(
        raised.value
    )
    assert observed == ["https://publisher.example/DXJ.csv"]
    assert sec_client_attempts == []


@pytest.mark.asyncio
async def test_cohen_steers_refresh_uses_loop_local_mocktransport_for_each_request(monkeypatch):
    from datetime import UTC, datetime

    from app.services import etf_holdings_refresh as refresh
    from app.services.etf_holdings_adapters import get_holdings_adapter

    adapter = get_holdings_adapter("cohen_steers")
    assert adapter is not None
    sitemap_url = adapter.fund_sitemap_url
    page_url = "https://www.cohenandsteers.com/funds/csre/"
    fund_url = adapter.fund_url
    composition_date = datetime.now(UTC).date().isoformat()
    payload = {
        "meta": {
            "shareClasses": [{"characteristics": {"symbol": "CSRE"}}],
            "fullHoldings": [
                {
                    "holdingName": "Acadia Realty Trust",
                    "ticker": "AKR",
                    "securityType": "Common Stock",
                    "accountWeight": "4.152700",
                    "asOfDate": f"{composition_date}T00:00:00Z",
                }
            ],
        }
    }
    observed_requests = []
    reviewed_requests = []

    def transport(request):
        observed_requests.append(request)
        if str(request.url) == sitemap_url:
            return httpx.Response(
                200,
                text=f"<urlset><url><loc>{page_url}</loc></url></urlset>",
                request=request,
            )
        if str(request.url) == page_url:
            return httpx.Response(
                200,
                text='<section data-id="15098" data-fund-type="etf" data-default-symbol="CSRE">',
                request=request,
            )
        if request.url.path == "/wp-admin/admin-ajax.php":
            assert request.url.params["action"] == "load_fund"
            assert request.url.params["id"] == "15098"
            return httpx.Response(200, json=payload, request=request)
        raise AssertionError(f"Unexpected offline Cohen & Steers request: {request.url}")

    original_attempt_factory = bridge._make_loop_local_httpx_attempt
    monkeypatch.setattr(
        bridge,
        "_make_loop_local_httpx_attempt",
        lambda **kwargs: original_attempt_factory(
            **kwargs,
            transport_factory=lambda: httpx.MockTransport(transport),
        ),
    )

    async def reviewed_context(_db, **context):
        reviewed_requests.append(context)
        return None

    dispatches = []

    async def offline_provider_call(
        _db,
        _capability,
        operation,
        *,
        instrument_id,
        provider_symbol,
        invoke,
        etf_holdings_adapters,
        request_log_id_callback,
        **_kwargs,
    ):
        assert operation == "fetch_etf_holdings_latest"
        assert instrument_id == 42
        assert provider_symbol == "CSRE"
        assert etf_holdings_adapters["cohen_steers"] is adapter
        response = _run_in_finite_worker(
            invoke,
            etf_holdings_adapters["cohen_steers"],
            provider_symbol,
        )
        request_log_id = len(dispatches) + 1
        dispatches.append(response.status_code)
        request_log_id_callback(request_log_id)
        return SimpleNamespace(result=response, request_log_id=request_log_id)

    class OfflineAttemptSession:
        def __init__(self, *, bind, expire_on_commit):
            self.bind = bind
            self.expire_on_commit = expire_on_commit

        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(bridge, "_review_attempt_context", reviewed_context)
    monkeypatch.setattr(bridge, "execute_provider_call", offline_provider_call)
    monkeypatch.setattr(bridge, "AsyncSession", OfflineAttemptSession)
    monkeypatch.setattr(
        refresh, "_validate_artifact_identity", lambda *_a, **_kw: {"status": "matched"}
    )

    async def accept_schema_fingerprint(*_args, **_kwargs):
        return None

    monkeypatch.setattr(refresh, "_ensure_schema_fingerprint_is_stable", accept_schema_fingerprint)
    ingested = {}

    async def capture_ingestion(_db, **kwargs):
        ingested.update(kwargs)
        return SimpleNamespace(id=99, source_provider=kwargs["source_provider"])

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", capture_ingestion)
    profile = SimpleNamespace(
        id=12,
        adapter_key="cohen_steers",
        instrument=SimpleNamespace(id=42, symbol="CSRE", name="fixture CSRE"),
        provider_aliases={},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
    )

    result = await refresh._refresh_adapter_route(SimpleNamespace(bind=object()), profile)

    expected_urls = [sitemap_url, page_url, f"{fund_url}?action=load_fund&id=15098"]
    assert [str(request.url) for request in observed_requests] == expected_urls
    assert [item["request_url"] for item in reviewed_requests] == expected_urls
    assert dispatches == [200, 200, 200]
    assert ingested["legal_metadata"]["provider_request_log_ids"] == [1, 2, 3]
    assert ingested["legal_metadata"]["provider_request_attempts"] == [
        {"request_log_id": index, "request_url": url}
        for index, url in enumerate(expected_urls, start=1)
    ]
    assert ingested["rows"][0].symbol == "AKR"
    assert result.source_provider == "cohen_steers"
