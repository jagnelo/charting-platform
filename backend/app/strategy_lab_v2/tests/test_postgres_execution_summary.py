from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.execution_summary import build_execution_summary
from app.strategy_lab_v2.outcomes import OutcomeStatus, OutcomeUpdate, apply_outcome_update
from app.strategy_lab_v2.postgres_execution_summary import (
    ExecutionSummaryStateDecision,
    PostgresExecutionSummaryAdapter,
    PostgresExecutionSummarySchema,
)
from app.strategy_lab_v2.progress import (
    ExecutionProgressUpdate,
    ProgressPhase,
    apply_progress_update,
)
from app.strategy_lab_v2.tests.test_execution_summary import (
    _outcome,
    _progress,
    _publication,
    _receipt,
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
        self.summaries: dict[tuple[str, str], dict[str, Any]] = {}

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
        if normalized.startswith("SELECT"):
            rows = [
                row
                for (owner, _), row in self.summaries.items()
                if owner == values["owner_id"]
                and (
                    values.get("state_key") is None
                    or row["state_key"] == values["state_key"]
                )
                and (
                    values.get("submission_id") is None
                    or row["submission_id"] == values["submission_id"]
                )
                and (
                    values.get("attempt_id") is None
                    or row["attempt_id"] == values["attempt_id"]
                )
            ]
            if "ORDER BY updated_at DESC" in sql and "submission_id ASC" not in sql:
                rows.sort(
                    key=lambda row: (
                        row["updated_at"],
                        row["outcome_sequence"],
                        row["progress_sequence"],
                        row["summary_fingerprint"],
                    ),
                    reverse=True,
                )
            elif "ORDER BY outcome_sequence ASC" in sql:
                rows.sort(
                    key=lambda row: (
                        row["outcome_sequence"],
                        row["progress_sequence"],
                        row["updated_at"],
                        row["summary_fingerprint"],
                    )
                )
            else:
                rows.sort(
                    key=lambda row: (
                        row["submission_id"],
                        row["attempt_id"],
                        row["updated_at"],
                        row["outcome_sequence"],
                        row["progress_sequence"],
                        row["summary_fingerprint"],
                    ),
                    reverse=False,
                )
                if "updated_at DESC" in sql:
                    rows.sort(
                        key=lambda row: (
                            row["submission_id"],
                            row["attempt_id"],
                            row["updated_at"],
                            row["outcome_sequence"],
                            row["progress_sequence"],
                            row["summary_fingerprint"],
                        ),
                        reverse=True,
                    )
            return FakeResult(rows)
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["state_key"])
            if key in self.summaries:
                return FakeResult(rowcount=0)
            self.summaries[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _running_summary():
    return build_execution_summary(
        _receipt(),
        _outcome(OutcomeStatus.RUNNING),
        _progress(ProgressPhase.RUNNING, sequence=1),
    )


def _succeeded_summary():
    receipt = _receipt()
    running_outcome = _outcome(OutcomeStatus.RUNNING)
    succeeded_outcome = apply_outcome_update(
        running_outcome,
        OutcomeUpdate(
            running_outcome.submission_id,
            running_outcome.attempt_id,
            2,
            OutcomeStatus.SUCCEEDED,
            datetime(2024, 1, 1, 0, 0, 2, tzinfo=UTC),
            result_digest=content_digest("result"),
        ),
    ).state
    running_progress = _progress(ProgressPhase.RUNNING, sequence=1)
    succeeded_progress = apply_progress_update(
        running_progress,
        ExecutionProgressUpdate(
            running_progress.attempt_id,
            2,
            ProgressPhase.SUCCEEDED,
            10,
            10,
            datetime(2024, 1, 1, 0, 0, 2, tzinfo=UTC),
        ),
    )
    return build_execution_summary(
        receipt,
        succeeded_outcome,
        succeeded_progress,
        _publication(succeeded_outcome.result_digest or ""),
    )


@pytest.mark.asyncio
async def test_execution_summary_adapter_registers_replays_latest_and_scopes_owner() -> None:
    session = FakeSession()
    adapter = PostgresExecutionSummaryAdapter(lambda: session)
    running = _running_summary()
    succeeded = _succeeded_summary()

    registered = await adapter.ensure(principal="owner-a", summary=running)
    assert registered.decision is ExecutionSummaryStateDecision.REGISTERED
    replay = await adapter.ensure(principal="owner-a", summary=running)
    assert replay.decision is ExecutionSummaryStateDecision.REPLAY_EXISTING
    await adapter.ensure(principal="owner-a", summary=succeeded)

    assert await adapter.load(
        principal="owner-a", submission_id=running.submission_id, attempt_id=running.attempt_id
    ) == succeeded
    assert await adapter.load(
        principal="owner-b", submission_id=running.submission_id, attempt_id=running.attempt_id
    ) is None
    assert await adapter.load_all(principal="owner-b") == ()


@pytest.mark.asyncio
async def test_execution_summary_adapter_preserves_immutable_history_and_conflicts() -> None:
    session = FakeSession()
    adapter = PostgresExecutionSummaryAdapter(lambda: session)
    running = _running_summary()
    await adapter.ensure(principal="owner-a", summary=running)
    history = await adapter.load_history(
        principal="owner-a", submission_id=running.submission_id, attempt_id=running.attempt_id
    )
    assert history == (running,)

    changed = replace(running, operation="forward")
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure(principal="owner-a", summary=changed)


@pytest.mark.asyncio
async def test_execution_summary_adapter_rejects_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresExecutionSummaryAdapter(lambda: session)
    running = _running_summary()
    await adapter.ensure(principal="owner-a", summary=running)
    key = next(iter(session.summaries))
    session.summaries[key]["summary_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(
            principal="owner-a", submission_id=running.submission_id, attempt_id=running.attempt_id
        )


def test_execution_summary_schema_is_explicit_and_validated() -> None:
    schema = PostgresExecutionSummarySchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, state_key)" in schema.statements[0]
    assert "UNIQUE (owner_id, summary_fingerprint)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresExecutionSummarySchema(summary_table="unsafe;drop")
