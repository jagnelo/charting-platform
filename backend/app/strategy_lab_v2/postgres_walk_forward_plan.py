"""Owner-scoped persistence for restart-stable walk-forward definitions.

The plan is stored as an immutable aggregate beside existing Strategy Lab
resources, so this adapter reuses PostgreSQL aggregate CAS storage and does not
introduce a second schema or an untracked in-process workflow definition.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.postgres_result_materialization import decode_canonical_contract
from app.strategy_lab_v2.storage import (
    AggregateKey,
    AggregateMutation,
    StorageTransactionDecision,
    StorageTransactionRequest,
    StoredAggregate,
)
from app.strategy_lab_v2.walk_forward_search import WalkForwardExecutionDefinition


class AggregateStore(Protocol):
    async def get(self, key: AggregateKey) -> StoredAggregate | None: ...

    async def apply(self, request: StorageTransactionRequest) -> Any: ...


class WalkForwardDefinitionDecision(StrEnum):
    APPLY = "apply"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WalkForwardDefinitionResolution:
    decision: WalkForwardDefinitionDecision
    definition: WalkForwardExecutionDefinition
    aggregate_version: int | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WalkForwardDefinitionDecision):
            raise TypeError("decision must be a WalkForwardDefinitionDecision")
        if not isinstance(self.definition, WalkForwardExecutionDefinition):
            raise TypeError("definition must be a WalkForwardExecutionDefinition")
        if self.aggregate_version is not None and (
            not isinstance(self.aggregate_version, int)
            or isinstance(self.aggregate_version, bool)
            or self.aggregate_version < 1
        ):
            raise ValueError("aggregate_version must be a positive integer")
        if (self.decision is WalkForwardDefinitionDecision.REJECT) != bool(self.rejection_reason):
            raise ValueError("only rejected resolutions contain a rejection reason")


class PostgresWalkForwardPlanAdapter:
    """Persist one immutable workflow definition per owner and experiment."""

    _AGGREGATE_TYPE = "strategy_lab_v2_walk_forward_plans"
    _SCHEMA_VERSION = 1

    def __init__(self, aggregate_store: AggregateStore) -> None:
        if not callable(getattr(aggregate_store, "get", None)) or not callable(
            getattr(aggregate_store, "apply", None)
        ):
            raise TypeError("aggregate_store must expose get() and apply()")
        self._aggregate_store = aggregate_store

    async def persist(
        self,
        *,
        principal: Any,
        definition: WalkForwardExecutionDefinition,
    ) -> WalkForwardDefinitionResolution:
        if not isinstance(definition, WalkForwardExecutionDefinition):
            raise TypeError("definition must be a WalkForwardExecutionDefinition")
        owner_id = _principal_id(principal)
        key = _aggregate_key(owner_id, definition.experiment_fingerprint)
        state = _state(owner_id, definition)
        current = await self._aggregate_store.get(key)
        if current is not None:
            return _existing_resolution(current, owner_id, definition)

        request_id = content_digest(
            {
                "owner_id": owner_id,
                "experiment_fingerprint": definition.experiment_fingerprint,
                "definition_fingerprint": definition.fingerprint,
                "purpose": "strategy-lab-v2-walk-forward-definition",
            }
        )
        outcome = await self._aggregate_store.apply(
            StorageTransactionRequest(
                request_id,
                (AggregateMutation(key, state),),
            )
        )
        if outcome.decision in {
            StorageTransactionDecision.APPLY,
            StorageTransactionDecision.REPLAY_EXISTING,
        }:
            aggregate = next(
                (item for item in outcome.aggregates if item.key == key),
                None,
            )
            if aggregate is not None and aggregate.state == state:
                decision = (
                    WalkForwardDefinitionDecision.APPLY
                    if outcome.decision is StorageTransactionDecision.APPLY
                    else WalkForwardDefinitionDecision.REPLAY_EXISTING
                )
                return WalkForwardDefinitionResolution(decision, definition, aggregate.version)

        # A concurrent create can win after the initial read. Re-read by the
        # owner-derived key and accept only exact immutable content.
        winner = await self._aggregate_store.get(key)
        if winner is not None:
            replay = _existing_resolution(winner, owner_id, definition)
            if replay.decision is WalkForwardDefinitionDecision.REPLAY_EXISTING:
                return replay
        reason = getattr(outcome, "rejection_reason", None) or (
            "walk-forward definition create was not durably accepted"
        )
        return WalkForwardDefinitionResolution(
            WalkForwardDefinitionDecision.REJECT,
            definition,
            rejection_reason=reason,
        )

    async def load(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
    ) -> WalkForwardExecutionDefinition | None:
        owner_id = _principal_id(principal)
        if not isinstance(experiment_fingerprint, str) or not experiment_fingerprint.strip():
            raise ValueError("experiment_fingerprint must not be empty")
        key = _aggregate_key(owner_id, experiment_fingerprint)
        aggregate = await self._aggregate_store.get(key)
        if aggregate is None:
            return None
        state = aggregate.state
        if not isinstance(state, Mapping):
            raise ValueError("persisted walk-forward definition state is malformed")
        if (
            state.get("owner_id") != owner_id
            or state.get("schema_version") != self._SCHEMA_VERSION
            or state.get("experiment_fingerprint") != experiment_fingerprint
        ):
            raise ValueError("persisted walk-forward definition owner or identity drifted")
        payload = state.get("definition_json")
        definition_fingerprint = state.get("definition_fingerprint")
        if not isinstance(payload, str) or not isinstance(definition_fingerprint, str):
            raise ValueError("persisted walk-forward definition payload is missing")
        definition = decode_canonical_contract(payload, WalkForwardExecutionDefinition)
        if (
            definition.experiment_fingerprint != experiment_fingerprint
            or definition.fingerprint != definition_fingerprint
            or canonical_json(definition) != payload
        ):
            raise ValueError("persisted walk-forward definition content identity drifted")
        return definition


def _existing_resolution(
    aggregate: StoredAggregate,
    owner_id: str,
    definition: WalkForwardExecutionDefinition,
) -> WalkForwardDefinitionResolution:
    state = aggregate.state
    if not isinstance(state, Mapping) or state.get("owner_id") != owner_id:
        return WalkForwardDefinitionResolution(
            WalkForwardDefinitionDecision.REJECT,
            definition,
            rejection_reason="persisted walk-forward definition is outside the owner scope",
        )
    if state == _state(owner_id, definition):
        return WalkForwardDefinitionResolution(
            WalkForwardDefinitionDecision.REPLAY_EXISTING,
            definition,
            aggregate.version,
        )
    return WalkForwardDefinitionResolution(
        WalkForwardDefinitionDecision.REJECT,
        definition,
        rejection_reason="experiment is already bound to a different walk-forward definition",
    )


def _state(owner_id: str, definition: WalkForwardExecutionDefinition) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "schema_version": PostgresWalkForwardPlanAdapter._SCHEMA_VERSION,
        "experiment_fingerprint": definition.experiment_fingerprint,
        "definition_fingerprint": definition.fingerprint,
        "definition_json": canonical_json(definition),
    }


def _aggregate_key(owner_id: str, experiment_fingerprint: str) -> AggregateKey:
    return AggregateKey(
        PostgresWalkForwardPlanAdapter._AGGREGATE_TYPE,
        content_digest({"owner_id": owner_id, "experiment_fingerprint": experiment_fingerprint}),
    )


def _principal_id(principal: Any) -> str:
    owner_id = getattr(principal, "id", principal)
    if owner_id is None or isinstance(owner_id, bool) or not isinstance(owner_id, str | int):
        raise ValueError("authenticated principal identity is required")
    normalized = str(owner_id).strip()
    if not normalized:
        raise ValueError("authenticated principal identity is required")
    return normalized


__all__ = [
    "PostgresWalkForwardPlanAdapter",
    "WalkForwardDefinitionDecision",
    "WalkForwardDefinitionResolution",
]
