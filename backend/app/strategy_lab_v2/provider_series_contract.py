"""Fail-closed binding of published Provider series to Strategy inputs.

This is a pure consumer boundary: callers supply locally persisted Provider
records and a frozen Strategy manifest. It performs no database, provider, or
transport I/O and never promotes a symbol or stale dataset into availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.capabilities import CapabilityCell, CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    DataSeriesManifest,
    EventGranularity,
    ProductClass,
)
from app.strategy_lab_v2.coverage import (
    CoverageAttestation,
    CoverageVerificationReport,
    verify_coverage_attestation,
)


class ProviderBindingDecision(StrEnum):
    VERIFIED = "verified"
    REJECTED = "rejected"


class ProviderFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderSeriesBinding:
    decision: ProviderBindingDecision
    instrument_key: str | None
    market_series_id: int | None
    series_scope_fingerprint: str
    mismatches: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.decision is ProviderBindingDecision.VERIFIED


@dataclass(frozen=True, slots=True)
class ProviderFreshnessAssessment:
    status: ProviderFreshness
    evaluated_at: datetime
    stale_after: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class ProviderCoverageResolution:
    attestation: CoverageAttestation | None
    verification: CoverageVerificationReport | None
    evidence_digest: str
    mismatches: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return (
            self.attestation is not None
            and self.verification is not None
            and self.verification.verified
        )


_TIMEFRAME_ALIASES = {
    "m1": "M1",
    "1m": "M1",
    "m5": "M5",
    "5m": "M5",
    "m15": "M15",
    "15m": "M15",
    "m30": "M30",
    "30m": "M30",
    "h1": "H1",
    "1h": "H1",
    "h2": "H2",
    "2h": "H2",
    "h4": "H4",
    "4h": "H4",
    "h12": "H12",
    "12h": "H12",
    "d1": "D1",
    "1d": "D1",
    "w1": "W1",
    "1w": "W1",
    "mn": "MN",
    "1mo": "MN",
    "y1": "Y1",
    "1y": "Y1",
}


def _canonical_timeframe(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _TIMEFRAME_ALIASES.get(value.casefold())


@dataclass(frozen=True, slots=True)
class ProviderSeriesCapabilityEvidence:
    """Locally read Provider records offered to Strategy's capability preflight.

    The host resolver supplies these values from persisted Provider state. They
    are re-verified here before a capability cell can reach the API summary;
    API payload fields never construct this evidence.
    """

    instrument: Any
    series: Any
    manifest: DataSeriesManifest
    coverage_assessment: Any
    dataset_state: Any | None
    calendar_digest: str
    evaluated_at: datetime
    product_class: ProductClass
    execution_models: frozenset[str]
    account_models: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, DataSeriesManifest):
            raise TypeError("manifest must be a DataSeriesManifest")
        if not isinstance(self.product_class, ProductClass):
            raise TypeError("product_class must be a ProductClass")
        require_sha256_digest(self.calendar_digest, field_name="calendar_digest")
        if _aware_utc(self.evaluated_at) is None:
            raise ValueError("evaluated_at must be timezone-aware")
        for name in ("execution_models", "account_models"):
            if isinstance(getattr(self, name), str | bytes):
                raise TypeError(f"{name} must be a collection of host-authorized values")
            values = frozenset(getattr(self, name))
            if not values or any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty host-authorized values")
            object.__setattr__(self, name, values)


def provider_series_capability_cell(
    evidence: ProviderSeriesCapabilityEvidence,
    requirement: CapabilityRequirement,
) -> CapabilityCell | None:
    """Admit a provider-backed bar requirement only from current local evidence.

    Returning ``None`` deliberately maps identity, coverage, freshness, or
    lineage failure to an unsupported data preflight; it does not query a
    provider, select another series, or synthesize a fallback cell.
    """

    if not isinstance(evidence, ProviderSeriesCapabilityEvidence):
        raise TypeError("evidence must be ProviderSeriesCapabilityEvidence")
    if not isinstance(requirement, CapabilityRequirement):
        raise TypeError("requirement must be a CapabilityRequirement")
    manifest = evidence.manifest
    if (
        requirement.event_type != "ohlcv"
        or requirement.event_granularity is not EventGranularity.BAR
        or evidence.product_class is not requirement.product_class
        or manifest.instrument_id != requirement.instrument_id
        or manifest.event_type != requirement.event_type
        or manifest.event_granularity is not requirement.event_granularity
        or _canonical_timeframe(manifest.timeframe) != _canonical_timeframe(requirement.timeframe)
        or manifest.session != requirement.session
        or manifest.feed != requirement.feed
        or manifest.start != requirement.start
        or manifest.end != requirement.end
        or manifest.adjustment is not requirement.adjustment
        or manifest.corporate_action_semantics != requirement.corporate_action_semantics
    ):
        return None

    binding = verify_provider_series_binding(evidence.instrument, evidence.series, manifest)
    freshness = assess_provider_freshness(
        evidence.dataset_state,
        instrument=evidence.instrument,
        series=evidence.series,
        evaluated_at=evidence.evaluated_at,
    )
    if not binding.verified or freshness.status is not ProviderFreshness.CURRENT:
        return None
    coverage = resolve_provider_coverage(
        evidence.instrument,
        evidence.series,
        manifest,
        evidence.coverage_assessment,
        calendar_digest=evidence.calendar_digest,
        attested_at=evidence.evaluated_at,
    )
    if not coverage.verified or coverage.attestation is None:
        return None
    covered_start = _aware_utc(getattr(evidence.coverage_assessment, "covered_start", None))
    covered_end = _aware_utc(getattr(evidence.coverage_assessment, "covered_end", None))
    if covered_start is None or covered_end is None:
        return None
    state_start = _aware_utc(getattr(evidence.dataset_state, "coverage_start", None))
    state_end = _aware_utc(getattr(evidence.dataset_state, "coverage_end", None))
    if (
        state_start is None
        or state_end is None
        or state_start > covered_start
        or state_end < covered_end
    ):
        return None

    evidence_digest = content_digest(
        {
            "provider_binding": binding.series_scope_fingerprint,
            "manifest_fingerprint": content_digest(manifest),
            "coverage_attestation": coverage.attestation.fingerprint,
            "freshness": freshness,
            "provider_series_id": getattr(evidence.series, "id", None),
            "provider_source_id": getattr(evidence.series, "data_source_id", None),
            "provider_source_series_key": getattr(evidence.series, "source_series_key", None),
        }
    )
    return CapabilityCell(
        instrument_id=requirement.instrument_id,
        product_class=evidence.product_class,
        event_granularities=frozenset({manifest.event_granularity}),
        event_types=frozenset({manifest.event_type}),
        timeframes=frozenset({requirement.timeframe}),
        adjustments=frozenset({manifest.adjustment}),
        sessions=frozenset({manifest.session}),
        feeds=frozenset({manifest.feed}),
        execution_models=evidence.execution_models,
        account_models=evidence.account_models,
        corporate_action_semantics=frozenset({manifest.corporate_action_semantics}),
        # A verified, complete attestation binds the manifest's requested
        # half-open interval. First/last observation timestamps are not the
        # corresponding interval edges and must not manufacture edge gaps.
        history_start=manifest.start,
        history_end=manifest.end,
        evidence_digest=evidence_digest,
    )


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _aware_utc(value: datetime) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def verify_provider_series_binding(
    instrument: Any,
    series: Any,
    manifest: DataSeriesManifest,
) -> ProviderSeriesBinding:
    """Bind a Strategy manifest to resolved Provider identity and local scope."""

    if not isinstance(manifest, DataSeriesManifest):
        raise TypeError("manifest must be a DataSeriesManifest")
    instrument_key = getattr(instrument, "domain_key", None)
    series_id = getattr(series, "id", None)
    provenance = getattr(series, "provenance", None)
    provenance = provenance if isinstance(provenance, dict) else {}
    mismatches: list[str] = []

    if _value(getattr(instrument, "identity_status", None)) != "resolved" or not instrument_key:
        mismatches.append("provider_identity_unresolved")
    if getattr(series, "instrument_id", None) != getattr(instrument, "id", None):
        mismatches.append("provider_series_instrument_mismatch")
    if getattr(series, "is_active", None) is not True:
        mismatches.append("provider_series_inactive")
    if manifest.instrument_id != instrument_key:
        mismatches.append("strategy_instrument_key_mismatch")
    if manifest.event_granularity is not EventGranularity.BAR or manifest.event_type != "ohlcv":
        mismatches.append("strategy_event_type_unsupported")

    basis = _value(getattr(series, "adjustment_basis", None))
    adjustment = {
        "raw": AdjustmentMode.RAW,
        "split_adjusted": AdjustmentMode.SPLIT_ADJUSTED,
        "total_return": AdjustmentMode.TOTAL_RETURN,
    }.get(str(basis))
    if adjustment is None:
        mismatches.append("provider_adjustment_semantics_unsupported")
    elif manifest.adjustment is not adjustment:
        mismatches.append("strategy_adjustment_mismatch")

    if _canonical_timeframe(getattr(series, "timeframe", None)) != _canonical_timeframe(
        manifest.timeframe
    ):
        mismatches.append("provider_timeframe_mismatch")
    comparisons = (
        ("session", getattr(series, "session_code", None), manifest.session),
        ("feed", getattr(series, "feed_scope", None), manifest.feed),
    )
    mismatches.extend(
        f"provider_{name}_mismatch" for name, actual, expected in comparisons if actual != expected
    )
    if not isinstance(series_id, int) or isinstance(series_id, bool) or series_id <= 0:
        mismatches.append("provider_series_id_invalid")
    if not isinstance(getattr(series, "data_source_id", None), int):
        mismatches.append("provider_data_source_unbound")
    if (
        not isinstance(getattr(series, "source_series_key", None), str)
        or not series.source_series_key
    ):
        mismatches.append("provider_source_series_key_missing")
    provider_name = provenance.get("provider")
    if not isinstance(provider_name, str) or not provider_name.strip():
        mismatches.append("provider_provenance_missing")
    corporate_action_semantics = provenance.get("corporate_action_semantics")
    if basis == "raw" and corporate_action_semantics is None:
        # The Provider enum's raw basis explicitly means bars have not been
        # adjusted; no symbol/provider-specific inference is needed.
        corporate_action_semantics = "raw_unadjusted"
    if corporate_action_semantics != manifest.corporate_action_semantics:
        mismatches.append("provider_corporate_action_semantics_unbound")

    scope = {
        "domain_key": instrument_key,
        "identity_status": _value(getattr(instrument, "identity_status", None)),
        "series_id": series_id,
        "instrument_id": getattr(series, "instrument_id", None),
        "data_source_id": getattr(series, "data_source_id", None),
        "source_series_key": getattr(series, "source_series_key", None),
        "timeframe": getattr(series, "timeframe", None),
        "adjustment_version": getattr(series, "adjustment_version", None),
        "session": getattr(series, "session_code", None),
        "feed": getattr(series, "feed_scope", None),
        "adjustment_basis": str(basis),
        "corporate_action_semantics": corporate_action_semantics,
        "provider": provider_name,
        "provenance": provenance,
        "manifest_fingerprint": content_digest(manifest),
    }
    ordered = tuple(sorted(set(mismatches)))
    return ProviderSeriesBinding(
        ProviderBindingDecision.REJECTED if ordered else ProviderBindingDecision.VERIFIED,
        instrument_key if isinstance(instrument_key, str) else None,
        series_id if isinstance(series_id, int) and not isinstance(series_id, bool) else None,
        content_digest(scope),
        ordered,
    )


def provider_coverage_evidence_digest(
    instrument: Any,
    series: Any,
    assessment: Any,
    *,
    calendar_digest: str,
) -> str:
    """Content-address the exact local Provider series and coverage assessment."""

    require_sha256_digest(calendar_digest, field_name="calendar_digest")
    provenance = getattr(series, "provenance", None)
    provenance = provenance if isinstance(provenance, dict) else {}
    missing_slices = tuple(
        tuple(_aware_utc(item) if isinstance(item, datetime) else item for item in pair)
        for pair in (getattr(assessment, "missing_slices", ()) or ())
    )
    return content_digest(
        {
            "provider_domain_key": getattr(instrument, "domain_key", None),
            "provider_identity_status": _value(getattr(instrument, "identity_status", None)),
            "provider_instrument_id": getattr(instrument, "id", None),
            "market_series_id": getattr(series, "id", None),
            "data_source_id": getattr(series, "data_source_id", None),
            "source_series_key": getattr(series, "source_series_key", None),
            "series_scope": {
                "feed": getattr(series, "feed_scope", None),
                "session": getattr(series, "session_code", None),
                "timeframe": getattr(series, "timeframe", None),
                "adjustment_version": getattr(series, "adjustment_version", None),
                "adjustment_basis": _value(getattr(series, "adjustment_basis", None)),
            },
            "provider": provenance.get("provider"),
            "coverage_assessment": {
                "status": _value(getattr(assessment, "status", None)),
                "covered_start": _aware_utc(getattr(assessment, "covered_start", None)),
                "covered_end": _aware_utc(getattr(assessment, "covered_end", None)),
                "bar_count": getattr(assessment, "bar_count", None),
                "missing_slices": missing_slices,
            },
            "calendar_digest": calendar_digest,
        }
    )


def resolve_provider_coverage(
    instrument: Any,
    series: Any,
    manifest: DataSeriesManifest,
    assessment: Any,
    *,
    calendar_digest: str,
    attested_at: datetime,
) -> ProviderCoverageResolution:
    """Convert ready local Provider coverage into Strategy's existing attestation."""

    binding = verify_provider_series_binding(instrument, series, manifest)
    evidence_digest = provider_coverage_evidence_digest(
        instrument,
        series,
        assessment,
        calendar_digest=calendar_digest,
    )
    mismatches = list(binding.mismatches)
    if manifest.coverage_evidence_digest != evidence_digest:
        mismatches.append("strategy_coverage_evidence_digest_mismatch")
    if _value(getattr(assessment, "status", None)) != "ready":
        mismatches.append("provider_coverage_not_ready")
    if getattr(assessment, "missing_slices", None):
        mismatches.append("provider_coverage_contains_gaps")
    row_count = getattr(assessment, "bar_count", None)
    if row_count != manifest.row_count:
        mismatches.append("provider_coverage_row_count_mismatch")
    start = _aware_utc(getattr(assessment, "covered_start", None))
    end = _aware_utc(getattr(assessment, "covered_end", None))
    if start is None or end is None or not manifest.start <= start <= end < manifest.end:
        mismatches.append("provider_coverage_window_mismatch")
    attested = _aware_utc(attested_at)
    if attested is None:
        raise ValueError("attested_at must be timezone-aware")
    if mismatches:
        return ProviderCoverageResolution(
            None, None, evidence_digest, tuple(sorted(set(mismatches)))
        )
    provenance = getattr(series, "provenance", None)
    provider_name = provenance.get("provider") if isinstance(provenance, dict) else None
    if not isinstance(provider_name, str) or not provider_name.strip():
        return ProviderCoverageResolution(
            None, None, evidence_digest, ("provider_provenance_missing",)
        )
    attestation = CoverageAttestation(
        evidence_digest=evidence_digest,
        series_content_digest=manifest.content_digest,
        instrument_id=manifest.instrument_id,
        event_type=manifest.event_type,
        event_granularity=manifest.event_granularity,
        timeframe=manifest.timeframe,
        session=manifest.session,
        feed=manifest.feed,
        adjustment=manifest.adjustment,
        corporate_action_semantics=manifest.corporate_action_semantics,
        start=manifest.start,
        end=manifest.end,
        row_count=manifest.row_count,
        calendar_digest=calendar_digest,
        complete=True,
        gap_free=True,
        provider_adapter=provider_name,
        attested_at=attested,
    )
    verification = verify_coverage_attestation(manifest, attestation)
    return ProviderCoverageResolution(
        attestation,
        verification,
        evidence_digest,
        () if verification.verified else verification.mismatches,
    )


