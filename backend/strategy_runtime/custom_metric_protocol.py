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

from app.strategy_lab_v2.contracts import (
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricValue,
)
from app.strategy_lab_v2.custom_metrics import (
    CustomMetricDefinition,
    CustomMetricInvocationResult,
    CustomMetricStatus,
)
from strategy_runtime.protocol import (
    _decode_value,
    _encode_value,
    _list,
    _load_json,
    _mapping,
)

CUSTOM_METRIC_WIRE_PROTOCOL_VERSION = "strategy-lab.custom-metric-runtime.v1"


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

    if not isinstance(source, str):
        raise TypeError("custom metric source must be a string")
    if not isinstance(definition, CustomMetricDefinition):
        raise TypeError("definition must be a CustomMetricDefinition")
    if not isinstance(observations, Mapping):
        raise TypeError("observations must be a mapping")
    if parameters is not None and not isinstance(parameters, Mapping):
        raise TypeError("parameters must be a mapping")
    payload = {
        "protocol_version": CUSTOM_METRIC_WIRE_PROTOCOL_VERSION,
        "source": source,
        "definition": _encode_definition(definition),
        "observations": _encode_value(observations),
        "parameters": _encode_value(parameters if parameters is not None else {}),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    source = item["source"]
    if not isinstance(source, str):
        raise TypeError("custom metric source must be a string")
    observations = _mapping(_decode_value(item["observations"]), "observations")
    parameters = _mapping(_decode_value(item["parameters"]), "parameters")
    return source, _decode_definition(item["definition"]), observations, parameters


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
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


__all__ = [
    "CUSTOM_METRIC_WIRE_PROTOCOL_VERSION",
    "deserialize_custom_metric_invocation",
    "deserialize_custom_metric_result",
    "serialize_custom_metric_invocation",
    "serialize_custom_metric_result",
]
