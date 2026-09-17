"""Strict JSON wire protocol for isolated custom-metric workers.

The protocol reuses the strategy runtime's tagged scalar encoding, duplicate
field rejection, and non-finite-number handling.  Source bytes, definition
identity, frozen observations, and result fingerprints are all explicit so a
worker can run from a mounted bundle without importing application state.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricValue,
)
from app.strategy_lab_v2.custom_metrics import (
    CustomMetricDefinition,
    CustomMetricInvocation,
    CustomMetricInvocationResult,
    CustomMetricStatus,
)
from strategy_runtime.protocol import (
    _decode_value,
    _dump_json,
    _encode_value,
    _list,
    _load_json,
    _mapping,
)

CUSTOM_METRIC_WIRE_PROTOCOL_VERSION = "strategy-lab.custom-metric-runtime.v1"
CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION = "strategy-lab.custom-metric-runtime.batch.v1"


def _encode_definition(definition: CustomMetricDefinition) -> dict[str, Any]:
    if not isinstance(definition, CustomMetricDefinition):
        raise TypeError("definition must be a CustomMetricDefinition")
    return {
        "name": definition.name,
        "unit": definition.unit,
        "basis": definition.basis.value,
        "source_digest": definition.source_digest,
        "entrypoint": definition.entrypoint,
        "definition_version": definition.definition_version,
    }


def _decode_definition(value: Any) -> CustomMetricDefinition:
    item = _mapping(value, "custom metric definition")
    required = {"name", "unit", "basis", "source_digest", "entrypoint", "definition_version"}
    if set(item) != required:
        raise ValueError("custom metric definition fields are invalid")
    try:
        return CustomMetricDefinition(
            name=item["name"],
            unit=item["unit"],
            basis=MetricBasis(item["basis"]),
            source_digest=item["source_digest"],
            entrypoint=item["entrypoint"],
            definition_version=item["definition_version"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("custom metric definition values are invalid") from error


def serialize_custom_metric_invocation(
    *,
    source: str,
    definition: CustomMetricDefinition,
    observations: Mapping[str, Sequence[Any]],
    parameters: Mapping[str, Any] | None = None,
) -> str:
    """Serialize one deterministic source-bound custom-metric request."""

    invocation = CustomMetricInvocation(source, definition, observations, parameters)
    payload = _encode_invocation(invocation)
    return _dump_json(payload, "custom metric invocation payload")


def _encode_invocation(invocation: CustomMetricInvocation) -> dict[str, Any]:
    if not isinstance(invocation, CustomMetricInvocation):
        raise TypeError("invocation must be a CustomMetricInvocation")
    return {
        "protocol_version": CUSTOM_METRIC_WIRE_PROTOCOL_VERSION,
        "source": invocation.source,
        "definition": _encode_definition(invocation.definition),
        "observations": _encode_value(invocation.observations),
        "parameters": _encode_value(invocation.parameters),
    }


def serialize_custom_metric_invocation_batch(
    invocations: Sequence[CustomMetricInvocation],
) -> str:
    """Serialize a deterministic batch of uniquely identified metric inputs."""

    if not isinstance(invocations, Sequence) or isinstance(invocations, str | bytes):
        raise TypeError("custom metric invocations must be a sequence")
    values = tuple(invocations)
    if not values:
        raise ValueError("custom metric invocations must not be empty")
    if any(not isinstance(item, CustomMetricInvocation) for item in values):
        raise TypeError("custom metric invocations must contain CustomMetricInvocation values")
    fingerprints = tuple(item.fingerprint for item in values)
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("custom metric invocation fingerprints must be unique")
    payload = {
        "protocol_version": CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION,
        "invocations": [_encode_invocation(item) for item in values],
        "fingerprint": content_digest(values),
    }
    return _dump_json(payload, "custom metric batch invocation payload")


def deserialize_custom_metric_invocation(
    payload: str,
) -> tuple[str, CustomMetricDefinition, Mapping[str, Sequence[Any]], Mapping[str, Any]]:
    """Decode a strict custom-metric request and preserve tagged values."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("custom metric invocation payload must not be empty")
    root = _load_json(payload, "custom metric invocation payload")
    item = _mapping(root, "custom metric invocation")
    required = {"protocol_version", "source", "definition", "observations", "parameters"}
    if set(item) != required:
        raise ValueError("custom metric invocation fields are invalid")
    if item["protocol_version"] != CUSTOM_METRIC_WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported custom metric runtime protocol version")
    invocation = _decode_invocation(item)
    assert invocation.parameters is not None
    return invocation.source, invocation.definition, invocation.observations, invocation.parameters


