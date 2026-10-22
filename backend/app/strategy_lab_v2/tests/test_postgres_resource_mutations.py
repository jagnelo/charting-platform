from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import ResourceMutationServiceResult
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    DataSnapshot,
    ExperimentDefinition,
    MetricSet,
    PortfolioComposition,
    RunAttempt,
    ScientificTrial,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.resource_domains import DomainResourceContract
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationRequest,
)
from app.strategy_lab_v2.tests.test_postgres_storage import FakeSession
from app.strategy_lab_v2.tests.test_resource_domains import _preflight_payload
from app.strategy_lab_v2.trial_hydration import NautilusTrialDomainHydrator

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _payload(*, parameters: dict[str, int] | None = None) -> dict:
    return {
        "attributes": {
            "resource_id": "strategy-version-1",
            "strategy_id": "momentum",
            "version_id": "v1",
            "sdk_version": "strategy-sdk.v2",
            "source_digest": content_digest("momentum-source"),
            "default_parameters": parameters if parameters is not None else {"lookback": 20},
        }
    }


def _request(*, parameters: dict[str, int] | None = None) -> ResourceMutationRequest:
    return ResourceMutationRequest(
        ApiResourceType.STRATEGY,
        "strategy-create-key",
        _payload(parameters=parameters),
        NOW,
    )


def _adapter(session: FakeSession, *, clock: datetime) -> PostgresStrategyLabV2Adapter:
    def session_factory() -> FakeSession:
        return session

    persistence = PostgresStrategyLabV2Persistence.build(
        session_factory,
        clock=lambda: clock,
    )
    return PostgresStrategyLabV2Adapter(
        session_factory,
        clock=lambda: clock,
        persistence=persistence,
    )


@pytest.mark.asyncio
async def test_postgres_resource_mutation_survives_adapter_reconstruction() -> None:
    session = FakeSession()
    owner = SimpleNamespace(id=42)
    other_owner = SimpleNamespace(id=7)
    accepted_at = NOW + timedelta(minutes=1)
    first_adapter = _adapter(session, clock=accepted_at)
    request = _request()
    first = await first_adapter.create_resource(
        principal=owner,
        request_id="request-create",
        request=request,
    )
    assert first.resolution.decision is ResourceMutationDecision.ACCEPT
    assert first.receipt is not None
    assert first.receipt.resource.id == "strategy-version-1"
    assert first.receipt.request.payload_digest == request.payload_digest
    assert first.receipt.accepted_at == accepted_at

    persisted = await first_adapter.get_resource(
        principal=owner,
        resource_type=ApiResourceType.STRATEGY,
        resource_id="strategy-version-1",
    )
    assert persisted is not None
    assert persisted.id == "strategy-version-1"

    assert len(session.aggregates) == 2  # resource plus owner-scoped domain identity
    assert len(session.receipts) == 1

    strategy_fingerprint = first.receipt.resource.meta["domain_fingerprint"]
    package_request = ResourceMutationRequest(
        ApiResourceType.PACKAGE,
        "package-create-key",
        {
            "attributes": {
                "package_id": "momentum-package",
                "strategy_fingerprint": strategy_fingerprint,
                "package_format": "source_archive",
                "archive_digest": content_digest("strategy-archive"),
                "manifest_digest": content_digest("strategy-manifest"),
                "dependency_lock_digest": content_digest("dependency-lock"),
                "archive_byte_length": 128,
                "entrypoint": "strategy.main:run",
                "sdk_version": "strategy-sdk.v2",
                "runtime_abi": "python3.12-linux-x86_64",
            }
        },
        NOW,
    )
    package = await first_adapter.create_resource(
        principal=owner,
        request_id="request-package",
        request=package_request,
    )
    assert package.resolution.decision is ResourceMutationDecision.ACCEPT
    assert package.receipt is not None
    assert package.receipt.resource.attributes["strategy_fingerprint"] == strategy_fingerprint
    assert len(session.aggregates) == 4  # package plus its domain identity
    assert len(session.receipts) == 2

    writes_before_replay = sum(
        sql.lstrip().startswith(("INSERT INTO", "UPDATE")) for sql, _values in session.calls
    )
    restarted_adapter = _adapter(session, clock=accepted_at + timedelta(hours=1))
    replay = await restarted_adapter.create_resource(
        principal=owner,
        request_id="request-replay",
        request=request,
    )
    assert replay.resolution.decision is ResourceMutationDecision.REPLAY_EXISTING
    assert replay.receipt == first.receipt
    assert replay.receipt is not None
    assert replay.receipt.accepted_at == accepted_at

    reconstructed_package = await restarted_adapter.get_resource(
        principal=owner,
        resource_type=ApiResourceType.PACKAGE,
        resource_id=package.receipt.resource.id,
    )
    assert reconstructed_package == package.receipt.resource
    typed_package = await restarted_adapter._resources.get_domain_contract_by_fingerprint(
        principal=owner,
        resource_type=ApiResourceType.PACKAGE,
        fingerprint=package.receipt.resource.meta["domain_fingerprint"],
    )
    assert isinstance(typed_package, StrategyPackage)
    assert typed_package.strategy_fingerprint == strategy_fingerprint

    writes_before_package_replay = sum(
        sql.lstrip().startswith(("INSERT INTO", "UPDATE")) for sql, _values in session.calls
    )
    package_replay = await restarted_adapter.create_resource(
        principal=owner,
        request_id="request-package-replay",
        request=package_request,
    )
    assert package_replay.resolution.decision is ResourceMutationDecision.REPLAY_EXISTING
    assert package_replay.receipt == package.receipt

    conflict = await restarted_adapter.create_resource(
        principal=owner,
        request_id="request-conflict",
        request=_request(parameters={"lookback": 30}),
    )
    assert conflict.resolution.decision is ResourceMutationDecision.IDEMPOTENCY_CONFLICT
    assert conflict.receipt is None

    writes_after_replay = sum(
        sql.lstrip().startswith(("INSERT INTO", "UPDATE")) for sql, _values in session.calls
    )
    assert writes_after_replay == writes_before_replay
    assert (
        sum(sql.lstrip().startswith(("INSERT INTO", "UPDATE")) for sql, _values in session.calls)
        == writes_before_package_replay
    )

    foreign = await restarted_adapter.get_resource(
        principal=other_owner,
        resource_type=ApiResourceType.STRATEGY,
        resource_id="strategy-version-1",
    )
    assert foreign is None
    foreign_package = await restarted_adapter.get_resource(
        principal=other_owner,
        resource_type=ApiResourceType.PACKAGE,
        resource_id=package.receipt.resource.id,
    )
    assert foreign_package is None

    assert len(session.aggregates) == 4
    assert len(session.receipts) == 2


