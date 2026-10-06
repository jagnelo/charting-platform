from __future__ import annotations

from dataclasses import replace

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_walk_forward_summary import (
    PostgresWalkForwardSummaryAdapter,
    WalkForwardSummaryDecision,
)
from app.strategy_lab_v2.tests.test_walk_forward_plan_persistence import MemoryAggregateStore
from app.strategy_lab_v2.tests.test_walk_forward_summary import _summary_fixture


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
