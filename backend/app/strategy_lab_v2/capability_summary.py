"""Immutable API projection of data and execution capability preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.capabilities import Degradation, PreflightClass, PreflightReport
from app.strategy_lab_v2.execution_capabilities import ExecutionCapabilityPreflight


class CapabilitySummaryDecision(StrEnum):
    RIGOROUS = "rigorous"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class CapabilitySummary:
    """Machine-facing capability view with no provider or engine handles."""

    report_fingerprint: str
    binding_fingerprint: str
    decision: CapabilitySummaryDecision
    data_gaps: tuple[str, ...]
    execution_gaps: tuple[str, ...]
    degradations: tuple[Degradation, ...]
    ranking_eligible: bool
    executable: bool
    authoritative: bool
    can_publish_authoritative_results: bool

    def __post_init__(self) -> None:
        require_sha256_digest(self.report_fingerprint, field_name="report_fingerprint")
        require_sha256_digest(self.binding_fingerprint, field_name="binding_fingerprint")
        if not isinstance(self.decision, CapabilitySummaryDecision):
            raise TypeError("decision must be a CapabilitySummaryDecision")
        for name in ("data_gaps", "execution_gaps"):
            values = tuple(getattr(self, name))
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be unique")
            object.__setattr__(self, name, tuple(sorted(values)))
        degradations = tuple(self.degradations)
        if any(not isinstance(item, Degradation) for item in degradations):
            raise TypeError("degradations must contain Degradation values")
        if not isinstance(self.ranking_eligible, bool):
            raise TypeError("ranking_eligible must be a boolean")
        if not isinstance(self.executable, bool):
            raise TypeError("executable must be a boolean")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        if not isinstance(self.can_publish_authoritative_results, bool):
            raise TypeError("can_publish_authoritative_results must be a boolean")
        if self.decision is CapabilitySummaryDecision.UNSUPPORTED and self.executable:
            raise ValueError("unsupported capability summaries cannot be executable")
        if self.ranking_eligible and (
            self.decision is not CapabilitySummaryDecision.RIGOROUS or not self.executable
        ):
            raise ValueError("only executable rigorous summaries can be ranking eligible")
        if self.can_publish_authoritative_results and (
            self.decision is not CapabilitySummaryDecision.RIGOROUS
            or not self.authoritative
            or not self.executable
        ):
            raise ValueError("authoritative publication requires executable authoritative rigor")
        object.__setattr__(self, "degradations", degradations)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def build_capability_summary(
    report: PreflightReport, execution: ExecutionCapabilityPreflight
) -> CapabilitySummary:
    """Project data and engine preflight into one stable boundary value."""

    if not isinstance(report, PreflightReport):
        raise TypeError("report must be a PreflightReport")
    if not isinstance(execution, ExecutionCapabilityPreflight):
        raise TypeError("execution must be an ExecutionCapabilityPreflight")
    if execution.report_fingerprint != report.fingerprint:
        raise ValueError("execution preflight must reference this data report")
    data_gaps = tuple(
        sorted(
            f"{decision.requirement.instrument_id}:{gap}"
            for decision in report.decisions
            for gap in decision.gaps
        )
    )
    decision = (
        CapabilitySummaryDecision.UNSUPPORTED
        if execution.classification is PreflightClass.UNSUPPORTED
        else CapabilitySummaryDecision.DEGRADED
        if execution.classification is PreflightClass.DEGRADED
        else CapabilitySummaryDecision.RIGOROUS
    )
    executable = execution.executable
    ranking_eligible = report.ranking_eligible and executable and decision is CapabilitySummaryDecision.RIGOROUS
    can_publish = (
        execution.can_publish_authoritative_results
        and report.classification is PreflightClass.RIGOROUS
    )
    return CapabilitySummary(
        report_fingerprint=report.fingerprint,
        binding_fingerprint=execution.binding_fingerprint,
        decision=decision,
        data_gaps=data_gaps,
        execution_gaps=execution.gaps,
        degradations=report.degradations,
        ranking_eligible=ranking_eligible,
        executable=executable,
        authoritative=execution.authoritative,
        can_publish_authoritative_results=can_publish,
    )
