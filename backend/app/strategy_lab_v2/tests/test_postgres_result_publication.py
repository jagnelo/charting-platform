from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_result_publication import (
    PostgresResultPublicationAdapter,
    PostgresResultPublicationSchema,
    PublicationStateDecision,
)
from app.strategy_lab_v2.result_publication import ResultPublicationDecision
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
        self.plans: dict[tuple[str, str], dict[str, Any]] = {}

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
                for (owner, _), row in self.plans.items()
                if owner == values["owner_id"]
                and (
                    values.get("publication_fingerprint") is None
                    or row["publication_fingerprint"] == values["publication_fingerprint"]
                )
                and (
                    values.get("attempt_id") is None
                    or row["attempt_id"] == values["attempt_id"]
                )
            ]
            return FakeResult(sorted(rows, key=lambda row: row["publication_fingerprint"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["publication_fingerprint"])
            if key in self.plans:
                return FakeResult(rowcount=0)
            self.plans[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_result_publication_adapter_registers_replays_and_scopes() -> None:
    result, evidence, conformance, runtime, integrity = _result()
    plan = __import__(
        "app.strategy_lab_v2.result_publication", fromlist=["plan_result_publication"]
    ).plan_result_publication(result, evidence, conformance, runtime, integrity)
    session = FakeSession()
    adapter = PostgresResultPublicationAdapter(lambda: session)
    registered = await adapter.ensure(principal="owner-a", plan=plan)
    assert registered.decision is PublicationStateDecision.REGISTERED
    replay = await adapter.ensure(principal="owner-a", plan=plan)
    assert replay.decision is PublicationStateDecision.REPLAY_EXISTING
    assert await adapter.load(principal="owner-a", publication_fingerprint=plan.fingerprint) == plan
    assert await adapter.load(principal="owner-b", publication_fingerprint=plan.fingerprint) is None
    assert await adapter.load_all(principal="owner-a") == (plan,)


@pytest.mark.asyncio
async def test_result_publication_adapter_preserves_rejected_plans_and_conflicts() -> None:
    result, evidence, conformance, runtime, integrity = _result()
    from app.strategy_lab_v2.result_publication import plan_result_publication

    plan = plan_result_publication(result, evidence, conformance, runtime, integrity)
    rejected = replace(
        plan,
        decision=ResultPublicationDecision.REJECT,
        rejection_reasons=("manual_gate",),
    )
    session = FakeSession()
    adapter = PostgresResultPublicationAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", plan=rejected)
    assert await adapter.load_for_attempt(principal="owner-a", attempt_id=plan.attempt_id) == (rejected,)
    changed = replace(rejected, rejection_reasons=("different_gate",))
    changed_result = await adapter.ensure(principal="owner-a", plan=changed)
    assert changed_result.decision is PublicationStateDecision.REGISTERED
    assert await adapter.load_for_attempt(
        principal="owner-a", attempt_id=plan.attempt_id
    ) == tuple(sorted((rejected, changed), key=lambda item: item.fingerprint))


@pytest.mark.asyncio
async def test_result_publication_adapter_rejects_tampered_rows() -> None:
    result, evidence, conformance, runtime, integrity = _result()
    from app.strategy_lab_v2.result_publication import plan_result_publication

    plan = plan_result_publication(result, evidence, conformance, runtime, integrity)
    session = FakeSession()
    adapter = PostgresResultPublicationAdapter(lambda: session)
    await adapter.ensure(principal="owner-a", plan=plan)
    session.plans[("owner-a", plan.fingerprint)]["engine_build_digest"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", publication_fingerprint=plan.fingerprint)


def test_result_publication_schema_is_explicit_and_validated() -> None:
    schema = PostgresResultPublicationSchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, publication_fingerprint)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresResultPublicationSchema(publication_table="unsafe;drop")
