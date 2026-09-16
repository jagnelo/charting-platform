from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    ArtifactManifest,
    AttemptState,
    DataSeriesManifest,
    DataSnapshot,
    EventGranularity,
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricSet,
    MetricValue,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    SensitivityComparisonEvidence,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
)
from app.strategy_lab_v2.sensitivity import (
    MetricDeltaUnavailable,
    MetricDeltaUnavailableReason,
    OneFactorMetricDelta,
    compare_one_factor_metric,
)

START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2021, 1, 1, tzinfo=UTC)
CREATED = datetime(2024, 1, 1, tzinfo=UTC)
METRIC_VERSION = "strategy-lab.metrics.test"
CALCULATION = MetricCalculationDefinition(
    formula_id="test.total-return",
    contract_version="test.v1",
    parameters={"window_start": "2020-01-01", "window_end": "2021-01-01"},
)


def _result_pair(
    *,
    baseline_parameters: dict[str, Any] | None = None,
    variant_parameters: dict[str, Any] | None = None,
    baseline_metrics: tuple[MetricValue, ...] | None = None,
    variant_metrics: tuple[MetricValue, ...] | None = None,
) -> SensitivityComparisonEvidence:
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
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
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
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=START,
        history_end=END,
        evidence_digest=content_digest({"capability": "test"}),
    )
    report = preflight_capabilities((requirement,), (cell,))
    series = DataSeriesManifest(
        instrument_id="US.AAPL",
        event_type="ohlcv",
        event_granularity=EventGranularity.BAR,
        timeframe="1d",
        session="regular",
        feed="consolidated",
        start=START,
        end=END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        corporate_action_semantics="split-adjusted-v1",
        coverage_evidence_digest=content_digest({"coverage": "test-claim"}),
        content_digest=content_digest({"bars": "test"}),
        row_count=252,
    )
    snapshot = DataSnapshot("snapshot", "provider-snapshot", report, (series,), CREATED)
    strategy = StrategyVersion("strategy", "v1", "2.0", content_digest("strategy-source"))
    portfolio = PortfolioComposition(
        "portfolio",
        "v1",
        Decimal("100000"),
        "USD",
        (PortfolioComponent("component", strategy.fingerprint, ("US.AAPL",), Decimal("1")),),
    )
    package = StrategyPackage(
        package_id="package",
        strategy_fingerprint=strategy.fingerprint,
        package_format=StrategyPackageFormat.SOURCE_ARCHIVE,
        archive_digest=content_digest("archive"),
        manifest_digest=content_digest("manifest"),
        dependency_lock_digest=content_digest("dependencies"),
        archive_byte_length=32,
        entrypoint="strategy.main:Strategy",
        sdk_version="2.0",
        runtime_abi="cpython-312",
    )
    experiment_fingerprint = content_digest("experiment")

    def build_result(
        *,
        parameters: dict[str, Any],
        attempt_id: str,
        metric_values: tuple[MetricValue, ...] | None,
        seed: int,
    ) -> RunResultManifest:
        trial = ScientificTrial.create(
            experiment_fingerprint=experiment_fingerprint,
            snapshot_fingerprint=snapshot.fingerprint,
            preflight_report=report,
            parameter_set=parameters,
            seed=seed,
        )
        attempt = RunAttempt(attempt_id, trial.trial_id, 1, AttemptState.SUCCEEDED, CREATED)
        metrics = (
            metric_values
            if metric_values is not None
            else (
                MetricValue(
                    "total_return",
                    Decimal("0.1"),
                    "fraction",
                    METRIC_VERSION,
                    MetricBasis.NET,
                    252,
                    calculation_definition=CALCULATION,
                    evidence_references=(
                        MetricEvidenceReference("session_calendar", content_digest("calendar")),
                        MetricEvidenceReference("calculator_input", content_digest(attempt_id)),
                    ),
                ),
            )
        )
        metric_set = MetricSet(
            f"metrics-{attempt_id}",
            trial.trial_id,
            attempt_id,
            METRIC_VERSION,
            metrics,
            CREATED,
        )
        output_digest = content_digest({"result": attempt_id})
        return RunResultManifest(
            trial=trial,
            attempt=attempt,
            strategy_packages=(package,),
            portfolio=portfolio,
            snapshot=snapshot,
            engine_name="test-engine",
            engine_version="1.0",
            engine_build_digest=content_digest("engine-build"),
            allocation_definition_version="allocation.v1",
            dependency_catalog_digest=content_digest("dependency-catalog"),
            assumptions_digest=content_digest("assumptions"),
            metric_set=metric_set,
            output_artifacts=(
                ArtifactManifest(
                    output_digest,
                    32,
                    "application/octet-stream",
                    "1",
                    output_digest,
                ),
            ),
            created_at=CREATED,
        )

    baseline = build_result(
        parameters=({"lookback": 20} if baseline_parameters is None else baseline_parameters),
        attempt_id="attempt-baseline",
        metric_values=baseline_metrics,
        seed=1,
    )
    variant = build_result(
        parameters=({"lookback": 30} if variant_parameters is None else variant_parameters),
        attempt_id="attempt-variant",
        metric_values=variant_metrics,
        seed=2,
    )
    return SensitivityComparisonEvidence(baseline, variant)


