from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_runtime_receipts import (
    PostgresRuntimeReceiptAdapter,
    PostgresRuntimeReceiptSchema,
    RuntimeReceiptDecision,
)
from app.strategy_lab_v2.runtime_execution import preflight_strategy_runtime
from app.strategy_lab_v2.tests.test_runtime_execution import _profile, _request


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
        self.requests: dict[tuple[str, str], dict[str, Any]] = {}
        self.preflights: dict[tuple[str, str], dict[str, Any]] = {}

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
        if normalized.startswith("SELECT owner_id") and "runtime_preflights" not in sql:
            rows = [
                row
                for (owner, fingerprint), row in self.requests.items()
                if owner == values["owner_id"]
                and (
                    row["attempt_id"] == values["fingerprint"]
                    if "attempt_id = :fingerprint" in sql
                    else fingerprint == values["fingerprint"]
                )
            ]
            return FakeResult(rows)
        if normalized.startswith("SELECT owner_id") and "runtime_preflights" in sql:
            rows = [
                row
                for (owner, fingerprint), row in self.preflights.items()
                if owner == values["owner_id"]
                and (
                    row["request_fingerprint"] == values["fingerprint"]
                    if "request_fingerprint = :fingerprint" in sql
                    else fingerprint == values["fingerprint"]
                )
            ]
            return FakeResult(rows)
        if normalized.startswith("INSERT INTO") and "runtime_requests" in sql:
            key = (values["owner_id"], values["request_fingerprint"])
            if key in self.requests:
                return FakeResult(rowcount=0)
            self.requests[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO") and "runtime_preflights" in sql:
            key = (values["owner_id"], values["preflight_fingerprint"])
            if key in self.preflights:
                return FakeResult(rowcount=0)
            self.preflights[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_runtime_receipt_adapter_registers_replays_and_scopes() -> None:
    profile = _profile()
    request = _request(profile)
    preflight = preflight_strategy_runtime(request, profile)
    session = FakeSession()
    adapter = PostgresRuntimeReceiptAdapter(lambda: session)
    request_registered = await adapter.ensure_request(principal="owner-a", request=request)
    assert request_registered.decision is RuntimeReceiptDecision.REGISTERED
    request_replay = await adapter.ensure_request(principal="owner-a", request=request)
    assert request_replay.decision is RuntimeReceiptDecision.REPLAY_EXISTING
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure_request(
            principal="owner-a",
            request=replace(request, source_digest=content_digest("different-source")),
        )
    assert await adapter.load_request(
        principal="owner-a", request_fingerprint=request.fingerprint
    ) == request_registered.receipt
    assert await adapter.load_request(
        principal="owner-b", request_fingerprint=request.fingerprint
    ) is None

    preflight_registered = await adapter.ensure_preflight(
        principal="owner-a", preflight=preflight
    )
    assert preflight_registered.decision is RuntimeReceiptDecision.REGISTERED
    preflight_replay = await adapter.ensure_preflight(
        principal="owner-a", preflight=preflight
    )
    assert preflight_replay.decision is RuntimeReceiptDecision.REPLAY_EXISTING
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure_preflight(
            principal="owner-a",
            preflight=replace(preflight, profile_fingerprint=content_digest("different-profile")),
        )
    assert await adapter.load_preflight(
        principal="owner-a", preflight_fingerprint=preflight.fingerprint
    ) == preflight_registered.receipt


@pytest.mark.asyncio
async def test_runtime_receipt_adapter_preserves_rejected_preflight_reasons() -> None:
    profile = _profile()
    request = _request(profile)
    rejected_profile = type(profile)(
        content_digest("image-rejected"),
        profile.runtime_abi,
        network_disabled=False,
    )
    rejected = preflight_strategy_runtime(request, rejected_profile)
    assert not rejected.accepted
    session = FakeSession()
    adapter = PostgresRuntimeReceiptAdapter(lambda: session)
    stored = await adapter.ensure_preflight(principal="owner-a", preflight=rejected)
    loaded = await adapter.load_preflight(
        principal="owner-a", preflight_fingerprint=rejected.fingerprint
    )
    assert stored.receipt == loaded
    assert loaded is not None
    assert "network_must_be_disabled" in loaded.rejection_reasons


@pytest.mark.asyncio
async def test_runtime_receipt_adapter_authenticates_tampered_payload_and_record() -> None:
    profile = _profile()
    request = _request(profile)
    preflight = preflight_strategy_runtime(request, profile)
    session = FakeSession()
    adapter = PostgresRuntimeReceiptAdapter(lambda: session)
    await adapter.ensure_request(principal="owner-a", request=request)
    session.requests[("owner-a", request.fingerprint)]["request_json"] = "tampered"
    with pytest.raises(ValueError, match="malformed"):
        await adapter.load_request(principal="owner-a", request_fingerprint=request.fingerprint)

    session = FakeSession()
    adapter = PostgresRuntimeReceiptAdapter(lambda: session)
    await adapter.ensure_preflight(principal="owner-a", preflight=preflight)
    session.preflights[("owner-a", preflight.fingerprint)]["record_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_preflight(
            principal="owner-a", preflight_fingerprint=preflight.fingerprint
        )


def test_runtime_receipt_schema_is_explicit_and_validated() -> None:
    schema = PostgresRuntimeReceiptSchema()
    assert len(schema.statements) == 2
    assert "UNIQUE (owner_id, attempt_id)" in schema.statements[0]
    assert "UNIQUE (owner_id, request_fingerprint)" in schema.statements[1]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresRuntimeReceiptSchema(request_table="unsafe;drop")
