"""Engine-neutral binding of data preflight to an execution capability cell."""

from __future__ import annotations

from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.capabilities import PreflightClass, PreflightReport
from app.strategy_lab_v2.contracts import ProductClass


@dataclass(frozen=True, slots=True)
class ExecutionCapabilityBinding:
    """Registered engine/build capability evidence supplied by an adapter."""

    engine_name: str
    engine_version: str
    engine_build_digest: str
    conformance_fingerprint: str
    product_classes: frozenset[ProductClass]
    execution_models: frozenset[str]
    account_models: frozenset[str]
    authoritative: bool = False

    def __post_init__(self) -> None:
        for name in ("engine_name", "engine_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        require_sha256_digest(self.engine_build_digest, field_name="engine_build_digest")
        require_sha256_digest(
            self.conformance_fingerprint, field_name="conformance_fingerprint"
        )
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        if not self.product_classes:
            raise ValueError("execution capability must declare product classes")
        if any(not isinstance(item, ProductClass) for item in self.product_classes):
            raise TypeError("product_classes must contain ProductClass values")
        for name in ("execution_models", "account_models"):
            values = getattr(self, name)
            if not values or any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, frozenset(values))
        object.__setattr__(self, "product_classes", frozenset(self.product_classes))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ExecutionCapabilityPreflight:
    """Decision that keeps data and engine gaps visible at execution time."""

    report_fingerprint: str
    binding_fingerprint: str
    classification: PreflightClass
    gaps: tuple[str, ...]
    authoritative: bool

    def __post_init__(self) -> None:
        require_sha256_digest(self.report_fingerprint, field_name="report_fingerprint")
        require_sha256_digest(self.binding_fingerprint, field_name="binding_fingerprint")
        if not isinstance(self.classification, PreflightClass):
            raise TypeError("classification must be a PreflightClass")
        if any(not isinstance(item, str) or not item.strip() for item in self.gaps):
            raise ValueError("execution capability gaps must be non-empty strings")
        if len(set(self.gaps)) != len(self.gaps):
            raise ValueError("execution capability gaps must be unique")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        object.__setattr__(self, "gaps", tuple(self.gaps))

    @property
    def executable(self) -> bool:
        return self.classification is not PreflightClass.UNSUPPORTED and not self.gaps

    @property
    def can_publish_authoritative_results(self) -> bool:
        return self.executable and self.authoritative


def preflight_execution_capability(
    report: PreflightReport, binding: ExecutionCapabilityBinding
) -> ExecutionCapabilityPreflight:
    """Require registered engine support for every executable data requirement."""

    if not isinstance(report, PreflightReport):
        raise TypeError("report must be a PreflightReport")
    if not isinstance(binding, ExecutionCapabilityBinding):
        raise TypeError("binding must be an ExecutionCapabilityBinding")

    gaps: list[str] = []
    if report.classification is PreflightClass.UNSUPPORTED:
        gaps.append("data_preflight_unsupported")
    for decision in report.decisions:
        requirement = decision.requirement
        if requirement.product_class not in binding.product_classes:
            gaps.append(f"product_class:{requirement.product_class.value}")
        if requirement.execution_model not in binding.execution_models:
            gaps.append(f"execution_model:{requirement.execution_model}")
        if requirement.account_model not in binding.account_models:
            gaps.append(f"account_model:{requirement.account_model}")
    classification = (
        PreflightClass.UNSUPPORTED
        if gaps
        else report.classification
    )
    return ExecutionCapabilityPreflight(
        report_fingerprint=report.fingerprint,
        binding_fingerprint=binding.fingerprint,
        classification=classification,
        gaps=tuple(sorted(set(gaps))),
        authoritative=binding.authoritative,
    )