def _metric(
    value: Decimal | None,
    *,
    sample_size: int = 252,
    calculation: MetricCalculationDefinition | None = CALCULATION,
    basis: MetricBasis = MetricBasis.NET,
    name: str = "total_return",
    null_reason: str | None = None,
    calendar_digest: str | None = "calendar",
    input_digest: str = "input",
) -> MetricValue:
    references = [MetricEvidenceReference("calculator_input", content_digest(input_digest))]
    if calendar_digest is not None:
        references.append(
            MetricEvidenceReference("session_calendar", content_digest(calendar_digest))
        )
    return MetricValue(
        name=name,
        value=value,
        unit="fraction",
        definition_version=METRIC_VERSION,
        basis=basis,
        sample_size=sample_size,
        null_reason=null_reason,
        calculation_definition=calculation,
        evidence_references=tuple(references),
    )


def _compare(evidence: SensitivityComparisonEvidence):
    return compare_one_factor_metric(evidence, metric_name="total_return", basis=MetricBasis.NET)


def test_one_factor_delta_is_signed_scoped_and_preserves_realized_sample_sizes() -> None:
    evidence = _result_pair(
        baseline_metrics=(
            _metric(Decimal("0.15"), sample_size=252, input_digest="baseline-input"),
            _metric(Decimal("4"), name="trade_count", input_digest="baseline-trades"),
        ),
        variant_metrics=(
            _metric(Decimal("4"), name="trade_count", input_digest="variant-trades"),
            _metric(Decimal("0.10"), sample_size=173, input_digest="variant-input"),
        ),
    )

    result = _compare(evidence)

    assert isinstance(result, OneFactorMetricDelta)
    assert result.delta == Decimal("-0.05")
    assert result.parameter_change.name == "lookback"
    assert (result.parameter_change.baseline_value, result.parameter_change.variant_value) == (
        20,
        30,
    )
    assert (result.baseline_sample_size, result.variant_sample_size) == (252, 173)
    assert result.baseline_attempt_id == "attempt-baseline"
    assert result.variant_attempt_id == "attempt-variant"
    assert result.evidence_level.value == "unpaired"
    assert result.measurement_scope.base_currency == "USD"
    assert result.measurement_scope.session_calendar_evidence_digests == (
        content_digest("calendar"),
    )
    assert result.measurement_scope.coverage_evidence_digests == (
        content_digest({"coverage": "test-claim"}),
    )
    mismatched_scope = replace(
        result.measurement_scope,
        metric_calculation_fingerprint=content_digest("different-calculation"),
    )
    with pytest.raises(ValueError, match="must bind the reported metric calculation"):
        replace(result, measurement_scope=mismatched_scope)


def test_delta_uses_the_platform_decimal_context_not_the_callers_context() -> None:
    evidence = _result_pair(
        baseline_metrics=(_metric(Decimal("1.0000000000000000000000000000000000")),),
        variant_metrics=(_metric(Decimal("1.0000000000000000000000000000000001")),),
    )

    with localcontext() as context:
        context.prec = 4
        result = _compare(evidence)

    assert isinstance(result, OneFactorMetricDelta)
    assert result.delta == Decimal("0.0000000000000000000000000000000001")


@pytest.mark.parametrize(
    ("baseline_parameters", "variant_parameters", "reason"),
    [
        ({"lookback": 20}, {"lookback": 30, "threshold": 0.5}, "parameter_keys_differ"),
        (
            {"lookback": 20, "threshold": 0.1},
            {"lookback": 30, "threshold": 0.2},
            "not_exactly_one_factor",
        ),
    ],
)
def test_parameter_scope_must_be_exactly_one_canonical_factor(
    baseline_parameters: dict[str, Any],
    variant_parameters: dict[str, Any],
    reason: str,
) -> None:
    result = _compare(
        _result_pair(
            baseline_parameters=baseline_parameters,
            variant_parameters=variant_parameters,
        )
    )

    assert isinstance(result, MetricDeltaUnavailable)
    assert result.reason.value == reason