@pytest.mark.asyncio
async def test_persisted_trial_dependency_graph_rehydrates_after_adapter_reconstruction() -> None:
    session = FakeSession()
    owner = SimpleNamespace(id="42")
    other_owner = SimpleNamespace(id="7")
    adapter = _adapter(session, clock=NOW + timedelta(minutes=1))

    async def create(
        resource_type: ApiResourceType,
        key: str,
        attributes: Mapping[str, Any],
    ) -> ResourceMutationServiceResult:
        response = await adapter.create_resource(
            principal=owner,
            request_id=f"request-{key}",
            request=ResourceMutationRequest(
                resource_type,
                key,
                {"attributes": attributes},
                NOW,
            ),
        )
        assert response.resolution.decision is ResourceMutationDecision.ACCEPT
        assert response.receipt is not None
        return response

    strategy = await create(
        ApiResourceType.STRATEGY,
        "strategy-key",
        {
            "strategy_id": "momentum",
            "version_id": "v1",
            "sdk_version": "strategy-sdk.v2",
            "source_digest": content_digest("strategy-source"),
            "default_parameters": {"lookback": 20},
        },
    )
    assert strategy.receipt is not None
    strategy_fingerprint = strategy.receipt.resource.meta["domain_fingerprint"]

    package = await create(
        ApiResourceType.PACKAGE,
        "package-key",
        {
            "package_id": "momentum-package",
            "strategy_fingerprint": strategy_fingerprint,
            "package_format": "source_archive",
            "archive_digest": content_digest("strategy-archive"),
            "manifest_digest": content_digest("strategy-manifest"),
            "dependency_lock_digest": content_digest("dependency-lock"),
            "archive_byte_length": 128,
            "entrypoint": "strategy.main:run",
            "sdk_version": "strategy-sdk.v2",
            "runtime_abi": "python3.12-linux-x86_64",
        },
    )
    assert package.receipt is not None
    package_fingerprint = package.receipt.resource.meta["domain_fingerprint"]

    portfolio = await create(
        ApiResourceType.PORTFOLIO,
        "portfolio-key",
        {
            "portfolio_id": "balanced",
            "version_id": "v1",
            "initial_capital": "100000",
            "base_currency": "USD",
            "components": [
                {
                    "component_id": "momentum",
                    "strategy_fingerprint": strategy_fingerprint,
                    "instrument_ids": ["US.AAPL"],
                    "capital_weight": "1.0",
                }
            ],
        },
    )
    assert portfolio.receipt is not None
    portfolio_fingerprint = portfolio.receipt.resource.meta["domain_fingerprint"]

    preflight = _preflight_payload()
    snapshot_request = ResourceMutationRequest(
        ApiResourceType.SNAPSHOT,
        "snapshot-key",
        {
            "attributes": {
                "snapshot_id": "snapshot-v1",
                "provider_snapshot_id": "provider-snapshot-v1",
                "preflight_report": preflight,
                "series": [
                    {
                        "instrument_id": "US.AAPL",
                        "event_type": "ohlcv",
                        "event_granularity": "bar",
                        "timeframe": "1d",
                        "session": "regular",
                        "feed": "consolidated",
                        "start": "2020-01-01T00:00:00Z",
                        "end": "2022-01-01T00:00:00Z",
                        "adjustment": "split_adjusted",
                        "corporate_action_semantics": "split-adjusted-v1",
                        "coverage_evidence_digest": content_digest("coverage-v1"),
                        "content_digest": content_digest("series-v1"),
                        "row_count": 500,
                    }
                ],
                "created_at": "2026-10-05T00:00:00Z",
            }
        },
        NOW,
    )
    snapshot = await adapter.create_resource(
        principal=owner,
        request_id="request-snapshot",
        request=snapshot_request,
    )
    assert snapshot.resolution.decision is ResourceMutationDecision.ACCEPT
    assert snapshot.receipt is not None
    snapshot_fingerprint = snapshot.receipt.resource.meta["domain_fingerprint"]

    experiment_attributes = {
        "experiment_id": "momentum-search",
        "portfolio_fingerprint": portfolio_fingerprint,
        "strategy_fingerprints": [strategy_fingerprint],
        "snapshot_fingerprint": snapshot_fingerprint,
        "capability_contract_digest": preflight["fingerprint"],
        "seed": 42,
        "metric_definition_version": "strategy-lab.metrics.v1",
        "engine_contract": {"engine": "nautilus", "version": "v2"},
        "strategy_package_fingerprints": {strategy_fingerprint: package_fingerprint},
    }
    invalid_experiment_attributes = {
        **experiment_attributes,
        "capability_contract_digest": content_digest("different-capability-contract"),
    }
    writes_before_invalid_experiment = sum(
        sql.lstrip().startswith(("INSERT INTO", "UPDATE")) for sql, _values in session.calls
    )
    with pytest.raises(ValueError, match="capability contract differs from its frozen snapshot"):
        await adapter.create_resource(
            principal=owner,
            request_id="request-invalid-experiment",
            request=ResourceMutationRequest(
                ApiResourceType.EXPERIMENT,
                "invalid-experiment-key",
                {"attributes": invalid_experiment_attributes},
                NOW,
            ),
        )
    assert (
        sum(sql.lstrip().startswith(("INSERT INTO", "UPDATE")) for sql, _values in session.calls)
        == writes_before_invalid_experiment
    )

    experiment = await create(
        ApiResourceType.EXPERIMENT,
        "experiment-key",
        experiment_attributes,
    )
    assert experiment.receipt is not None
    experiment_fingerprint = experiment.receipt.resource.meta["domain_fingerprint"]

    trial_request = ResourceMutationRequest(
        ApiResourceType.TRIAL,
        "trial-key",
        {
            "attributes": {
                "experiment_fingerprint": experiment_fingerprint,
                "snapshot_fingerprint": snapshot_fingerprint,
                "preflight_report": preflight,
                "parameter_set": {"lookback": 20},
                "scenario": {"slippage_bps": 2},
                "seed": 42,
            }
        },
        NOW,
    )
    trial = await adapter.create_resource(
        principal=owner,
        request_id="request-trial",
        request=trial_request,
    )
    assert trial.resolution.decision is ResourceMutationDecision.ACCEPT
    assert trial.receipt is not None

    attempt = await create(
        ApiResourceType.ATTEMPT,
        "attempt-key",
        {
            "attempt_id": content_digest("attempt-1"),
            "trial_id": trial.receipt.resource.attributes["trial_id"],
            "ordinal": 1,
            "state": "queued",
            "created_at": "2026-10-05T00:00:00Z",
        },
    )
    assert attempt.receipt is not None
    metric_set = await create(
        ApiResourceType.METRIC_SET,
        "metric-set-key",
        {
            "metric_set_id": "metric-set-v1",
            "trial_id": trial.receipt.resource.attributes["trial_id"],
            "attempt_id": attempt.receipt.resource.attributes["attempt_id"],
            "definition_version": "strategy-lab.metrics.v1",
            "values": [
                {
                    "name": "cumulative_net_return",
                    "value": "0.05",
                    "unit": "fraction",
                    "definition_version": "strategy-lab.metrics.v1",
                    "basis": "net",
                    "sample_size": 1,
                    "calculation_basis": "native_equity_trace",
                }
            ],
            "created_at": "2026-10-05T00:00:00Z",
        },
    )
    assert metric_set.receipt is not None

    reconstructed = _adapter(session, clock=NOW + timedelta(hours=1))

    async def read_contract(
        resource_type: ApiResourceType,
        fingerprint: str,
    ) -> DomainResourceContract:
        contract = await reconstructed._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=resource_type,
            fingerprint=fingerprint,
        )
        assert contract is not None
        return contract

    restored_strategy = await read_contract(ApiResourceType.STRATEGY, strategy_fingerprint)
    assert isinstance(restored_strategy, StrategyVersion)
    assert restored_strategy.fingerprint == strategy_fingerprint
    restored_package = await read_contract(ApiResourceType.PACKAGE, package_fingerprint)
    assert isinstance(restored_package, StrategyPackage)
    assert restored_package.strategy_fingerprint == strategy_fingerprint
    restored_portfolio = await read_contract(ApiResourceType.PORTFOLIO, portfolio_fingerprint)
    assert isinstance(restored_portfolio, PortfolioComposition)
    assert restored_portfolio.components[0].strategy_fingerprint == strategy_fingerprint
    restored_snapshot = await read_contract(ApiResourceType.SNAPSHOT, snapshot_fingerprint)
    assert isinstance(restored_snapshot, DataSnapshot)
    assert restored_snapshot.preflight_report.fingerprint == preflight["fingerprint"]
    restored_experiment = await read_contract(ApiResourceType.EXPERIMENT, experiment_fingerprint)
    assert isinstance(restored_experiment, ExperimentDefinition)
    assert restored_experiment.portfolio_fingerprint == portfolio_fingerprint
    assert (
        restored_experiment.capability_contract_digest
        == restored_snapshot.capability_contract_digest
    )
    restored_trial = await read_contract(
        ApiResourceType.TRIAL,
        trial.receipt.resource.meta["domain_fingerprint"],
    )
    assert isinstance(restored_trial, ScientificTrial)
    assert restored_trial.experiment_fingerprint == experiment_fingerprint
    restored_attempt = await read_contract(
        ApiResourceType.ATTEMPT,
        attempt.receipt.resource.meta["domain_fingerprint"],
    )
    assert isinstance(restored_attempt, RunAttempt)
    restored_metrics = await read_contract(
        ApiResourceType.METRIC_SET,
        metric_set.receipt.resource.meta["domain_fingerprint"],
    )
    assert isinstance(restored_metrics, MetricSet)
    assert restored_metrics.attempt_id == restored_attempt.attempt_id
    hydrated = await NautilusTrialDomainHydrator(reconstructed._resources).hydrate_attempt(
        principal=owner,
        attempt_resource_id=attempt.receipt.resource.id,
    )
    assert hydrated.attempt == restored_attempt
    assert hydrated.trial == restored_trial
    assert hydrated.experiment == restored_experiment
    assert hydrated.portfolio == restored_portfolio
    assert hydrated.snapshot == restored_snapshot
    assert hydrated.strategies == (restored_strategy,)
    assert hydrated.packages == {strategy_fingerprint: restored_package}

    replay = await reconstructed.create_resource(
        principal=owner,
        request_id="request-trial-replay",
        request=trial_request,
    )
    assert replay.resolution.decision is ResourceMutationDecision.REPLAY_EXISTING
    assert replay.receipt == trial.receipt

    assert (
        await reconstructed._resources.get_domain_contract(
            principal=other_owner,
            resource_type=ApiResourceType.ATTEMPT,
            resource_id=attempt.receipt.resource.id,
        )
        is None
    )
