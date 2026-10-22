from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_worker_settlement import (
    PostgresWorkerSettlementAdapter,
    PostgresWorkerSettlementSchema,
    SettlementReceiptDecision,
)
from app.strategy_lab_v2.worker_settlement import WorkerSettlementRecord

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
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

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
                for (owner, _), row in self.rows.items()
                if owner == values["owner_id"]
                and ("attempt_id" not in values or row["attempt_id"] == values["attempt_id"])
            ]
            return FakeResult(sorted(rows, key=lambda row: row["settlement_fingerprint"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["settlement_fingerprint"])
            if any(
                owner == values["owner_id"] and row["attempt_id"] == values["attempt_id"]
                for (owner, _), row in self.rows.items()
            ):
                return FakeResult(rowcount=0)
            self.rows[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _record() -> WorkerSettlementRecord:
    return WorkerSettlementRecord(
        content_digest("settlement"),
        content_digest("admission"),
        content_digest("execution"),
        "attempt-1",
        content_digest("reservation"),
        "worker-1",
        content_digest("release-observation"),
        NOW,
    )


@pytest.mark.asyncio
async def test_worker_settlement_adapter_registers_replays_and_scopes() -> None:
    session = FakeSession()
    adapter = PostgresWorkerSettlementAdapter(lambda: session)
    record = _record()
    registered = await adapter.ensure(principal="owner-a", record=record)
    assert registered.decision is SettlementReceiptDecision.REGISTERED
    replay = await adapter.ensure(principal="owner-a", record=record)
    assert replay.decision is SettlementReceiptDecision.REPLAY_EXISTING
    assert (await adapter.load_ledger(principal="owner-a")).records == (record,)
    assert (await adapter.load_ledger(principal="owner-b")).records == ()


@pytest.mark.asyncio
async def test_worker_settlement_adapter_authenticates_rows() -> None:
    session = FakeSession()
    adapter = PostgresWorkerSettlementAdapter(lambda: session)
    record = _record()
    await adapter.ensure(principal="owner-a", record=record)
    session.rows[("owner-a", record.settlement_fingerprint)]["record_fingerprint"] = content_digest(
        "tampered"
    )
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_ledger(principal="owner-a")


def test_worker_settlement_schema_is_explicit_and_validated() -> None:
    schema = PostgresWorkerSettlementSchema()
    assert "PRIMARY KEY (owner_id, settlement_fingerprint)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresWorkerSettlementSchema(settlement_table="unsafe;drop")
