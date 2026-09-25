from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.strategy_lab_v2.search_worker_handoff import AuthenticatedSearchDispatchMaterializer
from app.strategy_lab_v2.worker_callbacks import (
    create,
    create_search_dispatch,
    default_evidence_resolver_factory,
)
from app.strategy_lab_v2.worker_handoff import materialize_worker_handoff


def resolver_factory(persistence: Any, artifact_root: Path):
    assert persistence is not None
    assert artifact_root == Path("/tmp/artifacts")

    async def resolve(_context: Any) -> Any:
        return None

    return resolve


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
        self.plan_resolver: Any = None

    def artifact_publication(self, root: Path) -> object:
        self.root = root
        return _Publisher()

    def worker_terminal_evidence_resolver(self, resolver: Any) -> Any:
        self.plan_resolver = resolver
        return resolver


class _SearchDispatchPersistence(_Persistence):
    class _Store:
        async def load_by_request_fingerprint(self, _request_fingerprint: str) -> None:
            return None

    search_dispatch = _Store()


class _Publisher:
    async def publish_sandbox_result(self, *_args: Any, **_kwargs: Any) -> Any:
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
        "app.strategy_lab_v2.tests.test_worker_callbacks:resolver_factory",
    )
    monkeypatch.setenv("STRATEGY_LAB_V2_QUEUE", "strategy-backtest")
    callbacks = await create_search_dispatch(
        _SearchDispatchPersistence(), Path("/tmp/artifacts")
    )

    assert isinstance(callbacks.materializer, AuthenticatedSearchDispatchMaterializer)
    assert callbacks.materializer.queue_name == "strategy-backtest"


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
    assert callable(persistence.plan_resolver)
