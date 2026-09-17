from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.postgres_result_materialization import (
    PostgresResultMaterializationAdapter,
    PostgresResultMaterializationSchema,
    ResultManifestStateDecision,
)
from app.strategy_lab_v2.result_materialization import ResultMaterializationDecision
from app.strategy_lab_v2.tests.test_result_materialization import _inputs

NOW = datetime(2024, 1, 1, tzinfo=UTC)


class FakeResult:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return iter(self._rows)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self) -> None:
        self.manifests: dict[tuple[str, str], dict[str, Any]] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        normalized = sql.lstrip()
        if normalized.startswith("SELECT owner_id"):
            rows = [
                row
                for (owner, attempt), row in self.manifests.items()
                if owner == values["owner_id"]
                and (
                    values.get("attempt_id") is None
                    or attempt == values["attempt_id"]
                )
            ]
            return FakeResult(sorted(rows, key=lambda row: row["attempt_id"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["attempt_id"])
            if key in self.manifests:
                return FakeResult(rowcount=0)
            self.manifests[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_result_manifest_adapter_registers_replays_and_scopes_payload() -> None:
    manifest, _ = _inputs()
    session = FakeSession()
    adapter = PostgresResultMaterializationAdapter(lambda: session)
    registered = await adapter.ensure(principal="owner-a", manifest=manifest)
    assert registered.decision is ResultManifestStateDecision.REGISTERED
    assert registered.record.manifest_json == canonical_json(manifest)
    replay = await adapter.ensure(principal="owner-a", manifest=manifest)
    assert replay.decision is ResultManifestStateDecision.REPLAY_EXISTING
    loaded = await adapter.load(principal="owner-a", attempt_id=manifest.attempt_id)
    assert loaded == registered.record
    assert await adapter.load(principal="owner-b", attempt_id=manifest.attempt_id) is None
    assert await adapter.load_all(principal="owner-a") == (registered.record,)


@pytest.mark.asyncio
async def test_result_manifest_materialization_delegates_pure_gate_and_conflicts() -> None:
    manifest, evidence = _inputs()
    session = FakeSession()
    adapter = PostgresResultMaterializationAdapter(lambda: session)
    first = await adapter.materialize(
        principal="owner-a",
        trial=manifest.trial,
        attempt=manifest.attempt,
        strategy_packages=manifest.strategy_packages,
        portfolio=manifest.portfolio,
        snapshot=manifest.snapshot,
        evidence=evidence,
        metric_set=manifest.metric_set,
        output_artifacts=manifest.output_artifacts,
        created_at=NOW,
    )
    assert first.decision is ResultMaterializationDecision.MATERIALIZE
    replay = await adapter.materialize(
        principal="owner-a",
        trial=manifest.trial,
        attempt=manifest.attempt,
        strategy_packages=manifest.strategy_packages,
        portfolio=manifest.portfolio,
        snapshot=manifest.snapshot,
        evidence=evidence,
        metric_set=manifest.metric_set,
        output_artifacts=manifest.output_artifacts,
        created_at=NOW,
    )
    assert replay.decision is ResultMaterializationDecision.REPLAY_EXISTING
    changed = await adapter.materialize(
        principal="owner-a",
        trial=manifest.trial,
        attempt=manifest.attempt,
        strategy_packages=manifest.strategy_packages,
        portfolio=manifest.portfolio,
        snapshot=manifest.snapshot,
        evidence=evidence,
        metric_set=manifest.metric_set,
        output_artifacts=manifest.output_artifacts,
        created_at=NOW + timedelta(seconds=1),
    )
    assert changed.decision is ResultMaterializationDecision.CONFLICT


@pytest.mark.asyncio
async def test_result_manifest_adapter_authenticates_tampered_rows() -> None:
    manifest, _ = _inputs()
    session = FakeSession()
    adapter = PostgresResultMaterializationAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", manifest=manifest)
    session.manifests[("owner-a", manifest.attempt_id)]["record_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", attempt_id=manifest.attempt_id)


def test_result_materialization_schema_is_explicit_and_validated() -> None:
    schema = PostgresResultMaterializationSchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, attempt_id)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresResultMaterializationSchema(manifest_table="unsafe;drop")
