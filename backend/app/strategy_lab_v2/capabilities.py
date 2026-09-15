"""Capability-cell preflight with fail-closed and explicit degraded modes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass


class PreflightClass(StrEnum):
    RIGOROUS = "rigorous"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    instrument_id: str
    product_class: ProductClass
    event_granularity: EventGranularity
    event_type: str
    timeframe: str
    start: datetime
    end: datetime
    adjustment: AdjustmentMode
    session: str
    feed: str
    execution_model: str
    account_model: str
    corporate_action_semantics: str

    def __post_init__(self) -> None:
        for name in (
            "instrument_id",
            "event_type",
            "timeframe",
            "session",
            "feed",
            "execution_model",
            "account_model",
            "corporate_action_semantics",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.product_class, ProductClass):
            raise TypeError("product_class must be a ProductClass")
        if not isinstance(self.event_granularity, EventGranularity):
            raise TypeError("event_granularity must be an EventGranularity")
        if not isinstance(self.adjustment, AdjustmentMode):
            raise TypeError("adjustment must be an AdjustmentMode")
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("end must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("required history start must precede end")


@dataclass(frozen=True, slots=True)
class CapabilityCell:
    instrument_id: str
    product_class: ProductClass
    event_granularities: frozenset[EventGranularity]
    event_types: frozenset[str]
    timeframes: frozenset[str]
    adjustments: frozenset[AdjustmentMode]
    sessions: frozenset[str]
    feeds: frozenset[str]
    execution_models: frozenset[str]
    account_models: frozenset[str]
    corporate_action_semantics: frozenset[str]
    history_start: datetime
    history_end: datetime
    evidence_digest: str

    def __post_init__(self) -> None:
        for name in ("instrument_id", "evidence_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.product_class, ProductClass):
            raise TypeError("product_class must be a ProductClass")
        if self.history_start.tzinfo is None or self.history_start.utcoffset() is None:
            raise ValueError("history_start must be timezone-aware")
        if self.history_end.tzinfo is None or self.history_end.utcoffset() is None:
            raise ValueError("history_end must be timezone-aware")
        if self.history_start >= self.history_end:
            raise ValueError("capability history must have a positive interval")
        if any(
            not values
            for values in (
                self.event_granularities,
                self.event_types,
                self.timeframes,
                self.adjustments,
                self.sessions,
                self.feeds,
                self.execution_models,
                self.account_models,
                self.corporate_action_semantics,
            )
        ):
            raise ValueError("capability cells must declare non-empty supported values")
        if any(not isinstance(item, EventGranularity) for item in self.event_granularities):
            raise TypeError("event_granularities must contain EventGranularity values")
        if any(not isinstance(item, str) or not item.strip() for item in self.event_types):
            raise ValueError("event_types must contain non-empty strings")
        if any(not isinstance(item, AdjustmentMode) for item in self.adjustments):
            raise TypeError("adjustments must contain AdjustmentMode values")
        if any(
            not isinstance(item, str) or not item.strip()
            for collection in (
                self.timeframes,
                self.sessions,
                self.feeds,
                self.execution_models,
                self.account_models,
                self.corporate_action_semantics,
            )
            for item in collection
        ):
            raise ValueError("capability cell string values must not be empty")
        require_sha256_digest(self.evidence_digest, field_name="evidence_digest")
        for name in (
            "event_granularities",
            "event_types",
            "timeframes",
            "adjustments",
            "sessions",
            "feeds",
            "execution_models",
            "account_models",
            "corporate_action_semantics",
        ):
            object.__setattr__(self, name, frozenset(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class Degradation:
    instrument_id: str
    field: str
    substituted_value: str
    reason: str

    def __post_init__(self) -> None:
        allowed_fields = {
            "event_granularity",
            "event_type",
            "timeframe",
            "history_start",
            "history_end",
            "adjustment",
            "session",
            "feed",
            "execution_model",
            "account_model",
            "corporate_action_semantics",
        }
        if not self.instrument_id.strip() or self.field not in allowed_fields:
            raise ValueError("degradation must identify an instrument and supported field")
        if not self.substituted_value.strip() or not self.reason.strip():
            raise ValueError("degradation requires a replacement value and reason")


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    requirement: CapabilityRequirement
    classification: PreflightClass
    evidence_digest: str | None
    gaps: tuple[str, ...]
    degradations: tuple[Degradation, ...]
    ranking_eligible: bool

    def __post_init__(self) -> None:
        if not isinstance(self.classification, PreflightClass):
            raise TypeError("classification must be a PreflightClass")
        gaps = tuple(self.gaps)
        degradations = tuple(self.degradations)
        if any(not isinstance(item, str) or not item.strip() for item in gaps):
            raise ValueError("capability gaps must be non-empty strings")
        if len(set(gaps)) != len(gaps):
            raise ValueError("capability gaps must be unique")
        if any(not isinstance(item, Degradation) for item in degradations):
            raise TypeError("capability decision degradations must be typed records")
        degradation_fields = [item.field for item in degradations]
        if len(set(degradation_fields)) != len(degradation_fields):
            raise ValueError("decision degradations must be unique by field")
        if any(item.instrument_id != self.requirement.instrument_id for item in degradations):
            raise ValueError("decision degradations must belong to its requirement instrument")
        if {item.field for item in degradations} - set(gaps):
            raise ValueError("decision degradations must correspond to capability gaps")
        object.__setattr__(self, "gaps", gaps)
        object.__setattr__(self, "degradations", degradations)
        if self.evidence_digest is not None:
            require_sha256_digest(self.evidence_digest, field_name="evidence_digest")
        if self.classification is PreflightClass.RIGOROUS and (
            self.gaps or not self.ranking_eligible or self.degradations
        ):
            raise ValueError("rigorous decisions must be gap-free and ranking eligible")
        if self.classification in {PreflightClass.RIGOROUS, PreflightClass.DEGRADED} and (
            self.evidence_digest is None
        ):
            raise ValueError("executable decisions require capability evidence")
        if self.classification is PreflightClass.DEGRADED and (
            not self.gaps
            or self.ranking_eligible
            or {item.field for item in self.degradations} != set(self.gaps)
        ):
            raise ValueError("degraded decisions require explicit substitutions for every gap")
        if self.classification is PreflightClass.UNSUPPORTED and (
            not self.gaps or self.ranking_eligible
        ):
            raise ValueError("unsupported decisions require gaps and cannot be ranking eligible")


@dataclass(frozen=True, slots=True)
class PreflightReport:
    decisions: tuple[CapabilityDecision, ...]
    fingerprint: str
    allow_degraded: bool = False
    degradations: tuple[Degradation, ...] = ()

    def __post_init__(self) -> None:
        decisions = tuple(self.decisions)
        degradations = tuple(self.degradations)
        if not isinstance(self.allow_degraded, bool):
            raise TypeError("allow_degraded must be a boolean")
        if any(not isinstance(item, CapabilityDecision) for item in decisions):
            raise TypeError("preflight decisions must use CapabilityDecision records")
        if any(not isinstance(item, Degradation) for item in degradations):
            raise TypeError("preflight degradations must use Degradation records")
        if not decisions:
            raise ValueError("preflight reports require decisions")
        requirement_keys = [item.requirement for item in decisions]
        if len(set(requirement_keys)) != len(requirement_keys):
            raise ValueError("preflight decisions must have unique requirements")
        degradation_keys = [(item.instrument_id, item.field) for item in degradations]
        if len(set(degradation_keys)) != len(degradation_keys):
            raise ValueError("preflight degradations must be unique by instrument and field")
        decision_degradations = {
            (item.instrument_id, item.field)
            for decision in decisions
            for item in decision.degradations
        }
        if decision_degradations != set(degradation_keys):
            raise ValueError("preflight degradations must match the decision substitutions")
        if not self.allow_degraded and any(
            item.classification is PreflightClass.DEGRADED for item in decisions
        ):
            raise ValueError("degraded decisions require allow_degraded")
        require_sha256_digest(self.fingerprint, field_name="preflight fingerprint")
        expected = content_digest(
            {
                "decisions": decisions,
                "allow_degraded": self.allow_degraded,
                "degradations": degradations,
            }
        )
        if self.fingerprint != expected:
            raise ValueError("preflight fingerprint does not match its decisions")
        object.__setattr__(self, "decisions", decisions)
        object.__setattr__(self, "degradations", degradations)

    @property
    def classification(self) -> PreflightClass:
        classes = {item.classification for item in self.decisions}
        if PreflightClass.UNSUPPORTED in classes:
            return PreflightClass.UNSUPPORTED
        if PreflightClass.DEGRADED in classes:
            return PreflightClass.DEGRADED
        return PreflightClass.RIGOROUS

    @property
    def executable(self) -> bool:
        return self.classification is not PreflightClass.UNSUPPORTED

    @property
    def ranking_eligible(self) -> bool:
        return self.executable and all(item.ranking_eligible for item in self.decisions)


def _gaps(requirement: CapabilityRequirement, cell: CapabilityCell) -> tuple[str, ...]:
    checks = (
        ("event_granularity", requirement.event_granularity in cell.event_granularities),
        ("event_type", requirement.event_type in cell.event_types),
        ("timeframe", requirement.timeframe in cell.timeframes),
        ("history_start", requirement.start >= cell.history_start),
        ("history_end", requirement.end <= cell.history_end),
        ("adjustment", requirement.adjustment in cell.adjustments),
        ("session", requirement.session in cell.sessions),
        ("feed", requirement.feed in cell.feeds),
        ("execution_model", requirement.execution_model in cell.execution_models),
        ("account_model", requirement.account_model in cell.account_models),
        (
            "corporate_action_semantics",
            requirement.corporate_action_semantics in cell.corporate_action_semantics,
        ),
    )
    return tuple(name for name, supported in checks if not supported)


def _substitution_is_supported(degradation: Degradation, cell: CapabilityCell) -> bool:
    field_values = {
        "event_granularity": {item.value for item in cell.event_granularities},
        "event_type": cell.event_types,
        "timeframe": cell.timeframes,
        "adjustment": {item.value for item in cell.adjustments},
        "session": cell.sessions,
        "feed": cell.feeds,
        "execution_model": cell.execution_models,
        "account_model": cell.account_models,
        "corporate_action_semantics": cell.corporate_action_semantics,
    }
    if degradation.field in field_values:
        return degradation.substituted_value in field_values[degradation.field]
    try:
        replacement = datetime.fromisoformat(degradation.substituted_value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if replacement.tzinfo is None or replacement.utcoffset() is None:
        return False
    if degradation.field == "history_start":
        return replacement == cell.history_start
    if degradation.field == "history_end":
        return replacement == cell.history_end
    return False


def preflight_capabilities(
    requirements: tuple[CapabilityRequirement, ...],
    cells: tuple[CapabilityCell, ...],
    *,
    allow_degraded: bool = False,
    degradations: tuple[Degradation, ...] = (),
) -> PreflightReport:
    """Evaluate every required capability; gaps fail closed unless fully declared."""

    requirements = tuple(requirements)
    cells = tuple(cells)
    degradations = tuple(degradations)
    if not requirements:
        raise ValueError("preflight requires at least one capability requirement")
    if len(set(requirements)) != len(requirements):
        raise ValueError("capability requirements must not contain duplicates")
    requirements = tuple(
        sorted(
            requirements,
            key=lambda item: (
                item.instrument_id,
                item.product_class.value,
                item.event_granularity.value,
                item.event_type,
                item.timeframe,
                item.start,
                item.end,
                item.adjustment.value,
                item.session,
                item.feed,
                item.execution_model,
                item.account_model,
                item.corporate_action_semantics,
            ),
        )
    )
    degradations = tuple(
        sorted(
            degradations,
            key=lambda item: (
                item.instrument_id,
                item.field,
                item.substituted_value,
                item.reason,
            ),
        )
    )

    decisions: list[CapabilityDecision] = []
    used_degradations: set[tuple[str, str]] = set()
    degradation_keys = [(item.instrument_id, item.field) for item in degradations]
    if len(set(degradation_keys)) != len(degradation_keys):
        raise ValueError("only one degradation may be declared for an instrument field")

    for requirement in requirements:
        matching_cells = tuple(
            item
            for item in cells
            if item.instrument_id == requirement.instrument_id
            and item.product_class == requirement.product_class
        )
        if not matching_cells:
            decisions.append(
                CapabilityDecision(
                    requirement=requirement,
                    classification=PreflightClass.UNSUPPORTED,
                    evidence_digest=None,
                    gaps=("instrument_coverage",),
                    degradations=(),
                    ranking_eligible=False,
                )
            )
            continue

        candidates = []
        for cell in matching_cells:
            gaps = _gaps(requirement, cell)
            declared = tuple(
                item
                for item in degradations
                if item.instrument_id == requirement.instrument_id and item.field in gaps
            )
            complete_degradation = bool(gaps) and {item.field for item in declared} == set(gaps)
            classification = (
                PreflightClass.RIGOROUS
                if not gaps
                else PreflightClass.DEGRADED
                if allow_degraded and complete_degradation
                else PreflightClass.UNSUPPORTED
            )
            rank = {
                PreflightClass.RIGOROUS: 0,
                PreflightClass.DEGRADED: 1,
                PreflightClass.UNSUPPORTED: 2,
            }[classification]
            candidates.append(
                (
                    (rank, len(gaps), cell.evidence_digest, content_digest(cell)),
                    cell,
                    gaps,
                    declared,
                    classification,
                )
            )

        _, cell, gaps, declared, classification = min(candidates, key=lambda item: item[0])
        invalid = tuple(item for item in declared if not _substitution_is_supported(item, cell))
        if invalid:
            raise ValueError(
                "degradation substitutions must match values supported by the selected cell: "
                + ", ".join(f"{item.instrument_id}.{item.field}" for item in invalid)
            )
        used_degradations.update((item.instrument_id, item.field) for item in declared)
        decisions.append(
            CapabilityDecision(
                requirement=requirement,
                classification=classification,
                evidence_digest=cell.evidence_digest,
                gaps=gaps,
                degradations=declared,
                ranking_eligible=classification is PreflightClass.RIGOROUS,
            )
        )

    unused = set(degradation_keys) - used_degradations
    if unused:
        raise ValueError(f"degradations do not correspond to capability gaps: {sorted(unused)}")
    immutable_decisions = tuple(decisions)
    fingerprint = content_digest(
        {
            "decisions": immutable_decisions,
            "allow_degraded": allow_degraded,
            "degradations": degradations,
        }
    )
    return PreflightReport(
        decisions=immutable_decisions,
        fingerprint=fingerprint,
        allow_degraded=allow_degraded,
        degradations=degradations,
    )
