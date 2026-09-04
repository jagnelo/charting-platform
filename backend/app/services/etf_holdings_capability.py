"""Truthful, per-symbol ETF holdings capability evaluation.

The adapter registry describes what code exists.  This module describes what a
particular ETF can safely claim *now*, based on the latest stored snapshot and
the most recent adapter check.  In particular, SEC reconstruction and stale
snapshots remain visible but never become current issuer support implicitly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "outcome": self.outcome,
            "evidence_state": self.evidence_state,
            "provider_identity": self.provider_identity,
            "investigated_at": self.investigated_at,
            "next_action": self.next_action,
            "evidence_refs": list(self.evidence_refs),
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

_SHADOW_GATE_WINDOW_DAYS = 30
_SHADOW_GATE_MINIMUM_SUCCESS_RATE = 0.95
_SHADOW_GATE_MAX_CONSECUTIVE_MISSED_FRESHNESS = 1


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
        evidence_refs=(
            "web:wisdomtree-current-fund-holdings-2026-09-03",
            "live:wisdomtree-current-fund-holdings-2026-09-03-blocked",
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
        evidence_refs=(
            "web:wisdomtree-current-fund-holdings-2026-09-03",
            "live:wisdomtree-current-fund-holdings-2026-09-03-blocked",
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
        evidence_refs=("web:pacific-investments-geme-pimco-mint-2026-09-03",),
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
        evidence_refs=("web:pacific-investments-geme-pimco-mint-2026-09-03",),
    ),
    "GEME": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=NOT_APPLICABLE,
        evidence_state="identity_requires_reconciliation",
        provider_identity="pacific_investments",
        investigated_at=date(2026, 9, 4),
        next_action="Resolve GEME's sponsor/publisher identity before selecting a holdings route.",
        evidence_refs=("web:pacific-investments-geme-pimco-mint-2026-09-03",),
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
        evidence_refs=("web:us-benchmark-series-current-fm-pages-2026-09-04",),
    )


_NON_TIER_0_SYMBOL_AUDITS: dict[str, ETFHoldingsSymbolAudit] = {}


def _register_non_tier_0_audits(
    symbols: Sequence[str],
    *,
    outcome: str,
    evidence_state: str,
    provider_identity: str,
    investigated_at: date,
    evidence_refs: tuple[str, ...],
    next_action: str,
) -> None:
    for raw_symbol in symbols:
        symbol = raw_symbol.strip().upper()
        if not symbol:
            continue
        _NON_TIER_0_SYMBOL_AUDITS[symbol] = ETFHoldingsSymbolAudit(
            tier=1,
            outcome=outcome,
            evidence_state=evidence_state,
            provider_identity=provider_identity,
            investigated_at=investigated_at,
            next_action=next_action,
            evidence_refs=evidence_refs,
        )


_register_non_tier_0_audits(
    ("TALV", "TABD"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="aegon",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:aegonam-us-asset-management-capabilities-2026-09-03",),
    next_action=(
        "Re-test the official Transamerica TALV/TABD product and holdings routes; promote "
        "only after complete current rows, symbol mapping, parser coverage, and bounded "
        "live evidence are proven."
    ),
)
_register_non_tier_0_audits(
    ("ADFI",),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="anfield",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:anfield-adfi-current-close-notice-2026-09-03",),
    next_action=(
        "Confirm the ADFI closure/successor record; reopen only if a current successor "
        "issuer publishes a complete executable holdings artifact."
    ),
)
_register_non_tier_0_audits(
    ("GAUD", "GAID"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="guinness_atkinson",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:guinness-atkinson-fund-resources-2026-09-03",),
    next_action=(
        "Re-test the official Fund Resources and symbol-scoped ETF routes; promote only "
        "after complete rows, mapping, parser fixtures, and bounded live evidence are available."
    ),
)
_register_non_tier_0_audits(
    ("UDIV", "UDEF", "GEDG"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="manulife",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:manulife-canadian-etf-catalogue-2026-09-03",),
    next_action=(
        "Re-test Manulife/John Hancock symbol-scoped routes; promote only if a complete "
        "U.S.-listed holdings artifact, mapping, parser fixture, and live proof are established."
    ),
)
_register_non_tier_0_audits(
    ("QVOY",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="q3",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:q3-qvoy-official-etf-page-2026-09-03",),
    next_action=(
        "Re-test the QVOY page and declared holdings route after the issuer throttle clears; "
        "promote only after complete rows, mapping, parser fixtures, and live evidence are available."
    ),
)
_register_non_tier_0_audits(
    ("ACVF",),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_not_portfolio_publisher",
    provider_identity="ridgeline",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:ridgeline-acvf-adviser-identity-2026-09-03",),
    next_action=(
        "Keep ACVF under its existing ACV publisher route; reopen Ridgeline only if a distinct "
        "issuer-owned ETF holdings publisher is identified."
    ),
)
_register_non_tier_0_audits(
    ("MDST",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="westwood",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:westwood-mdst-current-holdings-2026-09-03",),
    next_action=(
        "Periodically re-test the official MDST page and declared CSV; promote only after "
        "complete rows, mapping, parser fixtures, and bounded live evidence are available."
    ),
)
_register_non_tier_0_audits(
    ("SPDV", "BDIV", "TRFM", "PFLD"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="advisors_asset_management",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:aam-etf-detail-empty-backend-response-2026-09-02",),
    next_action=(
        "Re-test AAM's symbol-scoped detail/export route from an allowed network path; promote "
        "only after capturing a complete artifact, mapping symbols, and adding parser plus "
        "bounded live coverage."
    ),
)
_register_non_tier_0_audits(
    ("ALFA", "ALFS", "ALFD", "ALFV"),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="alphaclone",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:alphaclone-domain-unrelated-content-2026-09-02",),
    next_action=(
        "Confirm liquidation or successor disposition for the historical AlphaClone symbols "
        "through current fund records; reopen only if a legitimate successor publishes "
        "complete holdings."
    ),
)
_register_non_tier_0_audits(
    ("SMCP",),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="alphamark_advisors",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:alphamark-redirect-2026-09-02",),
    next_action=(
        "Verify whether EP Wealth publishes a current complete SMCP successor holdings route; "
        "promote only after a stable issuer-owned executable artifact and live parser evidence exist."
    ),
)
_register_non_tier_0_audits(
    ("AAAA",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="amplius",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:amplius-aaaa-holdings-cloudflare-2026-09-02",),
    next_action=(
        "Re-test the issuer page or identify an issuer-published machine-readable route that is "
        "executable without browser challenge state; promote only after fixture and bounded live evidence."
    ),
)
_register_non_tier_0_audits(
    ("NDOW",),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="anydrus",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:anydrus-ndow-placeholder-holdings-2026-09-02",),
    next_action=(
        "Re-test the NDOW page for a populated complete download; promote only after current rows, "
        "symbol mapping, parser fixtures, and bounded live evidence are available."
    ),
)
_register_non_tier_0_audits(
    ("AMID", "ABIG", "ALIL"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="argent",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:argent-etf-holdings-cloudflare-2026-09-02",),
    next_action=(
        "Re-test symbol-scoped pages or identify an issuer-published machine-readable export accessible "
        "without challenge state; promote only after parser and bounded live evidence."
    ),
)
_register_non_tier_0_audits(
    ("ATTR",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="arin",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:arin-attr-holdings-cloudflare-2026-09-02",),
    next_action=(
        "Re-test the ATTR page or identify an issuer-published machine-readable export accessible "
        "without challenge state; promote only after parser and bounded live evidence."
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
            evidence_refs=tier_0.evidence_refs,
        )
    explicit = _NON_TIER_0_SYMBOL_AUDITS.get(symbol)
    if explicit is not None:
        provider_identity = (explicit.provider_identity or "").strip().lower()
        if adapter_key == provider_identity:
            return explicit
        return ETFHoldingsSymbolAudit(
            tier=explicit.tier,
            outcome=UNKNOWN,
            evidence_state="profile_provider_identity_mismatch",
            provider_identity=adapter_key or None,
            investigated_at=explicit.investigated_at,
            next_action=(
                f"Reconcile the {symbol} ETF profile with the audited "
                f"{provider_identity} identity before using its source evidence."
            ),
            evidence_refs=explicit.evidence_refs,
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


def evaluate_tier0_shadow_gate(
    observations_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    now: date | datetime | None = None,
    window_days: int = _SHADOW_GATE_WINDOW_DAYS,
    eligible_symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Evaluate the post-deployment Tier 0 shadow acceptance criteria.

    Observations are the bounded records persisted by the ETF canary.  A check
    is eligible when it has a parseable observation timestamp and is not a
    missing-profile report.  A passing check must be a successful, current,
    identity-verified, complete, current-analysis-usable observation whose
    freshness deadline has not elapsed.  This deliberately treats an otherwise
    successful fetch as a failure when the symbol audit is unresolved.
    """

    if isinstance(now, datetime):
        end_date = _as_utc(now).date() if _as_utc(now) is not None else date.today()
    else:
        end_date = now or date.today()
    days = max(1, int(window_days))
    start_date = end_date - timedelta(days=days - 1)
    requested_symbols = {
        str(symbol).strip().upper()
        for symbol in (eligible_symbols or _TIER_0_SYMBOL_AUDITS)
        if str(symbol).strip()
    }
    silent_violations: list[dict[str, Any]] = []
    eligible_checks = 0
    passing_checks = 0
    observed_symbols: set[str] = set()
    missing_symbols: list[str] = []
    max_consecutive_missed = 0
    missed_by_symbol: dict[str, int] = {}

    for raw_symbol in sorted(requested_symbols):
        symbol = raw_symbol.upper()
        observations = (
            observations_by_symbol.get(symbol) or observations_by_symbol.get(raw_symbol) or ()
        )
        parsed: list[tuple[date, Mapping[str, Any]]] = []
        for observation in observations:
            if not isinstance(observation, Mapping):
                continue
            observed_at = observation.get("observed_at") or observation.get("last_canary_at")
            try:
                observed_date = datetime.fromisoformat(str(observed_at)).date()
            except (TypeError, ValueError):
                continue
            if observed_date < start_date or observed_date > end_date:
                continue
            if str(observation.get("status") or "").lower() == "missing_profile":
                continue
            parsed.append((observed_date, observation))
        if not parsed:
            missing_symbols.append(symbol)
            continue
        observed_symbols.add(symbol)
        parsed.sort(key=lambda item: item[0])
        consecutive_missed = 0
        for observed_date, observation in parsed:
            eligible_checks += 1
            status = str(observation.get("status") or "").lower()
            availability = str(observation.get("availability") or "").lower()
            completeness = str(observation.get("completeness_status") or "").lower()
            source_tier = str(observation.get("source_tier") or "").lower()
            identity_verified = observation.get("identity_verified") is True
            usable = observation.get("usable_for_current_analysis") is True
            deadline_value = observation.get("freshness_deadline")
            try:
                deadline = date.fromisoformat(str(deadline_value)) if deadline_value else None
            except ValueError:
                deadline = None
            missed_freshness = availability == STALE or (
                deadline is not None and observed_date > deadline
            )
            if missed_freshness:
                consecutive_missed += 1
                max_consecutive_missed = max(max_consecutive_missed, consecutive_missed)
            else:
                consecutive_missed = 0

            symbol_audit_outcome = str(observation.get("symbol_audit_outcome") or "").lower()
            violation: str | None = None
            if availability == CURRENT and (
                not identity_verified
                or completeness not in _COMPLETE_STATUSES
                or source_tier not in {ISSUER_NATIVE, SUCCESSOR_NATIVE, LICENSED_VENDOR}
                or symbol_audit_outcome != CURRENT
            ):
                violation = "current_observation_failed_identity_completeness_or_source_gate"
            elif usable and availability != CURRENT:
                violation = "non_current_observation_marked_current_analysis_usable"
            if violation:
                silent_violations.append(
                    {
                        "symbol": symbol,
                        "observed_at": str(observation.get("observed_at") or ""),
                        "reason": violation,
                    }
                )

            is_passing = (
                status == "success"
                and availability == CURRENT
                and identity_verified
                and completeness in _COMPLETE_STATUSES
                and source_tier in {ISSUER_NATIVE, SUCCESSOR_NATIVE, LICENSED_VENDOR}
                and usable
                and deadline is not None
                and not missed_freshness
                and symbol_audit_outcome == CURRENT
            )
            if is_passing:
                passing_checks += 1
        missed_by_symbol[symbol] = consecutive_missed

    success_rate = passing_checks / eligible_checks if eligible_checks else 0.0
    reasons: list[str] = []
    if eligible_checks == 0:
        reasons.append("no eligible Tier 0 observations in the shadow window")
    elif success_rate < _SHADOW_GATE_MINIMUM_SUCCESS_RATE:
        reasons.append(
            f"eligible-check success rate {success_rate:.3f} is below "
            f"{_SHADOW_GATE_MINIMUM_SUCCESS_RATE:.2f}"
        )
    if max_consecutive_missed > _SHADOW_GATE_MAX_CONSECUTIVE_MISSED_FRESHNESS:
        reasons.append(
            f"maximum consecutive missed freshness deadlines is {max_consecutive_missed}"
        )
    if silent_violations:
        reasons.append(f"{len(silent_violations)} silent identity/schema/completeness violation(s)")
    if missing_symbols:
        reasons.append(
            "missing eligible Tier 0 observations for: " + ", ".join(sorted(missing_symbols))
        )

    return {
        "status": "pass" if not reasons else "fail",
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "window_days": days,
        "eligible_symbols": sorted(requested_symbols),
        "observed_symbols": sorted(observed_symbols),
        "missing_symbols": sorted(missing_symbols),
        "eligible_checks": eligible_checks,
        "passing_checks": passing_checks,
        "success_rate": round(success_rate, 4),
        "minimum_success_rate": _SHADOW_GATE_MINIMUM_SUCCESS_RATE,
        "max_consecutive_missed_freshness_deadlines": max_consecutive_missed,
        "max_allowed_consecutive_missed_freshness_deadlines": _SHADOW_GATE_MAX_CONSECUTIVE_MISSED_FRESHNESS,
        "silent_violation_count": len(silent_violations),
        "silent_violations": silent_violations,
        "failure_reasons": reasons,
        "missed_freshness_by_symbol": missed_by_symbol,
    }


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
