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

    search_dispatch = _Store()

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
    callbacks = await create_search_dispatch(_SearchDispatchPersistence(), Path("/tmp/artifacts"))

    assert isinstance(callbacks.materializer, AuthenticatedSearchDispatchMaterializer)
    assert callbacks.materializer.queue_name == "strategy-backtest"
    assert callbacks.materializer.domain_hydrator is not None


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
