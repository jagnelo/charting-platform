from __future__ import annotations

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore, PostgresStorageSchema
from app.strategy_lab_v2.storage import (
    AggregateKey,
    AggregateMutation,
    StorageTransactionDecision,
    StorageTransactionRequest,
)


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
        self.aggregates: dict[tuple[str, str], dict] = {}
        self.receipts: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_next_write = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        self.calls.append((sql, values))
        if sql.lstrip().startswith("SELECT aggregate_type") and "AND aggregate_id = :aggregate_id" in sql:
            key = (values["aggregate_type"], values["aggregate_id"])
            return FakeResult([] if key not in self.aggregates else [self.aggregates[key]])
        if sql.lstrip().startswith("SELECT aggregate_type") and "ORDER BY aggregate_id" in sql:
            aggregate_type = values["aggregate_type"]
            return FakeResult(
                [
                    row
                    for key, row in sorted(self.aggregates.items())
                    if key[0] == aggregate_type
                ]
            )
        if sql.lstrip().startswith("SELECT aggregate_type"):
            keys = {
                (values[name], values[name.replace("aggregate_type", "aggregate_id")])
                for name in values
                if name.startswith("aggregate_type_")
            }
            return FakeResult(
                [self.aggregates[key] for key in sorted(keys) if key in self.aggregates]
            )
        if sql.lstrip().startswith("SELECT request_id"):
            row = self.receipts.get(values["request_id"])
            return FakeResult([] if row is None else [row])
        if self.fail_next_write:
            self.fail_next_write = False
            return FakeResult(rowcount=0)
        if sql.lstrip().startswith("INSERT INTO") and "aggregate_type" in sql:
            key = (values["aggregate_type"], values["aggregate_id"])
            if key in self.aggregates:
                return FakeResult(rowcount=0)
            self.aggregates[key] = {
                "aggregate_type": key[0],
                "aggregate_id": key[1],
                "version": values["version"],
                "state_json": values["state_json"],
                "state_fingerprint": values["state_fingerprint"],
            }
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE"):
            key = (values["aggregate_type"], values["aggregate_id"])
            row = self.aggregates.get(key)
            if row is None or row["version"] != values["expected_version"] or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            row.update(
                version=values["next_version"],
                state_json=values["state_json"],
                state_fingerprint=values["next_state_fingerprint"],
            )
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "committed_json" in sql:
            if values["request_id"] in self.receipts:
                return FakeResult(rowcount=0)
            self.receipts[values["request_id"]] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _request(value: int = 1, *, request: str = "request", expected_version: int = 0, expected_state_fingerprint: str | None = None):
    return StorageTransactionRequest(
        content_digest(request),
        (
            AggregateMutation(
                AggregateKey("attempt", "attempt-1"),
                {"status": "queued", "value": value},
                expected_version,
                expected_state_fingerprint,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_postgres_store_applies_create_and_compare_set_update() -> None:
    session = FakeSession()
    store = PostgresAggregateStore(lambda: session)
    created = await store.apply(_request())
    assert created.decision is StorageTransactionDecision.APPLY
    assert created.receipt is not None
    current = created.aggregates[0]
    updated = await store.apply(
        _request(
            2,
            request="update",
            expected_version=current.version,
            expected_state_fingerprint=current.state_fingerprint,
        )
    )
    assert updated.decision is StorageTransactionDecision.APPLY
    assert updated.aggregates[0].version == 2
    assert updated.aggregates[0].state["value"] == 2


@pytest.mark.asyncio
async def test_exact_request_replays_receipt_without_writes() -> None:
    session = FakeSession()
    store = PostgresAggregateStore(lambda: session)
    request = _request()
    first = await store.apply(request)
    calls = len(session.calls)
    replay = await store.apply(request)
    assert replay.decision is StorageTransactionDecision.REPLAY_EXISTING
    assert replay.receipt == first.receipt
    assert len(session.calls) == calls + 2  # locked aggregate and receipt reads only


@pytest.mark.asyncio
async def test_compare_set_drift_and_write_race_preserve_current_state() -> None:
    session = FakeSession()
    store = PostgresAggregateStore(lambda: session)
    created = await store.apply(_request())
    current = created.aggregates[0]
    drift = await store.apply(
        _request(9, request="drift", expected_version=1, expected_state_fingerprint=content_digest({"wrong": True}))
    )
    assert drift.decision is StorageTransactionDecision.CONFLICT
    assert drift.aggregates[0] == current
    session.fail_next_write = True
    race = await store.apply(
        _request(3, request="race", expected_version=1, expected_state_fingerprint=current.state_fingerprint)
    )
    assert race.decision is StorageTransactionDecision.REJECT
    assert race.aggregates[0] == current


@pytest.mark.asyncio
async def test_canonical_state_round_trip_preserves_non_json_identity() -> None:
    session = FakeSession()
    store = PostgresAggregateStore(lambda: session)
    request = StorageTransactionRequest(
        content_digest("complex-request"),
        (
            AggregateMutation(
                AggregateKey("complex", "one"),
                {"tuple": (1, "two"), "nested": {"value": 3}, "none": None},
            ),
        ),
    )
    first = await store.apply(request)
    replay = await store.apply(request)
    assert replay.decision is StorageTransactionDecision.REPLAY_EXISTING
    assert first.receipt == replay.receipt
    assert replay.aggregates[0].state["tuple"] == (1, "two")
    assert replay.aggregates[0].state["none"] is None


def test_schema_is_explicit_but_never_applied_implicitly() -> None:
    schema = PostgresStorageSchema()
    assert schema.aggregate_table in schema.statements[0]
    assert schema.receipt_table in schema.statements[1]
    assert "CREATE TABLE" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresStorageSchema(aggregate_table="unsafe;drop")


@pytest.mark.asyncio
async def test_postgres_store_reads_one_and_deterministic_type_snapshot() -> None:
    session = FakeSession()
    store = PostgresAggregateStore(lambda: session)
    await store.apply(_request())

    found = await store.get(AggregateKey("attempt", "attempt-1"))
    assert found is not None
    assert found.key == AggregateKey("attempt", "attempt-1")
    assert found.state["value"] == 1
    assert await store.get(AggregateKey("attempt", "missing")) is None

    listed = await store.list_type("attempt")
    assert listed == (found,)
