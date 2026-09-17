from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.postgres_metrics import (
    MetricSetStateDecision,
    PostgresMetricsAdapter,
    PostgresMetricsSchema,
)
from app.strategy_lab_v2.tests.test_result_publication import _result


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
        self.metrics: dict[tuple[str, str], dict[str, Any]] = {}

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
            if "lookup_key" not in values:
                return FakeResult(
                    sorted(
                        [
                            row
                            for (owner, _), row in self.metrics.items()
                            if owner == values["owner_id"]
                        ],
                        key=lambda row: row["attempt_id"],
                    )
                )
            rows = [
                row
                for (owner, fingerprint), row in self.metrics.items()
                if owner == values["owner_id"]
                and (
                    row["attempt_id"] == values["lookup_key"]
                    if "attempt_id = :lookup_key" in sql
                    else fingerprint == values["lookup_key"]
                )
            ]
            return FakeResult(sorted(rows, key=lambda row: row["attempt_id"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["metric_set_fingerprint"])
            if key in self.metrics:
                return FakeResult(rowcount=0)
            self.metrics[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_metric_adapter_registers_replays_and_scopes_summary() -> None:
    manifest, *_ = _result()
    metric_set = manifest.metric_set
    session = FakeSession()
    adapter = PostgresMetricsAdapter(lambda: session)
    registered = await adapter.ensure(principal="owner-a", metric_set=metric_set)
    assert registered.decision is MetricSetStateDecision.REGISTERED
    assert registered.record.metric_set_json == canonical_json(metric_set)
    replay = await adapter.ensure(principal="owner-a", metric_set=metric_set)
    assert replay.decision is MetricSetStateDecision.REPLAY_EXISTING
    assert await adapter.load(
        principal="owner-a", metric_set_fingerprint=metric_set.fingerprint
    ) == registered.record
    assert await adapter.load_all(principal="owner-a") == (registered.record,)
    assert await adapter.load(
        principal="owner-b", metric_set_fingerprint=metric_set.fingerprint
    ) is None


@pytest.mark.asyncio
async def test_metric_adapter_conflicts_same_attempt_and_authenticates_rows() -> None:
    manifest, *_ = _result()
    metric_set = manifest.metric_set
    session = FakeSession()
    adapter = PostgresMetricsAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", metric_set=metric_set)
    changed = replace(metric_set, metric_set_id="different-id")
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure(principal="owner-a", metric_set=changed)
    session.metrics[("owner-a", metric_set.fingerprint)]["record_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", metric_set_fingerprint=metric_set.fingerprint)


def test_metrics_schema_is_explicit_and_validated() -> None:
    schema = PostgresMetricsSchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, metric_set_fingerprint)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresMetricsSchema(metric_table="unsafe;drop")
