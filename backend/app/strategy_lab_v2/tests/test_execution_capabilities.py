from __future__ import annotations

from datetime import UTC, datetime

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    PreflightReport,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.execution_capabilities import (
    ExecutionCapabilityBinding,
    preflight_execution_capability,
)

START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2022, 1, 1, tzinfo=UTC)


def _report() -> PreflightReport:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=START,
        end=END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash-equity",
        corporate_action_semantics="split-adjusted-v1",
    )
    cell = CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=START,
        history_end=END,
        evidence_digest=content_digest("capability-evidence"),
    )
    return preflight_capabilities((requirement,), (cell,))


def _binding(*, authoritative: bool = False) -> ExecutionCapabilityBinding:
    return ExecutionCapabilityBinding(
        engine_name="nautilus",
        engine_version="2.0.0",
        engine_build_digest=content_digest("engine-build"),
        conformance_fingerprint=content_digest("conformance"),
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
        authoritative=authoritative,
    )


def test_execution_capability_preflight_binds_engine_and_data_evidence() -> None:
    decision = preflight_execution_capability(_report(), _binding(authoritative=True))

    assert decision.executable
    assert decision.can_publish_authoritative_results
    assert decision.gaps == ()


def test_execution_capability_preflight_fails_closed_on_engine_gaps() -> None:
    binding = ExecutionCapabilityBinding(
        engine_name="nautilus",
        engine_version="2.0.0",
        engine_build_digest=content_digest("engine-build"),
        conformance_fingerprint=content_digest("conformance"),
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"tick"}),
        account_models=frozenset({"margin"}),
        authoritative=True,
    )
    decision = preflight_execution_capability(_report(), binding)

    assert not decision.executable
    assert not decision.can_publish_authoritative_results
    assert decision.gaps == ("account_model:cash-equity", "execution_model:bar-close")


def test_non_authoritative_engine_is_executable_but_cannot_publish_authoritative_results() -> None:
    decision = preflight_execution_capability(_report(), _binding())

    assert decision.executable
    assert not decision.can_publish_authoritative_results
