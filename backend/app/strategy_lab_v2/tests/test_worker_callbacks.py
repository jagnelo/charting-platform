from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.search_worker_handoff import AuthenticatedSearchDispatchMaterializer
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_worker_evidence_resolution import _context_and_lookup
from app.strategy_lab_v2.worker_callbacks import (
    create,
    create_default_search_dispatch_binding_resolver,
    create_search_dispatch,
    default_evidence_resolver_factory,
)
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.worker_evidence import WorkerSubmissionBinding
from app.strategy_lab_v2.worker_handoff import materialize_worker_handoff

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def resolver_factory(persistence: Any, artifact_root: Path):
    assert persistence is not None
    assert artifact_root == Path("/tmp/artifacts")

    async def resolve(_context: Any) -> Any:
        return None

    return resolve


def search_resolver_factory(
    persistence: Any,
    artifact_root: Path,
    *,
    search_dispatch_binding_resolver: Any,
):
    assert persistence is not None
    assert artifact_root == Path("/tmp/artifacts")
    assert callable(search_dispatch_binding_resolver)
    return resolver_factory(persistence, artifact_root)


class _Persistence:
    def __init__(self) -> None:
        self.resolver: Any = None

    def worker_terminal_writer(self, resolver: Any) -> Any:
        self.resolver = resolver

        async def terminal(_context: Any) -> Any:
            return None

        return terminal


class _ComposedPersistence:
    def __init__(self) -> None:
        self.root: Path | None = None
        self.lookup_arguments: dict[str, Any] | None = None

    class _Resources:
        async def get_domain_contract(self, **_kwargs: Any) -> None:
            return None

        async def get_domain_contract_by_fingerprint(self, **_kwargs: Any) -> None:
            return None

        async def get_domain_contracts_by_fingerprint(self, **_kwargs: Any) -> dict[str, Any]:
            return {}

    resources = _Resources()

    def artifact_publication(self, root: Path) -> object:
        self.root = root
        return _Publisher()

    async def load_worker_terminal_evidence_for_request(self, **kwargs: Any) -> None:
        self.lookup_arguments = kwargs
        return None


class _SearchDispatchPersistence(_Persistence):
    class _Store:
        async def load_by_request_fingerprint(self, _request_fingerprint: str) -> None:
            return None

        async def load_admission_ledger(self, **_kwargs: Any) -> None:
            return None

    search_dispatch = _Store()

    class _SearchState:
        async def load(self, **_kwargs: Any) -> None:
            return None

        async def record_terminal(self, **_kwargs: Any) -> None:
            return None

    search_state = _SearchState()

    class _Recoveries:
        async def load_ledger(self, **_kwargs: Any) -> None:
            return None

        async def recover(self, **_kwargs: Any) -> None:
            return None

    worker_recoveries = _Recoveries()

    class _ResultCompletion:
        async def load_completion_ledger(self, **_kwargs: Any) -> None:
            return None

    result_completion = _ResultCompletion()

    class _WorkerSettlements:
        async def load_ledger(self, **_kwargs: Any) -> None:
            return None

    worker_settlements = _WorkerSettlements()

    class _WorkerState:
        async def load_pool(self, _profile: Any) -> None:
            return None

        async def load_lease(self, _lease_id: str) -> None:
            return None

    worker_state = _WorkerState()

    async def persist_retry_attempt(self, **_kwargs: Any) -> None:
        return None

    class submissions:
        @staticmethod
        async def load_submission(**_kwargs: Any) -> None:
            return None

    class resources:
        @staticmethod
        async def get_domain_contract(**_kwargs: Any) -> None:
            return None

        @staticmethod
        async def get_domain_contract_by_fingerprint(**_kwargs: Any) -> None:
            return None

        @staticmethod
        async def get_domain_contracts_by_fingerprint(**_kwargs: Any) -> dict[str, Any]:
            return {}

        @staticmethod
        async def get_run_attempt_by_attempt_id(**_kwargs: Any) -> None:
            return None

        @staticmethod
        async def get_run_attempts_for_trial(**_kwargs: Any) -> tuple[Any, ...]:
            return ()


