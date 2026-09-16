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
    TRIAL_SEED_DERIVATION_VERSION,
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
    SensitivityEvidenceLevel,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
    TrialRandomization,
    TrialSeedPolicy,
)
from app.strategy_lab_v2.metrics import calculate_paired_metric_metrics
from app.strategy_lab_v2.pairing import (
    KEYED_STREAM_VERIFIER_VERSION,
    KeyedRandomDraw,
    PairedMetricObservation,
    verify_keyed_random_stream_pairing,
)
from app.strategy_lab_v2.sensitivity import (
    MetricDeltaUnavailable,
    MetricDeltaUnavailableReason,
    OneFactorMetricDelta,
    OneFactorReplicateMetricSummary,
    ReplicateMetricSummaryUnavailable,
    ReplicateSummaryUnavailableReason,
    compare_one_factor_metric,
    summarize_one_factor_metric_replicates,
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


def test_keyed_stream_verifier_requires_exact_draw_alignment_and_values() -> None:
    baseline = (
        KeyedRandomDraw("scenario-0:step-0", Decimal("0.125")),
        KeyedRandomDraw("scenario-0:step-1", Decimal("0.875")),
    )
    variant = (
        KeyedRandomDraw("scenario-0:step-1", Decimal("0.875")),
        KeyedRandomDraw("scenario-0:step-0", Decimal("0.125")),
    )
    receipt = verify_keyed_random_stream_pairing(
        baseline_attempt_id="attempt-baseline",
        variant_attempt_id="attempt-variant",
        engine_build_digest=content_digest("engine-build"),
        engine_conformance_fingerprint=content_digest("engine-conformance"),
        stream_contract_fingerprint=content_digest("stream-contract"),
        baseline_draws=baseline,
        variant_draws=variant,
    )
    assert receipt.verifier_version == KEYED_STREAM_VERIFIER_VERSION
    assert receipt.claim.matched_draw_count == 2
    assert receipt.claim.unmatched_baseline_draw_count == 0
    assert receipt.claim.unmatched_variant_draw_count == 0

    with pytest.raises(ValueError, match="align exactly"):
        verify_keyed_random_stream_pairing(
            baseline_attempt_id="attempt-baseline",
            variant_attempt_id="attempt-variant",
            engine_build_digest=content_digest("engine-build"),
            engine_conformance_fingerprint=content_digest("engine-conformance"),
            stream_contract_fingerprint=content_digest("stream-contract"),
            baseline_draws=baseline,
            variant_draws=variant[:-1],
        )
    with pytest.raises(ValueError, match="value mismatch"):
        verify_keyed_random_stream_pairing(
            baseline_attempt_id="attempt-baseline",
            variant_attempt_id="attempt-variant",
            engine_build_digest=content_digest("engine-build"),
            engine_conformance_fingerprint=content_digest("engine-conformance"),
            stream_contract_fingerprint=content_digest("stream-contract"),
            baseline_draws=baseline,
            variant_draws=(
                KeyedRandomDraw("scenario-0:step-0", Decimal("0.125")),
                KeyedRandomDraw("scenario-0:step-1", Decimal("0.5")),
            ),
        )


def test_verified_pairing_receipt_upgrades_sensitivity_provenance_only() -> None:
    source = _result_pair()
    baseline_result = _replicate_result(
        source.baseline_result,
        parameters={"lookback": 20},
        replicate_index=0,
        replicate_count=1,
        value=Decimal("0.1"),
        shared_seed=True,
    )
    variant_result = _replicate_result(
        source.variant_result,
        parameters={"lookback": 30},
        replicate_index=0,
        replicate_count=1,
        value=Decimal("0.1"),
        shared_seed=True,
    )
    evidence = SensitivityComparisonEvidence(baseline_result, variant_result)
    receipt = verify_keyed_random_stream_pairing(
        baseline_attempt_id=evidence.baseline_result.attempt_id,
        variant_attempt_id=evidence.variant_result.attempt_id,
        engine_build_digest=evidence.baseline_result.engine_build_digest,
        engine_conformance_fingerprint=content_digest("engine-conformance"),
        stream_contract_fingerprint=content_digest("stream-contract"),
        baseline_draws=(KeyedRandomDraw("draw-0", Decimal("0.25")),),
        variant_draws=(KeyedRandomDraw("draw-0", Decimal("0.25")),),
    )
    claim = receipt.claim
    required_digests = tuple(
        dict.fromkeys(
            (
                claim.baseline_trace_digest,
                claim.variant_trace_digest,
                claim.fingerprint,
                claim.paired_draws_digest,
            )
        )
    )
    baseline_artifacts = evidence.baseline_result.output_artifacts + tuple(
        ArtifactManifest(digest, 32, "application/octet-stream", "1", digest)
        for digest in required_digests
    )
    variant_artifacts = evidence.variant_result.output_artifacts + tuple(
        ArtifactManifest(digest, 32, "application/octet-stream", "1", digest)
        for digest in required_digests
    )
    paired = SensitivityComparisonEvidence(
        replace(evidence.baseline_result, output_artifacts=baseline_artifacts),
        replace(evidence.variant_result, output_artifacts=variant_artifacts),
        pairing_receipt=receipt,
    )
    assert paired.evidence_level is SensitivityEvidenceLevel.VERIFIED_PAIRED
    delta = _compare(paired)
    assert isinstance(delta, OneFactorMetricDelta)
    assert delta.evidence_level is SensitivityEvidenceLevel.VERIFIED_PAIRED


def test_paired_metric_metrics_require_receipt_and_preserve_keyed_descriptive_deltas() -> None:
    receipt = verify_keyed_random_stream_pairing(
        baseline_attempt_id="attempt-baseline",
        variant_attempt_id="attempt-variant",
        engine_build_digest=content_digest("engine-build"),
        engine_conformance_fingerprint=content_digest("engine-conformance"),
        stream_contract_fingerprint=content_digest("stream-contract"),
        baseline_draws=(KeyedRandomDraw("draw-0", Decimal("0.25")),),
        variant_draws=(KeyedRandomDraw("draw-0", Decimal("0.25")),),
    )
    observations = (
        PairedMetricObservation("session-2", Decimal("20"), Decimal("18")),
        PairedMetricObservation("session-1", Decimal("10"), Decimal("13")),
    )
    values = {item.name: item for item in calculate_paired_metric_metrics(
        observations,
        metric_name="session_return",
        unit="fraction",
        basis=MetricBasis.NET,
        pairing_receipt=receipt,
    )}
    assert values["paired_observation_count"].value == Decimal(2)
    assert values["paired_baseline_mean"].value == Decimal(15)
    assert values["paired_variant_mean"].value == Decimal(15.5)
    assert values["paired_mean_delta"].value == Decimal("0.5")
    assert values["paired_median_delta"].value == Decimal(-2)
    assert values["paired_minimum_delta"].value == Decimal(-2)
    assert values["paired_maximum_delta"].value == Decimal(3)
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        expected_stddev = (Decimal("12.5")).sqrt()
    assert values["paired_delta_sample_stddev"].value == expected_stddev
    paired_definition = values["paired_mean_delta"].calculation_definition
    assert paired_definition is not None
    assert paired_definition.parameters["inference_policy"] == (
        "descriptive_only_no_ranking_or_significance"
    )
    assert len(values["paired_mean_delta"].evidence_references) == 2

    with pytest.raises(ValueError, match="keys must be unique"):
        calculate_paired_metric_metrics(
            (
                PairedMetricObservation("same", Decimal("1"), Decimal("1")),
                PairedMetricObservation("same", Decimal("2"), Decimal("2")),
            ),
            metric_name="session_return",
            unit="fraction",
            basis=MetricBasis.NET,
            pairing_receipt=receipt,
        )


def _replicate_result(
    source: RunResultManifest,
    *,
    parameters: dict[str, Any],
    replicate_index: int,
    replicate_count: int,
    value: Decimal | None,
    shared_seed: bool = False,
    null_reason: str | None = None,
) -> RunResultManifest:
    group_identity = {
        "scope": source.trial.experiment_fingerprint if shared_seed else source.trial.parameter_set,
        "replicate_index": replicate_index,
    }
    seed_group = content_digest(group_identity)
    derived_seed = int(seed_group.split(":", 1)[1][:16], 16) & ((1 << 63) - 1)
    randomization = TrialRandomization(
        master_seed=41,
        seed=derived_seed,
        policy=(
            TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE
            if shared_seed
            else TrialSeedPolicy.PER_CANDIDATE
        ),
        replicate_index=replicate_index,
        scope_fingerprint=(source.trial.experiment_fingerprint if shared_seed else None),
        seed_group_fingerprint=seed_group,
        replicate_count=replicate_count,
        derivation_version=TRIAL_SEED_DERIVATION_VERSION,
    )
    trial = ScientificTrial.create(
        experiment_fingerprint=source.trial.experiment_fingerprint,
        snapshot_fingerprint=source.snapshot_fingerprint,
        preflight_report=source.snapshot.preflight_report,
        parameter_set=parameters,
        scenario=source.trial.scenario,
        randomization=randomization,
    )
    attempt_id = f"{source.attempt_id}-{replicate_index}"
    attempt = RunAttempt(attempt_id, trial.trial_id, 1, AttemptState.SUCCEEDED, CREATED)
    values = tuple(
        replace(metric, value=value, null_reason=null_reason)
        if metric.name == "total_return" and metric.basis is MetricBasis.NET
        else metric
        for metric in source.metric_set.values
    )
    metric_set = replace(
        source.metric_set,
        metric_set_id=f"metrics-{attempt_id}",
        trial_id=trial.trial_id,
        attempt_id=attempt_id,
        values=values,
    )
    output_digest = content_digest({"result": attempt_id})
    return replace(
        source,
        trial=trial,
        attempt=attempt,
        metric_set=metric_set,
        output_artifacts=(
            ArtifactManifest(output_digest, 32, "application/octet-stream", "1", output_digest),
        ),
    )


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


def test_replicate_summary_is_complete_deterministic_and_descriptive() -> None:
    pair = _result_pair()
    baseline = tuple(
        _replicate_result(
            pair.baseline_result,
            parameters={"lookback": 20},
            replicate_index=index,
            replicate_count=3,
            value=Decimal(value),
        )
        for index, value in enumerate(("0.10", "0.30", "0.20"))
    )
    variant = tuple(
        _replicate_result(
            pair.variant_result,
            parameters={"lookback": 30},
            replicate_index=index,
            replicate_count=3,
            value=Decimal(value),
        )
        for index, value in enumerate(("0.20", "0.40", "0.30"))
    )

    result = summarize_one_factor_metric_replicates(
        baseline,
        tuple(reversed(variant)),
        metric_name="total_return",
        basis=MetricBasis.NET,
    )

    assert isinstance(result, OneFactorReplicateMetricSummary)
    assert result.baseline.mean == Decimal("0.20")
    assert result.variant.mean == Decimal("0.30")
    assert result.mean_delta == Decimal("0.10")
    assert result.baseline.median == Decimal("0.20")
    assert result.baseline.minimum == Decimal("0.10")
    assert result.baseline.maximum == Decimal("0.30")
    assert [item.value for item in result.baseline.nearest_rank_statistics] == [
        Decimal("0.10"),
        Decimal("0.10"),
        Decimal("0.20"),
        Decimal("0.30"),
        Decimal("0.30"),
    ]
    assert result.baseline.observation_sample_sizes == (252, 252, 252)
    assert result.baseline_trial_ids == tuple(item.trial_id for item in baseline)
    assert result.variant_attempt_ids == tuple(item.attempt_id for item in variant)
    assert result.evidence_level.value == "unpaired"
    assert (
        result.fingerprint
        == summarize_one_factor_metric_replicates(
            tuple(reversed(baseline)),
            variant,
            metric_name="total_return",
            basis=MetricBasis.NET,
        ).fingerprint
    )


def test_replicate_summary_retains_shared_seed_provenance_without_pairing_claim() -> None:
    pair = _result_pair()
    baseline = tuple(
        _replicate_result(
            pair.baseline_result,
            parameters={"lookback": 20},
            replicate_index=index,
            replicate_count=2,
            value=Decimal("0.10") + Decimal(index) / Decimal("100"),
            shared_seed=True,
        )
        for index in range(2)
    )
    variant = tuple(
        _replicate_result(
            pair.variant_result,
            parameters={"lookback": 30},
            replicate_index=index,
            replicate_count=2,
            value=Decimal("0.20") + Decimal(index) / Decimal("100"),
            shared_seed=True,
        )
        for index in range(2)
    )

    result = summarize_one_factor_metric_replicates(
        baseline,
        variant,
        metric_name="total_return",
        basis=MetricBasis.NET,
    )

    assert isinstance(result, OneFactorReplicateMetricSummary)
    assert result.evidence_level.value == "shared_seed_only"
    assert result.baseline_randomization.seed_group_fingerprints == (
        result.variant_randomization.seed_group_fingerprints
    )
    assert result.baseline_randomization.replicate_indices == (0, 1)


@pytest.mark.parametrize(
    ("baseline_count", "variant_count", "reason"),
    [
        (3, 3, ReplicateSummaryUnavailableReason.REPLICATE_INDEX_INCOMPLETE),
        (2, 3, ReplicateSummaryUnavailableReason.REPLICATE_COUNT_MISMATCH),
    ],
)
def test_replicate_summary_fails_closed_on_incomplete_planned_groups(
    baseline_count: int,
    variant_count: int,
    reason: ReplicateSummaryUnavailableReason,
) -> None:
    pair = _result_pair()
    baseline = tuple(
        _replicate_result(
            pair.baseline_result,
            parameters={"lookback": 20},
            replicate_index=index,
            replicate_count=baseline_count,
            value=Decimal("0.10"),
        )
        for index in range(baseline_count - (1 if baseline_count == 3 else 0))
    )
    variant = tuple(
        _replicate_result(
            pair.variant_result,
            parameters={"lookback": 30},
            replicate_index=index,
            replicate_count=variant_count,
            value=Decimal("0.20"),
        )
        for index in range(variant_count)
    )

    result = summarize_one_factor_metric_replicates(
        baseline,
        variant,
        metric_name="total_return",
        basis=MetricBasis.NET,
    )

    assert isinstance(result, ReplicateMetricSummaryUnavailable)
    assert result.reason is reason


def test_replicate_summary_fails_closed_on_null_replicate_value() -> None:
    pair = _result_pair()
    baseline = tuple(
        _replicate_result(
            pair.baseline_result,
            parameters={"lookback": 20},
            replicate_index=index,
            replicate_count=2,
            value=(None if index == 1 else Decimal("0.10")),
            null_reason=("engine omitted metric" if index == 1 else None),
        )
        for index in range(2)
    )
    variant = tuple(
        _replicate_result(
            pair.variant_result,
            parameters={"lookback": 30},
            replicate_index=index,
            replicate_count=2,
            value=Decimal("0.20"),
        )
        for index in range(2)
    )

    result = summarize_one_factor_metric_replicates(
        baseline,
        variant,
        metric_name="total_return",
        basis=MetricBasis.NET,
    )

    assert isinstance(result, ReplicateMetricSummaryUnavailable)
    assert result.reason is ReplicateSummaryUnavailableReason.METRIC_VALUE_NULL
    assert result.baseline_null_reasons == ("engine omitted metric",)
