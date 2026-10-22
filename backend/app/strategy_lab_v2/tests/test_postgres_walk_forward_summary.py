from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    MetricBasis,
    MetricValue,
)
from app.strategy_lab_v2.postgres_walk_forward_summary import (
    PostgresWalkForwardNativeMetricsAdapter,
    PostgresWalkForwardSummaryAdapter,
    WalkForwardSummaryDecision,
)
from app.strategy_lab_v2.tests.test_walk_forward_plan_persistence import MemoryAggregateStore
from app.strategy_lab_v2.tests.test_walk_forward_summary import _summary_fixture
from app.strategy_lab_v2.walk_forward_summary import (
    WALK_FORWARD_NATIVE_EQUITY_CURVE_MEDIA_TYPE,
    WALK_FORWARD_NATIVE_EQUITY_CURVE_SCHEMA,
    WalkForwardNativeOosMetricSummary,
)


@pytest.mark.asyncio
async def test_walk_forward_summary_round_trips_owner_scoped_and_replays_immutably() -> None:
    adapter = PostgresWalkForwardSummaryAdapter(MemoryAggregateStore())
    summary = _summary_fixture()

    persisted = await adapter.persist(principal="owner-a", summary=summary)
    replay = await adapter.persist(principal="owner-a", summary=summary)
    restored = await adapter.load(
        principal="owner-a",
        experiment_fingerprint=summary.experiment_fingerprint,
    )
    other_owner = await adapter.load(
        principal="owner-b",
        experiment_fingerprint=summary.experiment_fingerprint,
    )

    assert persisted.decision is WalkForwardSummaryDecision.PERSISTED
    assert replay.decision is WalkForwardSummaryDecision.REPLAY_EXISTING
    assert restored == summary
    assert other_owner is None


@pytest.mark.asyncio
async def test_walk_forward_summary_rejects_rebinding_same_experiment() -> None:
    adapter = PostgresWalkForwardSummaryAdapter(MemoryAggregateStore())
    summary = _summary_fixture()
    await adapter.persist(principal="owner-a", summary=summary)

    conflicting = await adapter.persist(
        principal="owner-a",
        summary=replace(summary, definition_fingerprint=content_digest("different-plan")),
    )

    assert conflicting.decision is WalkForwardSummaryDecision.REJECT
    assert "different OOS result summary" in (conflicting.rejection_reason or "")


@pytest.mark.asyncio
async def test_native_walk_forward_metrics_round_trip_and_reject_owner_rebinding() -> None:
    adapter = PostgresWalkForwardNativeMetricsAdapter(MemoryAggregateStore())
    fold_summary = _summary_fixture()
    native_summary = WalkForwardNativeOosMetricSummary(
        experiment_fingerprint=fold_summary.experiment_fingerprint,
        definition_fingerprint=fold_summary.definition_fingerprint,
        selection_fingerprint=fold_summary.selection.fingerprint,
        result_manifest_fingerprints=tuple(
            result.result_fingerprint for result in fold_summary.results
        ),
        metrics=(
            MetricValue(
                "total_return",
                Decimal("-0.01"),
                "fraction",
                "strategy-lab.metrics.v2",
                MetricBasis.NET,
                2,
            ),
        ),
        curve_artifact=ArtifactManifest(
            content_digest("native-oos-curve"),
            256,
            WALK_FORWARD_NATIVE_EQUITY_CURVE_MEDIA_TYPE,
            WALK_FORWARD_NATIVE_EQUITY_CURVE_SCHEMA,
            content_digest("native-oos-curve"),
            ArtifactRetention.PINNED_RESULT,
        ),
    )

    persisted = await adapter.persist(principal="owner-a", summary=native_summary)
    replay = await adapter.persist(principal="owner-a", summary=native_summary)
    restored = await adapter.load(
        principal="owner-a",
        experiment_fingerprint=native_summary.experiment_fingerprint,
    )
    other_owner = await adapter.load(
        principal="owner-b",
        experiment_fingerprint=native_summary.experiment_fingerprint,
    )

    assert persisted.decision is WalkForwardSummaryDecision.PERSISTED
    assert replay.decision is WalkForwardSummaryDecision.REPLAY_EXISTING
    assert restored == native_summary
    assert other_owner is None