class _Publisher:
    async def publish_sandbox_result(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("test publisher should not be invoked during composition")

    async def publish_file(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("test publisher should not be invoked during composition")


@pytest.mark.asyncio
async def test_callback_factory_requires_application_evidence_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRATEGY_LAB_V2_EVIDENCE_RESOLVER", raising=False)
    with pytest.raises(ValueError, match="EVIDENCE_RESOLVER"):
        await create(_Persistence(), Path("/tmp/artifacts"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec",
    (
        "not-a-module-spec",
        "app.strategy_lab_v2.tests.test_worker_callbacks:no_such_factory",
    ),
)
async def test_callback_factory_rejects_malformed_or_missing_resolver_target(
    monkeypatch: pytest.MonkeyPatch,
    spec: str,
) -> None:
    monkeypatch.setenv("STRATEGY_LAB_V2_EVIDENCE_RESOLVER", spec)
    with pytest.raises((ValueError, TypeError, AttributeError)):
        await create(_Persistence(), Path("/tmp/artifacts"))


@pytest.mark.asyncio
async def test_callback_factory_composes_typed_materializer_and_terminal_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_EVIDENCE_RESOLVER",
        "app.strategy_lab_v2.tests.test_worker_callbacks:resolver_factory",
    )
    persistence = _Persistence()
    callbacks = await create(persistence, Path("/tmp/artifacts"))

    assert callbacks.materializer is materialize_worker_handoff
    assert callbacks.terminal_writer is not None
    assert persistence.resolver is not None


@pytest.mark.asyncio
async def test_search_callback_factory_binds_authenticated_dispatch_materializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_EVIDENCE_RESOLVER",
        "app.strategy_lab_v2.tests.test_worker_callbacks:search_resolver_factory",
    )
    monkeypatch.setenv("STRATEGY_LAB_V2_QUEUE", "strategy-backtest")
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH",
        "/tmp/strategy-lab-v2-preparation.sock",
    )
    monkeypatch.setenv("STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN", "x" * 48)
    callbacks = await create_search_dispatch(_SearchDispatchPersistence(), Path("/tmp/artifacts"))

    assert isinstance(callbacks.materializer, AuthenticatedSearchDispatchMaterializer)
    assert callbacks.materializer.queue_name == "strategy-backtest"
    assert callbacks.materializer.domain_hydrator is not None
    assert callbacks.recovery_writer is not None
    assert callbacks.lease_state_reader is not None


@pytest.mark.asyncio
async def test_terminal_search_success_notifies_walk_forward_coordinator_after_durable_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.strategy_lab_v2.worker_callbacks as callbacks_module

    monkeypatch.setenv(
        "STRATEGY_LAB_V2_EVIDENCE_RESOLVER",
        "app.strategy_lab_v2.tests.test_worker_callbacks:search_resolver_factory",
    )
    monkeypatch.setenv("STRATEGY_LAB_V2_QUEUE", "strategy-backtest")
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH",
        "/tmp/strategy-lab-v2-preparation.sock",
    )
    monkeypatch.setenv("STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN", "x" * 48)
    attempt_id = "worker-terminal-attempt"
    request_fingerprint = content_digest("worker-terminal-dispatch")
    entry_fingerprint = content_digest("worker-terminal-entry")
    dispatch = SearchDispatchRecord(
        "owner-42",
        content_digest("walk-forward-experiment"),
        0,
        DispatchRequest(
            "worker-terminal-key",
            attempt_id,
            content_digest("worker-terminal-payload"),
            "strategy-backtest",
            NOW,
        ),
    )
    events: list[str] = []

    class Store(_SearchDispatchPersistence._Store):
        async def load_by_request_fingerprint(self, fingerprint: str):
            events.append("load_dispatch")
            assert fingerprint == request_fingerprint
            return dispatch

    class Persistence(_SearchDispatchPersistence):
        search_dispatch = Store()

        def worker_terminal_writer(self, _resolver: Any):
            async def terminal(_context: Any) -> WorkerHandleResult:
                events.append("terminal_persisted")
                return WorkerHandleResult(
                    entry_fingerprint,
                    WorkerHandleDecision.COMPLETE,
                    content_digest("terminal-receipt"),
                )

            return terminal

    class Recovery:
        async def __call__(self, _context: Any):
            return None

        async def complete_terminal_if_persisted(self, **_kwargs: Any):
            events.append("search_receipt_persisted")
            return WorkerHandleResult(
                entry_fingerprint,
                WorkerHandleDecision.COMPLETE,
                content_digest("search-receipt"),
            )

    monkeypatch.setattr(
        callbacks_module,
        "create_worker_recovery_application",
        lambda *_args, **_kwargs: Recovery(),
    )

    async def progress(**kwargs: Any):
        events.append("progress_notified")
        assert kwargs["principal"] == "owner-42"
        assert kwargs["experiment_fingerprint"] == dispatch.experiment_fingerprint
        assert kwargs["attempt_id"] == attempt_id
        assert kwargs["dispatch_request_fingerprint"] == dispatch.request.fingerprint
        return callbacks_module.WalkForwardProgressRpcReceipt("waiting")

    callbacks = await create_search_dispatch(
        Persistence(),
        Path("/tmp/artifacts"),
        walk_forward_progress_client=progress,
    )
    context = type(
        "Context",
        (),
        {
            "entry": type(
                "Entry",
                (),
                {
                    "fingerprint": entry_fingerprint,
                    "request_fingerprint": request_fingerprint,
                    "attempt_id": attempt_id,
                },
            )(),
            "request": type(
                "Request",
                (),
                {"runtime_request": type("RuntimeRequest", (), {"attempt_id": attempt_id})()},
            )(),
            "observed_at": NOW,
        },
    )()

    result = await callbacks.terminal_writer(context)  # type: ignore[misc]

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert events == [
        "terminal_persisted",
        "search_receipt_persisted",
        "load_dispatch",
        "progress_notified",
    ]


