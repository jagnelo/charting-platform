from __future__ import annotations

from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_snapshot_coverage import (
    PostgresSnapshotCoverageAdapter,
    PostgresSnapshotCoverageSchema,
    SnapshotCoverageStateDecision,
)
from app.strategy_lab_v2.tests.test_snapshot_coverage import _snapshot_and_attestation


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
        self.resolutions: dict[tuple[str, str], dict[str, Any]] = {}

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
                for (owner, snapshot), row in self.resolutions.items()
                if owner == values["owner_id"]
                and values.get("snapshot_fingerprint", snapshot) == snapshot
            ]
            return FakeResult(sorted(rows, key=lambda row: row["snapshot_fingerprint"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["snapshot_fingerprint"])
            if key in self.resolutions:
                return FakeResult(rowcount=0)
            self.resolutions[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_snapshot_coverage_adapter_registers_replays_and_scopes() -> None:
    snapshot, attestation = _snapshot_and_attestation()
    resolution = __import__(
        "app.strategy_lab_v2.snapshot_coverage", fromlist=["verify_snapshot_coverage"]
    ).verify_snapshot_coverage(snapshot, (attestation,))
    session = FakeSession()
    adapter = PostgresSnapshotCoverageAdapter(lambda: session)
    registered = await adapter.ensure(principal="owner-a", resolution=resolution)
    assert registered.decision is SnapshotCoverageStateDecision.REGISTERED
    replay = await adapter.ensure(principal="owner-a", resolution=resolution)
    assert replay.decision is SnapshotCoverageStateDecision.REPLAY_EXISTING
    assert await adapter.load(principal="owner-a", snapshot_fingerprint=snapshot.fingerprint) == resolution
    assert await adapter.load_all(principal="owner-b") == ()


@pytest.mark.asyncio
async def test_snapshot_coverage_adapter_preserves_rejected_reason_and_conflicts() -> None:
    snapshot, _ = _snapshot_and_attestation()
    from app.strategy_lab_v2.snapshot_coverage import verify_snapshot_coverage

    resolution = verify_snapshot_coverage(snapshot, ())
    session = FakeSession()
    adapter = PostgresSnapshotCoverageAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", resolution=resolution)
    loaded = await adapter.load(principal="owner-a", snapshot_fingerprint=snapshot.fingerprint)
    assert loaded is not None
    assert loaded.rejection_reason
    changed = type(resolution)(
        resolution.decision,
        resolution.snapshot_fingerprint,
        resolution.reports,
        resolution.missing_series_digests,
        resolution.unexpected_series_digests,
        "different reason",
    )
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure(principal="owner-a", resolution=changed)


@pytest.mark.asyncio
async def test_snapshot_coverage_adapter_rejects_tampered_rows() -> None:
    snapshot, attestation = _snapshot_and_attestation()
    from app.strategy_lab_v2.snapshot_coverage import verify_snapshot_coverage

    resolution = verify_snapshot_coverage(snapshot, (attestation,))
    session = FakeSession()
    adapter = PostgresSnapshotCoverageAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", resolution=resolution)
    session.resolutions[("owner-a", snapshot.fingerprint)]["resolution_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", snapshot_fingerprint=snapshot.fingerprint)


def test_snapshot_coverage_schema_is_explicit_and_validated() -> None:
    schema = PostgresSnapshotCoverageSchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, snapshot_fingerprint)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresSnapshotCoverageSchema(resolution_table="unsafe;drop")
