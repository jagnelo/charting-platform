from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.legacy import (
    LegacyCompatibilityAssessment,
    LegacyImportDecision,
    LegacyImportRequest,
    LegacyRecordKind,
)
from app.strategy_lab_v2.postgres_legacy import (
    PostgresLegacyImportAdapter,
    PostgresLegacySchema,
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
        self.records: dict[tuple[str, str], dict[str, Any]] = {}

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
            owner_id = values["owner_id"]
            rows = [row for (owner, _), row in self.records.items() if owner == owner_id]
            return FakeResult(sorted(rows, key=lambda row: row["legacy_id"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["legacy_id"])
            if key in self.records:
                return FakeResult(rowcount=0)
            self.records[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _request(
    *,
    legacy_id: str = "legacy-1",
    kind: LegacyRecordKind = LegacyRecordKind.DEFINITION,
    payload: str = "payload",
    requested_at: datetime = NOW,
    preserve_original: bool = True,
) -> LegacyImportRequest:
    return LegacyImportRequest(
        content_digest({"request": legacy_id, "payload": payload}),
        legacy_id,
        kind,
        "legacy-v1",
        content_digest(payload),
        requested_at,
        preserve_original,
    )


def _assessment(
    *, supported: bool = True, mapping: str = "legacy-map.v1", notes: tuple[str, ...] = ("mapped",)
) -> LegacyCompatibilityAssessment:
    return LegacyCompatibilityAssessment(
        mapping,
        supported,
        content_digest("converted") if supported else None,
        notes,
    )


@pytest.mark.asyncio
async def test_legacy_adapter_persists_replays_and_scopes_registry() -> None:
    session = FakeSession()
    adapter = PostgresLegacyImportAdapter(lambda: session)
    request = _request()
    applied = await adapter.import_record(principal="owner-a", request=request, assessment=_assessment())
    assert applied.decision is LegacyImportDecision.ACCEPT
    replay = await adapter.import_record(
        principal="owner-a",
        request=_request(requested_at=NOW.replace(hour=1)),
        assessment=_assessment(),
    )
    assert replay.decision is LegacyImportDecision.REPLAY_EXISTING
    assert (await adapter.load_registry(principal="owner-a")).records == applied.registry.records
    assert (await adapter.load_registry(principal="owner-b")).records == ()


@pytest.mark.asyncio
async def test_unsupported_import_is_preserved_and_conflicts_do_not_mutate() -> None:
    session = FakeSession()
    adapter = PostgresLegacyImportAdapter(lambda: session)
    first = await adapter.import_record(
        principal="owner-a", request=_request(kind=LegacyRecordKind.RESULT), assessment=_assessment(supported=False)
    )
    assert first.decision is LegacyImportDecision.UNSUPPORTED
    before = dict(session.records)
    conflict = await adapter.import_record(
        principal="owner-a", request=_request(payload="changed"), assessment=_assessment()
    )
    assert conflict.decision is LegacyImportDecision.CONFLICT
    assert session.records == before


@pytest.mark.asyncio
async def test_legacy_adapter_rejects_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresLegacyImportAdapter(lambda: session)
    result = await adapter.import_record(
        principal="owner-a", request=_request(), assessment=_assessment()
    )
    legacy_id = result.report.original.legacy_id
    session.records[("owner-a", legacy_id)]["record_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_registry(principal="owner-a")


def test_legacy_schema_is_explicit_and_identifiers_are_validated() -> None:
    schema = PostgresLegacySchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, legacy_id)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresLegacySchema(import_table="unsafe;drop")

