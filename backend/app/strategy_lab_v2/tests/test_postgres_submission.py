from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.api_contracts import ApiErrorCode
from app.strategy_lab_v2.api_router import ApiAdapterError
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_submission import (
    PostgresSubmissionDispatchAdapter,
    PostgresSubmissionSchema,
)
from app.strategy_lab_v2.submissions import SubmissionDecision, SubmissionRequest

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


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
        self.submissions: dict[tuple[str, str], dict[str, Any]] = {}
        self.dispatches: dict[tuple[str, str], dict[str, Any]] = {}
        self.payloads: dict[str, dict[str, Any]] = {}
        self.outboxes: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        self.calls.append(sql)
        key = (values.get("owner_id", ""), values.get("idempotency_key", ""))
        if sql.lstrip().startswith("SELECT") and "submissions" in sql:
            row = self.submissions.get(key)
            return FakeResult([] if row is None else [row])
        if sql.lstrip().startswith("SELECT") and "dispatches" in sql:
            row = self.dispatches.get(key)
            return FakeResult([] if row is None else [row])
        if sql.lstrip().startswith("SELECT") and "dispatch_payloads" in sql:
            row = self.payloads.get(values["payload_digest"])
            return FakeResult([] if row is None else [row])
        if sql.lstrip().startswith("SELECT") and "execution_outbox" in sql:
            row = self.outboxes.get(values["request_id"])
            return FakeResult([] if row is None else [row])
        if sql.lstrip().startswith("INSERT") and "submissions" in sql:
            if key in self.submissions:
                return FakeResult(rowcount=0)
            self.submissions[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT") and "dispatches" in sql:
            if key in self.dispatches:
                return FakeResult(rowcount=0)
            self.dispatches[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT") and "dispatch_payloads" in sql:
            payload_digest = values["payload_digest"]
            if payload_digest in self.payloads:
                return FakeResult(rowcount=0)
            self.payloads[payload_digest] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT") and "execution_outbox" in sql:
            request_id = values["request_id"]
            if request_id in self.outboxes:
                return FakeResult(rowcount=0)
            self.outboxes[request_id] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _request(
    *,
    key: str = "submission-key",
    payload: dict[str, Any] | None = None,
) -> tuple[SubmissionRequest, dict[str, Any]]:
    body = payload or {"symbol": "AAPL", "side": "buy"}
    return (
        SubmissionRequest(
            idempotency_key=key,
            operation="backtest",
            attempt_id="attempt-1",
            payload_digest=content_digest(body),
            submitted_at=NOW,
        ),
        body,
    )


@pytest.mark.asyncio
async def test_submission_adapter_stages_receipt_and_dispatch_atomically() -> None:
    session = FakeSession()
    adapter = PostgresSubmissionDispatchAdapter(lambda: session, clock=lambda: NOW + timedelta(minutes=1))
    request, payload = _request()

    accepted = await adapter.submit(principal="alice", request=request, payload=payload)
    assert accepted.resolution.decision is SubmissionDecision.ACCEPT
    assert accepted.receipt.request == request
    assert len(session.submissions) == 1
    assert len(session.dispatches) == 1
    assert len(session.payloads) == 1
    assert len(session.outboxes) == 1

    calls = len(session.calls)
    replay = await adapter.submit(principal="alice", request=request, payload=payload)
    assert replay.resolution.decision is SubmissionDecision.REPLAY_EXISTING
    assert replay.receipt == accepted.receipt
    assert len(session.calls) == calls + 4  # submission, dispatch, payload, and outbox reads


@pytest.mark.asyncio
async def test_submission_adapter_repairs_missing_dispatch_and_scopes_owner() -> None:
    session = FakeSession()
    adapter = PostgresSubmissionDispatchAdapter(lambda: session, clock=lambda: NOW)
    request, payload = _request()
    await adapter.submit(principal="alice", request=request, payload=payload)
    del session.dispatches[("alice", request.idempotency_key)]

    repaired = await adapter.submit(principal="alice", request=request, payload=payload)
    assert repaired.resolution.decision is SubmissionDecision.REPLAY_EXISTING
    assert ("alice", request.idempotency_key) in session.dispatches

    del session.outboxes[next(iter(session.outboxes))]
    repaired_again = await adapter.submit(principal="alice", request=request, payload=payload)
    assert repaired_again.resolution.decision is SubmissionDecision.REPLAY_EXISTING
    assert len(session.outboxes) == 1

    del session.payloads[request.payload_digest]
    repaired_payload = await adapter.submit(principal="alice", request=request, payload=payload)
    assert repaired_payload.resolution.decision is SubmissionDecision.REPLAY_EXISTING
    assert request.payload_digest in session.payloads

    other_owner = await adapter.submit(principal="bob", request=request, payload=payload)
    assert other_owner.resolution.decision is SubmissionDecision.ACCEPT
    assert len(session.submissions) == 2


@pytest.mark.asyncio
async def test_submission_adapter_rejects_idempotency_and_payload_drift() -> None:
    session = FakeSession()
    adapter = PostgresSubmissionDispatchAdapter(lambda: session, clock=lambda: NOW)
    request, payload = _request()
    await adapter.submit(principal="alice", request=request, payload=payload)
    changed, changed_payload = _request(payload={"symbol": "MSFT", "side": "buy"})
    with pytest.raises(ApiAdapterError) as conflict:
        await adapter.submit(principal="alice", request=changed, payload=changed_payload)
    assert conflict.value.error.code is ApiErrorCode.IDEMPOTENCY_CONFLICT

    with pytest.raises(ApiAdapterError) as malformed:
        await adapter.submit(principal="alice", request=request, payload={"symbol": "MSFT"})
    assert malformed.value.error.code is ApiErrorCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_submission_adapter_fails_closed_on_tampered_row_or_principal() -> None:
    session = FakeSession()
    adapter = PostgresSubmissionDispatchAdapter(lambda: session, clock=lambda: NOW)
    request, payload = _request()
    await adapter.submit(principal="alice", request=request, payload=payload)
    session.submissions[("alice", request.idempotency_key)]["request_fingerprint"] = content_digest(
        "tampered"
    )
    with pytest.raises(ValueError, match="submission row is malformed"):
        await adapter.submit(principal="alice", request=request, payload=payload)
    session.payloads[request.payload_digest]["payload_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="dispatch payload row is malformed"):
        await adapter.load_payload(request.payload_digest)
    with pytest.raises(ApiAdapterError) as unauthorized:
        await adapter.submit(principal=object(), request=request, payload=payload)
    assert unauthorized.value.error.code is ApiErrorCode.AUTHORIZATION_REQUIRED


def test_submission_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresSubmissionSchema()
    assert "CREATE TABLE" in schema.statements[0]
    assert "CREATE TABLE" in schema.statements[1]
    assert "CREATE TABLE" in schema.statements[2]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresSubmissionSchema(dispatch_table="unsafe;drop")
