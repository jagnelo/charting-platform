from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import uvicorn

import app.strategy_lab_v2.search_dispatch_rpc as rpc_module
from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.api_router import ApiAdapterError
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.search_dispatch import SearchDispatchResolution, resolve_search_dispatch
from app.strategy_lab_v2.search_preparation_service import create_search_preparation_app
from app.strategy_lab_v2.search_state import new_search_execution_state
from app.strategy_lab_v2.tests.test_admission import _fixture, _reservation

NOW = datetime(2024, 1, 1, tzinfo=UTC)
AUTH_TOKEN = "local-preparation-test-token-0123456789abcdef"


def _resolution(command: dict[str, Any]) -> SearchDispatchResolution:
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    dispatch_intent = command["dispatch_intent"]
    return resolve_search_dispatch(
        new_search_execution_state(
            command["experiment_fingerprint"],
            (content_digest("trial-one"),),
            now=NOW,
        ),
        candidate_index=command["candidate_index"],
        attempt_id=command["attempt_id"],
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("rpc"),
        dispatch_request=dispatch_intent.bind_payload(content_digest("worker-payload")),
        prior_dispatches=(),
        now=NOW + timedelta(seconds=4),
    )


def _command_kwargs() -> dict[str, Any]:
    return {
        "principal": type("Principal", (), {"id": 42})(),
        "request_id": "request-rpc-1",
        "experiment_fingerprint": content_digest("experiment-rpc"),
        "candidate_index": 0,
        "attempt_id": "attempt-1",
        "dispatch_intent": SearchDispatchIntent(
            "dispatch-rpc-1",
            "attempt-1",
            "strategy-backtest",
            NOW,
        ),
    }


@pytest.mark.parametrize(
    "mutation",
    [
        {"unknown": True},
        {"candidate_index": 1},
        {"principal_id": "other-owner"},
    ],
)
def test_search_dispatch_rpc_command_rejects_fingerprint_drift(mutation: dict[str, Any]) -> None:
    command = rpc_module.SearchDispatchRpcCommand.from_call(**_command_kwargs())
    wire = command.to_wire()
    wire.update(mutation)

    with pytest.raises(ValueError):
        rpc_module.SearchDispatchRpcCommand.from_wire(wire)


def test_local_api_bindings_factory_requires_and_uses_complete_socket_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH", "/run/strategy/preparation.sock")
    monkeypatch.setenv("STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN", AUTH_TOKEN)
    forward_profile_digest = content_digest("forward-runtime")
    monkeypatch.setenv("STRATEGY_LAB_V2_FORWARD_WORKER_ID", "forward-worker-1")
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_FORWARD_RUNTIME_PROFILE_FINGERPRINT", forward_profile_digest
    )

    from app.strategy_lab_v2.application import StrategyLabV2ApiBindings

    bindings = rpc_module.build_api_bindings(None, None)

    assert isinstance(bindings, StrategyLabV2ApiBindings)
    assert isinstance(bindings.search_dispatch, rpc_module.UnixSocketSearchDispatchClient)
    assert bindings.search_dispatch.socket_path == Path("/run/strategy/preparation.sock")
    assert bindings.forward_worker_runtime_profile_fingerprint == forward_profile_digest

    monkeypatch.delenv("STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN")
    with pytest.raises(ValueError, match="must both be configured"):
        rpc_module.build_api_bindings(None, None)


@pytest.mark.asyncio
async def test_unix_search_dispatch_client_round_trips_typed_atomic_resolution(
    tmp_path: Path,
) -> None:
    command = rpc_module.SearchDispatchRpcCommand.from_call(**_command_kwargs())
    observed: dict[str, Any] = {}
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))

    async def dispatch_search_candidate(**kwargs: Any) -> SearchDispatchResolution:
        observed.update(kwargs)
        return _resolution(kwargs)

    adapter.dispatch_search_candidate = dispatch_search_candidate
    socket_path = tmp_path / "preparation.sock"
    app = create_search_preparation_app(
        adapter,
        auth_token=AUTH_TOKEN,
        socket_path=socket_path,
    )
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="critical",
            access_log=False,
            proxy_headers=False,
            ws="none",
        )
    )
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(500):
            if server.started:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("Unix-socket preparation service did not start")
        client = rpc_module.UnixSocketSearchDispatchClient(
            socket_path,
            AUTH_TOKEN,
        )

        resolution = await client(**_command_kwargs())
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)
        listener.close()

    assert resolution.decision.value == "enqueue"
    assert resolution.search_state.experiment_fingerprint == command.experiment_fingerprint
    assert observed["principal"] == "42"
    assert observed["request_id"] == "request-rpc-1"
    assert observed["dispatch_intent"] == command.dispatch_intent
    assert socket_path.stat().st_mode & 0o777 == 0o660


@pytest.mark.asyncio
async def test_unix_search_dispatch_client_preserves_typed_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))

    async def dispatch_search_candidate(**kwargs: Any) -> SearchDispatchResolution:
        raise ApiAdapterError(
            ApiError(
                ApiErrorCode.CONFLICT,
                "dispatch key belongs to different content",
                kwargs["request_id"],
                409,
                False,
                {"attempt_id": kwargs["attempt_id"]},
            )
        )

    adapter.dispatch_search_candidate = dispatch_search_candidate
    app = create_search_preparation_app(adapter, auth_token=AUTH_TOKEN)
    monkeypatch.setattr(
        rpc_module.httpx,
        "AsyncHTTPTransport",
        lambda **_kwargs: httpx.ASGITransport(app=app),
    )
    client = rpc_module.UnixSocketSearchDispatchClient(
        Path("/tmp/strategy-lab-preparation-test.sock"),
        AUTH_TOKEN,
    )

    with pytest.raises(ApiAdapterError) as raised:
        await client(**_command_kwargs())

    assert raised.value.error.code is ApiErrorCode.CONFLICT
    assert raised.value.error.status_code == 409
    assert raised.value.error.details["attempt_id"] == "attempt-1"


@pytest.mark.asyncio
async def test_preparation_service_rejects_requests_without_the_shared_local_token() -> None:
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    app = create_search_preparation_app(adapter, auth_token=AUTH_TOKEN)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://local.test") as client:
        response = await client.post(
            rpc_module.SEARCH_DISPATCH_RPC_PATH,
            json={},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == ApiErrorCode.AUTHORIZATION_REQUIRED.value
