from __future__ import annotations

from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import MetricBasis
from app.strategy_lab_v2.custom_metrics import (
    CustomMetricDefinition,
    CustomMetricInvocation,
    CustomMetricStatus,
    run_custom_metric,
    run_custom_metrics,
)

SAFE_SOURCE = """
from decimal import Decimal

def calculate(observations, parameters):
    values = observations['returns']
    return sum(values, Decimal('0')) / Decimal(len(values)) + parameters['offset']
"""


def _definition(source: str = SAFE_SOURCE) -> CustomMetricDefinition:
    return CustomMetricDefinition(
        name="custom_mean_return",
        unit="fraction",
        basis=MetricBasis.NET,
        source_digest=content_digest(source),
        entrypoint="custom_metric:calculate",
    )


def test_custom_metric_runs_over_frozen_decimal_inputs_and_emits_typed_metric() -> None:
    result = run_custom_metric(
        SAFE_SOURCE,
        definition=_definition(),
        observations={"returns": (Decimal("0.10"), Decimal("0.20"))},
        parameters={"offset": Decimal("0.05")},
    )

    assert result.status is CustomMetricStatus.SUCCEEDED
    assert result.accepted
    assert result.metric is not None
    assert result.metric.value == Decimal("0.20")
    assert result.metric.sample_size == 2
    assert result.metric.calculation_definition is not None
    assert result.metric.evidence_references[0].digest == result.input_digest
    assert result.fingerprint.startswith("sha256:")


def test_custom_metric_source_identity_and_static_violations_fail_closed() -> None:
    mismatch = run_custom_metric(
        SAFE_SOURCE,
        definition=_definition("def calculate(observations, parameters):\n    return Decimal('1')\n"),
        observations={},
    )
    assert mismatch.status is CustomMetricStatus.REJECTED
    assert mismatch.rejection_reasons == ("source_digest_mismatch",)

    rejected = run_custom_metric(
        "import os\n\ndef calculate(observations, parameters):\n    return Decimal('1')\n",
        definition=_definition(
            "import os\n\ndef calculate(observations, parameters):\n    return Decimal('1')\n"
        ),
        observations={},
    )
    assert rejected.status is CustomMetricStatus.REJECTED
    assert any("forbidden_import" in reason for reason in rejected.rejection_reasons)


def test_custom_metric_output_and_runtime_errors_are_typed_without_exception_text() -> None:
    wrong_output = """
def calculate(observations, parameters):
    return 1.0
"""
    rejected_output = run_custom_metric(
        wrong_output,
        definition=_definition(wrong_output),
        observations={},
    )
    assert rejected_output.status is CustomMetricStatus.FAILED
    assert rejected_output.metric is None
    assert rejected_output.error_digest is not None

    raises = """
def calculate(observations, parameters):
    raise ValueError('secret input must not leak')
"""
    failed = run_custom_metric(
        raises,
        definition=_definition(raises),
        observations={},
    )
    assert failed.status is CustomMetricStatus.FAILED
    assert failed.error_digest is not None
    assert "secret input" not in str(failed)


def test_custom_metric_rejects_mutable_or_non_decimal_inputs() -> None:
    source = """
from decimal import Decimal

def calculate(observations, parameters):
    return Decimal('1')
"""
    with pytest.raises(ValueError, match="finite Decimal"):
        run_custom_metric(
            source,
            definition=_definition(source),
            observations={"values": (1, 2)},  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="parameters must be a mapping"):
        run_custom_metric(
            source,
            definition=_definition(source),
            observations={},
            parameters=[],  # type: ignore[arg-type]
        )


def test_custom_metric_resolves_dotted_callable_entrypoints() -> None:
    source = """
from decimal import Decimal

class Metrics:
    @staticmethod
    def calculate(observations, parameters):
        return Decimal('1')
"""
    definition = CustomMetricDefinition(
        name="dotted_metric",
        unit="fraction",
        basis=MetricBasis.NET,
        source_digest=content_digest(source),
        entrypoint="custom_metric:Metrics.calculate",
    )
    result = run_custom_metric(source, definition=definition, observations={})
    assert result.status is CustomMetricStatus.SUCCEEDED
    assert result.metric is not None and result.metric.value == Decimal("1")


def test_custom_metric_batch_is_immutable_ordered_and_rejects_duplicate_inputs() -> None:
    first = CustomMetricInvocation(
        SAFE_SOURCE,
        _definition(),
        {"returns": [Decimal("0.10"), Decimal("0.20")]},
        {"offset": Decimal("0.05")},
    )
    second = CustomMetricInvocation(
        SAFE_SOURCE,
        _definition(),
        {"returns": [Decimal("0.30"), Decimal("0.40")]},
        {"offset": Decimal("0.05")},
    )
    results = run_custom_metrics((first, second))
    assert tuple(item.status for item in results) == (
        CustomMetricStatus.SUCCEEDED,
        CustomMetricStatus.SUCCEEDED,
    )
    assert results[0].metric is not None and results[0].metric.value == Decimal("0.20")
    assert results[1].metric is not None and results[1].metric.value == Decimal("0.40")
    with pytest.raises(ValueError, match="fingerprints must be unique"):
        run_custom_metrics((first, first))
