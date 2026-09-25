from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.strategy_lab_v2.worker_callbacks import create
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


@pytest.mark.asyncio
async def test_callback_factory_requires_application_evidence_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRATEGY_LAB_V2_EVIDENCE_RESOLVER", raising=False)
    with pytest.raises(ValueError, match="EVIDENCE_RESOLVER"):
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
