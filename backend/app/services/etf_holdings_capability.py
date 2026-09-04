"""Truthful, per-symbol ETF holdings capability evaluation.

The adapter registry describes what code exists.  This module describes what a
particular ETF can safely claim *now*, based on the latest stored snapshot and
the most recent adapter check.  In particular, SEC reconstruction and stale
snapshots remain visible but never become current issuer support implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.models.etf_holdings import ETFHoldingsAdapterState, ETFHoldingsSnapshot, ETFProfile
from app.services.etf_holdings_adapters import FALLBACK_ISSUER_AUDITS

CURRENT = "current"
DEGRADED = "degraded"
STALE = "stale"
UNAVAILABLE = "unavailable"
NOT_APPLICABLE = "not_applicable"
UNKNOWN = "unknown"

ISSUER_NATIVE = "issuer_native"
SUCCESSOR_NATIVE = "successor_native"
LICENSED_VENDOR = "licensed_vendor"
SEC_FILING = "sec_filing"
NO_SOURCE = "none"


@dataclass(frozen=True, slots=True)
class ETFHoldingsSymbolAudit:
    """Symbol-scoped source investigation metadata.

    Provider identity evidence is deliberately not promoted to symbol evidence:
    an identity-only fallback entry remains ``unknown`` until a symbol-scoped
    route or terminal product disposition is recorded.
    """

    tier: int
    outcome: str
    evidence_state: str
    provider_identity: str | None
    investigated_at: date | None
    next_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "outcome": self.outcome,
            "evidence_state": self.evidence_state,
            "provider_identity": self.provider_identity,
            "investigated_at": self.investigated_at,
            "next_action": self.next_action,
        }


_COMPLETE_STATUSES = {"complete", "issuer_current", "issuer_reported", "self_snapshotted"}
_CADENCE_WINDOWS = {
    "daily": timedelta(days=5),
    "weekly": timedelta(days=14),
    "monthly": timedelta(days=45),
    "quarterly": timedelta(days=120),
    "filing": timedelta(days=120),
    "unspecified": timedelta(days=7),
}


@dataclass(frozen=True, slots=True)
class ETFHoldingsCapability:
    """Serializable capability state for one ETF symbol."""

    availability: str
    source_tier: str
    identity_verified: bool
    usable_for_current_analysis: bool
    displayable_last_known: bool
    adapter_key: str | None
    source_provider: str | None
    transport_kind: str | None
    expected_cadence: str | None
    composition_date: date | None
    published_at: datetime | None
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    freshness_deadline: date | None
    row_count: int | None
    resolved_count: int | None
    unresolved_count: int | None
    completeness_status: str | None
    failure_reason: str | None
    consecutive_failures: int
    schema_fingerprint: str | None
    reason: str
    symbol_audit: ETFHoldingsSymbolAudit

    def as_dict(self) -> dict[str, Any]:
        return {
            "availability": self.availability,
            "source_tier": self.source_tier,
            "identity_verified": self.identity_verified,
            "usable_for_current_analysis": self.usable_for_current_analysis,
            "displayable_last_known": self.displayable_last_known,
            "adapter_key": self.adapter_key,
            "source_provider": self.source_provider,
            "transport_kind": self.transport_kind,
            "expected_cadence": self.expected_cadence,
            "composition_date": self.composition_date,
            "published_at": self.published_at,
            "last_checked_at": self.last_checked_at,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "freshness_deadline": self.freshness_deadline,
            "row_count": self.row_count,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "completeness_status": self.completeness_status,
            "failure_reason": self.failure_reason,
            "consecutive_failures": self.consecutive_failures,
            "schema_fingerprint": self.schema_fingerprint,
            "reason": self.reason,
            "symbol_audit": self.symbol_audit.as_dict(),
        }


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _source_tier(
    snapshot: ETFHoldingsSnapshot | None, state: ETFHoldingsAdapterState | None
) -> str:
    state_metadata = _metadata(state.extra_data if state else None)
    snapshot_metadata = _metadata(snapshot.extra_data if snapshot else None)
    metadata = {
        **state_metadata,
        **_metadata(state_metadata.get("legal_metadata")),
        **snapshot_metadata,
        **_metadata(snapshot_metadata.get("legal_metadata")),
    }
    explicit = str(metadata.get("source_tier") or "").strip().lower()
    if explicit in {ISSUER_NATIVE, SUCCESSOR_NATIVE, LICENSED_VENDOR, SEC_FILING, NO_SOURCE}:
        return explicit
    provenance = " ".join(
        str(value or "").lower()
        for value in (
            snapshot.provenance if snapshot else None,
            snapshot.source_provider if snapshot else None,
            snapshot.completeness_status if snapshot else None,
            metadata.get("route_resolution"),
        )
    )
    if "sec" in provenance or "filing" in provenance:
        return SEC_FILING
    if any(token in provenance for token in ("vendor", "licensed", "aggregator")):
        return LICENSED_VENDOR
    if metadata.get("successor_publisher") or metadata.get("publisher_relationship"):
        return SUCCESSOR_NATIVE
    if any(token in provenance for token in ("issuer", "native", "self_snapshotted")):
        return ISSUER_NATIVE
    return NO_SOURCE


def _transport_kind(
    snapshot: ETFHoldingsSnapshot | None, state: ETFHoldingsAdapterState | None
) -> str | None:
    state_metadata = _metadata(state.extra_data if state else None)
    snapshot_metadata = _metadata(snapshot.extra_data if snapshot else None)
    state_metadata = {**state_metadata, **_metadata(state_metadata.get("legal_metadata"))}
    snapshot_metadata = {**snapshot_metadata, **_metadata(snapshot_metadata.get("legal_metadata"))}
    explicit = state_metadata.get("transport_kind") or snapshot_metadata.get("transport_kind")
    if explicit:
        return str(explicit)
    if snapshot is None:
        return None
    url = str(snapshot.source_url or "").lower()
    if snapshot.source_provider == "sec" or "sec" in str(snapshot.provenance).lower():
        return "sec_filing"
    if url.endswith((".csv", ".xls", ".xlsx", ".pdf", ".zip")):
        return "file_export"
    if url.startswith(("http://", "https://")):
        return "structured_or_page"
    return "stored_artifact"


def _identity_verified(
    snapshot: ETFHoldingsSnapshot | None, state: ETFHoldingsAdapterState | None
) -> bool:
    for value in (
        _metadata(snapshot.extra_data if snapshot else None),
        _metadata(state.extra_data if state else None),
    ):
        validation = value.get("artifact_identity_validation")
        if not validation:
            validation = _metadata(value.get("legal_metadata")).get("artifact_identity_validation")
        if _metadata(validation).get("status") in {"matched", "matched_inferred"}:
            return True
    return False


def infer_expected_cadence(
    *,
    source_access: str | None = None,
    metadata: dict[str, Any] | None = None,
    source_tier: str | None = None,
) -> str:
    """Infer a conservative cadence from explicit adapter/source metadata.

    New and repaired adapters should provide ``expected_cadence`` explicitly.
    Existing adapters retain a short seven-day conservative window until their
    source cadence is reviewed, rather than being marked current indefinitely.
    """

    metadata = metadata or {}
    explicit = str(metadata.get("expected_cadence") or "").strip().lower()
    if explicit in _CADENCE_WINDOWS:
        return explicit
    if source_tier == SEC_FILING:
        return "filing"
    text = str(source_access or "").lower()
    for cadence in ("daily", "weekly", "monthly", "quarterly"):
        if cadence in text:
            return cadence
    return "unspecified"


def freshness_deadline(composition_date: date | None, cadence: str) -> date | None:
    if composition_date is None:
        return None
    return composition_date + _CADENCE_WINDOWS.get(cadence, _CADENCE_WINDOWS["unspecified"])


_TIER_0_SYMBOL_AUDITS: dict[str, ETFHoldingsSymbolAudit] = {
    "DXJ": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="issuer_route_access_blocked",
        provider_identity="wisdomtree",
        investigated_at=date(2026, 9, 4),
        next_action=(
            "Re-test WisdomTree's official DXJ route; promote only after complete, "
            "identity-verified current rows and live evidence."
        ),
    ),
    "NTSX": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="issuer_route_access_blocked",
        provider_identity="wisdomtree",
        investigated_at=date(2026, 9, 4),
        next_action=(
            "Re-test WisdomTree's official NTSX route; promote only after complete, "
            "identity-verified current rows and live evidence."
        ),
    ),
    "MINT": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="no_complete_executable_public_artifact",
        provider_identity="pacific_investments",
        investigated_at=date(2026, 9, 4),
        next_action=(
            "Re-check PIMCO's official MINT holdings/download surfaces; do not treat "
            "top-ten or factsheet data as a complete basket."
        ),
    ),
    "BOND": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="no_complete_executable_public_artifact",
        provider_identity="pacific_investments",
        investigated_at=date(2026, 9, 4),
        next_action=(
            "Re-check PIMCO's official BOND holdings/download surfaces; do not treat "
            "top-ten or factsheet data as a complete basket."
        ),
    ),
    "GEME": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=NOT_APPLICABLE,
        evidence_state="identity_requires_reconciliation",
        provider_identity="pacific_investments",
        investigated_at=date(2026, 9, 4),
        next_action="Resolve GEME's sponsor/publisher identity before selecting a holdings route.",
    ),
}

_TIER_0_ADAPTER_ALIASES: dict[str, frozenset[str]] = {
    # The F/m product family is represented by the reconciled
    # ``us_benchmark_series`` adapter while the publisher identity is
    # ``fm_investments`` in the audit ledger.
    "fm_investments": frozenset({"fm_investments", "us_benchmark_series"}),
}

for _symbol in (
    "TBIL",
    "XBIL",
    "OBIL",
    "UTWO",
    "UTRE",
    "UFIV",
    "USVN",
    "UTEN",
    "UTWY",
    "UTHY",
):
    _TIER_0_SYMBOL_AUDITS[_symbol] = ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="route_requires_bounded_canary",
        provider_identity="fm_investments",
        investigated_at=date(2026, 9, 4),
        next_action=(
            "Run the opt-in F/m symbol-scoped canary and record source, schema, "
            "completeness, and freshness evidence."
        ),
    )


def symbol_audit_for_profile(profile: ETFProfile) -> ETFHoldingsSymbolAudit:
    """Return conservative symbol-level source evidence for an ETF profile."""

    instrument = getattr(profile, "instrument", None)
    symbol = str(getattr(instrument, "symbol", "") or "").strip().upper()
    tier_0 = _TIER_0_SYMBOL_AUDITS.get(symbol)
    adapter_key = str(getattr(profile, "adapter_key", "") or "").strip().lower()
    if tier_0 is not None:
        provider_identity = (tier_0.provider_identity or "").strip().lower()
        expected_adapter_keys = _TIER_0_ADAPTER_ALIASES.get(
            provider_identity, frozenset({provider_identity})
        )
        if adapter_key in expected_adapter_keys:
            return tier_0
        return ETFHoldingsSymbolAudit(
            tier=0,
            outcome=UNKNOWN,
            evidence_state="profile_provider_identity_mismatch",
            provider_identity=adapter_key or None,
            investigated_at=tier_0.investigated_at,
            next_action=(
                f"Reconcile the {symbol} ETF profile with the audited "
                f"{tier_0.provider_identity} identity before using its source evidence."
            ),
        )
    fallback = FALLBACK_ISSUER_AUDITS.get(adapter_key)
    if fallback is not None:
        if fallback.status in {
            "inactive_or_successor_disposition",
            "provider_not_a_portfolio_publisher",
        }:
            outcome = NOT_APPLICABLE
            evidence_state = "identity_level_terminal_disposition"
        else:
            outcome = UNKNOWN
            evidence_state = "identity_level_only"
        return ETFHoldingsSymbolAudit(
            tier=1,
            outcome=outcome,
            evidence_state=evidence_state,
            provider_identity=adapter_key or None,
            investigated_at=fallback.last_checked,
            next_action=fallback.next_action,
        )

    return ETFHoldingsSymbolAudit(
        tier=2,
        outcome=UNKNOWN,
        evidence_state="no_symbol_audit_record",
        provider_identity=adapter_key or None,
        investigated_at=None,
        next_action="Record a symbol-scoped first-party source investigation before claiming support.",
    )


def evaluate_capability(
    profile: ETFProfile,
    snapshot: ETFHoldingsSnapshot | None,
    state: ETFHoldingsAdapterState | None,
    *,
    now: datetime | None = None,
) -> ETFHoldingsCapability:
    """Evaluate current usability without contacting an external provider."""

    now = _as_utc(now or datetime.now(UTC)) or datetime.now(UTC)
    state_metadata = _metadata(state.extra_data if state else None)
    source_tier = _source_tier(snapshot, state)
    cadence = infer_expected_cadence(
        source_access=state_metadata.get("source_access"),
        metadata=state_metadata,
        source_tier=source_tier,
    )
    composition_date = snapshot.composition_date if snapshot else None
    deadline = freshness_deadline(composition_date, cadence)
    checked = _as_utc(state.last_checked_at if state else None)
    success = _as_utc(state.last_success_at if state else None)
    failure = _as_utc(state.last_failure_at if state else None)
    complete = bool(snapshot and snapshot.completeness_status in _COMPLETE_STATUSES)
    has_snapshot = snapshot is not None
    identity_verified = _identity_verified(snapshot, state)
    state_status = str(state.status if state else "").lower()
    failure_reason = state.failure_reason if state else None
    schema_fingerprint = state_metadata.get("schema_fingerprint")

    if not profile.adapter_key or profile.adapter_key == "unresolved":
        availability = NOT_APPLICABLE if not has_snapshot else STALE
        reason = "No concrete ETF holdings adapter is assigned to this profile."
    elif not has_snapshot:
        availability = (
            UNAVAILABLE
            if state_status
            in {
                "failure",
                "needs_issuer_route",
                "holdings_adapter_unresolved",
                "circuit_open",
            }
            else UNKNOWN
        )
        reason = failure_reason or "No holdings snapshot has been stored for this ETF."
    elif source_tier == SEC_FILING:
        availability = DEGRADED
        reason = "Holdings are reconstructed from SEC filings and are not issuer-current support."
    elif not identity_verified:
        availability = DEGRADED
        reason = "The latest holdings artifact has not passed explicit ETF identity verification."
    elif not complete:
        availability = DEGRADED
        reason = (
            "The latest snapshot is incomplete and cannot support current constituent analysis."
        )
    elif deadline is not None and now.date() > deadline:
        availability = STALE
        reason = f"The latest holdings composition passed its {cadence} freshness window."
    elif state_status == "success" and checked is not None and checked <= now:
        availability = CURRENT
        reason = "A complete holdings snapshot passed the latest adapter check."
    elif state_status in {
        "failure",
        "needs_issuer_route",
        "holdings_adapter_unresolved",
        "circuit_open",
    }:
        availability = DEGRADED
        reason = failure_reason or (
            "The latest holdings route check failed; showing last-known data only."
        )
    else:
        availability = UNKNOWN
        reason = (
            "A stored snapshot exists, but the route has not completed a current capability check."
        )

    symbol_audit = symbol_audit_for_profile(profile)
    if availability == CURRENT and symbol_audit.tier in {0, 1} and symbol_audit.outcome != CURRENT:
        audit_availability = symbol_audit.outcome
        if audit_availability not in {
            DEGRADED,
            STALE,
            UNAVAILABLE,
            NOT_APPLICABLE,
            UNKNOWN,
        }:
            audit_availability = UNKNOWN
        availability = audit_availability
        reason = (
            "The symbol-level source audit is not current support "
            f"({symbol_audit.evidence_state}); showing last-known data only."
        )
    usable = availability == CURRENT and source_tier in {
        ISSUER_NATIVE,
        SUCCESSOR_NATIVE,
        LICENSED_VENDOR,
    }
    return ETFHoldingsCapability(
        availability=availability,
        source_tier=source_tier,
        identity_verified=identity_verified,
        usable_for_current_analysis=usable,
        displayable_last_known=has_snapshot,
        adapter_key=profile.adapter_key,
        source_provider=snapshot.source_provider if snapshot else None,
        transport_kind=_transport_kind(snapshot, state),
        expected_cadence=cadence if has_snapshot or state is not None else None,
        composition_date=composition_date,
        published_at=snapshot.published_at if snapshot else None,
        last_checked_at=state.last_checked_at if state else None,
        last_success_at=state.last_success_at if state else success,
        last_failure_at=state.last_failure_at if state else failure,
        freshness_deadline=deadline,
        row_count=snapshot.row_count if snapshot else state.row_count if state else None,
        resolved_count=snapshot.resolved_count
        if snapshot
        else state.resolved_count
        if state
        else None,
        unresolved_count=snapshot.unresolved_count
        if snapshot
        else state.unresolved_count
        if state
        else None,
        completeness_status=snapshot.completeness_status
        if snapshot
        else state.completeness_status
        if state
        else None,
        failure_reason=failure_reason,
        consecutive_failures=int(
            state_metadata.get("consecutive_failures") or (1 if state_status == "failure" else 0)
        ),
        schema_fingerprint=str(schema_fingerprint) if schema_fingerprint else None,
        reason=reason,
        symbol_audit=symbol_audit,
    )