def test_canonical_parameter_comparison_distinguishes_boolean_from_integer() -> None:
    result = _compare(
        _result_pair(
            baseline_parameters={"enabled": True},
            variant_parameters={"enabled": 1},
        )
    )

    assert isinstance(result, OneFactorMetricDelta)
    assert result.parameter_change.baseline_value is True
    assert result.parameter_change.variant_value == 1
    assert isinstance(result.parameter_change.variant_value, int)
    assert not isinstance(result.parameter_change.variant_value, bool)


@pytest.mark.parametrize(
    ("baseline_metrics", "variant_metrics", "reason"),
    [
        (
            (_metric(Decimal("0.1")),),
            (_metric(Decimal("0.2"), calculation=None),),
            MetricDeltaUnavailableReason.CALCULATION_IDENTITY_UNAVAILABLE,
        ),
        (
            (_metric(Decimal("0.1")),),
            (
                _metric(
                    Decimal("0.2"),
                    calculation=MetricCalculationDefinition(
                        "other.total-return", "test.v1", {"window": "same"}
                    ),
                ),
            ),
            MetricDeltaUnavailableReason.CALCULATION_IDENTITY_MISMATCH,
        ),
        (
            (_metric(Decimal("0.1")),),
            (_metric(Decimal("0.2"), calendar_digest="another-calendar"),),
            MetricDeltaUnavailableReason.MEASUREMENT_SCOPE_MISMATCH,
        ),
        (
            (_metric(None, null_reason="insufficient sessions"),),
            (_metric(Decimal("0.2")),),
            MetricDeltaUnavailableReason.METRIC_VALUE_NULL,
        ),
    ],
)
def test_incompatible_or_unavailable_metric_pairs_are_explicit(
    baseline_metrics: tuple[MetricValue, ...],
    variant_metrics: tuple[MetricValue, ...],
    reason: MetricDeltaUnavailableReason,
) -> None:
    result = _compare(
        _result_pair(
            baseline_metrics=baseline_metrics,
            variant_metrics=variant_metrics,
        )
    )

    assert isinstance(result, MetricDeltaUnavailable)
    assert result.reason is reason
    if reason is MetricDeltaUnavailableReason.METRIC_VALUE_NULL:
        assert result.baseline_null_reason == "insufficient sessions"
        with pytest.raises(ValueError, match="retain at least one side's null reason"):
            replace(result, baseline_null_reason=None)


def test_absent_calendar_evidence_is_symmetric_and_run_input_digests_may_differ() -> None:
    evidence = _result_pair(
        baseline_metrics=(_metric(Decimal("0.1"), calendar_digest=None, input_digest="a"),),
        variant_metrics=(_metric(Decimal("0.2"), calendar_digest=None, input_digest="b"),),
    )

    result = _compare(evidence)

    assert isinstance(result, OneFactorMetricDelta)
    assert result.measurement_scope.session_calendar_evidence_digests == ()


@pytest.mark.parametrize(
    ("baseline_metrics", "variant_metrics", "reason"),
    [
        (
            (_metric(Decimal("0.1"), name="trade_count"),),
            (_metric(Decimal("0.2")),),
            MetricDeltaUnavailableReason.BASELINE_METRIC_MISSING,
        ),
        (
            (_metric(Decimal("0.1")),),
            (_metric(Decimal("0.2"), name="trade_count"),),
            MetricDeltaUnavailableReason.VARIANT_METRIC_MISSING,
        ),
    ],
)
def test_missing_metric_side_is_reported_explicitly(
    baseline_metrics: tuple[MetricValue, ...],
    variant_metrics: tuple[MetricValue, ...],
    reason: MetricDeltaUnavailableReason,
) -> None:
    result = _compare(
        _result_pair(
            baseline_metrics=baseline_metrics,
            variant_metrics=variant_metrics,
        )
    )

    assert isinstance(result, MetricDeltaUnavailable)
    assert result.reason is reason


def test_metric_lookup_uses_name_and_basis_not_metric_tuple_position() -> None:
    evidence = _result_pair(
        baseline_metrics=(
            _metric(Decimal("0.3"), basis=MetricBasis.GROSS),
            _metric(Decimal("0.1"), basis=MetricBasis.NET),
        ),
        variant_metrics=(
            _metric(Decimal("0.2"), basis=MetricBasis.NET),
            _metric(Decimal("0.4"), basis=MetricBasis.GROSS),
        ),
    )

    result = _compare(evidence)

    assert isinstance(result, OneFactorMetricDelta)
    assert result.delta == Decimal("0.1")
