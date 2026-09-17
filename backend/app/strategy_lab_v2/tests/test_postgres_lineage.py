from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.lineage import ArtifactLineageEntry, LineageDecision, LineageRole
from app.strategy_lab_v2.postgres_lineage import PostgresLineageAdapter, PostgresLineageSchema

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
MANIFEST = content_digest({"manifest": "one"})


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
        self.entries: dict[str, dict[str, Any]] = {}

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
        if normalized.startswith("SELECT semantic_key"):
            rows = [
                row
                for row in self.entries.values()
                if row["owner_type"] == values["owner_type"]
                and row["owner_id"] == values["owner_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["semantic_key"]))
        if normalized.startswith("INSERT INTO"):
            key = values["semantic_key"]
            if key in self.entries:
                return FakeResult(rowcount=0)
            self.entries[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _entry(value: str, *, owner_id: str = "experiment-1") -> ArtifactLineageEntry:
    return ArtifactLineageEntry(
        "experiment",
        owner_id,
        MANIFEST,
        LineageRole.OUTPUT_ARTIFACT,
        NOW,
    )


@pytest.mark.asyncio
async def test_lineage_adapter_appends_replays_and_scopes_owner() -> None:
    session = FakeSession()
    adapter = PostgresLineageAdapter(lambda: session)
    entry = _entry("one")
    appended = await adapter.append(entry)
    assert appended.decision is LineageDecision.APPEND
    replay = await adapter.append(entry)
    assert replay.decision is LineageDecision.REPLAY_EXISTING
    assert (await adapter.load_index(owner_type="experiment", owner_id="experiment-1")).entries == (
        entry,
    )
    assert (await adapter.load_index(owner_type="experiment", owner_id="other")).entries == ()


@pytest.mark.asyncio
async def test_lineage_adapter_conflicts_on_changed_semantic_content() -> None:
    session = FakeSession()
    adapter = PostgresLineageAdapter(lambda: session)
    first = _entry("one")
    await adapter.append(first)
    changed = ArtifactLineageEntry(
        first.owner_type,
        first.owner_id,
        first.artifact_manifest_fingerprint,
        first.role,
        NOW + timedelta(minutes=1),
    )
    conflict = await adapter.append(changed)
    assert conflict.decision is LineageDecision.CONFLICT


@pytest.mark.asyncio
async def test_lineage_adapter_rejects_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresLineageAdapter(lambda: session)
    entry = _entry("one")
    await adapter.append(entry)
    session.entries[entry.semantic_key]["entry_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_index(owner_type="experiment", owner_id="experiment-1")


def test_lineage_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresLineageSchema()
    assert len(schema.statements) == 1
    assert "UNIQUE" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresLineageSchema(lineage_table="unsafe;drop")
