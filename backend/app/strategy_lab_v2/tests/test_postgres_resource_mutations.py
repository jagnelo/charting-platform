from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import StrategyPackage
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationRequest,
)
from app.strategy_lab_v2.tests.test_postgres_storage import FakeSession

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
