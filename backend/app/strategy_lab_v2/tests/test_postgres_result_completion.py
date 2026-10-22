from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_result_completion import (
    PostgresResultCompletionAdapter,
    PostgresResultCompletionSchema,
)
from app.strategy_lab_v2.result_completion import ResultCompletionDecision, ResultCompletionLedger
from app.strategy_lab_v2.tests.test_artifact_commit import _plan as artifact_plan
from app.strategy_lab_v2.tests.test_result_completion import _fixture

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
        self.completions: dict[tuple[str, str], dict[str, Any]] = {}
        self.commits: dict[str, dict[str, Any]] = {}

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
                for (owner, _), row in self.completions.items()
                if owner == values["owner_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["completion_fingerprint"]))
        if normalized.startswith("SELECT commit_key"):
            return FakeResult(sorted(self.commits.values(), key=lambda row: row["commit_key"]))
        if normalized.startswith("INSERT INTO") and "result_completions" in sql:
            key = (values["owner_id"], values["attempt_id"])
            if key in self.completions:
                return FakeResult(rowcount=0)
            self.completions[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO") and "artifact_commits" in sql:
            key = values["commit_key"]
            if key in self.commits or any(
                row["storage_key"] == values["storage_key"] for row in self.commits.values()
            ):
                return FakeResult(rowcount=0)
            self.commits[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_result_completion_adapter_commits_all_artifacts_and_replays() -> None:
    submission, outcome, progress, runtime, publication = _fixture()
    session = FakeSession()
    adapter = PostgresResultCompletionAdapter(lambda: session)
    plans = (artifact_plan(b"one"), artifact_plan(b"two"))

    first = await adapter.finalize(
        principal="owner-a",
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=3),
    )
    assert first.decision is ResultCompletionDecision.COMPLETE
    assert first.record is not None
    assert len(session.commits) == 2
    replay = await adapter.finalize(
        principal="owner-a",
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=4),
    )
    assert replay.decision is ResultCompletionDecision.REPLAY_EXISTING
    assert replay.record == first.record
    assert (await adapter.load_completion_ledger(principal="owner-a")).records == (first.record,)
    assert (await adapter.load_artifact_commit_ledger()).records == first.artifact_commit_ledger.records
    assert await adapter.load_completion_ledger(principal="owner-b") == ResultCompletionLedger()


@pytest.mark.asyncio
async def test_result_completion_adapter_rolls_back_on_artifact_conflict() -> None:
    submission, outcome, progress, runtime, publication = _fixture()
    session = FakeSession()
    adapter = PostgresResultCompletionAdapter(lambda: session)
    first = artifact_plan(b"one")
    conflicting = replace(first, manifest_fingerprint=content_digest("different-manifest"))
    resolution = await adapter.finalize(
        principal="owner-a",
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=(first, conflicting),
        completed_at=NOW + timedelta(seconds=3),
    )
    assert resolution.decision is ResultCompletionDecision.CONFLICT
    assert resolution.artifact_commit_ledger.records == ()
    assert not session.commits
    assert not session.completions


@pytest.mark.asyncio
async def test_result_completion_adapter_scopes_and_authenticates_rows() -> None:
    submission, outcome, progress, runtime, publication = _fixture()
    session = FakeSession()
    adapter = PostgresResultCompletionAdapter(lambda: session)
    completed = await adapter.finalize(
        principal="owner-a",
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=(artifact_plan(),),
        completed_at=NOW + timedelta(seconds=3),
    )
    assert completed.record is not None
    assert await adapter.load_completion_ledger(principal="owner-b") == ResultCompletionLedger()
    key = ("owner-a", completed.record.attempt_id)
    session.completions[key]["record_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_completion_ledger(principal="owner-a")


def test_result_completion_schema_is_explicit_and_validated() -> None:
    schema = PostgresResultCompletionSchema()
    assert len(schema.statements) == 2
    assert "PRIMARY KEY (owner_id, attempt_id)" in schema.statements[0]
    assert "CREATE TABLE strategy_lab_v2_artifact_commits" in schema.statements[1]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresResultCompletionSchema(commit_table="unsafe;drop")
