"""Immutable public domain contracts for reproducible strategy experiments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from app.strategy_lab_v2.canonical import (
    canonical_json,
    content_digest,
    freeze_json,
    require_sha256_digest,
)
from app.strategy_lab_v2.decimal_math import deterministic_decimal_math
from app.strategy_lab_v2.observations import ObservationPoint
from app.strategy_lab_v2.rebalance import CalendarRebalancePolicy

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


METRIC_CALCULATION_CONTRACT_VERSION = "strategy-lab.metric-calculation.v1"


class TrialSeedPolicy(StrEnum):
    PER_CANDIDATE = "per_candidate"
    SHARED_PER_SCENARIO_REPLICATE = "shared_per_scenario_replicate"


class SensitivityEvidenceLevel(StrEnum):
    UNPAIRED = "unpaired"
    SHARED_SEED_ONLY = "shared_seed_only"
    PAIRING_CLAIM_UNVERIFIED = "pairing_claim_unverified"
    VERIFIED_PAIRED = "verified_paired"


TRIAL_SEED_DERIVATION_VERSION = "strategy-lab.trial-seed.sha256-canonical-63.v1"
EXPLICIT_SEED_DERIVATION_VERSION = "explicit-seed.v1"


class TargetConflictPolicy(StrEnum):
    REJECT = "reject"
    HIGHEST_PRIORITY = "highest_priority"
    SUM_COMPONENT_TARGETS = "sum_component_targets"


class RiskExposureMeasure(StrEnum):
    SIGNED_BASE_NOTIONAL = "signed_base_notional"
    SIGNED_CONTRACT_NOTIONAL = "signed_contract_notional"
    DELTA_ADJUSTED_BASE_NOTIONAL = "delta_adjusted_base_notional"
    SIGNED_BASE_CURRENCY_NOTIONAL = "signed_base_currency_notional"


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
        dependencies = tuple(self.dependencies)
        if any(not isinstance(item, StrategyDependency) for item in dependencies):
            raise TypeError("strategy dependencies must contain StrategyDependency values")
        names = [dependency.distribution.casefold() for dependency in dependencies]
        if len(set(names)) != len(names):
            raise ValueError("strategy dependencies must have unique distribution names")
        object.__setattr__(
            self,
            "dependencies",
            tuple(
                sorted(
                    dependencies,
                    key=lambda item: (
                        item.distribution.casefold(),
                        item.version,
                        item.artifact_digest,
                    ),
                )
            ),
        )
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
        if (
            not isinstance(self.priority, int)
            or isinstance(self.priority, bool)
            or self.priority < 0
        ):
            raise ValueError("priority must be a non-negative integer")
        object.__setattr__(self, "instrument_ids", instruments)


@dataclass(frozen=True, slots=True)
class ProductRiskModel:
    product_class: ProductClass
    exposure_measure: RiskExposureMeasure
    definition_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.product_class, ProductClass):
            raise TypeError("product_class must be a ProductClass")
        if not isinstance(self.exposure_measure, RiskExposureMeasure):
            raise TypeError("exposure_measure must be a RiskExposureMeasure")
        require_sha256_digest(self.definition_digest, field_name="definition_digest")


CASH_EQUITY_NOTIONAL_RISK_MODEL = ProductRiskModel(
    product_class=ProductClass.EQUITY,
    exposure_measure=RiskExposureMeasure.SIGNED_BASE_NOTIONAL,
    definition_digest=content_digest(
        {"model": "cash-equity-market-value-as-signed-base-notional", "version": 1}
    ),
)

CRYPTO_SPOT_NOTIONAL_RISK_MODEL = ProductRiskModel(
    product_class=ProductClass.CRYPTO,
    exposure_measure=RiskExposureMeasure.SIGNED_BASE_NOTIONAL,
    definition_digest=content_digest(
        {"model": "crypto-spot-market-value-as-signed-base-notional", "version": 1}
    ),
)

FUTURE_CONTRACT_NOTIONAL_RISK_MODEL = ProductRiskModel(
    product_class=ProductClass.FUTURE,
    exposure_measure=RiskExposureMeasure.SIGNED_CONTRACT_NOTIONAL,
    definition_digest=content_digest(
        {"model": "future-contract-notional-as-signed-base-notional", "version": 1}
    ),
)

OPTION_DELTA_NOTIONAL_RISK_MODEL = ProductRiskModel(
    product_class=ProductClass.OPTION,
    exposure_measure=RiskExposureMeasure.DELTA_ADJUSTED_BASE_NOTIONAL,
    definition_digest=content_digest(
        {"model": "option-delta-adjusted-underlying-notional", "version": 1}
    ),
)

FX_BASE_NOTIONAL_RISK_MODEL = ProductRiskModel(
    product_class=ProductClass.FX,
    exposure_measure=RiskExposureMeasure.SIGNED_BASE_CURRENCY_NOTIONAL,
    definition_digest=content_digest(
        {"model": "fx-pair-base-currency-notional", "version": 1}
    ),
)

SUPPORTED_PRODUCT_RISK_MODELS = (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    CRYPTO_SPOT_NOTIONAL_RISK_MODEL,
    FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
    OPTION_DELTA_NOTIONAL_RISK_MODEL,
    FX_BASE_NOTIONAL_RISK_MODEL,
)


@dataclass(frozen=True, slots=True)
class SharedRiskPolicy:
    """Versioned limits applied to component-attributed account exposure."""

    max_gross_exposure_fraction: Decimal = Decimal("1.0")
    max_net_exposure_fraction: Decimal = Decimal("1.0")
    max_instrument_gross_exposure_fraction: Decimal = Decimal("1.0")
    max_component_gross_exposure_fraction: Decimal = Decimal("1.0")
    max_component_leverage: Decimal = Decimal("1.0")
    max_open_instruments: int | None = None
    allow_short_positions: bool = False
    target_conflict_policy: TargetConflictPolicy = TargetConflictPolicy.REJECT
    risk_models: tuple[ProductRiskModel, ...] = ()
    definition_version: str = "strategy-lab.shared-risk.v1"

    def __post_init__(self) -> None:
        for name in (
            "max_gross_exposure_fraction",
            "max_instrument_gross_exposure_fraction",
            "max_component_gross_exposure_fraction",
            "max_component_leverage",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be a finite positive Decimal")
        if (
            not isinstance(self.max_net_exposure_fraction, Decimal)
            or not self.max_net_exposure_fraction.is_finite()
            or self.max_net_exposure_fraction < 0
        ):
            raise ValueError("max_net_exposure_fraction must be a finite non-negative Decimal")
        if self.max_open_instruments is not None and (
            not isinstance(self.max_open_instruments, int)
            or isinstance(self.max_open_instruments, bool)
            or self.max_open_instruments < 1
        ):
            raise ValueError("max_open_instruments must be a positive integer when provided")
        if not isinstance(self.allow_short_positions, bool):
            raise TypeError("allow_short_positions must be a bool")
        if not isinstance(self.target_conflict_policy, TargetConflictPolicy):
            raise TypeError("target_conflict_policy must be a TargetConflictPolicy")
        risk_models = tuple(self.risk_models)
        if any(not isinstance(item, ProductRiskModel) for item in risk_models):
            raise TypeError("risk_models must contain ProductRiskModel values")
        product_classes = [item.product_class for item in risk_models]
        if len(product_classes) != len(set(product_classes)):
            raise ValueError("shared risk policy may declare one risk model per product class")
        object.__setattr__(
            self,
            "risk_models",
            tuple(sorted(risk_models, key=lambda item: item.product_class.value)),
        )
        _nonempty(self.definition_version, "definition_version")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PortfolioComposition:
    portfolio_id: str
    version_id: str
    initial_capital: Decimal
    base_currency: str
    components: tuple[PortfolioComponent, ...]
    rebalance_policy: CalendarRebalancePolicy | None = None
    shared_risk_policy: SharedRiskPolicy = field(default_factory=SharedRiskPolicy)

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        _nonempty(self.portfolio_id, "portfolio_id")
        _nonempty(self.version_id, "version_id")
        _positive(self.initial_capital, "initial_capital")
        if (
            not isinstance(self.base_currency, str)
            or len(self.base_currency) != 3
            or not self.base_currency.isascii()
            or not self.base_currency.isalpha()
        ):
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
        if self.rebalance_policy is not None and not isinstance(
            self.rebalance_policy, CalendarRebalancePolicy
        ):
            raise TypeError("rebalance_policy must be a CalendarRebalancePolicy or None")
        if not isinstance(self.shared_risk_policy, SharedRiskPolicy):
            raise TypeError("shared_risk_policy must be a SharedRiskPolicy")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    @property
    @deterministic_decimal_math
    def unallocated_capital_weight(self) -> Decimal:
        """Share of current account equity not assigned to strategy components."""

        return Decimal(1) - sum((item.capital_weight for item in self.components), Decimal(0))


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
            ordered_candidates = sorted(
                candidates, key=lambda entry: (entry[1].start, entry[1].end)
            )
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
        if len(set(strategies)) != len(strategies):
            raise ValueError("experiment strategy fingerprints must be unique")
        _nonempty(self.metric_definition_version, "metric_definition_version")
        object.__setattr__(self, "strategy_fingerprints", tuple(sorted(strategies)))
        object.__setattr__(self, "engine_contract", freeze_json(self.engine_contract))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class TrialRandomization:
    """Reproducible seed assignment; shared seeds alone do not imply paired draws."""

    master_seed: int
    seed: int
    policy: TrialSeedPolicy
    replicate_index: int
    scope_fingerprint: str | None
    seed_group_fingerprint: str | None
    replicate_count: int
    derivation_version: str

    def __post_init__(self) -> None:
        for name, value in (("master_seed", self.master_seed), ("seed", self.seed)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
        if not isinstance(self.policy, TrialSeedPolicy):
            raise TypeError("policy must be a TrialSeedPolicy")
        if (
            not isinstance(self.replicate_index, int)
            or isinstance(self.replicate_index, bool)
            or self.replicate_index < 0
        ):
            raise ValueError("replicate_index must be a non-negative integer")
        if (
            not isinstance(self.replicate_count, int)
            or isinstance(self.replicate_count, bool)
            or self.replicate_count < 1
        ):
            raise ValueError("replicate_count must be a positive integer")
        if self.replicate_index >= self.replicate_count:
            raise ValueError("replicate_index must be less than replicate_count")
        if self.scope_fingerprint is not None:
            require_sha256_digest(self.scope_fingerprint, field_name="scope_fingerprint")
        if self.seed_group_fingerprint is not None:
            require_sha256_digest(self.seed_group_fingerprint, field_name="seed_group_fingerprint")
        if self.policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE and (
            self.scope_fingerprint is None or self.seed_group_fingerprint is None
        ):
            raise ValueError("shared-seed assignments require scope and seed-group fingerprints")
        _nonempty(self.derivation_version, "derivation_version")
        if self.derivation_version == EXPLICIT_SEED_DERIVATION_VERSION:
            if (
                self.seed_group_fingerprint is not None
                or self.scope_fingerprint is not None
                or self.policy is not TrialSeedPolicy.PER_CANDIDATE
                or self.replicate_index != 0
                or self.replicate_count != 1
                or self.master_seed != self.seed
            ):
                raise ValueError("explicit-seed provenance cannot claim a derived schedule")
        elif self.derivation_version == TRIAL_SEED_DERIVATION_VERSION:
            if self.seed_group_fingerprint is None:
                raise ValueError("derived seed provenance requires a seed-group fingerprint")
            expected_seed = int(self.seed_group_fingerprint.split(":", 1)[1][:16], 16) & (
                (1 << 63) - 1
            )
            if self.seed != expected_seed:
                raise ValueError("trial seed does not match its seed-group fingerprint")
        else:
            raise ValueError("unsupported trial seed derivation version")

    @property
    def has_schedule_provenance(self) -> bool:
        return (
            self.scope_fingerprint is not None
            or self.policy is not TrialSeedPolicy.PER_CANDIDATE
            or self.replicate_index != 0
            or self.replicate_count != 1
        )


@dataclass(frozen=True, slots=True)
class EvaluationWindow:
    """Explicit evaluation interval, optionally preceded by immutable warm-up."""

    start: datetime
    end: datetime
    purpose: str
    warmup_start: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("start", "end"):
            _aware(getattr(self, name), name)
        if self.end <= self.start:
            raise ValueError("evaluation window end must be after start")
        if self.warmup_start is not None:
            _aware(self.warmup_start, "warmup_start")
            if self.warmup_start > self.start:
                raise ValueError("evaluation warmup_start must not be after start")
        _nonempty(self.purpose, "purpose")
        object.__setattr__(self, "start", self.start.astimezone(UTC))
        object.__setattr__(self, "end", self.end.astimezone(UTC))
        if self.warmup_start is not None:
            object.__setattr__(self, "warmup_start", self.warmup_start.astimezone(UTC))

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
    randomization: TrialRandomization
    evaluation_window: EvaluationWindow | None = None

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
        if not isinstance(self.randomization, TrialRandomization):
            raise TypeError("scientific trial requires typed TrialRandomization provenance")
        if self.evaluation_window is not None and not isinstance(
            self.evaluation_window, EvaluationWindow
        ):
            raise TypeError("evaluation_window must use EvaluationWindow")
        if self.randomization.seed != self.seed:
            raise ValueError("trial seed must match its randomization assignment")
        if self.randomization.scope_fingerprint not in (None, self.experiment_fingerprint):
            raise ValueError("trial randomization scope must match its experiment")
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
        identity = {
            "experiment_fingerprint": self.experiment_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "preflight_fingerprint": self.preflight_report.fingerprint,
            "parameter_set": self.parameter_set,
            "scenario": self.scenario,
            "seed": self.seed,
        }
        if self.randomization.has_schedule_provenance:
            identity["randomization"] = self.randomization
        if self.evaluation_window is not None:
            identity["evaluation_window"] = self.evaluation_window
        return identity

    @classmethod
    def create(
        cls,
        *,
        experiment_fingerprint: str,
        snapshot_fingerprint: str,
        preflight_report: PreflightReport,
        parameter_set: Mapping[str, Any],
        scenario: Mapping[str, Any] | None = None,
        seed: int | None = None,
        randomization: TrialRandomization | None = None,
        evaluation_window: EvaluationWindow | None = None,
    ) -> ScientificTrial:
        trial_seed = (
            0
            if seed is None and randomization is None
            else (randomization.seed if seed is None and randomization is not None else seed)
        )
        if not isinstance(trial_seed, int) or isinstance(trial_seed, bool):
            raise ValueError("trial seed must be an integer")
        assignment = randomization or TrialRandomization(
            master_seed=trial_seed,
            seed=trial_seed,
            policy=TrialSeedPolicy.PER_CANDIDATE,
            replicate_index=0,
            scope_fingerprint=None,
            seed_group_fingerprint=None,
            replicate_count=1,
            derivation_version=EXPLICIT_SEED_DERIVATION_VERSION,
        )
        if assignment.seed != trial_seed:
            raise ValueError("trial seed must match its randomization assignment")
        identity = {
            "experiment_fingerprint": experiment_fingerprint,
            "snapshot_fingerprint": snapshot_fingerprint,
            "preflight_fingerprint": preflight_report.fingerprint,
            "parameter_set": parameter_set,
            "scenario": scenario or {},
            "seed": trial_seed,
        }
        if assignment.has_schedule_provenance:
            identity["randomization"] = assignment
        if evaluation_window is not None:
            identity["evaluation_window"] = evaluation_window
        return cls(
            trial_id=content_digest(identity),
            experiment_fingerprint=experiment_fingerprint,
            snapshot_fingerprint=snapshot_fingerprint,
            preflight_report=preflight_report,
            parameter_set=parameter_set,
            scenario=scenario or {},
            seed=trial_seed,
            randomization=assignment,
            evaluation_window=evaluation_window,
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
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("attempt ordinal must be positive")
        if not isinstance(self.state, AttemptState):
            raise TypeError("attempt state must be an AttemptState")
        _aware(self.created_at, "created_at")
        created_at = self.created_at.astimezone(UTC)
        updated_at = (self.updated_at or self.created_at).astimezone(UTC)
        _aware(updated_at, "updated_at")
        if updated_at < created_at:
            raise ValueError("attempt updated_at must not precede created_at")
        object.__setattr__(self, "created_at", created_at)
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
        if (
            not isinstance(self.byte_length, int)
            or isinstance(self.byte_length, bool)
            or self.byte_length < 0
        ):
            raise ValueError("byte_length must be a non-negative integer")
        if self.storage_key != self.content_digest:
            raise ValueError("artifact storage_key must equal its content digest")
        for name in ("media_type", "schema_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.retention_class, ArtifactRetention):
            raise TypeError("retention_class must be an ArtifactRetention")


@dataclass(frozen=True, slots=True)
class MetricCalculationDefinition:
    """Stable formula identity and effective parameters, without run outputs."""

    formula_id: str
    contract_version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("formula_id", "contract_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.parameters, Mapping):
            raise TypeError("calculation parameters must be a mapping")
        frozen_parameters = freeze_json(self.parameters)
        if not isinstance(frozen_parameters, Mapping):
            raise TypeError("calculation parameters must be a mapping")
        object.__setattr__(self, "parameters", frozen_parameters)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class MetricEvidenceReference:
    """A typed digest for run-specific observations or supporting evidence."""

    role: str
    digest: str

    def __post_init__(self) -> None:
        _nonempty(self.role, "role")
        require_sha256_digest(self.digest, field_name="digest")


@dataclass(frozen=True, slots=True)
class MetricValue:
    name: str
    value: Decimal | None
    unit: str
    definition_version: str
    basis: MetricBasis
    sample_size: int
    annualization_basis: str | None = None
    calculation_basis: str | None = None
    null_reason: str | None = None
    calculation_definition: MetricCalculationDefinition | None = None
    evidence_references: tuple[MetricEvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        for name in ("name", "unit", "definition_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.basis, MetricBasis):
            raise TypeError("basis must be a MetricBasis")
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
        if self.annualization_basis is not None:
            _nonempty(self.annualization_basis, "annualization_basis")
        if self.calculation_basis is not None:
            _nonempty(self.calculation_basis, "calculation_basis")
        if self.calculation_definition is not None and not isinstance(
            self.calculation_definition, MetricCalculationDefinition
        ):
            raise TypeError("calculation_definition must be a MetricCalculationDefinition")
        evidence_references = tuple(self.evidence_references)
        if any(not isinstance(item, MetricEvidenceReference) for item in evidence_references):
            raise TypeError("evidence_references must contain MetricEvidenceReference values")
        if len(set(evidence_references)) != len(evidence_references):
            raise ValueError("evidence references must not contain duplicates")
        object.__setattr__(
            self,
            "evidence_references",
            tuple(sorted(evidence_references, key=lambda item: (item.role, item.digest))),
        )

    @property
    def calculation_fingerprint(self) -> str | None:
        """Return stable calculation compatibility identity, or None for legacy values.

        Run values, sample sizes, null outcomes, free-text presentation fields, and
        evidence digests are intentionally excluded so separate runs using the same
        formula/configuration can be compared without claiming identical evidence.
        """

        if self.calculation_definition is None:
            return None
        return content_digest(
            {
                "metric_name": self.name,
                "unit": self.unit,
                "basis": self.basis,
                "definition_version": self.definition_version,
                "calculation_definition": self.calculation_definition,
            }
        )


@dataclass(frozen=True, slots=True)
class RollingMetricPoint:
    """One structured end-of-session point in a rolling metric series."""

    portfolio_fingerprint: str
    run_attempt_id: str
    calendar_fingerprint: str
    window_sessions: int
    observed_sessions: int
    window_start_session_label: date | None
    window_end_session_label: date
    window_start_point: ObservationPoint | None
    window_end_point: ObservationPoint
    coverage_complete: bool
    observation_digest: str
    metrics: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        _nonempty(self.run_attempt_id, "run_attempt_id")
        require_sha256_digest(self.calendar_fingerprint, field_name="calendar_fingerprint")
        if (
            not isinstance(self.window_sessions, int)
            or isinstance(self.window_sessions, bool)
            or self.window_sessions < 1
        ):
            raise ValueError("window_sessions must be a positive integer")
        if (
            not isinstance(self.observed_sessions, int)
            or isinstance(self.observed_sessions, bool)
            or not 1 <= self.observed_sessions <= self.window_sessions
        ):
            raise ValueError("observed_sessions must be between one and window_sessions")
        if (
            self.window_start_session_label is not None
            and type(self.window_start_session_label) is not date
        ):
            raise TypeError("window_start_session_label must be a date or None")
        if type(self.window_end_session_label) is not date:
            raise TypeError("window_end_session_label must be a date, not a datetime")
        if (
            self.window_start_session_label is not None
            and self.window_start_session_label > self.window_end_session_label
        ):
            raise ValueError("rolling window start label must not follow its end label")
        if self.window_start_point is not None and not isinstance(
            self.window_start_point, ObservationPoint
        ):
            raise TypeError("window_start_point must be an ObservationPoint or None")
        if not isinstance(self.window_end_point, ObservationPoint):
            raise TypeError("window_end_point must be an ObservationPoint")
        if not isinstance(self.coverage_complete, bool):
            raise TypeError("coverage_complete must be a bool")
        if self.coverage_complete and (
            self.observed_sessions != self.window_sessions
            or self.window_start_session_label is None
            or self.window_start_point is None
        ):
            raise ValueError(
                "complete rolling points require full session and opening-mark coverage"
            )
        if self.window_start_point is not None and self.window_end_point <= self.window_start_point:
            raise ValueError("rolling window end point must follow its opening mark")
        require_sha256_digest(self.observation_digest, field_name="observation_digest")
        metrics = tuple(self.metrics)
        if not metrics or any(not isinstance(item, MetricValue) for item in metrics):
            raise ValueError("rolling points must contain typed MetricValue records")
        metric_names = [item.name for item in metrics]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("rolling point metric names must be unique")
        if len({item.definition_version for item in metrics}) != 1:
            raise ValueError("rolling point metrics must use one definition version")
        if any(item.sample_size != self.observed_sessions for item in metrics):
            raise ValueError("rolling point metric sample sizes must match observed_sessions")
        object.__setattr__(self, "metrics", metrics)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class SessionReturnDistribution:
    """Run-scoped distribution summary from an exact calendar session range."""

    portfolio_fingerprint: str
    run_attempt_id: str
    calendar_fingerprint: str
    start_session_label: date
    end_session_label: date
    opening_point: ObservationPoint
    closing_point: ObservationPoint
    expected_sessions: int
    observed_sessions: int
    coverage_complete: bool
    external_cash_flow_reports_complete: bool
    external_flows_occurred: bool | None
    minimum_observations: int
    quantile_probabilities: tuple[Decimal, ...]
    confidence_levels: tuple[Decimal, ...]
    effective_tail_observation_counts: tuple[int | None, ...]
    observation_digest: str
    metrics: tuple[MetricValue, ...]
    returns_flow_adjusted: bool = False

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        _nonempty(self.run_attempt_id, "run_attempt_id")
        require_sha256_digest(self.calendar_fingerprint, field_name="calendar_fingerprint")
        if type(self.start_session_label) is not date or type(self.end_session_label) is not date:
            raise TypeError("session range labels must be dates, not datetimes")
        if self.start_session_label > self.end_session_label:
            raise ValueError("start_session_label must not follow end_session_label")
        if not isinstance(self.opening_point, ObservationPoint) or not isinstance(
            self.closing_point, ObservationPoint
        ):
            raise TypeError("distribution boundary marks must be ObservationPoint values")
        if self.closing_point <= self.opening_point:
            raise ValueError("distribution closing mark must follow its opening mark")
        for name, value, minimum in (
            ("expected_sessions", self.expected_sessions, 1),
            ("observed_sessions", self.observed_sessions, 1),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} must be a positive integer")
        if self.observed_sessions > self.expected_sessions:
            raise ValueError("observed_sessions must not exceed expected_sessions")
        if not isinstance(self.coverage_complete, bool):
            raise TypeError("coverage_complete must be a bool")
        if self.coverage_complete and self.observed_sessions != self.expected_sessions:
            raise ValueError("complete distributions require all expected session observations")
        if not isinstance(self.external_cash_flow_reports_complete, bool):
            raise TypeError("external_cash_flow_reports_complete must be a bool")
        if self.external_flows_occurred is not None and not isinstance(
            self.external_flows_occurred, bool
        ):
            raise TypeError("external_flows_occurred must be a bool or None")
        if not isinstance(self.returns_flow_adjusted, bool):
            raise TypeError("returns_flow_adjusted must be a bool")
        if self.returns_flow_adjusted and self.external_flows_occurred is not True:
            raise ValueError("flow-adjusted distributions require external-flow occurrence evidence")
        if self.external_cash_flow_reports_complete != (self.external_flows_occurred is not None):
            raise ValueError(
                "complete flow reports require occurrence evidence; incomplete reports must be unknown"
            )
        if (
            not isinstance(self.minimum_observations, int)
            or isinstance(self.minimum_observations, bool)
            or self.minimum_observations < 2
        ):
            raise ValueError("minimum_observations must be an integer of at least two")

        quantiles = tuple(self.quantile_probabilities)
        confidence = tuple(self.confidence_levels)
        for name, values in (
            ("quantile_probabilities", quantiles),
            ("confidence_levels", confidence),
        ):
            if not values or any(
                not isinstance(value, Decimal)
                or not value.is_finite()
                or not Decimal(0) < value < Decimal(1)
                for value in values
            ):
                raise ValueError(f"{name} must contain probabilities strictly between zero and one")
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{name} must be unique and sorted")

        tail_counts = tuple(self.effective_tail_observation_counts)
        if len(tail_counts) != len(confidence):
            raise ValueError("tail observation counts must align with confidence levels")
        eligible = (
            self.coverage_complete
            and self.external_cash_flow_reports_complete
            and (self.external_flows_occurred is False or self.returns_flow_adjusted)
            and self.observed_sessions >= self.minimum_observations
        )
        for count in tail_counts:
            if count is not None and (
                not isinstance(count, int)
                or isinstance(count, bool)
                or not 1 <= count <= self.observed_sessions
            ):
                raise ValueError("effective tail observation counts must be valid sample counts")
            if eligible != (count is not None):
                raise ValueError(
                    "tail observation counts must be present only for eligible samples"
                )

        require_sha256_digest(self.observation_digest, field_name="observation_digest")
        metrics = tuple(self.metrics)
        expected_metric_count = len(quantiles) + 2 * len(confidence)
        if len(metrics) != expected_metric_count or any(
            not isinstance(item, MetricValue) for item in metrics
        ):
            raise ValueError(
                "distribution metrics must contain each requested quantile and tail value"
            )
        if len({item.name for item in metrics}) != len(metrics):
            raise ValueError("distribution metric names must be unique")
        if len({item.definition_version for item in metrics}) != 1:
            raise ValueError("distribution metrics must use one definition version")
        if any(
            item.sample_size != self.observed_sessions or item.basis is not MetricBasis.NET
            for item in metrics
        ):
            raise ValueError(
                "distribution metrics must use the observed sample count and net basis"
            )
        if eligible and any(item.value is None for item in metrics):
            raise ValueError("eligible distribution samples must provide every requested metric")
        if not eligible and any(item.value is not None for item in metrics):
            raise ValueError("ineligible distribution samples must not provide metric values")
        object.__setattr__(self, "quantile_probabilities", quantiles)
        object.__setattr__(self, "confidence_levels", confidence)
        object.__setattr__(self, "effective_tail_observation_counts", tail_counts)
        object.__setattr__(self, "metrics", metrics)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


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
        values = tuple(self.values)
        if not values:
            raise ValueError("a metric set must contain values")
        if any(not isinstance(item, MetricValue) for item in values):
            raise TypeError("metric set values must contain MetricValue records")
        keys = [(item.name, item.basis) for item in values]
        if len(set(keys)) != len(keys):
            raise ValueError("metric names must be unique within a basis")
        if any(item.definition_version != self.definition_version for item in values):
            raise ValueError("metric values must match their metric-set definition version")
        _aware(self.created_at, "created_at")
        object.__setattr__(
            self,
            "values",
            tuple(sorted(values, key=lambda item: (item.name, item.basis.value, item.unit))),
        )

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
    allocation_definition_version: str
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
        require_sha256_digest(
            self.dependency_catalog_digest, field_name="dependency_catalog_digest"
        )
        require_sha256_digest(self.assumptions_digest, field_name="assumptions_digest")
        for name in ("engine_name", "engine_version", "allocation_definition_version"):
            _nonempty(getattr(self, name), name)
        packages = tuple(self.strategy_packages)
        artifacts = tuple(self.output_artifacts)
        if any(not isinstance(item, StrategyPackage) for item in packages):
            raise TypeError("result strategy packages must use StrategyPackage records")
        if any(not isinstance(item, ArtifactManifest) for item in artifacts):
            raise TypeError("result outputs must use ArtifactManifest records")
        package_strategies = [item.strategy_fingerprint for item in packages]
        portfolio_strategies = {item.strategy_fingerprint for item in self.portfolio.components}
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
class KeyedRandomStreamPairingClaim:
    """Run-bound pairing claim that is not authoritative until externally verified."""

    baseline_attempt_id: str
    variant_attempt_id: str
    engine_build_digest: str
    engine_conformance_fingerprint: str
    stream_contract_fingerprint: str
    baseline_trace_digest: str
    variant_trace_digest: str
    paired_draws_digest: str
    matched_draw_count: int
    unmatched_baseline_draw_count: int = 0
    unmatched_variant_draw_count: int = 0

    def __post_init__(self) -> None:
        for name in ("baseline_attempt_id", "variant_attempt_id"):
            _nonempty(getattr(self, name), name)
        if self.baseline_attempt_id == self.variant_attempt_id:
            raise ValueError("paired stream evidence must reference distinct run attempts")
        for name in (
            "engine_build_digest",
            "engine_conformance_fingerprint",
            "stream_contract_fingerprint",
            "baseline_trace_digest",
            "variant_trace_digest",
            "paired_draws_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "matched_draw_count",
            "unmatched_baseline_draw_count",
            "unmatched_variant_draw_count",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.matched_draw_count == 0:
            raise ValueError("paired stream evidence requires at least one matched draw")
        if self.unmatched_baseline_draw_count or self.unmatched_variant_draw_count:
            raise ValueError("paired stream evidence requires complete draw-key alignment")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class KeyedRandomStreamPairingReceipt:
    """Deterministic receipt emitted after keyed draw streams are verified."""

    claim: KeyedRandomStreamPairingClaim
    verifier_version: str
    verification_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.claim, KeyedRandomStreamPairingClaim):
            raise TypeError("claim must use KeyedRandomStreamPairingClaim")
        _nonempty(self.verifier_version, "verifier_version")
        require_sha256_digest(self.verification_digest, field_name="verification_digest")
        expected_digest = content_digest(
            {"claim": self.claim, "verifier_version": self.verifier_version}
        )
        if self.verification_digest != expected_digest:
            raise ValueError("verification_digest must bind the claim and verifier version")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class SensitivityComparisonEvidence:
    """Successful runs plus the strongest currently supported randomization evidence.

    This class classifies randomization provenance only; it does not compare
    metric values/semantics or assert statistical significance. It validates
    provenance links and artifact references. The artifact store/worker must
    verify the referenced bytes and emit a verified pairing receipt only after
    the engine build has passed registered conformance checks. No such verifier
    is implemented here, so a keyed-stream claim remains explicitly unverified
    and absence of pairing evidence does not prove statistical independence.
    A verifier receipt upgrades the provenance classification to verified
    pairing, but downstream comparison remains descriptive and does not infer
    statistical significance by itself.
    """

    baseline_result: RunResultManifest
    variant_result: RunResultManifest
    pairing_claim: KeyedRandomStreamPairingClaim | None = None
    pairing_receipt: KeyedRandomStreamPairingReceipt | None = None

    def __post_init__(self) -> None:
        baseline = self.baseline_result
        variant = self.variant_result
        if not isinstance(baseline, RunResultManifest) or not isinstance(
            variant, RunResultManifest
        ):
            raise TypeError("sensitivity evidence requires two RunResultManifest values")
        if baseline.trial.trial_id == variant.trial.trial_id:
            raise ValueError("retries of one scientific trial are not sensitivity replicates")
        if canonical_json(baseline.trial.parameter_set) == canonical_json(
            variant.trial.parameter_set
        ):
            raise ValueError("sensitivity comparisons must change strategy parameters")
        if baseline.attempt.attempt_id == variant.attempt.attempt_id:
            raise ValueError("sensitivity comparisons require distinct successful attempts")

        comparable_context = (
            baseline.experiment_fingerprint == variant.experiment_fingerprint
            and baseline.snapshot_fingerprint == variant.snapshot_fingerprint
            and baseline.capability_contract_digest == variant.capability_contract_digest
            and baseline.trial.scenario == variant.trial.scenario
            and baseline.trial.evaluation_window == variant.trial.evaluation_window
            and baseline.portfolio_fingerprint == variant.portfolio_fingerprint
            and baseline.strategy_package_fingerprints == variant.strategy_package_fingerprints
            and baseline.engine_name == variant.engine_name
            and baseline.engine_version == variant.engine_version
            and baseline.engine_build_digest == variant.engine_build_digest
            and baseline.allocation_definition_version == variant.allocation_definition_version
            and baseline.dependency_catalog_digest == variant.dependency_catalog_digest
            and baseline.assumptions_digest == variant.assumptions_digest
        )
        if not comparable_context:
            raise ValueError("sensitivity results must share their fixed execution context")

        shared_seed_group = self._shares_seed_group()
        claim = self.pairing_claim
        receipt = self.pairing_receipt
        if claim is not None and receipt is not None:
            raise ValueError("sensitivity evidence cannot include both a pairing claim and receipt")
        if receipt is not None:
            if not isinstance(receipt, KeyedRandomStreamPairingReceipt):
                raise TypeError("pairing_receipt must use KeyedRandomStreamPairingReceipt")
            claim = receipt.claim
        if claim is not None:
            if not isinstance(claim, KeyedRandomStreamPairingClaim):
                raise TypeError("pairing_claim must use KeyedRandomStreamPairingClaim")
            if not shared_seed_group:
                raise ValueError("a keyed-stream pairing claim requires one shared seed group")
            if (
                claim.baseline_attempt_id != baseline.attempt_id
                or claim.variant_attempt_id != variant.attempt_id
            ):
                raise ValueError("keyed-stream pairing claim must bind these result attempts")
            if claim.engine_build_digest != baseline.engine_build_digest:
                raise ValueError("keyed-stream pairing claim must bind the result engine build")
            if claim.baseline_trace_digest not in baseline.output_artifact_digests:
                raise ValueError("baseline random-stream trace must be a result output artifact")
            if claim.variant_trace_digest not in variant.output_artifact_digests:
                raise ValueError("variant random-stream trace must be a result output artifact")
            for result in (baseline, variant):
                output_digests = result.output_artifact_digests
                if (
                    claim.fingerprint not in output_digests
                    or claim.paired_draws_digest not in output_digests
                ):
                    raise ValueError(
                        "pairing claim and paired-draw artifacts must be referenced by both results"
                    )

    def _shares_seed_group(self) -> bool:
        baseline = self.baseline_result.trial
        variant = self.variant_result.trial
        left = baseline.randomization
        right = variant.randomization
        return (
            left.policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE
            and right.policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE
            and left.seed_group_fingerprint is not None
            and left.seed_group_fingerprint == right.seed_group_fingerprint
            and left.scope_fingerprint is not None
            and left.scope_fingerprint == right.scope_fingerprint
            and left.master_seed == right.master_seed
            and left.seed == right.seed
            and left.replicate_index == right.replicate_index
            and left.replicate_count == right.replicate_count
        )

    @property
    def evidence_level(self) -> SensitivityEvidenceLevel:
        if self.pairing_receipt is not None:
            return SensitivityEvidenceLevel.VERIFIED_PAIRED
        if self.pairing_claim is not None:
            return SensitivityEvidenceLevel.PAIRING_CLAIM_UNVERIFIED
        if self._shares_seed_group():
            return SensitivityEvidenceLevel.SHARED_SEED_ONLY
        return SensitivityEvidenceLevel.UNPAIRED

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
        created_at = self.created_at.astimezone(UTC)
        updated_at = self.updated_at.astimezone(UTC)
        if updated_at < created_at:
            raise ValueError("updated_at must not precede created_at")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
