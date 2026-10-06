from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ScientificTrial
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.nautilus_runtime_bundle import NautilusTrialInputBinding
from app.strategy_lab_v2.nautilus_trial_assembly import strategy_runtime_identity
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.search_worker_handoff import (
    AuthenticatedSearchDispatchMaterializer,
    _require_persisted_trial_binding,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from app.strategy_lab_v2.tests.test_worker_process import _request
from app.strategy_lab_v2.trial_hydration import (
    HydratedNautilusTrial,
)
from app.strategy_lab_v2.worker_handoff import encode_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class DispatchStore:
    def __init__(self, record: SearchDispatchRecord | None) -> None:
        self.record = record
        self.request_fingerprints: list[str] = []

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> SearchDispatchRecord | None:
        self.request_fingerprints.append(request_fingerprint)
        return self.record


class OutboxDispatchStore(DispatchStore):
    async def load_by_payload_digest(self, payload_digest: str) -> SearchDispatchRecord | None:
        if self.record is None or self.record.request.payload_digest != payload_digest:
            return None
        return self.record


class StaticTrialHydrator:
    def __init__(self, graph: HydratedNautilusTrial) -> None:
        self.graph = graph
        self.calls: list[tuple[Any, str]] = []

    async def hydrate_attempt(
        self,
        *,
        principal: Any,
        attempt_resource_id: str,
    ) -> HydratedNautilusTrial:
        self.calls.append((principal, attempt_resource_id))
        return self.graph


def _hydrated_graph() -> tuple[dict[str, Any], HydratedNautilusTrial]:
    values = _inputs()
    strategy = values["strategy_manifest"].strategy
    graph = HydratedNautilusTrial(
        attempt=values["attempt"],
        trial=values["trial"],
        experiment=values["experiment"],
        portfolio=values["portfolio"],
        snapshot=values["snapshot"],
        strategies=(strategy,),
        packages={strategy.fingerprint: values["strategy_package"]},
    )
    return values, graph


def _trial_binding(graph: HydratedNautilusTrial) -> NautilusTrialInputBinding:
    strategy_fingerprint = graph.experiment.strategy_fingerprints[0]
    package = graph.packages[strategy_fingerprint]
    return NautilusTrialInputBinding(
        attempt_id=graph.attempt.attempt_id,
        trial_fingerprint=graph.trial.trial_id,
        experiment_fingerprint=graph.experiment.fingerprint,
        portfolio_fingerprint=graph.portfolio.fingerprint,
        snapshot_fingerprint=graph.snapshot.fingerprint,
        strategy_package_fingerprint=package.fingerprint,
        engine_input_fingerprint=content_digest("engine-input"),
        invocation_input_digest=content_digest("invocation-input"),
    )


def _entry_and_payload(
    tmp_path: Path,
) -> tuple[RedisStreamEntry, DispatchPayload, SearchDispatchRecord, WorkerExecutionRequest]:
    execution_request = _request(tmp_path)
    payload = DispatchPayload.from_mapping(encode_worker_handoff(execution_request))
    dispatch_request = DispatchRequest(
        "dispatch-key",
        execution_request.authorization.attempt_id,
        payload.payload_digest,
        "strategy-backtest",
        NOW,
    )
    record = SearchDispatchRecord(
        "owner-1",
        content_digest("experiment"),
        0,
        dispatch_request,
    )
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:strategy-backtest",
        "1-0",
        content_digest("message"),
        dispatch_request.attempt_id,
        dispatch_request.payload_digest,
        dispatch_request.fingerprint,
    )
    return entry, payload, record, execution_request


@pytest.mark.asyncio
async def test_authenticated_materializer_binds_entry_before_decoding(tmp_path: Path) -> None:
    entry, payload, record, expected = _entry_and_payload(tmp_path)
    store = DispatchStore(record)
    materializer = AuthenticatedSearchDispatchMaterializer(
        store,
        queue_name="strategy-backtest",
    )

    actual = await materializer(entry, payload)

    assert actual == expected
    assert store.request_fingerprints == [entry.request_fingerprint]


@pytest.mark.asyncio
async def test_authenticated_materializer_resolves_outbox_transport_identity_by_payload(
    tmp_path: Path,
) -> None:
    entry, payload, record, expected = _entry_and_payload(tmp_path)
    transport_entry = replace(
        entry,
        attempt_id=content_digest("outbox-event-id"),
        request_fingerprint=content_digest("outbox-envelope-request"),
    )
    materializer = AuthenticatedSearchDispatchMaterializer(
        OutboxDispatchStore(record),
        queue_name="strategy-backtest",
    )

    actual = await materializer(transport_entry, payload)

    assert actual == expected


