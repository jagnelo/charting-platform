"""Restricted, deterministic execution of user-defined result metrics.

Custom metrics run in the same process-local restricted surface as strategies;
the containing worker must still use the hardened no-network sandbox for real
isolation.  The callable receives only frozen Decimal observations and frozen
JSON parameters, and its scalar output is wrapped in the platform's typed
``MetricValue`` contract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricValue,
)
from app.strategy_lab_v2.strategy_validation import validate_strategy_source
from strategy_runtime.runner import RUNTIME_ERROR_EVIDENCE_VERSION, _restricted_builtins

CUSTOM_METRIC_DEFINITION_VERSION = "strategy-lab.custom-metric.v1"


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _entrypoint(value: str) -> None:
    parts = value.split(":")
    if len(parts) != 2 or any(
        not part or any(not token.isidentifier() for token in part.split("."))
        for part in parts
    ):
        raise ValueError("entrypoint must use module.path:callable syntax")


class CustomMetricStatus(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CustomMetricDefinition:
    """Immutable identity and output contract for one custom metric."""

    name: str
    unit: str
    basis: MetricBasis
    source_digest: str
    entrypoint: str
    definition_version: str = CUSTOM_METRIC_DEFINITION_VERSION

    def __post_init__(self) -> None:
        for name in ("name", "unit", "definition_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.basis, MetricBasis):
            raise TypeError("basis must be a MetricBasis")
        require_sha256_digest(self.source_digest, field_name="source_digest")
        _entrypoint(self.entrypoint)
        if self.definition_version != CUSTOM_METRIC_DEFINITION_VERSION:
            raise ValueError("unsupported custom metric definition version")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class CustomMetricInvocationResult:
    """Typed, content-addressed outcome of one custom metric invocation."""

    request_fingerprint: str
    definition_fingerprint: str
    input_digest: str
    parameters_digest: str
    status: CustomMetricStatus
    metric: MetricValue | None = None
    rejection_reasons: tuple[str, ...] = ()
    error_digest: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "request_fingerprint",
            "definition_fingerprint",
            "input_digest",
            "parameters_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.status, CustomMetricStatus):
            raise TypeError("status must be a CustomMetricStatus")
        if self.metric is not None and not isinstance(self.metric, MetricValue):
            raise TypeError("metric must be a MetricValue")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError("custom metric rejection reasons must be unique and non-empty")
        if self.error_digest is not None:
            require_sha256_digest(self.error_digest, field_name="error_digest")
        if self.status is CustomMetricStatus.SUCCEEDED:
            if self.metric is None or reasons or self.error_digest is not None:
                raise ValueError("successful custom metrics require a metric and no errors")
        elif self.status is CustomMetricStatus.REJECTED:
            if self.metric is not None or not reasons or self.error_digest is not None:
                raise ValueError("rejected custom metrics require reasons and no metric")
        elif self.metric is not None or reasons or self.error_digest is None:
            raise ValueError("failed custom metrics require an error and no metric")
        object.__setattr__(self, "rejection_reasons", tuple(sorted(reasons)))

    @property
    def accepted(self) -> bool:
        return self.status is CustomMetricStatus.SUCCEEDED

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def _error_digest(error: BaseException) -> str:
    error_type = f"{type(error).__module__}.{type(error).__qualname__}"
    return content_digest(
        {
            "type": error_type,
            "version": f"{RUNTIME_ERROR_EVIDENCE_VERSION}.custom-metric",
        }
    )


def _normalize_observations(
    observations: Mapping[str, Sequence[Any]],
) -> Mapping[str, tuple[Any, ...]]:
    if not isinstance(observations, Mapping):
        raise TypeError("observations must be a mapping")
    normalized: dict[str, tuple[Any, ...]] = {}
    for name, values in observations.items():
        _nonempty(name, "observation name")
        if not isinstance(values, Sequence) or isinstance(values, str | bytes):
            raise TypeError("observation values must be sequences")
        decimal_values = tuple(values)
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in decimal_values):
            raise ValueError("observations must contain only finite Decimal values")
        normalized[name] = decimal_values
    return MappingProxyType({name: normalized[name] for name in sorted(normalized)})


def _load_metric_callable(source: str, entrypoint: str) -> Callable[..., Any]:
    module_name, _separator, callable_name = entrypoint.partition(":")
    namespace: dict[str, Any] = {
        "__name__": module_name,
        "__file__": f"<custom-metric:{content_digest(source)}>",
        "__builtins__": _restricted_builtins(),
    }
    namespace["Decimal"] = Decimal
    code = compile(source, namespace["__file__"], "exec")
    exec(code, namespace, namespace)
    candidate = namespace.get(callable_name)
    if not callable(candidate):
        raise TypeError("custom metric entrypoint must be callable")
    return candidate


def run_custom_metric(
    source: str,
    *,
    definition: CustomMetricDefinition,
    observations: Mapping[str, Sequence[Any]],
    parameters: Mapping[str, Any] | None = None,
) -> CustomMetricInvocationResult:
    """Run a source-bound metric over frozen observations without I/O.

    The source callable must accept ``(observations, parameters)`` and return
    one finite ``Decimal``.  Static violations, source identity drift, and
    malformed outputs become typed evidence; exception text never crosses the
    result boundary.
    """

    if not isinstance(source, str):
        raise TypeError("custom metric source must be a string")
    if not isinstance(definition, CustomMetricDefinition):
        raise TypeError("definition must be a CustomMetricDefinition")
    frozen_observations = _normalize_observations(observations)
    raw_parameters: Mapping[str, Any] = {} if parameters is None else parameters
    if not isinstance(raw_parameters, Mapping):
        raise TypeError("parameters must be a mapping")
    frozen_parameters = freeze_json(raw_parameters)
    if not isinstance(frozen_parameters, Mapping):
        raise TypeError("parameters must be a mapping")
    input_digest = content_digest(frozen_observations)
    parameters_digest = content_digest(frozen_parameters)
    request_fingerprint = content_digest(
        {
            "definition_fingerprint": definition.fingerprint,
            "input_digest": input_digest,
            "parameters_digest": parameters_digest,
        }
    )
    if content_digest(source) != definition.source_digest:
        return CustomMetricInvocationResult(
            request_fingerprint,
            definition.fingerprint,
            input_digest,
            parameters_digest,
            CustomMetricStatus.REJECTED,
            rejection_reasons=("source_digest_mismatch",),
        )
    validation = validate_strategy_source(source)
    if not validation.accepted:
        return CustomMetricInvocationResult(
            request_fingerprint,
            definition.fingerprint,
            input_digest,
            parameters_digest,
            CustomMetricStatus.REJECTED,
            rejection_reasons=tuple(f"source:{item}" for item in validation.violations),
        )
    try:
        callable_metric = _load_metric_callable(source, definition.entrypoint)
        value = callable_metric(frozen_observations, frozen_parameters)
        if not isinstance(value, Decimal) or not value.is_finite():
            raise TypeError("custom metric must return a finite Decimal")
        sample_size = sum(len(values) for values in frozen_observations.values())
        metric = MetricValue(
            name=definition.name,
            value=value,
            unit=definition.unit,
            definition_version=definition.definition_version,
            basis=definition.basis,
            sample_size=sample_size,
            calculation_basis="custom metric over frozen declared observations",
            calculation_definition=MetricCalculationDefinition(
                formula_id=f"strategy-lab.custom-metric/{definition.name}",
                contract_version=definition.definition_version,
                parameters={"source_digest": definition.source_digest},
            ),
            evidence_references=(MetricEvidenceReference("custom_metric_input", input_digest),),
        )
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        return CustomMetricInvocationResult(
            request_fingerprint,
            definition.fingerprint,
            input_digest,
            parameters_digest,
            CustomMetricStatus.FAILED,
            error_digest=_error_digest(error),
        )
    return CustomMetricInvocationResult(
        request_fingerprint,
        definition.fingerprint,
        input_digest,
        parameters_digest,
        CustomMetricStatus.SUCCEEDED,
        metric=metric,
    )


__all__ = [
    "CUSTOM_METRIC_DEFINITION_VERSION",
    "CustomMetricDefinition",
    "CustomMetricInvocationResult",
    "CustomMetricStatus",
    "run_custom_metric",
]