def _decode_invocation(value: Any) -> CustomMetricInvocation:
    item = _mapping(value, "custom metric invocation")
    required = {"protocol_version", "source", "definition", "observations", "parameters"}
    if set(item) != required:
        raise ValueError("custom metric invocation fields are invalid")
    if item["protocol_version"] != CUSTOM_METRIC_WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported custom metric runtime protocol version")
    source = item["source"]
    if not isinstance(source, str):
        raise TypeError("custom metric source must be a string")
    observations = _mapping(_decode_value(item["observations"]), "observations")
    parameters = _mapping(_decode_value(item["parameters"]), "parameters")
    return CustomMetricInvocation(
        source,
        _decode_definition(item["definition"]),
        observations,
        parameters,
    )


def deserialize_custom_metric_invocation_batch(
    payload: str,
) -> tuple[CustomMetricInvocation, ...]:
    """Decode and verify a strict custom-metric input batch."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("custom metric invocation batch payload must not be empty")
    root = _load_json(payload, "custom metric invocation batch payload")
    item = _mapping(root, "custom metric invocation batch")
    if set(item) != {"protocol_version", "invocations", "fingerprint"}:
        raise ValueError("custom metric invocation batch fields are invalid")
    if item["protocol_version"] != CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported custom metric runtime batch protocol version")
    values = tuple(_decode_invocation(raw) for raw in _list(item["invocations"], "invocations"))
    if not values:
        raise ValueError("custom metric invocations must not be empty")
    fingerprints = tuple(value.fingerprint for value in values)
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("custom metric invocation fingerprints must be unique")
    if item["fingerprint"] != content_digest(values):
        raise ValueError("custom metric invocation batch fingerprint does not match its payload")
    return values


def _encode_metric(metric: MetricValue) -> dict[str, Any]:
    if not isinstance(metric, MetricValue):
        raise TypeError("metric must be a MetricValue")
    calculation_definition = metric.calculation_definition
    encoded_definition = None
    if calculation_definition is not None:
        encoded_definition = {
            "formula_id": calculation_definition.formula_id,
            "contract_version": calculation_definition.contract_version,
            "parameters": _encode_value(calculation_definition.parameters),
        }
    return {
        "name": metric.name,
        "value": _encode_value(metric.value),
        "unit": metric.unit,
        "definition_version": metric.definition_version,
        "basis": metric.basis.value,
        "sample_size": metric.sample_size,
        "annualization_basis": metric.annualization_basis,
        "calculation_basis": metric.calculation_basis,
        "null_reason": metric.null_reason,
        "calculation_definition": encoded_definition,
        "evidence_references": [
            {"role": item.role, "digest": item.digest} for item in metric.evidence_references
        ],
    }


def _decode_metric(value: Any) -> MetricValue:
    item = _mapping(value, "custom metric result")
    required = {
        "name",
        "value",
        "unit",
        "definition_version",
        "basis",
        "sample_size",
        "annualization_basis",
        "calculation_basis",
        "null_reason",
        "calculation_definition",
        "evidence_references",
    }
    if set(item) != required:
        raise ValueError("custom metric result fields are invalid")
    encoded_definition = item["calculation_definition"]
    calculation_definition = None
    if encoded_definition is not None:
        definition_item = _mapping(encoded_definition, "calculation definition")
        if set(definition_item) != {"formula_id", "contract_version", "parameters"}:
            raise ValueError("custom metric calculation definition fields are invalid")
        calculation_definition = MetricCalculationDefinition(
            formula_id=definition_item["formula_id"],
            contract_version=definition_item["contract_version"],
            parameters=_mapping(
                _decode_value(definition_item["parameters"]),
                "calculation definition parameters",
            ),
        )
    references: list[MetricEvidenceReference] = []
    for raw in _list(item["evidence_references"], "evidence references"):
        reference = _mapping(raw, "evidence reference")
        if set(reference) != {"role", "digest"}:
            raise ValueError("evidence reference fields are invalid")
        references.append(MetricEvidenceReference(reference["role"], reference["digest"]))
    try:
        return MetricValue(
            name=item["name"],
            value=_decode_value(item["value"]),
            unit=item["unit"],
            definition_version=item["definition_version"],
            basis=MetricBasis(item["basis"]),
            sample_size=item["sample_size"],
            annualization_basis=item["annualization_basis"],
            calculation_basis=item["calculation_basis"],
            null_reason=item["null_reason"],
            calculation_definition=calculation_definition,
            evidence_references=tuple(references),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("custom metric result values are invalid") from error


def serialize_custom_metric_result(result: CustomMetricInvocationResult) -> str:
    """Serialize one typed custom-metric result without exception text."""

    if not isinstance(result, CustomMetricInvocationResult):
        raise TypeError("result must be a CustomMetricInvocationResult")
    payload = {
        "protocol_version": CUSTOM_METRIC_WIRE_PROTOCOL_VERSION,
        "request_fingerprint": result.request_fingerprint,
        "definition_fingerprint": result.definition_fingerprint,
        "input_digest": result.input_digest,
        "parameters_digest": result.parameters_digest,
        "status": result.status.value,
        "metric": _encode_metric(result.metric) if result.metric is not None else None,
        "rejection_reasons": list(result.rejection_reasons),
        "error_digest": result.error_digest,
    }
    payload["fingerprint"] = result.fingerprint
    return _dump_json(payload, "custom metric result payload")


def deserialize_custom_metric_result(payload: str) -> CustomMetricInvocationResult:
    """Decode a result and verify its content-addressed fingerprint."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("custom metric result payload must not be empty")
    root = _load_json(payload, "custom metric result payload")
    item = _mapping(root, "custom metric result")
    required = {
        "protocol_version",
        "request_fingerprint",
        "definition_fingerprint",
        "input_digest",
        "parameters_digest",
        "status",
        "metric",
        "rejection_reasons",
        "error_digest",
        "fingerprint",
    }
    if set(item) != required:
        raise ValueError("custom metric result envelope fields are invalid")
    if item["protocol_version"] != CUSTOM_METRIC_WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported custom metric runtime protocol version")
    metric = None if item["metric"] is None else _decode_metric(item["metric"])
    result = CustomMetricInvocationResult(
        request_fingerprint=item["request_fingerprint"],
        definition_fingerprint=item["definition_fingerprint"],
        input_digest=item["input_digest"],
        parameters_digest=item["parameters_digest"],
        status=CustomMetricStatus(item["status"]),
        metric=metric,
        rejection_reasons=tuple(_list(item["rejection_reasons"], "rejection reasons")),
        error_digest=item["error_digest"],
    )
    if item["fingerprint"] != result.fingerprint:
        raise ValueError("custom metric result fingerprint does not match its payload")
    return result


