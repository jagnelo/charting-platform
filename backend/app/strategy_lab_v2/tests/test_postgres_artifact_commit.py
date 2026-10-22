from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.artifact_commit import ArtifactCommitDecision
from app.strategy_lab_v2.artifact_publication import plan_artifact_publication
from app.strategy_lab_v2.artifacts import artifact_content_digest, verify_artifact_payload
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.postgres_artifact_commit import (
    PostgresArtifactCommitAdapter,
    PostgresArtifactCommitSchema,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


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
        self.records: dict[str, dict[str, Any]] = {}

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
        if normalized.startswith("SELECT commit_key"):
            return FakeResult(sorted(self.records.values(), key=lambda row: row["commit_key"]))
        if normalized.startswith("INSERT INTO"):
            key = values["commit_key"]
            if key in self.records or any(
                row["storage_key"] == values["storage_key"] for row in self.records.values()
            ):
                return FakeResult(rowcount=0)
            self.records[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _plan(payload: bytes = b"artifact", *, already_present: bool = False):
    digest = artifact_content_digest(payload)
    manifest = ArtifactManifest(
        content_digest=digest,
        byte_length=len(payload),
        media_type="application/octet-stream",
        schema_version="v1",
        storage_key=digest,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    receipt = verify_artifact_payload(manifest, payload)
    return plan_artifact_publication(manifest, receipt, already_present=already_present)


@pytest.mark.asyncio
async def test_artifact_commit_adapter_commits_and_replays_exactly() -> None:
    session = FakeSession()
    adapter = PostgresArtifactCommitAdapter(lambda: session)
    plan = _plan()
    committed = await adapter.finalize(plan, committed_at=NOW)
    assert committed.decision is ArtifactCommitDecision.COMMIT
    assert committed.record is not None
    replay = await adapter.finalize(plan, committed_at=NOW + timedelta(days=1))
    assert replay.decision is ArtifactCommitDecision.REPLAY_EXISTING
    assert replay.record == committed.record
    assert (await adapter.load_ledger()).records == (committed.record,)


@pytest.mark.asyncio
async def test_artifact_commit_adapter_preserves_storage_collision_and_reuse_rejection() -> None:
    session = FakeSession()
    adapter = PostgresArtifactCommitAdapter(lambda: session)
    first = await adapter.finalize(_plan(), committed_at=NOW)
    assert first.record is not None
    changed = replace(
        _plan(),
        manifest_fingerprint=content_digest({"different": "manifest"}),
    )
    collision = await adapter.finalize(changed, committed_at=NOW)
    assert collision.decision is ArtifactCommitDecision.CONFLICT
    fresh = PostgresArtifactCommitAdapter(lambda: FakeSession())
    rejected = await fresh.finalize(_plan(already_present=True), committed_at=NOW)
    assert rejected.decision is ArtifactCommitDecision.REJECT


@pytest.mark.asyncio
async def test_artifact_commit_adapter_rejects_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresArtifactCommitAdapter(lambda: session)
    committed = await adapter.finalize(_plan(), committed_at=NOW)
    assert committed.record is not None
    session.records[committed.record.commit_key]["record_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_ledger()


def test_artifact_commit_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresArtifactCommitSchema()
    assert len(schema.statements) == 1
    assert "UNIQUE" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresArtifactCommitSchema(commit_table="unsafe;drop")
