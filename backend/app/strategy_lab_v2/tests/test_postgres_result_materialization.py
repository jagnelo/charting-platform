from __future__ import annotations

import hashlib
import json
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
from app.strategy_lab_v2.tests.test_result_materialization import (
    _inputs,
    _nautilus_oos_references,
)

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
                and (values.get("attempt_id") is None or attempt == values["attempt_id"])
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
    assert (
        await adapter.load_manifest(principal="owner-a", attempt_id=manifest.attempt_id) == manifest
    )
    assert await adapter.load(principal="owner-b", attempt_id=manifest.attempt_id) is None
    assert await adapter.load_all(principal="owner-a") == (registered.record,)
    assert await adapter.load_all_manifests(principal="owner-a") == (manifest,)
    artifacts = await adapter.load_artifacts(principal="owner-a")
    assert tuple(reference.artifact for reference in artifacts) == manifest.output_artifacts
    assert all(reference.manifest_fingerprint == manifest.fingerprint for reference in artifacts)
    assert await adapter.load_artifacts(principal="owner-b") == ()


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
async def test_nautilus_oos_materialization_persists_native_artifact_manifest(tmp_path) -> None:
    original, evidence = _inputs()
    equity_path = tmp_path / "account-equity.parquet"
    reports_path = tmp_path / "native-reports.parquet"
    equity_reference, expected_events, reports_reference = _nautilus_oos_references(
        original,
        equity_path,
        reports_path,
    )
    session = FakeSession()
    adapter = PostgresResultMaterializationAdapter(lambda: session)
    arguments = {
        "principal": "owner-a",
        "trial": original.trial,
        "attempt": original.attempt,
        "strategy_packages": original.strategy_packages,
        "portfolio": original.portfolio,
        "snapshot": original.snapshot,
        "evidence": evidence,
        "equity_reference": equity_reference,
        "equity_trace_path": equity_path,
        "equity_expected_events": expected_events,
        "native_reports_reference": reports_reference,
        "native_reports_path": reports_path,
        "output_artifacts": original.output_artifacts,
        "created_at": NOW,
    }

    materialized = await adapter.materialize_nautilus_oos(**arguments)
    assert materialized.decision is ResultMaterializationDecision.MATERIALIZE
    assert materialized.manifest is not None
    persisted = await adapter.load_manifest(
        principal="owner-a",
        attempt_id=original.attempt_id,
    )
    assert persisted == materialized.manifest
    assert equity_reference.artifact in persisted.output_artifacts
    assert reports_reference.artifact in persisted.output_artifacts

    replay = await adapter.materialize_nautilus_oos(
        **arguments,
        existing=persisted,
    )
    assert replay.decision is ResultMaterializationDecision.REPLAY_EXISTING
    assert replay.manifest == persisted


@pytest.mark.asyncio
async def test_result_manifest_adapter_authenticates_tampered_rows() -> None:
    manifest, _ = _inputs()
    session = FakeSession()
    adapter = PostgresResultMaterializationAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", manifest=manifest)
    session.manifests[("owner-a", manifest.attempt_id)]["record_fingerprint"] = content_digest(
        "tampered"
    )
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", attempt_id=manifest.attempt_id)


@pytest.mark.asyncio
async def test_result_manifest_adapter_rejects_authenticated_nested_tag_drift() -> None:
    manifest, _ = _inputs()
    session = FakeSession()
    adapter = PostgresResultMaterializationAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", manifest=manifest)
    row = session.manifests[("owner-a", manifest.attempt_id)]
    root = json.loads(row["manifest_json"])
    root_fields = {item[0]: item for item in root[2]}
    artifacts = root_fields["output_artifacts"][1]
    artifacts[1][0][2][0][1] = ["unsupported", "tampered"]
    payload = json.dumps(root, separators=(",", ":"), sort_keys=True)
    row["manifest_json"] = payload
    row["manifest_fingerprint"] = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    row["record_fingerprint"] = content_digest(
        {
            "attempt_id": row["attempt_id"],
            "manifest_fingerprint": row["manifest_fingerprint"],
            "manifest_json": payload,
            "metric_set_fingerprint": row["metric_set_fingerprint"],
            "snapshot_fingerprint": row["snapshot_fingerprint"],
            "trial_id": row["trial_id"],
        }
    )
    with pytest.raises(ValueError, match="payload is malformed"):
        await adapter.load_manifest(principal="owner-a", attempt_id=manifest.attempt_id)


@pytest.mark.asyncio
async def test_result_manifest_adapter_rejects_authenticated_noncanonical_order() -> None:
    manifest, _ = _inputs()
    session = FakeSession()
    adapter = PostgresResultMaterializationAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", manifest=manifest)
    row = session.manifests[("owner-a", manifest.attempt_id)]
    root = json.loads(row["manifest_json"])
    root[2] = list(reversed(root[2]))
    payload = json.dumps(root, separators=(",", ":"), sort_keys=True)
    row["manifest_json"] = payload
    row["manifest_fingerprint"] = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    row["record_fingerprint"] = content_digest(
        {
            "attempt_id": row["attempt_id"],
            "manifest_fingerprint": row["manifest_fingerprint"],
            "manifest_json": payload,
            "metric_set_fingerprint": row["metric_set_fingerprint"],
            "snapshot_fingerprint": row["snapshot_fingerprint"],
            "trial_id": row["trial_id"],
        }
    )
    with pytest.raises(ValueError, match="payload is malformed"):
        await adapter.load_manifest(principal="owner-a", attempt_id=manifest.attempt_id)


def test_result_materialization_schema_is_explicit_and_validated() -> None:
    schema = PostgresResultMaterializationSchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, attempt_id)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresResultMaterializationSchema(manifest_table="unsafe;drop")
