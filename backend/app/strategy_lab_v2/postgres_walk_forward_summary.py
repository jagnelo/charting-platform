"""Owner-scoped immutable persistence for walk-forward OOS summaries."""

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
from app.strategy_lab_v2.walk_forward_summary import WalkForwardOosSummary


class AggregateStore(Protocol):
    async def get(self, key: AggregateKey) -> StoredAggregate | None: ...

    async def apply(self, request: StorageTransactionRequest) -> Any: ...


class WalkForwardSummaryDecision(StrEnum):
    PERSISTED = "persisted"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WalkForwardSummaryResolution:
    decision: WalkForwardSummaryDecision
    summary: WalkForwardOosSummary
    aggregate_version: int | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WalkForwardSummaryDecision):
            raise TypeError("decision must be a WalkForwardSummaryDecision")
        if not isinstance(self.summary, WalkForwardOosSummary):
            raise TypeError("summary must be a WalkForwardOosSummary")
        if (self.decision is WalkForwardSummaryDecision.REJECT) != bool(self.rejection_reason):
            raise ValueError("only rejected summary resolutions contain a rejection reason")


class PostgresWalkForwardSummaryAdapter:
    """Persist one immutable OOS summary per owner and experiment."""

    _AGGREGATE_TYPE = "strategy_lab_v2_walk_forward_oos_summaries"
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
        summary: WalkForwardOosSummary,
    ) -> WalkForwardSummaryResolution:
        if not isinstance(summary, WalkForwardOosSummary):
            raise TypeError("summary must be a WalkForwardOosSummary")
        owner_id = _principal_id(principal)
        key = _aggregate_key(owner_id, summary.experiment_fingerprint)
        state = _state(owner_id, summary)
        current = await self._aggregate_store.get(key)
        if current is not None:
            return _existing_resolution(current, owner_id, summary)
        request_id = content_digest(
            {
                "owner_id": owner_id,
                "experiment_fingerprint": summary.experiment_fingerprint,
                "summary_fingerprint": summary.fingerprint,
                "purpose": "strategy-lab-v2-walk-forward-oos-summary",
            }
        )
        outcome = await self._aggregate_store.apply(
            StorageTransactionRequest(request_id, (AggregateMutation(key, state),))
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
                    WalkForwardSummaryDecision.PERSISTED
                    if outcome.decision is StorageTransactionDecision.APPLY
                    else WalkForwardSummaryDecision.REPLAY_EXISTING
                )
                return WalkForwardSummaryResolution(decision, summary, aggregate.version)
        winner = await self._aggregate_store.get(key)
        if winner is not None:
            replay = _existing_resolution(winner, owner_id, summary)
            if replay.decision is WalkForwardSummaryDecision.REPLAY_EXISTING:
                return replay
        return WalkForwardSummaryResolution(
            WalkForwardSummaryDecision.REJECT,
            summary,
            rejection_reason=getattr(outcome, "rejection_reason", None)
            or "walk-forward OOS summary was not durably accepted",
        )

    async def load(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
    ) -> WalkForwardOosSummary | None:
        owner_id = _principal_id(principal)
        if not isinstance(experiment_fingerprint, str) or not experiment_fingerprint.strip():
            raise ValueError("experiment_fingerprint must not be empty")
        aggregate = await self._aggregate_store.get(
            _aggregate_key(owner_id, experiment_fingerprint)
        )
        if aggregate is None:
            return None
        state = aggregate.state
        if not isinstance(state, Mapping):
            raise ValueError("persisted walk-forward summary state is malformed")
        if (
            state.get("owner_id") != owner_id
            or state.get("schema_version") != self._SCHEMA_VERSION
            or state.get("experiment_fingerprint") != experiment_fingerprint
        ):
            raise ValueError("persisted walk-forward summary owner or identity drifted")
        payload = state.get("summary_json")
        fingerprint = state.get("summary_fingerprint")
        if not isinstance(payload, str) or not isinstance(fingerprint, str):
            raise ValueError("persisted walk-forward summary payload is missing")
        summary = decode_canonical_contract(payload, WalkForwardOosSummary)
        if (
            summary.experiment_fingerprint != experiment_fingerprint
            or summary.fingerprint != fingerprint
            or canonical_json(summary) != payload
        ):
            raise ValueError("persisted walk-forward summary content identity drifted")
        return summary


def _existing_resolution(
    aggregate: StoredAggregate,
    owner_id: str,
    summary: WalkForwardOosSummary,
) -> WalkForwardSummaryResolution:
    state = aggregate.state
    if not isinstance(state, Mapping) or state.get("owner_id") != owner_id:
        return WalkForwardSummaryResolution(
            WalkForwardSummaryDecision.REJECT,
            summary,
            rejection_reason="persisted walk-forward summary is outside the owner scope",
        )
    if state == _state(owner_id, summary):
        return WalkForwardSummaryResolution(
            WalkForwardSummaryDecision.REPLAY_EXISTING,
            summary,
            aggregate.version,
        )
    return WalkForwardSummaryResolution(
        WalkForwardSummaryDecision.REJECT,
        summary,
        rejection_reason="experiment is already bound to a different OOS result summary",
    )


def _state(owner_id: str, summary: WalkForwardOosSummary) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "schema_version": PostgresWalkForwardSummaryAdapter._SCHEMA_VERSION,
        "experiment_fingerprint": summary.experiment_fingerprint,
        "summary_fingerprint": summary.fingerprint,
        "summary_json": canonical_json(summary),
    }


def _aggregate_key(owner_id: str, experiment_fingerprint: str) -> AggregateKey:
    return AggregateKey(
        PostgresWalkForwardSummaryAdapter._AGGREGATE_TYPE,
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
    "PostgresWalkForwardSummaryAdapter",
    "WalkForwardSummaryDecision",
    "WalkForwardSummaryResolution",
]
