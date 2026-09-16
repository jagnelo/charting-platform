from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.artifact_retention import (
    ArtifactRetentionPin,
    ArtifactRetentionState,
    RetentionDecision,
    RetentionPinDecision,
)
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.postgres_artifact_retention import (
    PostgresArtifactRetentionAdapter,
    PostgresArtifactRetentionSchema,
    RetentionStateDecision,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
PAYLOAD = b"artifact"
MANIFEST = ArtifactManifest(
    content_digest=artifact_content_digest(PAYLOAD),
    byte_length=len(PAYLOAD),
    media_type="application/octet-stream",
    schema_version="v1",
    storage_key=artifact_content_digest(PAYLOAD),
    retention_class=ArtifactRetention.PINNED_RESULT,
)
MANIFEST_FINGERPRINT = content_digest(MANIFEST)


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
        self.states: dict[str, dict[str, Any]] = {}
        self.pins: dict[str, dict[str, Any]] = {}

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
        if normalized.startswith("SELECT manifest_fingerprint"):
            row = self.states.get(values["manifest_fingerprint"])
            return FakeResult([] if row is None else [row])
        if normalized.startswith("SELECT pin_id"):
            rows = [
                row
                for row in self.pins.values()
                if row["manifest_fingerprint"] == values["manifest_fingerprint"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["pin_id"]))
        if normalized.startswith("INSERT INTO") and "state_fingerprint" in sql:
            key = values["manifest_fingerprint"]
            if key in self.states:
                return FakeResult(rowcount=0)
            self.states[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO") and "pin_fingerprint" in sql:
            key = values["pin_id"]
            if key in self.pins:
                return FakeResult(rowcount=0)
            self.pins[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "pin_fingerprint" in sql:
            row = self.pins.get(values["pin_id"])
            if row is None or row["manifest_fingerprint"] != values["manifest_fingerprint"]:
                return FakeResult(rowcount=0)
            if row["pin_fingerprint"] != values["expected_fingerprint"]:
                return FakeResult(rowcount=0)
            row.update(
                released_at=values["released_at"],
                pin_fingerprint=values["next_fingerprint"],
            )
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "state_fingerprint" in sql:
            row = self.states.get(values["manifest_fingerprint"])
            if row is None or row["state_fingerprint"] != values["expected_fingerprint"]:
                return FakeResult(rowcount=0)
            row["state_fingerprint"] = values["next_fingerprint"]
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _state() -> ArtifactRetentionState:
    return ArtifactRetentionState.from_manifest(MANIFEST)


def _pin(value: str) -> ArtifactRetentionPin:
    return ArtifactRetentionPin(
        pin_id=content_digest({"pin": value}),
        artifact_manifest_fingerprint=MANIFEST_FINGERPRINT,
        owner_type="experiment",
        owner_id="experiment-1",
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_retention_adapter_registers_pins_releases_and_resolves() -> None:
    session = FakeSession()
    adapter = PostgresArtifactRetentionAdapter(lambda: session)
    state = _state()
    registered = await adapter.ensure_state(state)
    assert registered.decision is RetentionStateDecision.REGISTERED
    assert (
        await adapter.resolve(manifest_fingerprint=MANIFEST_FINGERPRINT, observed_at=NOW)
    ).decision is RetentionDecision.PIN_REQUIRED

    pin = _pin("one")
    added = await adapter.add_pin(pin)
    assert added.decision is RetentionPinDecision.ADD
    replay = await adapter.add_pin(pin)
    assert replay.decision is RetentionPinDecision.REPLAY_EXISTING
    retained = await adapter.resolve(
        manifest_fingerprint=MANIFEST_FINGERPRINT,
        observed_at=NOW,
    )
    assert retained.decision is RetentionDecision.RETAIN_PINNED
    assert retained.active_pin_ids == (pin.pin_id,)

    released = await adapter.release_pin(
        manifest_fingerprint=MANIFEST_FINGERPRINT,
        pin_id=pin.pin_id,
        released_at=NOW + timedelta(hours=1),
    )
    assert released.pins[0].released_at == NOW + timedelta(hours=1)
    assert await adapter.release_pin(
        manifest_fingerprint=MANIFEST_FINGERPRINT,
        pin_id=pin.pin_id,
        released_at=NOW + timedelta(hours=2),
    ) == released
    assert (
        await adapter.resolve(
            manifest_fingerprint=MANIFEST_FINGERPRINT,
            observed_at=NOW + timedelta(hours=1),
        )
    ).decision is RetentionDecision.PIN_REQUIRED


@pytest.mark.asyncio
async def test_retention_adapter_preserves_initial_pins_and_rejects_conflicts() -> None:
    session = FakeSession()
    adapter = PostgresArtifactRetentionAdapter(lambda: session)
    pin = _pin("initial")
    initial = ArtifactRetentionState.from_manifest(MANIFEST, pins=(pin,))
    await adapter.ensure_state(initial)
    assert (await adapter.read_state(MANIFEST_FINGERPRINT)) == initial
    changed = ArtifactRetentionPin(
        pin.pin_id,
        pin.artifact_manifest_fingerprint,
        pin.owner_type,
        "different-owner",
        pin.created_at,
    )
    conflict = await adapter.add_pin(changed)
    assert conflict.decision is RetentionPinDecision.CONFLICT


@pytest.mark.asyncio
async def test_retention_adapter_rejects_tampered_state_and_pin_rows() -> None:
    session = FakeSession()
    adapter = PostgresArtifactRetentionAdapter(lambda: session)
    await adapter.ensure_state(_state())
    session.states[MANIFEST_FINGERPRINT]["state_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="state fingerprint"):
        await adapter.read_state(MANIFEST_FINGERPRINT)

    session = FakeSession()
    adapter = PostgresArtifactRetentionAdapter(lambda: session)
    await adapter.ensure_state(_state())
    pin = _pin("one")
    await adapter.add_pin(pin)
    session.pins[pin.pin_id]["pin_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="pin fingerprint"):
        await adapter.read_state(MANIFEST_FINGERPRINT)


def test_retention_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresArtifactRetentionSchema()
    assert len(schema.statements) == 2
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresArtifactRetentionSchema(pin_table="unsafe;drop")