def serialize_custom_metric_result_batch(
    results: Sequence[CustomMetricInvocationResult],
) -> str:
    """Serialize a deterministic batch of typed custom-metric outcomes."""

    if not isinstance(results, Sequence) or isinstance(results, str | bytes):
        raise TypeError("custom metric results must be a sequence")
    values = tuple(results)
    if not values:
        raise ValueError("custom metric results must not be empty")
    if any(not isinstance(item, CustomMetricInvocationResult) for item in values):
        raise TypeError(
            "custom metric results must contain CustomMetricInvocationResult values"
        )
    fingerprints = tuple(item.fingerprint for item in values)
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("custom metric result fingerprints must be unique")
    payload = {
        "protocol_version": CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION,
        "results": [json.loads(serialize_custom_metric_result(item)) for item in values],
        "fingerprint": content_digest(values),
    }
    return _dump_json(payload, "custom metric batch result payload")


def deserialize_custom_metric_result_batch(
    payload: str,
) -> tuple[CustomMetricInvocationResult, ...]:
    """Decode and verify a strict custom-metric result batch."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("custom metric result batch payload must not be empty")
    root = _load_json(payload, "custom metric result batch payload")
    item = _mapping(root, "custom metric result batch")
    if set(item) != {"protocol_version", "results", "fingerprint"}:
        raise ValueError("custom metric result batch fields are invalid")
    if item["protocol_version"] != CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported custom metric runtime batch protocol version")
    values = tuple(
        deserialize_custom_metric_result(
            json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        for raw in _list(item["results"], "results")
    )
    if not values:
        raise ValueError("custom metric results must not be empty")
    fingerprints = tuple(value.fingerprint for value in values)
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("custom metric result fingerprints must be unique")
    if item["fingerprint"] != content_digest(values):
        raise ValueError("custom metric result batch fingerprint does not match its payload")
    return values


__all__ = [
    "CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION",
    "CUSTOM_METRIC_WIRE_PROTOCOL_VERSION",
    "deserialize_custom_metric_invocation",
    "deserialize_custom_metric_invocation_batch",
    "deserialize_custom_metric_result",
    "deserialize_custom_metric_result_batch",
    "serialize_custom_metric_invocation",
    "serialize_custom_metric_invocation_batch",
    "serialize_custom_metric_result",
    "serialize_custom_metric_result_batch",
]
