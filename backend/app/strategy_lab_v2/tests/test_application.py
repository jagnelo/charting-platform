from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import ResourceMutationServiceResult
from app.strategy_lab_v2.application import (
    PostgresStrategyLabV2Adapter,
    _principal_identity,
    create_registered_strategy_lab_v2_router,
    get_strategy_lab_v2_adapter,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_commands import PostgresCommandAdapter
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter
from app.strategy_lab_v2.resource_mutations import ResourceMutationRequest
from app.strategy_lab_v2.storage import (
    StorageTransactionDecision,
    resolve_storage_transaction,
)


@dataclass
class _User:
    id: int


NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def test_principal_identity_normalizes_existing_integer_user_ids() -> None:
    assert _principal_identity(_User(42)).id == "42"
    assert _principal_identity("owner-a").id == "owner-a"


def test_principal_identity_rejects_missing_or_boolean_identity() -> None:
    for principal in (None, object(), True, " "):
        try:
            _principal_identity(principal)
        except ValueError as error:
            assert "principal identity" in str(error)
        else:  # pragma: no cover - assertion branch
            raise AssertionError("principal identity should be rejected")


def test_application_adapter_composes_all_durable_api_adapters() -> None:
    adapter = PostgresStrategyLabV2Adapter(lambda: object())

    assert isinstance(adapter._persistence, PostgresStrategyLabV2Persistence)
    assert isinstance(adapter._resources, PostgresResourceReader)
    assert isinstance(adapter._submissions, PostgresSubmissionDispatchAdapter)
    assert isinstance(adapter._execution_state, PostgresExecutionStateAdapter)
    assert isinstance(adapter._commands, PostgresCommandAdapter)


def test_registered_router_uses_versioned_prefix_and_application_dependencies() -> None:
    router = create_registered_strategy_lab_v2_router()

    assert router.prefix == "/strategy-lab/v2"
    assert {route.path for route in router.routes} >= {
        "/strategy-lab/v2/strategies/validate",
        "/strategy-lab/v2/submissions",
        "/strategy-lab/v2/attempts/{attempt_id}/commands",
    }
    assert get_strategy_lab_v2_adapter() is get_strategy_lab_v2_adapter()


@pytest.mark.asyncio
async def test_application_adapter_persists_and_replays_resource_mutations() -> None:
    class InMemoryAggregateStore:
        def __init__(self) -> None:
            self.current = ()
            self.receipts = ()

        async def get(self, key):
            return next((aggregate for aggregate in self.current if aggregate.key == key), None)

        async def list_type(self, aggregate_type):
            return tuple(
                aggregate
                for aggregate in self.current
                if aggregate.key.aggregate_type == aggregate_type
            )

        async def apply(self, request):
            resolved = resolve_storage_transaction(self.current, request, self.receipts)
            if resolved.decision is StorageTransactionDecision.APPLY:
                self.current = resolved.aggregates
                self.receipts = (*self.receipts, resolved.receipt)
            return resolved

    store = InMemoryAggregateStore()
    reader = PostgresResourceReader(store)
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(aggregate_store=store)
    adapter._resources = reader
    accepted_at = NOW.replace(hour=13)
    conflict_clock = NOW.replace(hour=14)
    strategy_clock = NOW.replace(hour=15)
    package_clock = NOW.replace(hour=16)
    portfolio_clock = NOW.replace(hour=17)
    experiment_clock = NOW.replace(hour=18)
    attempt_clock = NOW.replace(hour=19)
    clocks = iter(
        (
            accepted_at,
            conflict_clock,
            strategy_clock,
            package_clock,
            portfolio_clock,
            experiment_clock,
            attempt_clock,
        )
    )
    adapter._clock = lambda: next(clocks)
    request = ResourceMutationRequest(
        ApiResourceType.TRIAL,
        "trial-key",
        {"attributes": {"resource_id": "trial-1", "name": "demo"}},
        NOW,
    )

    first = await adapter.create_resource(
        principal=_User(42), request_id="request-1", request=request
    )
    assert isinstance(first, ResourceMutationServiceResult)
    assert first.receipt is not None
    assert first.receipt.resource.id == "trial-1"
    assert first.receipt.resource.attributes["name"] == "demo"
    assert first.receipt.accepted_at == accepted_at

    replay = await adapter.create_resource(
        principal=_User(42), request_id="request-2", request=request
    )
    assert replay.resolution.decision.value == "replay_existing"
    assert replay.receipt == first.receipt

    owner_conflict = await adapter.create_resource(
        principal=_User(7), request_id="request-3", request=request
    )
    assert owner_conflict.resolution.decision.value == "reject"
    assert owner_conflict.receipt is None

    strategy = await adapter.create_resource(
        principal=_User(42),
        request_id="request-4",
        request=ResourceMutationRequest(
            ApiResourceType.STRATEGY,
            "strategy-key",
            {
                "attributes": {
                    "strategy_id": "momentum",
                    "version_id": "2026-09-17",
                    "sdk_version": "strategy-sdk.v2",
                    "source_digest": content_digest("strategy-source"),
                    "default_parameters": {"lookback": 20},
                }
            },
            NOW,
        ),
    )
    assert strategy.resolution.decision.value == "accept"
    assert strategy.receipt is not None
    assert strategy.receipt.resource.attributes["strategy_id"] == "momentum"
    assert strategy.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    package = await adapter.create_resource(
        principal=_User(42),
        request_id="request-5",
        request=ResourceMutationRequest(
            ApiResourceType.PACKAGE,
            "package-key",
            {
                "attributes": {
                    "package_id": "momentum-package",
                    "strategy_fingerprint": strategy.receipt.resource.meta["domain_fingerprint"],
                    "package_format": "source_archive",
                    "archive_digest": content_digest("strategy-archive"),
                    "manifest_digest": content_digest("strategy-manifest"),
                    "dependency_lock_digest": content_digest("dependency-lock"),
                    "archive_byte_length": 128,
                    "entrypoint": "strategy.main:run",
                    "sdk_version": "strategy-sdk.v2",
                    "runtime_abi": "python3.12-linux-arm64",
                }
            },
            NOW,
        ),
    )
    assert package.resolution.decision.value == "accept"
    assert package.receipt is not None
    assert package.receipt.resource.attributes["package_format"] == "source_archive"
    assert package.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    portfolio = await adapter.create_resource(
        principal=_User(42),
        request_id="request-6",
        request=ResourceMutationRequest(
            ApiResourceType.PORTFOLIO,
            "portfolio-key",
            {
                "attributes": {
                    "portfolio_id": "balanced",
                    "version_id": "v1",
                    "initial_capital": "100000",
                    "base_currency": "usd",
                    "components": [
                        {
                            "component_id": "momentum",
                            "strategy_fingerprint": strategy.receipt.resource.meta[
                                "domain_fingerprint"
                            ],
                            "instrument_ids": ["US.AAPL"],
                            "capital_weight": "1.0",
                        }
                    ],
                }
            },
            NOW,
        ),
    )
    assert portfolio.resolution.decision.value == "accept"
    assert portfolio.receipt is not None
    assert portfolio.receipt.resource.attributes["base_currency"] == "USD"
    assert portfolio.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    experiment = await adapter.create_resource(
        principal=_User(42),
        request_id="request-7",
        request=ResourceMutationRequest(
            ApiResourceType.EXPERIMENT,
            "experiment-key",
            {
                "attributes": {
                    "experiment_id": "momentum-search",
                    "portfolio_fingerprint": portfolio.receipt.resource.meta[
                        "domain_fingerprint"
                    ],
                    "strategy_fingerprints": [
                        strategy.receipt.resource.meta["domain_fingerprint"]
                    ],
                    "snapshot_fingerprint": content_digest("snapshot-v1"),
                    "capability_contract_digest": content_digest("capability-v1"),
                    "seed": 42,
                    "metric_definition_version": "strategy-lab.metrics.v1",
                    "engine_contract": {"engine": "nautilus", "version": "v2"},
                }
            },
            NOW,
        ),
    )
    assert experiment.resolution.decision.value == "accept"
    assert experiment.receipt is not None
    assert experiment.receipt.resource.attributes["seed"] == 42
    assert experiment.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    attempt = await adapter.create_resource(
        principal=_User(42),
        request_id="request-8",
        request=ResourceMutationRequest(
            ApiResourceType.ATTEMPT,
            "attempt-key",
            {
                "attributes": {
                    "attempt_id": content_digest("attempt-1"),
                    "trial_id": content_digest("trial-1"),
                    "ordinal": 1,
                    "state": "queued",
                    "created_at": "2026-09-17T12:00:00Z",
                }
            },
            NOW,
        ),
    )
    assert attempt.resolution.decision.value == "accept"
    assert attempt.receipt is not None
    assert attempt.receipt.resource.attributes["state"] == "queued"
    assert attempt.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")
