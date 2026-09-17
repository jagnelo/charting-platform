from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.data_acquisition import DataAcquisitionReceipt
from app.strategy_lab_v2.postgres_acquisition import (
    AcquisitionStateDecision,
    PostgresAcquisitionAdapter,
    PostgresAcquisitionSchema,
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
        self.receipts: dict[tuple[str, str], dict[str, Any]] = {}

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
                for (owner, request), row in self.receipts.items()
                if owner == values["owner_id"]
                and values.get("request_fingerprint", request) == request
            ]
            return FakeResult(sorted(rows, key=lambda row: row["request_fingerprint"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["request_fingerprint"])
            if key in self.receipts:
                return FakeResult(rowcount=0)
            self.receipts[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _receipt(*, snapshot: str = "snapshot", provider: str = "provider") -> DataAcquisitionReceipt:
    return DataAcquisitionReceipt(
        content_digest("request"),
        content_digest(snapshot),
        "snapshot-1",
        provider,
        content_digest("coverage"),
        content_digest("provider-receipt"),
        NOW,
    )


@pytest.mark.asyncio
async def test_acquisition_adapter_registers_replays_and_scopes_receipts() -> None:
    session = FakeSession()
    adapter = PostgresAcquisitionAdapter(lambda: session)
    receipt = _receipt()
    registered = await adapter.ensure(principal="owner-a", receipt=receipt)
    assert registered.decision is AcquisitionStateDecision.REGISTERED
    replay = await adapter.ensure(principal="owner-a", receipt=receipt)
    assert replay.decision is AcquisitionStateDecision.REPLAY_EXISTING
    assert await adapter.load(principal="owner-a", request_fingerprint=receipt.request_fingerprint) == receipt
    assert await adapter.load_all(principal="owner-b") == ()


@pytest.mark.asyncio
async def test_acquisition_adapter_conflicts_on_changed_handoff() -> None:
    session = FakeSession()
    adapter = PostgresAcquisitionAdapter(lambda: session)
    receipt = _receipt()
    await adapter.ensure(principal="owner-a", receipt=receipt)
    changed = DataAcquisitionReceipt(
        receipt.request_fingerprint,
        content_digest("different-snapshot"),
        receipt.snapshot_id,
        receipt.provider_snapshot_id,
        receipt.coverage_resolution_fingerprint,
        receipt.provider_receipt_digest,
        receipt.acquired_at,
    )
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure(principal="owner-a", receipt=changed)


@pytest.mark.asyncio
async def test_acquisition_adapter_rejects_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresAcquisitionAdapter(lambda: session)
    receipt = _receipt()
    await adapter.ensure(principal="owner-a", receipt=receipt)
    session.receipts[("owner-a", receipt.request_fingerprint)]["receipt_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", request_fingerprint=receipt.request_fingerprint)


def test_acquisition_schema_is_explicit_and_identifiers_are_validated() -> None:
    schema = PostgresAcquisitionSchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, request_fingerprint)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresAcquisitionSchema(receipt_table="unsafe;drop")