@pytest.mark.asyncio
async def test_authenticated_materializer_rejects_transport_identity_drift(tmp_path: Path) -> None:
    entry, payload, record, _ = _entry_and_payload(tmp_path)
    store = DispatchStore(record)
    materializer = AuthenticatedSearchDispatchMaterializer(
        store,
        queue_name="strategy-backtest",
    )

    with pytest.raises(ValueError, match="attempt identity"):
        await materializer(replace(entry, attempt_id="different-attempt"), payload)

    with pytest.raises(ValueError, match="queue identity"):
        await AuthenticatedSearchDispatchMaterializer(
            store,
            queue_name="different-queue",
        )(entry, payload)


@pytest.mark.asyncio
async def test_authenticated_materializer_rejects_missing_record_and_handoff_drift(
    tmp_path: Path,
) -> None:
    entry, payload, record, expected = _entry_and_payload(tmp_path)
    missing = AuthenticatedSearchDispatchMaterializer(
        DispatchStore(None),
        queue_name="strategy-backtest",
    )
    with pytest.raises(ValueError, match="not available"):
        await missing(entry, payload)

    drifted = replace(
        expected,
        authorization=replace(expected.authorization, attempt_id="different-attempt"),
    )
    drifted_payload = DispatchPayload.from_mapping(encode_worker_handoff(drifted))
    drifted_record = replace(
        record,
        request=replace(record.request, payload_digest=drifted_payload.payload_digest),
    )
    drifted_entry = replace(
        entry,
        payload_digest=drifted_payload.payload_digest,
        request_fingerprint=drifted_record.request.fingerprint,
    )
    with pytest.raises(ValueError, match="different attempt"):
        await AuthenticatedSearchDispatchMaterializer(
            DispatchStore(drifted_record),
            queue_name="strategy-backtest",
        )(drifted_entry, drifted_payload)


def test_persisted_trial_binding_checks_experiment_package_source_and_entrypoint(
    tmp_path: Path,
) -> None:
    _values, graph = _hydrated_graph()
    identity = strategy_runtime_identity(graph.strategies, graph.packages)
    request_template = _request(tmp_path)
    runtime_request = replace(
        request_template.runtime_request,
        package_fingerprint=identity.package_fingerprint,
        source_digest=identity.source_digest,
        entrypoint=identity.entrypoint,
        isolation_request=replace(
            request_template.runtime_request.isolation_request,
            dependency_digests=identity.dependency_digests,
        ),
    )
    runtime_input_artifact = replace(
        request_template.runtime_input_artifact,
        trial_binding=_trial_binding(graph),
    )

    _require_persisted_trial_binding(
        graph,
        experiment_fingerprint=graph.experiment.fingerprint,
        runtime_request=runtime_request,
        runtime_input_artifact=runtime_input_artifact,
    )

    with pytest.raises(ValueError, match="experiment differs"):
        _require_persisted_trial_binding(
            graph,
            experiment_fingerprint=content_digest("different-experiment"),
            runtime_request=runtime_request,
            runtime_input_artifact=runtime_input_artifact,
        )
    with pytest.raises(ValueError, match="not pinned"):
        _require_persisted_trial_binding(
            graph,
            experiment_fingerprint=graph.experiment.fingerprint,
            runtime_request=replace(
                runtime_request,
                package_fingerprint=content_digest("unpinned-package"),
            ),
            runtime_input_artifact=runtime_input_artifact,
        )
    with pytest.raises(ValueError, match="source differs"):
        _require_persisted_trial_binding(
            graph,
            experiment_fingerprint=graph.experiment.fingerprint,
            runtime_request=replace(
                runtime_request,
                source_digest=content_digest("different-source"),
            ),
            runtime_input_artifact=runtime_input_artifact,
        )
    with pytest.raises(ValueError, match="entrypoint differs"):
        _require_persisted_trial_binding(
            graph,
            experiment_fingerprint=graph.experiment.fingerprint,
            runtime_request=replace(runtime_request, entrypoint="other.main:run"),
            runtime_input_artifact=runtime_input_artifact,
        )

    with pytest.raises(ValueError, match="dependencies differ"):
        _require_persisted_trial_binding(
            graph,
            experiment_fingerprint=graph.experiment.fingerprint,
            runtime_request=replace(
                runtime_request,
                isolation_request=replace(
                    runtime_request.isolation_request,
                    dependency_digests=(content_digest("unbound-dependency"),),
                ),
            ),
            runtime_input_artifact=runtime_input_artifact,
        )

    with pytest.raises(ValueError, match="missing its persisted trial-input binding"):
        _require_persisted_trial_binding(
            graph,
            experiment_fingerprint=graph.experiment.fingerprint,
            runtime_request=runtime_request,
            runtime_input_artifact=replace(runtime_input_artifact, trial_binding=None),
        )

    with pytest.raises(ValueError, match="differs from the persisted trial graph"):
        _require_persisted_trial_binding(
            graph,
            experiment_fingerprint=graph.experiment.fingerprint,
            runtime_request=runtime_request,
            runtime_input_artifact=replace(
                runtime_input_artifact,
                trial_binding=replace(
                    _trial_binding(graph),
                    snapshot_fingerprint=content_digest("different-snapshot"),
                ),
            ),
        )