@pytest.mark.asyncio
async def test_search_callback_factory_requires_queue_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_EVIDENCE_RESOLVER",
        "app.strategy_lab_v2.tests.test_worker_callbacks:resolver_factory",
    )
    monkeypatch.delenv("STRATEGY_LAB_V2_QUEUE", raising=False)
    with pytest.raises(ValueError, match="QUEUE"):
        await create_search_dispatch(_SearchDispatchPersistence(), Path("/tmp/artifacts"))


def test_default_evidence_resolver_factory_composes_persistence_and_artifacts() -> None:
    persistence = _ComposedPersistence()
    resolver = default_evidence_resolver_factory(persistence, Path("/tmp/artifacts"))

    assert callable(resolver)
    assert persistence.root == Path("/tmp/artifacts")


@pytest.mark.asyncio
async def test_default_evidence_resolver_factory_propagates_search_binding(
    tmp_path: Path,
) -> None:
    persistence = _ComposedPersistence()

    async def binding(_dispatch: SearchDispatchRecord) -> None:
        return None

    resolver = default_evidence_resolver_factory(
        persistence,
        Path("/tmp/artifacts"),
        search_dispatch_binding_resolver=binding,
    )

    assert callable(resolver)
    context, _lookup = _context_and_lookup(tmp_path)
    with pytest.raises(LookupError, match="not found"):
        await resolver(context)
    assert persistence.lookup_arguments is not None
    assert persistence.lookup_arguments["search_dispatch_binding_resolver"] is binding


@pytest.mark.asyncio
async def test_default_search_binding_resolver_loads_authoritative_submission() -> None:
    request = SubmissionRequest(
        "search-key",
        "search",
        "attempt-1",
        content_digest("search-payload"),
        NOW,
    )
    receipt = SubmissionReceipt(request, NOW)
    calls: list[tuple[Any, str]] = []

    class Persistence:
        class submissions:
            @staticmethod
            async def load_submission(*, principal: Any, attempt_id: str) -> SubmissionReceipt:
                calls.append((principal, attempt_id))
                return receipt

    resolver = create_default_search_dispatch_binding_resolver(Persistence())
    dispatch = SearchDispatchRecord(
        "owner-a",
        content_digest("search-experiment"),
        0,
        DispatchRequest(
            "dispatch-key",
            "attempt-1",
            content_digest("search-payload"),
            "strategy-backtest",
            NOW,
        ),
    )
    binding = await cast(
        Callable[[SearchDispatchRecord], Awaitable[WorkerSubmissionBinding | None]], resolver
    )(dispatch)

    assert binding is not None
    assert binding.owner_id == "owner-a"
    assert binding.receipt == receipt
    assert calls == [("owner-a", "attempt-1")]
