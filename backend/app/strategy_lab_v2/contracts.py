"""Immutable public domain contracts for reproducible strategy experiments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest

if TYPE_CHECKING:
    from app.strategy_lab_v2.capabilities import PreflightReport


class ProductClass(StrEnum):
    EQUITY = "equity"
    CRYPTO = "crypto"
    FUTURE = "future"
    OPTION = "option"
    FX = "fx"
    OTHER = "other"


class AdjustmentMode(StrEnum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"


class EventGranularity(StrEnum):
    TICK = "tick"
    TRADE = "trade"
    QUOTE = "quote"
    BAR = "bar"


class MetricBasis(StrEnum):
    GROSS = "gross"
    NET = "net"


class ArtifactRetention(StrEnum):
    PERMANENT_MANIFEST = "permanent_manifest"
    PINNED_INPUT = "pinned_input"
    PINNED_RESULT = "pinned_result"
    TIERED_RESULT = "tiered_result"
    EPHEMERAL = "ephemeral"


class StrategyPackageFormat(StrEnum):
    SOURCE_ARCHIVE = "source_archive"
    WHEEL = "wheel"


class AttemptState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ForwardState(StrEnum):
    CREATED = "created"
    WARMING_UP = "warming_up"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class CarryInMode(StrEnum):
    FLAT = "flat"
    SYNTHETIC_HISTORICAL = "synthetic_historical"


def _nonempty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _positive(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be a finite positive Decimal")


@dataclass(frozen=True, slots=True)
class StrategyDependency:
    distribution: str
    version: str
    artifact_digest: str

    def __post_init__(self) -> None:
        _nonempty(self.distribution, "distribution")
        _nonempty(self.version, "version")
        if any(token in self.version for token in ("*", ">", "<", "~", "^", "=", ",", ";", " ")):
            raise ValueError("strategy dependencies must use exact versions")
        require_sha256_digest(self.artifact_digest, field_name="artifact_digest")


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    strategy_id: str
    version_id: str
    sdk_version: str
    source_digest: str
    dependencies: tuple[StrategyDependency, ...] = ()
    parameter_schema: Mapping[str, Any] = field(default_factory=dict)
    default_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("strategy_id", "version_id", "sdk_version"):
            _nonempty(getattr(self, name), name)
        require_sha256_digest(self.source_digest, field_name="source_digest")
        names = [dependency.distribution.casefold() for dependency in self.dependencies]
        if len(set(names)) != len(names):
            raise ValueError("strategy dependencies must have unique distribution names")
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "default_parameters", freeze_json(self.default_parameters))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class StrategyPackage:
    package_id: str
    strategy_fingerprint: str
    package_format: StrategyPackageFormat
    archive_digest: str
    manifest_digest: str
    dependency_lock_digest: str
    archive_byte_length: int
    entrypoint: str
    sdk_version: str
    runtime_abi: str

    def __post_init__(self) -> None:
        _nonempty(self.package_id, "package_id")
        for name in (
            "strategy_fingerprint",
            "archive_digest",
            "manifest_digest",
            "dependency_lock_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.package_format, StrategyPackageFormat):
            raise TypeError("package_format must be a StrategyPackageFormat")
        if (
            not isinstance(self.archive_byte_length, int)
            or isinstance(self.archive_byte_length, bool)
            or self.archive_byte_length <= 0
        ):
            raise ValueError("archive_byte_length must be a positive integer")
        _nonempty(self.sdk_version, "sdk_version")
        _nonempty(self.runtime_abi, "runtime_abi")
        entrypoint_parts = self.entrypoint.split(":")
        if len(entrypoint_parts) != 2 or any(
            not part or any(not token.isidentifier() for token in part.split("."))
            for part in entrypoint_parts
        ):
            raise ValueError("entrypoint must use module.path:callable syntax")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PortfolioComponent:
    component_id: str
    strategy_fingerprint: str
    instrument_ids: tuple[str, ...]
    capital_weight: Decimal
    priority: int = 0

    def __post_init__(self) -> None:
        _nonempty(self.component_id, "component_id")
        require_sha256_digest(self.strategy_fingerprint, field_name="strategy_fingerprint")
        instruments = tuple(self.instrument_ids)
        if not instruments or any(not value.strip() for value in instruments):
            raise ValueError("a portfolio component must declare instruments")
        if len(set(instruments)) != len(instruments):
            raise ValueError("portfolio component instrument ids must be unique")
        if not isinstance(self.capital_weight, Decimal) or not self.capital_weight.is_finite():
            raise ValueError("capital_weight must be a finite Decimal")
        if self.capital_weight <= 0 or self.capital_weight > 1:
            raise ValueError("capital_weight must be greater than zero and at most one")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")
        object.__setattr__(self, "instrument_ids", instruments)


@dataclass(frozen=True, slots=True)
class PortfolioComposition:
    portfolio_id: str
    version_id: str
    initial_capital: Decimal
    base_currency: str
    components: tuple[PortfolioComponent, ...]
    rebalance_policy: Mapping[str, Any] = field(default_factory=dict)
    shared_risk_policy: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty(self.portfolio_id, "portfolio_id")
        _nonempty(self.version_id, "version_id")
        _positive(self.initial_capital, "initial_capital")
        if len(self.base_currency) != 3 or not self.base_currency.isalpha():
            raise ValueError("base_currency must be a three-letter code")
        if not self.components:
            raise ValueError("a portfolio must contain at least one component")
        component_ids = [item.component_id for item in self.components]
        if len(set(component_ids)) != len(component_ids):
            raise ValueError("portfolio component ids must be unique")
        if sum((item.capital_weight for item in self.components), Decimal(0)) > Decimal(1):
            raise ValueError("portfolio capital weights must not exceed one")
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(self, "base_currency", self.base_currency.upper())
        object.__setattr__(self, "rebalance_policy", freeze_json(self.rebalance_policy))
        object.__setattr__(self, "shared_risk_policy", freeze_json(self.shared_risk_policy))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class DataSeriesManifest:
    """Content and upstream-verified coverage references for one frozen series.

    The coverage evidence digest must identify the provider-platform attestation
    that checks observations against the declared calendar/series semantics. This
    engine-neutral contract cannot inspect that upstream evidence document itself.
    """

    instrument_id: str
    event_type: str
    event_granularity: EventGranularity
    timeframe: str
    session: str
    feed: str
    start: datetime
    end: datetime
    adjustment: AdjustmentMode
    corporate_action_semantics: str
    coverage_evidence_digest: str
    content_digest: str
    row_count: int

    def __post_init__(self) -> None:
        _nonempty(self.instrument_id, "instrument_id")
        _nonempty(self.event_type, "event_type")
        for name in ("timeframe", "session", "feed", "corporate_action_semantics"):
            _nonempty(getattr(self, name), name)
        _aware(self.start, "start")
        _aware(self.end, "end")
        if self.start >= self.end:
            raise ValueError("series start must be earlier than end")
        if not isinstance(self.event_granularity, EventGranularity):
            raise TypeError("event_granularity must be an EventGranularity")
        if not isinstance(self.adjustment, AdjustmentMode):
            raise TypeError("adjustment must be an AdjustmentMode")
        require_sha256_digest(self.coverage_evidence_digest, field_name="coverage_evidence_digest")
        require_sha256_digest(self.content_digest, field_name="content_digest")
        if (
            not isinstance(self.row_count, int)
            or isinstance(self.row_count, bool)
            or self.row_count <= 0
        ):
            raise ValueError("row_count must be positive")


@dataclass(frozen=True, slots=True)
class DataSnapshot:
    snapshot_id: str
    provider_snapshot_id: str
    preflight_report: PreflightReport
    series: tuple[DataSeriesManifest, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        from app.strategy_lab_v2.capabilities import PreflightClass, PreflightReport

        for name in ("snapshot_id", "provider_snapshot_id"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.preflight_report, PreflightReport):
            raise TypeError("a data snapshot requires a typed PreflightReport")
        if self.preflight_report.classification is PreflightClass.UNSUPPORTED:
            raise ValueError("unsupported preflight reports cannot freeze a data snapshot")
        _aware(self.created_at, "created_at")
        series = tuple(self.series)
        if not series:
            raise ValueError("a frozen data snapshot must contain at least one series")
        if any(not isinstance(item, DataSeriesManifest) for item in series):
            raise TypeError("data snapshot series must use DataSeriesManifest records")
        keys = [
            (
                item.instrument_id,
                item.event_type,
                item.event_granularity,
                item.timeframe,
                item.session,
                item.feed,
                item.adjustment,
                item.corporate_action_semantics,
                item.coverage_evidence_digest,
                item.start,
                item.end,
            )
            for item in series
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("data snapshot series keys must be unique")
        object.__setattr__(
            self,
            "series",
            tuple(
                sorted(
                    series,
                    key=lambda item: (
                        item.instrument_id,
                        item.event_type,
                        item.event_granularity.value,
                        item.timeframe,
                        item.session,
                        item.feed,
                        item.corporate_action_semantics,
                        item.adjustment.value,
                        item.start,
                        item.end,
                        item.coverage_evidence_digest,
                        item.content_digest,
                        item.row_count,
                    ),
                )
            ),
        )
        matched_series: set[int] = set()
        for decision in self.preflight_report.decisions:
            requirement = decision.requirement
            replacements = {item.field: item.substituted_value for item in decision.degradations}
            granularity = replacements.get("event_granularity", requirement.event_granularity.value)
            event_type = replacements.get("event_type", requirement.event_type)
            timeframe = replacements.get("timeframe", requirement.timeframe)
            adjustment = replacements.get("adjustment", requirement.adjustment.value)
            session = replacements.get("session", requirement.session)
            feed = replacements.get("feed", requirement.feed)
            action_semantics = replacements.get(
                "corporate_action_semantics", requirement.corporate_action_semantics
            )
            start = replacements.get("history_start")
            end = replacements.get("history_end")
            effective_start = (
                datetime.fromisoformat(start.replace("Z", "+00:00"))
                if start is not None
                else requirement.start
            )
            effective_end = (
                datetime.fromisoformat(end.replace("Z", "+00:00"))
                if end is not None
                else requirement.end
            )
            _aware(effective_start, "effective_start")
            _aware(effective_end, "effective_end")
            if effective_start >= effective_end:
                raise ValueError("effective preflight history must be a positive interval")
            candidates = [
                (index, item)
                for index, item in enumerate(self.series)
                if item.instrument_id == requirement.instrument_id
                and item.event_granularity.value == granularity
                and item.event_type == event_type
                and item.timeframe == timeframe
                and item.adjustment.value == adjustment
                and item.session == session
                and item.feed == feed
                and item.corporate_action_semantics == action_semantics
                and item.start < effective_end
                and item.end > effective_start
            ]
            ordered_candidates = sorted(candidates, key=lambda entry: (entry[1].start, entry[1].end))
            previous_end: datetime | None = None
            for _, item in ordered_candidates:
                if previous_end is not None and item.start < previous_end:
                    raise ValueError("frozen snapshot contains overlapping series coverage")
                previous_end = item.end
            cursor = effective_start
            for index, item in ordered_candidates:
                if item.end <= cursor:
                    continue
                if item.start > cursor:
                    break
                matched_series.add(index)
                cursor = max(cursor, item.end)
                if cursor >= effective_end:
                    break
            if cursor < effective_end:
                raise ValueError(
                    f"frozen snapshot does not cover preflight requirement for "
                    f"{requirement.instrument_id} {timeframe}"
                )
        if len(matched_series) != len(self.series):
            raise ValueError("frozen snapshot contains series outside its preflight requirements")

    @property
    def capability_contract_digest(self) -> str:
        return self.preflight_report.fingerprint

    @property
    def fingerprint(self) -> str:
        """Address data and execution capability, excluding receipt metadata."""

        return content_digest(
            {
                "capability_contract_digest": self.preflight_report.fingerprint,
                "series": self.series,
            }
        )


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    experiment_id: str
    portfolio_fingerprint: str
    strategy_fingerprints: tuple[str, ...]
    snapshot_fingerprint: str
    capability_contract_digest: str
    seed: int
    metric_definition_version: str
    engine_contract: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty(self.experiment_id, "experiment_id")
        for name in (
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "capability_contract_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        strategies = tuple(self.strategy_fingerprints)
        if not strategies:
            raise ValueError("an experiment must declare at least one strategy version")
        for strategy_fingerprint in strategies:
            require_sha256_digest(strategy_fingerprint, field_name="strategy_fingerprint")
        _nonempty(self.metric_definition_version, "metric_definition_version")
        object.__setattr__(self, "strategy_fingerprints", strategies)
        object.__setattr__(self, "engine_contract", freeze_json(self.engine_contract))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ScientificTrial:
    trial_id: str
    experiment_fingerprint: str
    snapshot_fingerprint: str
    preflight_report: PreflightReport
    parameter_set: Mapping[str, Any]
    scenario: Mapping[str, Any]
    seed: int

    def __post_init__(self) -> None:
        from app.strategy_lab_v2.capabilities import PreflightClass, PreflightReport

        require_sha256_digest(self.trial_id, field_name="trial_id")
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        require_sha256_digest(self.snapshot_fingerprint, field_name="snapshot_fingerprint")
        if not isinstance(self.preflight_report, PreflightReport):
            raise TypeError("a scientific trial requires a typed PreflightReport")
        if self.preflight_report.classification is PreflightClass.UNSUPPORTED:
            raise ValueError("unsupported preflight reports cannot create executable trials")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("trial seed must be an integer")
        object.__setattr__(self, "parameter_set", freeze_json(self.parameter_set))
        object.__setattr__(self, "scenario", freeze_json(self.scenario))
        if self.trial_id != content_digest(self._identity_payload()):
            raise ValueError("trial_id does not match the immutable scientific trial identity")

    @property
    def preflight_fingerprint(self) -> str:
        return self.preflight_report.fingerprint

    @property
    def ranking_eligible(self) -> bool:
        return self.preflight_report.ranking_eligible

    @property
    def preflight_label(self) -> str:
        return self.preflight_report.classification.value

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "experiment_fingerprint": self.experiment_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "preflight_fingerprint": self.preflight_report.fingerprint,
            "parameter_set": self.parameter_set,
            "scenario": self.scenario,
            "seed": self.seed,
        }

    @classmethod
    def create(
        cls,
        *,
        experiment_fingerprint: str,
        snapshot_fingerprint: str,
        preflight_report: PreflightReport,
        parameter_set: Mapping[str, Any],
        scenario: Mapping[str, Any] | None = None,
        seed: int = 0,
    ) -> ScientificTrial:
        identity = {
            "experiment_fingerprint": experiment_fingerprint,
            "snapshot_fingerprint": snapshot_fingerprint,
            "preflight_fingerprint": preflight_report.fingerprint,
            "parameter_set": parameter_set,
            "scenario": scenario or {},
            "seed": seed,
        }
        return cls(
            trial_id=content_digest(identity),
            experiment_fingerprint=experiment_fingerprint,
            snapshot_fingerprint=snapshot_fingerprint,
            preflight_report=preflight_report,
            parameter_set=parameter_set,
            scenario=scenario or {},
            seed=seed,
        )


@dataclass(frozen=True, slots=True)
class RunAttempt:
    attempt_id: str
    trial_id: str
    ordinal: int
    state: AttemptState
    created_at: datetime
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _nonempty(self.attempt_id, "attempt_id")
        _nonempty(self.trial_id, "trial_id")
        if (
            not isinstance(self.ordinal, int)
            or isinstance(self.ordinal, bool)
            or self.ordinal < 1
        ):
            raise ValueError("attempt ordinal must be positive")
        if not isinstance(self.state, AttemptState):
            raise TypeError("attempt state must be an AttemptState")
        _aware(self.created_at, "created_at")
        updated_at = self.updated_at or self.created_at
        _aware(updated_at, "updated_at")
        if updated_at < self.created_at:
            raise ValueError("attempt updated_at must not precede created_at")
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    content_digest: str
    byte_length: int
    media_type: str
    schema_version: str
    storage_key: str
    retention_class: ArtifactRetention = ArtifactRetention.PERMANENT_MANIFEST

    def __post_init__(self) -> None:
        require_sha256_digest(self.content_digest, field_name="content_digest")
        if self.byte_length < 0:
            raise ValueError("byte_length must not be negative")
        if self.storage_key != self.content_digest:
            raise ValueError("artifact storage_key must equal its content digest")
        for name in ("media_type", "schema_version"):
            _nonempty(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class MetricValue:
    name: str
    value: Decimal | None
    unit: str
    definition_version: str
    basis: MetricBasis
    sample_size: int
    annualization_basis: str | None = None
    null_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("name", "unit", "definition_version"):
            _nonempty(getattr(self, name), name)
        if (
            not isinstance(self.sample_size, int)
            or isinstance(self.sample_size, bool)
            or self.sample_size < 0
        ):
            raise ValueError("sample_size must not be negative")
        if self.value is None:
            if not self.null_reason or not self.null_reason.strip():
                raise ValueError("a null metric value must include a null_reason")
        elif (
            not isinstance(self.value, Decimal)
            or not self.value.is_finite()
            or self.null_reason is not None
        ):
            raise ValueError("metric values must be finite and cannot have a null_reason")


@dataclass(frozen=True, slots=True)
class MetricSet:
    metric_set_id: str
    trial_id: str
    attempt_id: str
    definition_version: str
    values: tuple[MetricValue, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("metric_set_id", "trial_id", "attempt_id", "definition_version"):
            _nonempty(getattr(self, name), name)
        if not self.values:
            raise ValueError("a metric set must contain values")
        keys = [(item.name, item.basis) for item in self.values]
        if len(set(keys)) != len(keys):
            raise ValueError("metric names must be unique within a basis")
        if any(item.definition_version != self.definition_version for item in self.values):
            raise ValueError("metric values must match their metric-set definition version")
        _aware(self.created_at, "created_at")
        object.__setattr__(self, "values", tuple(self.values))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class RunResultManifest:
    """Immutable execution provenance plus content-addressed result references."""

    trial: ScientificTrial
    attempt: RunAttempt
    strategy_packages: tuple[StrategyPackage, ...]
    portfolio: PortfolioComposition
    snapshot: DataSnapshot
    engine_name: str
    engine_version: str
    engine_build_digest: str
    dependency_catalog_digest: str
    assumptions_digest: str
    metric_set: MetricSet
    output_artifacts: tuple[ArtifactManifest, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for name, record, record_type in (
            ("trial", self.trial, ScientificTrial),
            ("attempt", self.attempt, RunAttempt),
            ("portfolio", self.portfolio, PortfolioComposition),
            ("snapshot", self.snapshot, DataSnapshot),
            ("metric_set", self.metric_set, MetricSet),
        ):
            if not isinstance(record, record_type):
                raise TypeError(f"result manifest {name} must use a typed {record_type.__name__}")
        if self.attempt.state is not AttemptState.SUCCEEDED:
            raise ValueError("a result manifest requires a succeeded run attempt")
        if self.attempt.trial_id != self.trial.trial_id:
            raise ValueError("result attempt must reference its scientific trial")
        if self.metric_set.trial_id != self.trial.trial_id:
            raise ValueError("result metric set must reference its scientific trial")
        if self.metric_set.attempt_id != self.attempt.attempt_id:
            raise ValueError("result metric set must reference its successful attempt")
        if self.snapshot.fingerprint != self.trial.snapshot_fingerprint:
            raise ValueError("result snapshot must match its scientific trial")
        if self.snapshot.preflight_report.fingerprint != self.trial.preflight_fingerprint:
            raise ValueError("result snapshot capability report must match its scientific trial")
        require_sha256_digest(self.engine_build_digest, field_name="engine_build_digest")
        require_sha256_digest(self.dependency_catalog_digest, field_name="dependency_catalog_digest")
        require_sha256_digest(self.assumptions_digest, field_name="assumptions_digest")
        for name in ("engine_name", "engine_version"):
            _nonempty(getattr(self, name), name)
        packages = tuple(self.strategy_packages)
        artifacts = tuple(self.output_artifacts)
        if any(not isinstance(item, StrategyPackage) for item in packages):
            raise TypeError("result strategy packages must use StrategyPackage records")
        if any(not isinstance(item, ArtifactManifest) for item in artifacts):
            raise TypeError("result outputs must use ArtifactManifest records")
        package_strategies = [item.strategy_fingerprint for item in packages]
        portfolio_strategies = {
            item.strategy_fingerprint for item in self.portfolio.components
        }
        if not packages or set(package_strategies) != portfolio_strategies:
            raise ValueError("result packages must match the portfolio strategy versions")
        if len(package_strategies) != len(set(package_strategies)):
            raise ValueError("result strategy packages must be unique by strategy version")
        if not artifacts:
            raise ValueError("result provenance must reference at least one output artifact")
        artifact_digests = [item.content_digest for item in artifacts]
        if len(artifact_digests) != len(set(artifact_digests)):
            raise ValueError("result output artifact digests must be unique")
        _aware(self.created_at, "created_at")
        packages = tuple(sorted(packages, key=lambda item: item.strategy_fingerprint))
        artifacts = tuple(sorted(artifacts, key=lambda item: item.content_digest))
        object.__setattr__(self, "strategy_packages", packages)
        object.__setattr__(self, "output_artifacts", artifacts)

    @property
    def experiment_fingerprint(self) -> str:
        return self.trial.experiment_fingerprint

    @property
    def trial_id(self) -> str:
        return self.trial.trial_id

    @property
    def attempt_id(self) -> str:
        return self.attempt.attempt_id

    @property
    def strategy_fingerprints(self) -> tuple[str, ...]:
        return tuple(item.strategy_fingerprint for item in self.strategy_packages)

    @property
    def strategy_package_fingerprints(self) -> tuple[str, ...]:
        return tuple(item.fingerprint for item in self.strategy_packages)

    @property
    def portfolio_fingerprint(self) -> str:
        return self.portfolio.fingerprint

    @property
    def snapshot_fingerprint(self) -> str:
        return self.snapshot.fingerprint

    @property
    def capability_contract_digest(self) -> str:
        return self.trial.preflight_fingerprint

    @property
    def seed(self) -> int:
        return self.trial.seed

    @property
    def metric_definition_version(self) -> str:
        return self.metric_set.definition_version

    @property
    def metric_set_fingerprint(self) -> str:
        return self.metric_set.fingerprint

    @property
    def output_artifact_digests(self) -> tuple[str, ...]:
        return tuple(item.content_digest for item in self.output_artifacts)

    @property
    def reproduction_fingerprint(self) -> str:
        return content_digest(
            {
                "experiment_fingerprint": self.experiment_fingerprint,
                "trial_id": self.trial_id,
                "strategy_fingerprints": self.strategy_fingerprints,
                "strategy_package_fingerprints": self.strategy_package_fingerprints,
                "portfolio_fingerprint": self.portfolio_fingerprint,
                "snapshot_fingerprint": self.snapshot_fingerprint,
                "capability_contract_digest": self.capability_contract_digest,
                "engine_name": self.engine_name,
                "engine_version": self.engine_version,
                "engine_build_digest": self.engine_build_digest,
                "dependency_catalog_digest": self.dependency_catalog_digest,
                "assumptions_digest": self.assumptions_digest,
                "seed": self.seed,
                "metric_definition_version": self.metric_definition_version,
            }
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardInstance:
    instance_id: str
    portfolio_fingerprint: str
    warmup_snapshot_fingerprint: str
    carry_in_mode: CarryInMode
    state: ForwardState
    last_event_id: str | None
    last_event_sequence: int
    correction_count: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _nonempty(self.instance_id, "instance_id")
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        require_sha256_digest(
            self.warmup_snapshot_fingerprint, field_name="warmup_snapshot_fingerprint"
        )
        if self.last_event_sequence < 0 or self.correction_count < 0:
            raise ValueError("event sequence and correction count must be non-negative")
        if self.last_event_id is None and self.last_event_sequence > 0:
            raise ValueError("a forward event sequence requires its last_event_id")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