def assess_provider_freshness(
    state: Any | None,
    *,
    instrument: Any,
    series: Any,
    evaluated_at: datetime,
) -> ProviderFreshnessAssessment:
    """Classify the exact Provider dataset state without treating unknown as current."""

    observed = _aware_utc(evaluated_at)
    if observed is None:
        raise ValueError("evaluated_at must be timezone-aware")
    if state is None:
        return ProviderFreshnessAssessment(
            ProviderFreshness.UNKNOWN, observed, None, "provider_dataset_state_missing"
        )
    adjustment_basis = _value(getattr(series, "adjustment_basis", None))
    if adjustment_basis not in {"raw", "split_adjusted", "total_return", "provider_adjusted"}:
        return ProviderFreshnessAssessment(
            ProviderFreshness.UNKNOWN, observed, None, "provider_series_adjustment_unknown"
        )
    instrument_id = getattr(instrument, "id", None)
    data_source_id = getattr(series, "data_source_id", None)
    timeframe = _value(getattr(series, "timeframe", None))
    if not isinstance(instrument_id, int) or not isinstance(data_source_id, int) or not timeframe:
        return ProviderFreshnessAssessment(
            ProviderFreshness.UNKNOWN, observed, None, "provider_series_scope_incomplete"
        )
    dataset_key = f"{timeframe}:{'raw' if adjustment_basis == 'raw' else 'adj'}"
    matches = (
        getattr(state, "instrument_id", None) == instrument_id
        and getattr(state, "data_source_id", None) == data_source_id
        and getattr(state, "dataset_type", None) == "ohlcv"
        and getattr(state, "dataset_key", None) == dataset_key
    )
    if not matches:
        return ProviderFreshnessAssessment(
            ProviderFreshness.UNKNOWN, observed, None, "provider_dataset_state_scope_mismatch"
        )
    status = str(_value(getattr(state, "status", "")))
    stale_after = _aware_utc(getattr(state, "stale_after", None))
    fetched_at = _aware_utc(getattr(state, "fetched_at", None))
    coverage_start = _aware_utc(getattr(state, "coverage_start", None))
    coverage_end = _aware_utc(getattr(state, "coverage_end", None))
    if status in {"pending", "failed"}:
        return ProviderFreshnessAssessment(
            ProviderFreshness.UNAVAILABLE, observed, stale_after, f"provider_dataset_{status}"
        )
    if status == "stale" or stale_after is not None and stale_after <= observed:
        return ProviderFreshnessAssessment(
            ProviderFreshness.STALE, observed, stale_after, "provider_dataset_stale"
        )
    if (
        status != "fresh"
        or stale_after is None
        or fetched_at is None
        or fetched_at > observed
        or coverage_start is None
        or coverage_end is None
        or coverage_start > coverage_end
    ):
        return ProviderFreshnessAssessment(
            ProviderFreshness.UNKNOWN,
            observed,
            stale_after,
            "provider_freshness_evidence_incomplete",
        )
    return ProviderFreshnessAssessment(
        ProviderFreshness.CURRENT, observed, stale_after, "provider_dataset_current"
    )
