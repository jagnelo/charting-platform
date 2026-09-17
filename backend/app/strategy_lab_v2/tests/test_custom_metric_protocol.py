from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import MetricBasis
from app.strategy_lab_v2.custom_metrics import (
    CustomMetricDefinition,
    CustomMetricStatus,
    run_custom_metric,
)
from strategy_runtime.custom_metric_protocol import (
    deserialize_custom_metric_invocation,
    deserialize_custom_metric_result,
    serialize_custom_metric_invocation,
    serialize_custom_metric_result,
)
from strategy_runtime.custom_metric_runner import main as custom_metric_main

SOURCE = """
from decimal import Decimal

def calculate(observations, parameters):
    return sum(observations['returns'], Decimal('0')) + parameters['offset']
"""


def _definition() -> CustomMetricDefinition:
    return CustomMetricDefinition(
        name="protocol_metric",
        unit="currency:USD",
        basis=MetricBasis.NET,
        source_digest=content_digest(SOURCE),
        entrypoint="custom_metric:calculate",
    )


def test_custom_metric_invocation_wire_round_trips_deterministically() -> None:
    definition = _definition()
    first = serialize_custom_metric_invocation(
        source=SOURCE,
        definition=definition,
        observations={"returns": (Decimal("1.0"), Decimal("2.0"))},
        parameters={"offset": Decimal("0.5")},
    )
    second = serialize_custom_metric_invocation(
        source=SOURCE,
        definition=definition,
        observations={"returns": (Decimal("1.0"), Decimal("2.0"))},
        parameters={"offset": Decimal("0.5")},
    )
    assert first == second
    source, decoded_definition, observations, parameters = deserialize_custom_metric_invocation(
        first
    )
    assert source == SOURCE
    assert decoded_definition == definition
    assert observations["returns"] == (Decimal("1.0"), Decimal("2.0"))
    assert parameters["offset"] == Decimal("0.5")


def test_custom_metric_result_wire_round_trips_and_verifies_fingerprint() -> None:
    definition = _definition()
    result = run_custom_metric(
        SOURCE,
        definition=definition,
        observations={"returns": (Decimal("1"), Decimal("2"))},
        parameters={"offset": Decimal("0.5")},
    )
    payload = serialize_custom_metric_result(result)
    decoded = deserialize_custom_metric_result(payload)
    assert decoded == result
    assert decoded.metric is not None
    assert decoded.metric.value == Decimal("3.5")

    tampered = json.loads(payload)
    tampered["request_fingerprint"] = content_digest("different-request")
    with pytest.raises(ValueError, match="fingerprint"):
        deserialize_custom_metric_result(json.dumps(tampered))


def test_custom_metric_wire_rejects_duplicate_fields() -> None:
    payload = serialize_custom_metric_invocation(
        source=SOURCE,
        definition=_definition(),
        observations={},
    )
    duplicate = payload.replace('"source":', '"source":"duplicate","source":', 1)
    with pytest.raises(ValueError, match="duplicate JSON fields"):
        deserialize_custom_metric_invocation(duplicate)


def test_custom_metric_cli_reads_and_atomically_writes_typed_result(tmp_path) -> None:
    definition = _definition()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(
        serialize_custom_metric_invocation(
            source=SOURCE,
            definition=definition,
            observations={"returns": (Decimal("1"), Decimal("2"))},
            parameters={"offset": Decimal("0.5")},
        ),
        encoding="utf-8",
    )
    assert custom_metric_main(["--request", str(request_path), "--result", str(result_path)]) == 0
    result = deserialize_custom_metric_result(result_path.read_text(encoding="utf-8"))
    assert result.status is CustomMetricStatus.SUCCEEDED
    assert result.metric is not None and result.metric.value == Decimal("3.5")
