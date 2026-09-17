from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    Degradation,
    preflight_capabilities,
)
from app.strategy_lab_v2.capability_summary import build_capability_summary
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.execution_capabilities import (
    ExecutionCapabilityBinding,
    preflight_execution_capability,
)
from app.strategy_lab_v2.postgres_capability import (
    CapabilitySummaryStateDecision,
    PostgresCapabilityAdapter,
    PostgresCapabilitySchema,
)

START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2022, 1, 1, tzinfo=UTC)


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
        self.summaries: dict[tuple[str, str, str], dict[str, Any]] = {}

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
                for (owner, report, binding), row in self.summaries.items()
                if owner == values["owner_id"]
                and values.get("report_fingerprint", report) == report
                and values.get("binding_fingerprint", binding) == binding
            ]
            return FakeResult(
                sorted(rows, key=lambda row: (row["report_fingerprint"], row["binding_fingerprint"]))
            )
        if normalized.startswith("INSERT INTO"):
            key = (
                values["owner_id"],
                values["report_fingerprint"],
                values["binding_fingerprint"],
            )
            if key in self.summaries:
                return FakeResult(rowcount=0)
            self.summaries[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _summary(*, degraded: bool = False):
    requirement = CapabilityRequirement(
        "US.AAPL",
        ProductClass.EQUITY,
        EventGranularity.BAR,
        "ohlcv",
        "1d",
        START,
        END,
        AdjustmentMode.SPLIT_ADJUSTED,
        "extended" if degraded else "regular",
        "consolidated",
        "bar-close",
        "cash-equity",
        "split-v1",
    )
    cell = CapabilityCell(
        "US.AAPL",
        ProductClass.EQUITY,
        frozenset({EventGranularity.BAR}),
        frozenset({"ohlcv"}),
        frozenset({"1d"}),
        frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        frozenset({"regular"}),
        frozenset({"consolidated"}),
        frozenset({"bar-close"}),
        frozenset({"cash-equity"}),
        frozenset({"split-v1"}),
        START,
        END,
        content_digest("coverage"),
    )
    degradations = (
        Degradation("US.AAPL", "session", "regular", "use regular-session evidence"),
    ) if degraded else ()
    report = preflight_capabilities(
        (requirement,), (cell,), allow_degraded=degraded, degradations=degradations
    )
    execution = preflight_execution_capability(
        report,
        ExecutionCapabilityBinding(
            "nautilus",
            "2.0.0",
            content_digest("engine"),
            content_digest("conformance"),
            frozenset({ProductClass.EQUITY}),
            frozenset({"bar-close"}),
            frozenset({"cash-equity"}),
            True,
        ),
    )
    return build_capability_summary(report, execution)


@pytest.mark.asyncio
async def test_capability_adapter_registers_replays_and_scopes_summaries() -> None:
    session = FakeSession()
    adapter = PostgresCapabilityAdapter(lambda: session)
    summary = _summary()
    registered = await adapter.ensure(principal="owner-a", summary=summary)
    assert registered.decision is CapabilitySummaryStateDecision.REGISTERED
    replay = await adapter.ensure(principal="owner-a", summary=summary)
    assert replay.decision is CapabilitySummaryStateDecision.REPLAY_EXISTING
    assert await adapter.load(
        principal="owner-a",
        report_fingerprint=summary.report_fingerprint,
        binding_fingerprint=summary.binding_fingerprint,
    ) == summary
    assert await adapter.load_all(principal="owner-b") == ()


@pytest.mark.asyncio
async def test_capability_adapter_conflicts_on_changed_projection_identity() -> None:
    session = FakeSession()
    adapter = PostgresCapabilityAdapter(lambda: session)
    summary = _summary(degraded=True)
    await adapter.ensure(principal="owner-a", summary=summary)
    changed = replace(summary, data_gaps=("US.AAPL:foreign-gap",), ranking_eligible=False)
    with pytest.raises(ValueError, match="already bound"):
        await adapter.ensure(principal="owner-a", summary=changed)


@pytest.mark.asyncio
async def test_capability_adapter_rejects_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresCapabilityAdapter(lambda: session)
    summary = _summary()
    await adapter.ensure(principal="owner-a", summary=summary)
    session.summaries[("owner-a", summary.report_fingerprint, summary.binding_fingerprint)]["summary_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(
            principal="owner-a",
            report_fingerprint=summary.report_fingerprint,
            binding_fingerprint=summary.binding_fingerprint,
        )


def test_capability_schema_is_explicit_and_identifiers_are_validated() -> None:
    schema = PostgresCapabilitySchema()
    assert len(schema.statements) == 1
    assert "PRIMARY KEY (owner_id, report_fingerprint, binding_fingerprint)" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresCapabilitySchema(summary_table="unsafe;drop")

