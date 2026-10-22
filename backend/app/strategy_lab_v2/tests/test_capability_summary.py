from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    Degradation,
    preflight_capabilities,
)
from app.strategy_lab_v2.capability_summary import (
    CapabilitySummaryDecision,
    build_capability_summary,
)
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.execution_capabilities import (
    ExecutionCapabilityBinding,
    ExecutionCapabilityPreflight,
    preflight_execution_capability,
)

START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2022, 1, 1, tzinfo=UTC)


def _requirement(*, session: str = "regular") -> CapabilityRequirement:
    return CapabilityRequirement(
        "US.AAPL", ProductClass.EQUITY, EventGranularity.BAR, "ohlcv", "1d", START, END,
        AdjustmentMode.SPLIT_ADJUSTED, session, "consolidated", "bar-close", "cash-equity", "split-v1",
    )


def _cell() -> CapabilityCell:
    return CapabilityCell(
        "US.AAPL", ProductClass.EQUITY, frozenset({EventGranularity.BAR}), frozenset({"ohlcv"}),
        frozenset({"1d"}), frozenset({AdjustmentMode.SPLIT_ADJUSTED}), frozenset({"regular"}),
        frozenset({"consolidated"}), frozenset({"bar-close"}), frozenset({"cash-equity"}),
        frozenset({"split-v1"}), START, END, content_digest("coverage"),
    )


def _binding(*, authoritative: bool = True, execution_model: str = "bar-close") -> ExecutionCapabilityBinding:
    return ExecutionCapabilityBinding(
        "nautilus", "2.0.0", content_digest("engine"), content_digest("conformance"),
        frozenset({ProductClass.EQUITY}), frozenset({execution_model}), frozenset({"cash-equity"}), authoritative,
    )


def test_rigorous_capability_summary_is_publishable_and_ranking_eligible() -> None:
    report = preflight_capabilities((_requirement(),), (_cell(),))
    execution = preflight_execution_capability(report, _binding())
    summary = build_capability_summary(report, execution)
    assert summary.decision is CapabilitySummaryDecision.RIGOROUS
    assert summary.executable
    assert summary.ranking_eligible
    assert summary.can_publish_authoritative_results
    assert summary.data_gaps == ()
    assert summary.execution_gaps == ()


def test_engine_gaps_are_projected_and_block_execution_and_publication() -> None:
    report = preflight_capabilities((_requirement(),), (_cell(),))
    execution = preflight_execution_capability(report, _binding(execution_model="tick"))
    summary = build_capability_summary(report, execution)
    assert summary.decision is CapabilitySummaryDecision.UNSUPPORTED
    assert not summary.executable
    assert not summary.can_publish_authoritative_results
    assert summary.execution_gaps == ("execution_model:bar-close",)


def test_data_gaps_and_degradations_are_retained_without_ranking() -> None:
    requirement = _requirement(session="extended")
    degradation = (Degradation("US.AAPL", "session", "regular", "use regular-session evidence"),)
    report = preflight_capabilities(
        (requirement,), (_cell(),), allow_degraded=True, degradations=degradation
    )
    execution = preflight_execution_capability(report, _binding())
    summary = build_capability_summary(report, execution)
    assert summary.decision is CapabilitySummaryDecision.DEGRADED
    assert summary.executable
    assert not summary.ranking_eligible
    assert not summary.can_publish_authoritative_results
    assert summary.data_gaps == ("US.AAPL:session",)


def test_report_identity_mismatch_fails_closed() -> None:
    report = preflight_capabilities((_requirement(),), (_cell(),))
    execution = ExecutionCapabilityPreflight(
        report_fingerprint=content_digest("other-report"),
        binding_fingerprint=content_digest("binding"),
        classification=report.classification,
        gaps=(),
        authoritative=True,
    )
    with pytest.raises(ValueError, match="reference this data report"):
        build_capability_summary(report, execution)


def test_summary_contract_rejects_invalid_digest_and_flags() -> None:
    from app.strategy_lab_v2.capability_summary import CapabilitySummary

    with pytest.raises(ValueError, match="report_fingerprint"):
        CapabilitySummary(
            "bad", content_digest("binding"), CapabilitySummaryDecision.RIGOROUS,
            (), (), (), True, True, True, True,
        )
