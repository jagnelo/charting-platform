from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity
from app.strategy_lab_v2.coverage import CoverageAttestation
from app.strategy_lab_v2.postgres_coverage import (
    CoverageStateDecision,
    PostgresCoverageAdapter,
    PostgresCoverageSchema,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
END = NOW + timedelta(days=1)


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
        self.attestations: dict[tuple[str, str], dict[str, Any]] = {}

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
                for (owner, series), row in self.attestations.items()
                if owner == values["owner_id"]
                and values.get("series_content_digest", series) == series
            ]
            return FakeResult(sorted(rows, key=lambda row: row["series_content_digest"]))
        if normalized.startswith("INSERT INTO"):
            key = (values["owner_id"], values["series_content_digest"])
            if key in self.attestations:
                return FakeResult(rowcount=0)
            self.attestations[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _attestation(*, series: str = "series", instrument: str = "AAPL") -> CoverageAttestation:
    return CoverageAttestation(
        content_digest("evidence"),
        content_digest(series),
        instrument,
        "ohlcv",
        EventGranularity.BAR,
        "1d",
        "regular",
        "sip",
        AdjustmentMode.SPLIT_ADJUSTED,
        "split-only",
        NOW,
        END,
        100,
        content_digest("calendar"),
        True,
        True,
        "market-data-adapter",
        END,
    )


@pytest.mark.asyncio
async def test_coverage_adapter_registers_replays_and_scopes_attestations() -> None:
    session = FakeSession()
    adapter = PostgresCoverageAdapter(lambda: session)
    attestation = _attestation()
    registered = await adapter.ensure(principal="owner-a", attestation=attestation)
    assert registered.decision is CoverageStateDecision.REGISTERED
    replay = await adapter.ensure(principal="owner-a", attestation=attestation)
    assert replay.decision is CoverageStateDecision.REPLAY_EXISTING
    assert await adapter.load(principal="owner-a", series_content_digest=attestation.series_content_digest) == attestation
    assert await adapter.load(principal="owner-b", series_content_digest=attestation.series_content_digest) is None


@pytest.mark.asyncio
async def test_coverage_adapter_rejects_changed_identity_and_lists_deterministically() -> None:
    session = FakeSession()
    adapter = PostgresCoverageAdapter(lambda: session)
    first = _attestation(series="series-a")
    second = _attestation(series="series-b", instrument="MSFT")
    await adapter.ensure(principal="owner-a", attestation=second)
    await adapter.ensure(principal="owner-a", attestation=first)
    assert await adapter.load_all(principal="owner-a") == (first, second)
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure(
            principal="owner-a", attestation=_attestation(series="series-a", instrument="MSFT")
        )


@pytest.mark.asyncio
async def test_coverage_adapter_rejects_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresCoverageAdapter(lambda: session)
    attestation = _attestation()
    await adapter.ensure(principal="owner-a", attestation=attestation)
    session.attestations[("owner-a", attestation.series_content_digest)]["attestation_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", series_content_digest=attestation.series_content_digest)


def test_coverage_schema_is_explicit_and_identifiers_are_validated() -> None:
    schema = PostgresCoverageSchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, series_content_digest)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresCoverageSchema(attestation_table="unsafe;drop")
