from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.experiments import WalkForwardMode, WalkForwardSpec
from app.strategy_lab_v2.postgres_walk_forward_plan import (
    PostgresWalkForwardPlanAdapter,
    WalkForwardDefinitionDecision,
)
from app.strategy_lab_v2.storage import (
    AggregateKey,
    StorageTransactionDecision,
    StorageTransactionReceipt,
    StorageTransactionRequest,
    StoredAggregate,
    resolve_storage_transaction,
)
from app.strategy_lab_v2.walk_forward_search import (
    SelectionDirection,
    WalkForwardExecutionDefinition,
)


class MemoryAggregateStore:
    def __init__(self) -> None:
        self.aggregates: dict[AggregateKey, StoredAggregate] = {}
        self.receipts: dict[str, StorageTransactionReceipt] = {}

    async def get(self, key: AggregateKey) -> StoredAggregate | None:
        return self.aggregates.get(key)

    async def apply(self, request: StorageTransactionRequest):
        current = tuple(
            self.aggregates[mutation.key]
            for mutation in request.mutations
            if mutation.key in self.aggregates
        )
        receipt = self.receipts.get(request.request_id)
        resolution = resolve_storage_transaction(
            current,
            request,
            (receipt,) if receipt is not None else (),
        )
        if resolution.decision is StorageTransactionDecision.APPLY:
            self.aggregates.update({item.key: item for item in resolution.aggregates})
            assert resolution.receipt is not None
            self.receipts[request.request_id] = resolution.receipt
        return resolution


def _definition(*, direction: SelectionDirection = SelectionDirection.MAXIMIZE):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return WalkForwardExecutionDefinition(
        experiment_fingerprint=content_digest("experiment"),
        candidate_fingerprints=(content_digest("candidate-a"), content_digest("candidate-b")),
        observation_boundaries=tuple(start + timedelta(days=index) for index in range(20)),
        spec=WalkForwardSpec(
            train_periods=6,
            test_periods=3,
            step_periods=3,
            mode=WalkForwardMode.ROLLING,
            gap_periods=1,
            embargo_periods=1,
        ),
        metric_id="net_return",
        direction=direction,
    )


@pytest.mark.asyncio
async def test_walk_forward_definition_round_trips_and_reconstructs_exact_tasks() -> None:
    store = MemoryAggregateStore()
    adapter = PostgresWalkForwardPlanAdapter(store)
    definition = _definition()

    persisted = await adapter.persist(principal="owner-a", definition=definition)
    restored = await adapter.load(
        principal="owner-a",
        experiment_fingerprint=definition.experiment_fingerprint,
    )

    assert persisted.decision is WalkForwardDefinitionDecision.APPLY
    assert restored == definition
    assert restored is not None
    assert restored.fingerprint == definition.fingerprint
    assert restored.folds == definition.folds
    assert restored.training_plan == definition.training_plan
    assert (
        await adapter.load(
            principal="owner-b",
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        is None
    )


@pytest.mark.asyncio
async def test_walk_forward_definition_is_immutable_per_owner_experiment_and_replayable() -> None:
    adapter = PostgresWalkForwardPlanAdapter(MemoryAggregateStore())
    definition = _definition()

    created = await adapter.persist(principal="owner-a", definition=definition)
    replay = await adapter.persist(principal="owner-a", definition=definition)
    conflict = await adapter.persist(
        principal="owner-a",
        definition=_definition(direction=SelectionDirection.MINIMIZE),
    )

    assert created.decision is WalkForwardDefinitionDecision.APPLY
    assert replay.decision is WalkForwardDefinitionDecision.REPLAY_EXISTING
    assert conflict.decision is WalkForwardDefinitionDecision.REJECT
    assert "different walk-forward definition" in (conflict.rejection_reason or "")
