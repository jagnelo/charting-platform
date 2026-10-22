from __future__ import annotations

import importlib
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance_fixtures import resolve_nautilus_rc_conformance
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.engine_execution import NautilusExecutionScope
from app.strategy_lab_v2.local_conformance_source import (
    LOCAL_NAUTILUS_RC_EVIDENCE_ENV,
    LocalNautilusRcConformanceEvidencePublisher,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.search_dispatch_preparation import (
    NautilusTrialPreparationContext,
    SearchDispatchPreparationRequest,
)
from app.strategy_lab_v2.search_preparation_composition import (
    SearchPreparationHostBindings,
    bind_context_to_rc_evidence,
    create_search_preparation_evidence_resolver,
)
from app.strategy_lab_v2.search_preparation_service import (
    create_search_preparation_app_from_environment,
)
from app.strategy_lab_v2.tests.test_conformance_fixtures import (
    _rc_evidence_artifact,
    _rc_probe,
    _rc_receipt,
    _rc_runtime,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import RUNTIME_ABI
from app.strategy_lab_v2.tests.test_search_dispatch_preparation import _setup


def _environment_bindings_factory(_persistence, _artifact_root, _resolution):
    def unavailable_context(_request, _graph):
        raise RuntimeError("test-only context resolver must not be invoked")

    return SearchPreparationHostBindings(
        runtime_abi=RUNTIME_ABI,
        series_decoder=JsonFrozenSeriesDecoder(),
        context_resolver=unavailable_context,
    )


def _resolution(tested_at=BASE):
    runtime = _rc_runtime()
    return resolve_nautilus_rc_conformance(
        runtime,
        _rc_probe(runtime),
        _rc_receipt(runtime),
        build_digest=content_digest("nautilus-v2-rc6-build"),
        tested_at=tested_at,
    )


def _request(attempt_id: str) -> SearchDispatchPreparationRequest:
    return SearchDispatchPreparationRequest(
        principal="owner-composition-test",
        request_id="search-preparation-composition-test",
        experiment_fingerprint=content_digest("experiment-composition-test"),
        candidate_index=0,
        attempt_id=attempt_id,
        dispatch_intent=SearchDispatchIntent(
            "search-preparation-composition-key",
            attempt_id,
            "strategy-backtest",
            BASE,
        ),
    )


def test_local_preparation_composition_uses_shared_persistence_and_pinned_rc(
    tmp_path: Path,
) -> None:
    _graph, _artifact_store, _package_resolver, _materializer, context, _worker_state = _setup(
        tmp_path / "trial"
    )
    runtime = _rc_runtime()
    payload = _rc_evidence_artifact(runtime)
    evidence_directory = tmp_path / "evidence"
    evidence_directory.mkdir()
    published = LocalNautilusRcConformanceEvidencePublisher(evidence_directory).publish(
        runtime=runtime,
        probe_payload=payload["probe"],
        fixture_payload=payload["receipt"],
        build_digest=content_digest("nautilus-v2-rc6-build"),
        tested_at=BASE,
    )
    persistence = PostgresStrategyLabV2Persistence.build(lambda: object())
    bindings = SearchPreparationHostBindings(
        runtime_abi=RUNTIME_ABI,
        series_decoder=JsonFrozenSeriesDecoder(),
        context_resolver=lambda _request, _graph: context,
    )

    resolver = create_search_preparation_evidence_resolver(
        persistence,
        tmp_path / "artifacts",
        host_bindings=bindings,
        conformance_resolution=published.resolution,
    )

    assert callable(resolver)
    assert (tmp_path / "artifacts").is_dir()


@pytest.mark.asyncio
async def test_context_binding_rejects_another_valid_rc_report(tmp_path: Path) -> None:
    graph, _store, _packages, _materializer, context, _worker_state = _setup(tmp_path / "trial")
    pinned = _resolution()
    drifted = _resolution(BASE + timedelta(seconds=1))
    mismatched_context = NautilusTrialPreparationContext.from_compatibility_backtest_conformance(
        conformance_resolution=drifted,
        product_classes=frozenset({context.market_context.instruments[0].product_class}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        market_context=context.market_context,
        runtime_profile=context.runtime_profile,
        admission_ledger=context.admission_ledger,
        image_name=context.image_name,
        output_path=context.output_path,
        now=context.now,
        lease_duration=context.lease_duration,
    )
    bound = bind_context_to_rc_evidence(
        lambda _request, _graph: mismatched_context,
        conformance_resolution=pinned,
        runtime_abi=RUNTIME_ABI,
    )

    with pytest.raises(ValueError, match="operator-pinned RC evidence"):
        await bound(_request(graph.attempt.attempt_id), graph)


@pytest.mark.asyncio
async def test_context_binding_accepts_async_exact_rc_context(tmp_path: Path) -> None:
    graph, _store, _packages, _materializer, context, _worker_state = _setup(tmp_path / "trial")
    pinned = _resolution()

    async def resolve(_request, _graph):
        return context

    bound = bind_context_to_rc_evidence(
        resolve,
        conformance_resolution=pinned,
        runtime_abi=RUNTIME_ABI,
    )

    assert await bound(_request(graph.attempt.attempt_id), graph) == context


@pytest.mark.asyncio
async def test_context_binding_accepts_exact_rc_authoritative_backtest_context(
    tmp_path: Path,
) -> None:
    graph, _store, _packages, _materializer, compatibility_context, _worker_state = _setup(
        tmp_path / "trial"
    )
    resolution = _resolution()
    authoritative_context = NautilusTrialPreparationContext.from_authoritative_backtest_conformance(
        conformance_resolution=resolution,
        product_classes=frozenset(
            {compatibility_context.market_context.instruments[0].product_class}
        ),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        market_context=compatibility_context.market_context,
        runtime_profile=compatibility_context.runtime_profile,
        admission_ledger=compatibility_context.admission_ledger,
        image_name=compatibility_context.image_name,
        output_path=compatibility_context.output_path,
        now=compatibility_context.now,
        lease_duration=compatibility_context.lease_duration,
    )
    bound = bind_context_to_rc_evidence(
        lambda _request, _graph: authoritative_context,
        conformance_resolution=resolution,
        runtime_abi=RUNTIME_ABI,
    )

    assert await bound(_request(graph.attempt.attempt_id), graph) == authoritative_context


@pytest.mark.asyncio
async def test_context_binding_rejects_non_compatibility_scope(
    tmp_path: Path,
) -> None:
    graph, _store, _packages, _materializer, context, _worker_state = _setup(tmp_path / "trial")
    incompatible_context = replace(
        context,
        execution_scope=NautilusExecutionScope.FORWARD_COMPATIBILITY,
        requested_authoritative=False,
    )
    bound = bind_context_to_rc_evidence(
        lambda _request, _graph: incompatible_context,
        conformance_resolution=_resolution(),
        runtime_abi=RUNTIME_ABI,
    )

    with pytest.raises(ValueError, match="RC search preparation is restricted to local backtest"):
        await bound(_request(graph.attempt.attempt_id), graph)


def test_host_bindings_reject_missing_provider_context_inputs() -> None:
    with pytest.raises(TypeError, match="series_decoder"):
        SearchPreparationHostBindings(
            runtime_abi=RUNTIME_ABI,
            series_decoder=cast(Any, object()),
            context_resolver=cast(Any, lambda _request, _graph: None),
        )


def test_preparation_service_builds_platform_owned_composition_from_local_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _rc_runtime()
    payload = _rc_evidence_artifact(runtime)
    evidence_directory = tmp_path / "evidence"
    evidence_directory.mkdir()
    published = LocalNautilusRcConformanceEvidencePublisher(evidence_directory).publish(
        runtime=runtime,
        probe_payload=payload["probe"],
        fixture_payload=payload["receipt"],
        build_digest=content_digest("nautilus-v2-rc6-build"),
        tested_at=BASE,
    )
    original_import_module = importlib.import_module

    def import_module(name: str):
        if name == "app.database":
            return SimpleNamespace(AsyncSessionLocal=lambda: object())
        return original_import_module(name)

    monkeypatch.setattr(importlib, "import_module", import_module)
    environment = {
        "STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN": "composition-test-token-0123456789abcdef",
        "STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH": str(tmp_path / "preparation.sock"),
        "STRATEGY_LAB_V2_PREPARATION_BINDINGS_FACTORY": (
            f"{__name__}:_environment_bindings_factory"
        ),
        "STRATEGY_LAB_V2_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["artifact_directory"]: str(evidence_directory),
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["artifact_digest"]: published.artifact_digest,
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["source_digest"]: runtime.source_digest,
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["runtime_image_digest"]: runtime.runtime_image_digest,
    }

    app, socket_path = create_search_preparation_app_from_environment(environment)

    assert socket_path == tmp_path / "preparation.sock"
    assert (tmp_path / "artifacts").is_dir()
    assert app.state.dispatch_lock is not None