def test_persisted_trial_binding_authenticates_a_multi_strategy_package_set(
    tmp_path: Path,
) -> None:
    _values, single_graph = _hydrated_graph()
    first_strategy = single_graph.strategies[0]
    first_package = single_graph.packages[first_strategy.fingerprint]
    second_strategy = replace(first_strategy, version_id="v2")
    second_package = replace(
        first_package,
        package_id="package-2",
        strategy_fingerprint=second_strategy.fingerprint,
        archive_digest=content_digest("archive-2"),
        manifest_digest=content_digest("manifest-2"),
        dependency_lock_digest=content_digest("dependency-lock-2"),
    )
    base_component = single_graph.portfolio.components[0]
    portfolio = replace(
        single_graph.portfolio,
        components=(
            replace(
                base_component,
                component_id="component-a",
                capital_weight=Decimal("0.5"),
            ),
            replace(
                base_component,
                component_id="component-b",
                strategy_fingerprint=second_strategy.fingerprint,
                capital_weight=Decimal("0.5"),
            ),
        ),
    )
    experiment = replace(
        single_graph.experiment,
        portfolio_fingerprint=portfolio.fingerprint,
        strategy_fingerprints=(first_strategy.fingerprint, second_strategy.fingerprint),
        strategy_package_fingerprints={
            first_strategy.fingerprint: first_package.fingerprint,
            second_strategy.fingerprint: second_package.fingerprint,
        },
    )
    previous_trial = single_graph.trial
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=single_graph.snapshot.fingerprint,
        preflight_report=previous_trial.preflight_report,
        parameter_set=previous_trial.parameter_set,
        scenario=previous_trial.scenario,
        seed=previous_trial.seed,
        randomization=previous_trial.randomization,
    )
    graph = HydratedNautilusTrial(
        attempt=replace(single_graph.attempt, trial_id=trial.trial_id),
        trial=trial,
        experiment=experiment,
        portfolio=portfolio,
        snapshot=single_graph.snapshot,
        strategies=(first_strategy, second_strategy),
        packages={
            first_strategy.fingerprint: first_package,
            second_strategy.fingerprint: second_package,
        },
    )
    identity = strategy_runtime_identity(graph.strategies, graph.packages)
    request_template = _request(tmp_path)
    runtime_request = replace(
        request_template.runtime_request,
        package_fingerprint=identity.package_fingerprint,
        source_digest=identity.source_digest,
        entrypoint=identity.entrypoint,
        isolation_request=replace(
            request_template.runtime_request.isolation_request,
            dependency_digests=identity.dependency_digests,
        ),
    )
    runtime_input_artifact = replace(
        request_template.runtime_input_artifact,
        trial_binding=NautilusTrialInputBinding(
            attempt_id=graph.attempt.attempt_id,
            trial_fingerprint=graph.trial.trial_id,
            experiment_fingerprint=graph.experiment.fingerprint,
            portfolio_fingerprint=graph.portfolio.fingerprint,
            snapshot_fingerprint=graph.snapshot.fingerprint,
            strategy_package_fingerprint=identity.package_fingerprint,
            engine_input_fingerprint=content_digest("multi-engine-input"),
            invocation_input_digest=content_digest("multi-invocation-input"),
        ),
    )

    _require_persisted_trial_binding(
        graph,
        experiment_fingerprint=graph.experiment.fingerprint,
        runtime_request=runtime_request,
        runtime_input_artifact=runtime_input_artifact,
    )


@pytest.mark.asyncio
async def test_authenticated_materializer_hydrates_with_dispatch_owner_before_execution(
    tmp_path: Path,
) -> None:
    entry, payload, record, _ = _entry_and_payload(tmp_path)
    _values, graph = _hydrated_graph()
    dispatch = replace(record, experiment_fingerprint=graph.experiment.fingerprint)
    hydrator = StaticTrialHydrator(graph)
    materializer = AuthenticatedSearchDispatchMaterializer(
        DispatchStore(dispatch),
        queue_name="strategy-backtest",
        domain_hydrator=hydrator,
    )

    with pytest.raises(ValueError, match="package is not pinned"):
        await materializer(entry, payload)

    assert hydrator.calls == [(dispatch.owner_id, dispatch.request.attempt_id)]
