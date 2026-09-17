from __future__ import annotations

from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import MetricBasis
from app.strategy_lab_v2.metrics import calculate_paired_inference_metrics
from app.strategy_lab_v2.paired_inference import (
    ExactPairedInference,
    PairedInferenceUnavailable,
    PairedInferenceUnavailableReason,
    infer_paired_mean,
)
from app.strategy_lab_v2.pairing import (
    KeyedRandomDraw,
    PairedMetricObservation,
    verify_keyed_random_stream_pairing,
)


def _receipt():
    return verify_keyed_random_stream_pairing(
        baseline_attempt_id="attempt-baseline",
        variant_attempt_id="attempt-variant",
        engine_build_digest=content_digest("engine-build"),
        engine_conformance_fingerprint=content_digest("engine-conformance"),
        stream_contract_fingerprint=content_digest("stream-contract"),
        baseline_draws=(KeyedRandomDraw("draw-0", Decimal("0.25")),),
        variant_draws=(KeyedRandomDraw("draw-0", Decimal("0.25")),),
    )


def _observations() -> tuple[PairedMetricObservation, ...]:
    return (
        PairedMetricObservation("session-3", Decimal("10"), Decimal("13")),
        PairedMetricObservation("session-1", Decimal("10"), Decimal("11")),
        PairedMetricObservation("session-2", Decimal("10"), Decimal("8")),
    )


def test_exact_paired_mean_inference_is_order_invariant_and_content_addressed() -> None:
    receipt = _receipt()
    result = infer_paired_mean(
        _observations(),
        metric_name="session_return",
        pairing_receipt=receipt,
    )
    reordered = infer_paired_mean(
        tuple(reversed(_observations())),
        metric_name="session_return",
        pairing_receipt=receipt,
    )

    assert isinstance(result, ExactPairedInference)
    assert result == reordered
    assert result.sample_size == 3
    assert result.mean_delta == Decimal("0.6666666666666666666666666666666667")
    assert result.observed_absolute_sum == Decimal(2)
    assert result.extreme_permutation_count == 6
    assert result.permutation_count == 8
    assert result.two_sided_p_value == Decimal("0.75")
    assert result.fingerprint.startswith("sha256:")


def test_inference_withholds_large_exact_enumerations_with_typed_evidence() -> None:
    outcome = infer_paired_mean(
        _observations(),
        metric_name="session_return",
        pairing_receipt=_receipt(),
        maximum_exact_observations=2,
    )

    assert isinstance(outcome, PairedInferenceUnavailable)
    assert outcome.reason is PairedInferenceUnavailableReason.EXACT_ENUMERATION_LIMIT
    assert outcome.sample_size == 3
    assert outcome.maximum_exact_observations == 2
    assert outcome.fingerprint.startswith("sha256:")


def test_metric_projection_retains_inference_provenance_and_null_reason() -> None:
    values = {
        item.name: item
        for item in calculate_paired_inference_metrics(
            _observations(),
            metric_name="session_return",
            unit="fraction",
            basis=MetricBasis.NET,
            pairing_receipt=_receipt(),
        )
    }
    assert values["paired_inference_observation_count"].value == Decimal(3)
    assert values["paired_inference_mean_delta"].value == Decimal(
        "0.6666666666666666666666666666666667"
    )
    assert values["paired_inference_two_sided_p_value"].value == Decimal("0.75")
    assert values["paired_inference_extreme_permutation_count"].value == Decimal(6)
    assert values["paired_inference_permutation_count"].value == Decimal(8)
    definition = values["paired_inference_two_sided_p_value"].calculation_definition
    assert definition is not None
    assert definition.parameters["inference_policy"] == "exact_sign_flip_two_sided_mean"
    assert definition.parameters["inclusive_tail"] is True
    assert len(values["paired_inference_two_sided_p_value"].evidence_references) == 2

    unavailable = {
        item.name: item
        for item in calculate_paired_inference_metrics(
            _observations(),
            metric_name="session_return",
            unit="fraction",
            basis=MetricBasis.NET,
            pairing_receipt=_receipt(),
            maximum_exact_observations=2,
        )
    }
    assert unavailable["paired_inference_observation_count"].value == Decimal(3)
    assert unavailable["paired_inference_two_sided_p_value"].value is None
    assert unavailable["paired_inference_two_sided_p_value"].null_reason == (
        "exact_enumeration_limit: exact sign-flip inference is bounded at 2 observations"
    )


def test_paired_inference_rejects_invalid_inputs() -> None:
    receipt = _receipt()
    with pytest.raises(ValueError, match="at least one"):
        infer_paired_mean((), metric_name="session_return", pairing_receipt=receipt)
    with pytest.raises(ValueError, match="between 1 and 20"):
        infer_paired_mean(
            _observations(),
            metric_name="session_return",
            pairing_receipt=receipt,
            maximum_exact_observations=21,
        )
    with pytest.raises(TypeError, match="Metric"):
        infer_paired_mean(
            ("bad",),  # type: ignore[arg-type]
            metric_name="session_return",
            pairing_receipt=receipt,
        )
