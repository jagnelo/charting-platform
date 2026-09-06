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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.etf_holdings import ETFHoldingsAdapterState, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
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
CONTROLLED_FIXTURE = "controlled_fixture"
_CURRENT_SOURCE_TIERS = {ISSUER_NATIVE, SUCCESSOR_NATIVE, LICENSED_VENDOR}
_CANARY_HISTORY_LIMIT = 90


async def load_latest_adapter_state(
    db: AsyncSession,
    profile_id: int,
) -> ETFHoldingsAdapterState | None:
    """Load the latest persisted route-health state for one ETF profile.

    Current-analysis consumers must evaluate the same per-profile state as the
    holdings capability endpoint.  Keeping this lookup here prevents a read
    surface from accidentally treating a stored snapshot as current merely
    because it is the newest row in the database.
    """

    return (
        await db.execute(
            select(ETFHoldingsAdapterState)
            .where(ETFHoldingsAdapterState.etf_profile_id == profile_id)
            .order_by(
                ETFHoldingsAdapterState.last_checked_at.desc().nullslast(),
                ETFHoldingsAdapterState.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


def tier0_symbols() -> tuple[str, ...]:
    """Return the canonical Tier 0 symbol set used by the shadow gate."""

    return tuple(sorted(_TIER_0_SYMBOL_AUDITS))


async def load_tier0_shadow_observations(
    db: AsyncSession,
    *,
    eligible_symbols: Sequence[str] | None = None,
) -> dict[str, list[Mapping[str, Any]]]:
    """Collect bounded canary histories for the Tier 0 symbols.

    Adapter state is the ETF-owned persistence boundary for canary evidence.
    This read intentionally returns only recorded observations; it never probes
    an issuer route or synthesizes a passing observation for a missing symbol.
    """

    requested_symbols = {
        str(symbol).strip().upper()
        for symbol in (eligible_symbols or tier0_symbols())
        if str(symbol).strip()
    }
    observations_by_symbol: dict[str, list[Mapping[str, Any]]] = {
        symbol: [] for symbol in requested_symbols
    }
    if not requested_symbols:
        return observations_by_symbol

    rows = (
        await db.execute(
            select(ETFHoldingsAdapterState, Instrument.symbol)
            .join(ETFProfile, ETFProfile.id == ETFHoldingsAdapterState.etf_profile_id)
            .join(Instrument, Instrument.id == ETFProfile.instrument_id)
            .where(func.upper(Instrument.symbol).in_(requested_symbols))
        )
    ).all()
    for state, raw_symbol in rows:
        symbol = str(raw_symbol).strip().upper()
        metadata = state.extra_data if isinstance(state.extra_data, dict) else {}
        history = metadata.get("canary_history")
        if not isinstance(history, list):
            continue
        observations_by_symbol.setdefault(symbol, []).extend(
            observation for observation in history if isinstance(observation, Mapping)
        )
    for symbol, observations in observations_by_symbol.items():
        observations.sort(
            key=lambda observation: str(
                observation.get("observed_at") or observation.get("last_canary_at") or ""
            )
        )
        observations_by_symbol[symbol] = observations[-_CANARY_HISTORY_LIMIT:]
    return observations_by_symbol


async def load_canary_history(
    db: AsyncSession,
    profile_id: int,
    *,
    limit: int = 90,
) -> list[Mapping[str, Any]]:
    """Return the bounded persisted canary history for one ETF profile.

    This is an observation read only: it never probes a provider or infers a
    passing result.  The persisted history is already capped by the canary
    writer; the read applies a second caller-controlled bound for safe admin
    inspection.
    """

    state = await load_latest_adapter_state(db, profile_id)
    if state is None:
        return []
    metadata = _metadata(state.extra_data)
    history = metadata.get("canary_history")
    if not isinstance(history, list):
        return []
    bounded_limit = max(1, min(int(limit), _CANARY_HISTORY_LIMIT))
    return [
        dict(observation)
        for observation in history[-bounded_limit:]
        if isinstance(observation, Mapping)
    ]


async def load_canary_history_for_symbol(
    db: AsyncSession,
    symbol: str,
    *,
    limit: int = 90,
) -> list[Mapping[str, Any]]:
    """Read canary history for an existing symbol without hydrating catalog rows."""

    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return []
    profile_id = (
        await db.execute(
            select(ETFProfile.id)
            .join(Instrument, Instrument.id == ETFProfile.instrument_id)
            .where(func.upper(Instrument.symbol) == normalized_symbol)
            .limit(1)
        )
    ).scalar_one_or_none()
    if profile_id is None:
        return []
    return await load_canary_history(db, int(profile_id), limit=limit)


def current_analysis_error_detail(capability: ETFHoldingsCapability) -> dict[str, Any]:
    """Return the stable API detail for a non-current holdings capability."""

    return {
        "code": "etf_holdings_not_current",
        "availability": capability.availability,
        "source_tier": capability.source_tier,
        "usable_for_current_analysis": False,
        "failure_class": capability.failure_class,
        "reason": capability.reason,
    }


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
    last_canary_at: datetime | None
    last_canary_status: str | None
    last_canary_latency_ms: float | None
    last_canary_recovered: bool | None
    circuit_state: str | None
    circuit_open_until: datetime | None
    freshness_deadline: date | None
    row_count: int | None
    resolved_count: int | None
    unresolved_count: int | None
    completeness_status: str | None
    failure_reason: str | None
    failure_class: str | None
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
            "last_canary_at": self.last_canary_at,
            "last_canary_status": self.last_canary_status,
            "last_canary_latency_ms": self.last_canary_latency_ms,
            "last_canary_recovered": self.last_canary_recovered,
            "circuit_state": self.circuit_state,
            "circuit_open_until": self.circuit_open_until,
            "freshness_deadline": self.freshness_deadline,
            "row_count": self.row_count,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "completeness_status": self.completeness_status,
            "failure_reason": self.failure_reason,
            "failure_class": self.failure_class,
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


def _metadata_datetime(metadata: Mapping[str, Any], key: str) -> datetime | None:
    """Parse an optional persisted ISO timestamp without making reads fail open."""

    value = metadata.get(key)
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return _as_utc(parsed)


def _metadata_float(metadata: Mapping[str, Any], key: str) -> float | None:
    value = metadata.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _metadata_bool(metadata: Mapping[str, Any], key: str) -> bool | None:
    value = metadata.get(key)
    return value if isinstance(value, bool) else None


def _failure_streak(metadata: Mapping[str, Any], *, state_status: str) -> int:
    """Read persisted health state without allowing malformed JSON to crash reads."""

    fallback = 1 if state_status == "failure" else 0
    value = metadata.get("consecutive_failures")
    if value in (None, ""):
        return fallback
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


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
    if explicit in {
        ISSUER_NATIVE,
        SUCCESSOR_NATIVE,
        LICENSED_VENDOR,
        SEC_FILING,
        NO_SOURCE,
        CONTROLLED_FIXTURE,
    }:
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
    entitlement_status = (
        str(
            metadata.get("entitlement_status")
            or metadata.get("entitlement_class")
            or metadata.get("data_entitlement")
            or ""
        )
        .strip()
        .lower()
    )
    if metadata.get("licensed_vendor") is True or entitlement_status in {
        "licensed",
        "licensed_vendor",
        "entitled",
    }:
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


def _source_provider(
    profile: ETFProfile,
    snapshot: ETFHoldingsSnapshot | None,
    state: ETFHoldingsAdapterState | None,
) -> str | None:
    """Keep the known provider visible even when a route has no snapshot yet."""

    if snapshot is not None and snapshot.source_provider:
        return str(snapshot.source_provider)
    state_metadata = _metadata(state.extra_data if state else None)
    for key in ("source_provider", "provider_identity"):
        value = state_metadata.get(key)
        if value:
            return str(value)
    adapter_key = str(profile.adapter_key or "").strip()
    if adapter_key and adapter_key != "unresolved":
        return adapter_key
    return None


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


def _future_snapshot_reason(
    snapshot: ETFHoldingsSnapshot | None,
    *,
    now: datetime,
) -> str | None:
    """Keep legacy future-dated rows from being advertised as current.

    The ingestion boundary rejects new future metadata, but old rows or direct
    database imports can predate that guard.  Capability reads must therefore
    fail closed as well instead of trusting a future freshness deadline.
    """

    if snapshot is None:
        return None
    reference_date = now.date()
    for label, value in (
        ("composition", snapshot.composition_date),
        ("as-of", getattr(snapshot, "as_of_date", None)),
    ):
        if value is not None and value > reference_date:
            return (
                "The latest holdings artifact has a future " f"{label} date ({value.isoformat()})."
            )
    published_at = getattr(snapshot, "published_at", None)
    if published_at is not None:
        normalized_published_at = (
            published_at if published_at.tzinfo is not None else published_at.replace(tzinfo=UTC)
        )
        if normalized_published_at > now:
            return "The latest holdings artifact has a future published-at timestamp."
    return None


_TIER_0_SYMBOL_AUDITS: dict[str, ETFHoldingsSymbolAudit] = {
    "DXJ": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="issuer_route_access_blocked",
        provider_identity="wisdomtree",
        investigated_at=date(2026, 9, 6),
        next_action=(
            "Keep DXJ unavailable and periodically re-test WisdomTree's official route; the "
            "public fund-holdings API requires an issuer session that is not repeatably "
            "executable through the application transport. Promote only after complete, "
            "identity-verified current rows and repeatable live evidence."
        ),
        evidence_refs=(
            "web:wisdomtree-public-fund-holdings-api-2026-09-05",
            "live:wisdomtree-public-fund-holdings-api-2026-09-05-httpx-403",
            "web:wisdomtree-dxj-product-page-2026-09-05-current",
            "live:wisdomtree-public-fund-holdings-api-2026-09-06-httpx-403",
            "web:etf-holdings-api-contract-2026-09-06",
        ),
    ),
    "NTSX": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="issuer_route_access_blocked",
        provider_identity="wisdomtree",
        investigated_at=date(2026, 9, 6),
        next_action=(
            "Keep NTSX unavailable and periodically re-test WisdomTree's official route; the "
            "public fund-holdings API requires an issuer session that is not repeatably "
            "executable through the application transport. Promote only after complete, "
            "identity-verified current rows and repeatable live evidence."
        ),
        evidence_refs=(
            "web:wisdomtree-public-fund-holdings-api-2026-09-05",
            "live:wisdomtree-public-fund-holdings-api-2026-09-05-httpx-403",
            "web:wisdomtree-ntsx-product-page-2026-09-05-current",
            "live:wisdomtree-public-fund-holdings-api-2026-09-06-httpx-403",
            "web:etf-holdings-api-contract-2026-09-06",
        ),
    ),
    "MINT": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="no_complete_executable_public_artifact",
        provider_identity="pacific_investments",
        investigated_at=date(2026, 9, 6),
        next_action=(
            "Keep MINT unavailable and re-test only when PIMCO exposes a changed route; its "
            "fund-detail API requires authentication and no complete public export is proven. Do "
            "not treat top-ten, factsheet, or DealCharts SEC N-PORT quarterly data as a current "
            "basket."
        ),
        evidence_refs=(
            "web:pimco-mint-daily-disclosure-2026-09-05",
            "live:pimco-mint-fund-detail-api-2026-09-05-unauthorized",
            "live:pimco-mint-fund-detail-api-2026-09-05-retest-unauthorized",
            "web:pimco-third-party-holdings-candidates-2026-09-05",
            "web:pimco-fund-ui-top-ten-only-2026-09-05",
            "live:pimco-fund-ui-top-ten-route-2026-09-05-forbidden",
            "live:pimco-www-top-ten-route-2026-09-05-not-found",
            "web:securitiesdb-free-etf-holdings-api-2026-09-05",
            "live:securitiesdb-mint-bond-no-holdings-2026-09-05",
            "live:securitiesdb-qqq-control-future-metadata-2026-09-05",
            "web:dealcharts-free-sec-nport-aggregator-2026-09-05",
            "live:dealcharts-mint-facts-2026-09-05-quarterly-stale",
            "web:pimco-mint-document-route-recheck-2026-09-05-404",
            "live:pimco-mint-fund-detail-api-2026-09-06-unauthorized",
            "web:pimco-public-fund-explorer-api-2026-09-06",
            "live:pimco-fund-explorer-metadata-2026-09-06",
            "live:pimco-creation-basket-not-holdings-2026-09-06",
            "web:etf-holdings-api-contract-2026-09-06",
        ),
    ),
    "BOND": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=UNAVAILABLE,
        evidence_state="no_complete_executable_public_artifact",
        provider_identity="pacific_investments",
        investigated_at=date(2026, 9, 6),
        next_action=(
            "Keep BOND unavailable and re-test only when PIMCO exposes a changed route; its "
            "fund-detail API requires authentication and no complete public export is proven. Do "
            "not treat top-ten, factsheet, or DealCharts SEC N-PORT quarterly data as a current "
            "basket."
        ),
        evidence_refs=(
            "web:pimco-bond-daily-disclosure-2026-09-05",
            "live:pimco-bond-fund-detail-api-2026-09-05-unauthorized",
            "live:pimco-bond-fund-detail-api-2026-09-05-retest-unauthorized",
            "web:pimco-third-party-holdings-candidates-2026-09-05",
            "web:pimco-fund-ui-top-ten-only-2026-09-05",
            "live:pimco-fund-ui-top-ten-route-2026-09-05-forbidden",
            "live:pimco-www-top-ten-route-2026-09-05-not-found",
            "web:securitiesdb-free-etf-holdings-api-2026-09-05",
            "live:securitiesdb-mint-bond-no-holdings-2026-09-05",
            "live:securitiesdb-qqq-control-future-metadata-2026-09-05",
            "web:dealcharts-free-sec-nport-aggregator-2026-09-05",
            "live:dealcharts-bond-facts-2026-09-05-quarterly-stale",
            "web:pimco-bond-document-route-recheck-2026-09-05-404",
            "live:pimco-bond-fund-detail-api-2026-09-06-unauthorized",
            "web:pimco-public-fund-explorer-api-2026-09-06",
            "live:pimco-fund-explorer-metadata-2026-09-06",
            "live:pimco-creation-basket-not-holdings-2026-09-06",
            "web:etf-holdings-api-contract-2026-09-06",
        ),
    ),
    "GEME": ETFHoldingsSymbolAudit(
        tier=0,
        outcome=CURRENT,
        evidence_state="issuer_current_canary_verified",
        provider_identity="pacific_investments",
        investigated_at=date(2026, 9, 5),
        next_action=(
            "Keep Pacific AM's GEME page canary bounded and freshness-aware; retain current "
            "only while the complete dated table remains identity-bound and executable."
        ),
        evidence_refs=(
            "web:pacific-asset-management-geme-holdings-2026-09-05",
            "live:pacific-asset-management-geme-holdings-2026-09-05",
        ),
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
        outcome=CURRENT,
        evidence_state="issuer_current_canary_verified",
        provider_identity="fm_investments",
        investigated_at=date(2026, 9, 5),
        next_action=(
            "Keep the F/m symbol-scoped canary bounded and freshness-aware; retain current "
            "only while the issuer API remains complete, identity-bound, and within deadline."
        ),
        evidence_refs=(
            "web:us-benchmark-series-current-fm-pages-2026-09-04",
            "live:fm-investments-tier0-canary-2026-09-05",
        ),
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
    investigated_at=date(2026, 9, 5),
    evidence_refs=(
        "web:q3-qvoy-official-etf-page-2026-09-03",
        "web:q3-qvoy-official-etf-page-2026-09-05",
        "live:q3-qvoy-official-etf-page-2026-09-05-application-503",
        "live:q3-qvoy-download-route-2026-09-05-application-503",
    ),
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
    investigated_at=date(2026, 9, 5),
    evidence_refs=(
        "web:westwood-mdst-current-holdings-2026-09-03",
        "web:westwood-mdst-current-holdings-2026-09-05",
        "live:westwood-mdst-current-holdings-page-2026-09-05-403",
        "live:westwood-mdst-current-holdings-csv-2026-09-05-403",
    ),
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
    investigated_at=date(2026, 9, 5),
    evidence_refs=(
        "web:aam-etf-detail-empty-backend-response-2026-09-02",
        "web:aam-spdv-current-paginated-holdings-2026-09-05",
        "live:aam-spdv-application-empty-reply-2026-09-05",
    ),
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
    evidence_state="future_dated_source",
    provider_identity="amplius",
    investigated_at=date(2026, 9, 5),
    evidence_refs=(
        "web:amplius-aaaa-current-holdings-page-2026-09-05",
        "live:amplius-aaaa-application-200-2026-09-05",
        "live:amplius-aaaa-future-effective-date-2026-09-05",
    ),
    next_action=(
        "Re-test AAAA after the issuer effective date is no longer in the future; retain the "
        "provider-specific parser and add bounded live evidence before native promotion."
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
_register_non_tier_0_audits(
    ("AVOS",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="avos",
    investigated_at=date(2026, 9, 4),
    evidence_refs=(
        "web:avos-current-holdings-page-2026-09-04",
        "live:avos-current-holdings-page-2026-09-04-blocked",
    ),
    next_action=(
        "Periodically re-test the official AVOS page; promote only after backend access "
        "returns complete current rows with proven mapping."
    ),
)
_register_non_tier_0_audits(
    ("BGGG", "BGIA", "BGEG", "BGUS"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="baillie_gifford",
    investigated_at=date(2026, 9, 2),
    evidence_refs=("web:baillie-gifford-top-ten-only-2026-09-02",),
    next_action=(
        "Locate a complete constituent export for each U.S. ETF, prove symbol mapping and "
        "identifiers, then add a provider-specific parser and live route test."
    ),
)
_register_non_tier_0_audits(
    ("CHRG",),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="elements",
    investigated_at=date(2026, 9, 2),
    evidence_refs=(
        "web:elements-chrg-liquidation-2026-09-02",
        "web:elements-successor-no-etf-route-2026-09-02",
    ),
    next_action=(
        "Keep fallback-only as an inactive_or_successor_disposition; resolve any historical "
        "CHRG references to the Energy & Minerals Group successor only if a current U.S.-listed "
        "ETF is re-established with a complete executable first-party holdings route."
    ),
)
_register_non_tier_0_audits(
    ("USSE",),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_not_portfolio_publisher",
    provider_identity="emirate_abu_dhabi",
    investigated_at=date(2026, 9, 2),
    evidence_refs=(
        "web:sec-usse-segall-bryant-2026-09-02",
        "web:ci-sbh-usse-page-2026-09-02",
    ),
    next_action=(
        "Keep fallback-only as a non-publisher identity; resolve USSE references to the "
        "separately tracked Segall Bryant & Hamill/CI SBH identity and do not create a duplicate route."
    ),
)
_register_non_tier_0_audits(
    ("AIEQ", "AWAY", "BDRY", "BWET"),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="etf_managers_group",
    investigated_at=date(2026, 9, 2),
    evidence_refs=(
        "web:amplify-etfmg-acquisition-complete-2026-09-02",
        "web:etfmg-domain-unreachable-successor-amplify-2026-09-02",
    ),
    next_action=(
        "Keep fallback-only as an inactive_or_successor_disposition; resolve historical ETFMG "
        "symbols to their Amplify successor or actual current sponsor and reopen only if ETFMG "
        "resumes a distinct U.S.-listed ETF portfolio with an executable first-party route."
    ),
)
_register_non_tier_0_audits(
    ("ABFL", "ABLG", "ABLD", "ABOT", "ABLS", "ABXB"),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="fcf_advisors",
    investigated_at=date(2026, 9, 2),
    evidence_refs=(
        "web:abacus-fcf-rebrand-2026-09-02",
        "web:abacus-fcf-catalogue-2026-09-02",
        "web:abacus-fcf-current-holdings-2026-09-02",
    ),
    next_action=(
        "Keep fallback-only as an inactive_or_successor_disposition; resolve historical FCF "
        "Advisors symbols to the existing Abacus FCF/abacus_global adapter and reopen only if "
        "FCF Advisors resumes a distinct U.S.-listed ETF portfolio with an executable route."
    ),
)
_register_non_tier_0_audits(
    ("FMCX", "FMCE"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="first_manhattan",
    investigated_at=date(2026, 9, 2),
    evidence_refs=(
        "web:first-manhattan-official-etf-catalogue-2026-09-02",
        "web:first-manhattan-daily-holdings-disclosure-2026-09-02",
        "web:first-manhattan-fmcx-prospectus-2026-09-02",
    ),
    next_action=(
        "Re-test only if First Manhattan publishes a complete executable current holdings "
        "artifact for FMCX and FMCE; then prove symbol mapping, current-date provenance, "
        "parser fixtures, and bounded live coverage before native promotion."
    ),
)
_register_non_tier_0_audits(
    ("FFHG", "FFSG", "FFTG", "FFTI"),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="formula_folio",
    investigated_at=date(2026, 9, 2),
    evidence_refs=(
        "web:formula-folios-official-liquidation-supplement-2026-09-02",
        "web:brookstone-formulafolios-successor-2026-09-02",
    ),
    next_action=(
        "Keep fallback-only as an inactive_or_successor_disposition; resolve historical FormulaFolios "
        "symbols to their October 2023 liquidation and Brookstone successor context, and reopen "
        "only if a distinct current FormulaFolios portfolio is re-established."
    ),
)
_register_non_tier_0_audits(
    ("FPAG", "FPAS", "FPAA"),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_requires_reconciliation",
    provider_identity="fpa",
    investigated_at=date(2026, 9, 2),
    evidence_refs=(
        "web:fpa-official-etf-catalogue-2026-09-02",
        "live:fpa-first-pacific-fpag-daily-route-2026-09-02",
    ),
    next_action=(
        "Resolve the abbreviated FPA identity to the existing native first_pacific adapter; "
        "monitor FPAG/FPAS/FPAA and extend that native owner only after each product exposes "
        "a complete executable current route and bounded live proof."
    ),
)
_register_non_tier_0_audits(
    ("FEGE", "FEOE", "USFE", "FEMD"),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_not_portfolio_publisher",
    provider_identity="gc_ferry_parent",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:gc-ferry-parent-sec-transaction-2026-09-03",
        "web:gc-ferry-parent-first-eagle-ownership-2026-09-03",
        "web:gc-ferry-parent-first-eagle-etf-catalogue-2026-09-03",
    ),
    next_action=(
        "Keep fallback-only as a non-publisher identity and resolve GC Ferry Parent references "
        "to the existing first_eagle publisher/adapter; reopen only if GC Ferry Parent exposes "
        "a distinct ETF portfolio route separate from First Eagle."
    ),
)
_register_non_tier_0_audits(
    ("GENT", "GEND", "GENM", "GENW"),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_requires_reconciliation",
    provider_identity="genter_capital",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "live:genter-mcivy-gend-current-holdings-2026-09-03",
        "web:genter-mcivy-fund-settings-2026-09-03",
        "web:genter-mcivy-issuer-alias-2026-09-03",
    ),
    next_action=(
        "Resolve the queued Genter identity to the existing native mcivy adapter; extend that "
        "native owner only when additional products gain equivalent identity-verified current "
        "holdings routes, and do not create a duplicate genter_capital adapter."
    ),
)
_register_non_tier_0_audits(
    ("AQLG",),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="highland_capital",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:highland-aqlg-page-and-csv-2026-09-03",
        "web:highland-sec-prospectus-2026-09-03",
    ),
    next_action=(
        "Re-test the official AQLG/AQLV pages for a ticker-bearing complete export or an "
        "issuer-declared mapping; promote only after symbol mapping, current-date semantics, "
        "parser fixtures, and bounded live evidence are all proven."
    ),
)
_register_non_tier_0_audits(
    ("QYLD", "HSPX", "DAX"),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="horizons",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:horizons-globalx-reorganization-2018",
        "web:globalx-horizons-successor-products-2026-09-03",
        "web:horizons-current-route-disposition-2026-09-03",
    ),
    next_action=(
        "Keep fallback-only as an inactive_or_successor_disposition resolved to the existing "
        "global_x identity; reopen only if Horizons independently sponsors a current U.S.-listed "
        "ETF and publishes a distinct complete executable first-party route."
    ),
)
_register_non_tier_0_audits(
    ("HOMZ", "RIET"),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_requires_reconciliation",
    provider_identity="hoya",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:hoya-official-homz-riet-pages-2026-09-03",
        "live:pettee-hoya-current-holdings-2026-09-03",
    ),
    next_action=(
        "Resolve the queued Hoya identity to the existing native pettee adapter; extend that "
        "native owner only when additional Hoya products gain equivalent identity-verified "
        "current holdings routes, and do not create a duplicate hoya adapter."
    ),
)
_register_non_tier_0_audits(
    ("FFTY", "BOUT"),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_not_portfolio_publisher",
    provider_identity="m2_financial",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:m2-financial-capforce-adviser-2026-09-03",),
    next_action=(
        "Resolve M2-advised products to the actual CapForce portfolio publisher and existing "
        "capforce adapter; reopen only if M2 publishes a distinct complete first-party holdings "
        "route separate from CapForce."
    ),
)
_register_non_tier_0_audits(
    ("SASS",),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="m_d_sass",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:m-d-sass-official-page-placeholder-holdings-2026-09-03",),
    next_action=(
        "Re-test the official SASS page for a populated complete holdings export or table with "
        "current date and ticker/identifier mapping; promote only after parser fixtures and "
        "bounded live evidence are added."
    ),
)
_register_non_tier_0_audits(
    ("SIXH", "SIXL", "SIXA", "SIXS", "SXQG"),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_not_portfolio_publisher",
    provider_identity="madison_avenue",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:madison-avenue-6meridian-subadvisor-2026-09-03",),
    next_action=(
        "Resolve Madison Avenue/6 Meridian references to the actual Exchange Traded Concepts "
        "publisher and existing route; do not create a duplicate adapter unless Madison Avenue "
        "publishes a distinct complete first-party holdings artifact."
    ),
)
_register_non_tier_0_audits(
    ("MAVF",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="matrix",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:matrix-mavf-official-page-2026-09-03",
        "live:matrix-mavf-cloudflare-block-2026-09-03",
    ),
    next_action=(
        "Re-test the official MAVF page from an allowed backend path; promote only after the "
        "complete table is executable, identity/date semantics are captured, and deterministic "
        "plus bounded live parser coverage is added."
    ),
)
_register_non_tier_0_audits(
    ("STGF",),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="merk",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:merk-stgf-liquidation-2026-09-03",
        "web:merk-stgf-sec-fund-identity-2026-09-03",
    ),
    next_action=(
        "Keep STGF as historical liquidation context; reopen only if Merk launches a distinct "
        "current U.S.-listed ETF with a complete executable first-party holdings route."
    ),
)
_register_non_tier_0_audits(
    ("OUNZ",),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="merk",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:merk-ounz-vaneck-successor-2026-09-03",),
    next_action=(
        "Resolve OUNZ references to the existing VanEck publisher relationship; do not create a "
        "duplicate Merk route unless Merk publishes a distinct complete first-party artifact."
    ),
)
_register_non_tier_0_audits(
    ("WIZ", "SNUG", "BOB", "DUDE"),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="merlyn_ai",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:merlyn-ai-liquidation-2026-09-03",
        "web:merlyn-ai-sec-fund-series-2026-09-03",
    ),
    next_action=(
        "Keep the Merlyn.AI symbols as historical liquidation context; reopen only if Merlyn.AI "
        "launches a distinct current U.S.-listed ETF with a complete executable first-party "
        "holdings route."
    ),
)
_register_non_tier_0_audits(
    ("DRMY", "GLDN", "NUKX", "WEPN", "SLVX", "GIAX", "BHDG", "BLOX", "NGHT", "FIAX", "XCSH"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="nicholas_wealth",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:nicholas-wealth-official-xfunds-2026-09-03",
        "web:nicholas-wealth-sec-series-identities-2026-09-03",
        "web:nicholas-wealth-access-blocked-2026-09-03",
    ),
    next_action=(
        "Re-test the issuer-owned XFUNDS product pages when access permits; promote only after "
        "a complete executable current holdings artifact is proven for each symbol."
    ),
)
_register_non_tier_0_audits(
    ("NSIV", "NSIG", "QTPI"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="north_square",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:north-square-nsiv-non-executable-2026-09-03",
        "web:north-square-nsig-filepoint-2026-09-03",
        "web:north-square-sec-disclosure-2026-09-03",
    ),
    next_action=(
        "Re-audit the official North Square product and FilePoint pages after the next reporting "
        "cycle; promote only when executable current rows and dates are proven."
    ),
)
_register_non_tier_0_audits(
    ("WAGN",),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="pabrai",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:pabrai-wagons-investor-resources-2026-09-03",
        "web:pabrai-wagons-current-report-2026-09-03",
    ),
    next_action=(
        "Re-audit the official WAGN investor resources after a new reporting cycle; promote only "
        "when a public complete holdings artifact, executable route, and current date are proven."
    ),
)
_register_non_tier_0_audits(
    ("CLOX", "CLOZ"),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="panagram",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:panagram-eldridge-successor-2026-09-03",
        "web:panagram-eldridge-sec-name-change-2026-09-03",
    ),
    next_action=(
        "Resolve CLOX/CLOZ references to the existing Eldridge successor holdings route; reopen "
        "only if a distinct active Panagram ETF and first-party route reappear."
    ),
)
_register_non_tier_0_audits(
    ("PRCS", "PRVS"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="parnassus_investments",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:parnassus-official-daily-holdings-routes-2026-09-03",
        "web:parnassus-sec-etf-identity-2026-09-03",
    ),
    next_action=(
        "Re-test the official PRCS/PRVS daily-holdings pages and resolve their data endpoint when "
        "backend access returns a usable payload; promote only after complete rows and current "
        "dates are proven."
    ),
)
_register_non_tier_0_audits(
    ("STBF",),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="performance_trust",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:performance-trust-ptam-resources-2026-09-03",
        "web:performance-trust-current-holdings-pdf-2026-09-03",
        "live:performance-trust-holdings-pdf-stale-2026-09-03",
    ),
    next_action=(
        "Recheck the PTAM resources page for a refreshed current STBF artifact; promote only after "
        "a current symbol-scoped route and parser/live proof are available."
    ),
)
_register_non_tier_0_audits(
    ("TCTL",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="premise_capital",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:premise-tctl-current-identity-2026-09-03",
        "live:premise-tctl-domain-unreachable-2026-09-03",
    ),
    next_action=(
        "Recheck tctl.us and current trust disclosures for a reachable TCTL issuer route; do not "
        "promote from SEC filings alone."
    ),
)
_register_non_tier_0_audits(
    (
        "PFRX",
        "SYNB",
        "PGRO",
        "PHYD",
        "PBDC",
        "PCRB",
        "PLDR",
        "PFUT",
        "PULT",
        "PEMX",
        "PVAL",
        "PPIE",
        "PPEM",
        "PGRI",
    ),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="putnam",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:putnam-franklin-current-etf-catalogue-2026-09-03",
        "web:putnam-quarterly-holdings-disclosure-2026-09-03",
        "live:putnam-franklin-api-stale-or-empty-2026-09-03",
    ),
    next_action=(
        "Recheck Franklin Templeton product/API holdings for a complete current snapshot across "
        "the mapped Putnam symbols; promote only after current-date coverage, parser fixtures, and "
        "bounded live tests pass."
    ),
)
_register_non_tier_0_audits(
    ("PZIV", "PZLV"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="pzena",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:pzena-current-etf-catalogue-2026-09-03",
        "web:pzena-daily-holdings-disclosure-2026-09-03",
        "live:pzena-etf-page-shell-blocked-2026-09-03",
    ),
    next_action=(
        "Re-test the official Pzena /etfs and product pages with an issuer-supported backend-readable "
        "holdings payload; promote only after complete symbol-scoped parsing and live validation."
    ),
)
_register_non_tier_0_audits(
    ("RFDI", "RFEM"),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_not_portfolio_publisher",
    provider_identity="riverfront",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:riverfront-subadvised-first-trust-2026-09-03",
        "web:riverfront-rfdi-rfem-current-first-trust-holdings-2026-09-03",
    ),
    next_action=(
        "Resolve RiverFront requests to the existing First Trust native adapter; monitor "
        "sub-adviser/product identity changes and do not create a duplicate publisher route."
    ),
)
_register_non_tier_0_audits(
    ("ROCI",),
    outcome=NOT_APPLICABLE,
    evidence_state="inactive_or_successor_disposition",
    provider_identity="roc",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:roc-roci-liquidation-2023-10-11",),
    next_action=(
        "Keep ROCI inactive unless ROC Investments launches a new U.S.-listed ETF with a distinct "
        "current first-party holdings route."
    ),
)
_register_non_tier_0_audits(
    ("AMEI", "AMGR", "AMEM", "AMSU"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="saturna",
    investigated_at=date(2026, 9, 4),
    evidence_refs=(
        "web:saturna-current-amana-etf-holdings-pages-2026-09-04",
        "live:saturna-current-amana-etf-holdings-pages-2026-09-04-blocked",
    ),
    next_action=(
        "Periodically re-test the official Amana ETF pages and declared holdings downloads; promote "
        "only after bounded backend access returns complete current rows with proven mapping."
    ),
)
_register_non_tier_0_audits(
    ("EMEM", "EMSC"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="sophus",
    investigated_at=date(2026, 9, 4),
    evidence_refs=("live:sophus-current-emem-emsc-holdings-pages-2026-09-04-blocked",),
    next_action=(
        "Periodically re-test the official EMEM and EMSC pages and declared downloads; promote "
        "only after bounded backend access returns complete current rows with proven mapping."
    ),
)
_register_non_tier_0_audits(
    ("GOLY", "HNDL", "MPLY", "ROMO"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="strategy_shares",
    investigated_at=date(2026, 9, 4),
    evidence_refs=("web:strategy-shares-current-goly-hndl-mply-romo-pages-2026-09-04",),
    next_action=(
        "Re-audit the official GOLY, HNDL, MPLY, and ROMO pages for a declared complete current "
        "holdings artifact; promote only after executable route, mapping, and freshness are proven."
    ),
)
_register_non_tier_0_audits(
    ("GOP", "NANC"),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="subversive",
    investigated_at=date(2026, 9, 4),
    evidence_refs=(
        "web:subversive-current-gop-nanc-holdings-pages-2026-09-04",
        "live:subversive-current-gop-nanc-holdings-pages-2026-09-04-blocked",
    ),
    next_action=(
        "Periodically re-test the official GOP and NANC pages and declared downloads; promote "
        "only after bounded backend access returns complete current rows with proven mapping."
    ),
)
_register_non_tier_0_audits(
    ("SEMG",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="suncoast",
    investigated_at=date(2026, 9, 4),
    evidence_refs=(
        "web:suncoast-current-semg-holdings-page-2026-09-04",
        "live:suncoast-current-semg-holdings-page-2026-09-04-blocked",
    ),
    next_action=(
        "Periodically re-test the official SEMG page; promote only after bounded backend access "
        "returns complete current rows with proven mapping."
    ),
)
_register_non_tier_0_audits(
    ("TCV",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="towle",
    investigated_at=date(2026, 9, 4),
    evidence_refs=(
        "web:towle-current-tcv-holdings-page-2026-09-04",
        "live:towle-current-tcv-holdings-page-2026-09-04-blocked",
    ),
    next_action=(
        "Periodically re-test the official TCV page; promote only after bounded backend access "
        "returns complete current rows with proven mapping."
    ),
)
_register_non_tier_0_audits(
    ("COPY",),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="tweedy_browne",
    investigated_at=date(2026, 9, 4),
    evidence_refs=("web:tweedy-browne-current-copy-holdings-page-2026-09-04",),
    next_action=(
        "Re-test the official ETF overview and FilePoint holdings page for a current complete "
        "artifact before considering native promotion."
    ),
)
_register_non_tier_0_audits(
    ("RMME", "BEGS", "RSEE", "RTRE", "RDFI", "RTAI"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="rareview_funds",
    investigated_at=date(2026, 9, 3),
    evidence_refs=(
        "web:rareview-current-etf-catalogue-2026-09-03",
        "web:rareview-stale-holdings-pages-2026-09-03",
    ),
    next_action=(
        "Recheck Rareview ETF product pages for a current complete holdings route; promote only "
        "after current rows, strict parsing, and bounded live validation are proven."
    ),
)
_register_non_tier_0_audits(
    ("ODTE", "VAIE", "XSPC", "CGPT", "COOL"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="vega_financial",
    investigated_at=date(2026, 9, 4),
    evidence_refs=("web:vega-shares-current-product-pages-2026-09-04",),
    next_action=(
        "Re-test VegaShares product pages and resolve the full-holdings download/API before "
        "considering native promotion."
    ),
)
_register_non_tier_0_audits(
    ("RTOO", "AIS", "AMMO", "QUSA", "OMAH", "ACKY", "DRKY"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="vistashares",
    investigated_at=date(2026, 9, 4),
    evidence_refs=("web:vistashares-current-product-pages-2026-09-04",),
    next_action=(
        "Re-test official VistaShares product pages and resolve the Download All Holdings endpoint "
        "before considering native promotion."
    ),
)
_register_non_tier_0_audits(
    ("MCRT",),
    outcome=NOT_APPLICABLE,
    evidence_state="identity_not_portfolio_publisher",
    provider_identity="wellesley_asset_management",
    investigated_at=date(2026, 9, 4),
    evidence_refs=("web:wellesley-asset-management-current-identity-pages-2026-09-04",),
    next_action=(
        "Preserve Wellesley as an adviser/sub-adviser identity and revisit only if a legally "
        "published distinct ETF catalogue and holdings route is identified."
    ),
)
_register_non_tier_0_audits(
    ("WRTH",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="worth_charting",
    investigated_at=date(2026, 9, 4),
    evidence_refs=(
        "web:worth-charting-current-wrth-holdings-page-2026-09-04",
        "live:worth-charting-current-wrth-holdings-csv-2026-09-04-blocked",
    ),
    next_action=(
        "Periodically re-test the official WRTH page and CSV; promote only after complete artifact "
        "access succeeds through the application client."
    ),
)
_register_non_tier_0_audits(
    ("YOKE",),
    outcome=UNAVAILABLE,
    evidence_state="issuer_route_access_blocked",
    provider_identity="yoke",
    investigated_at=date(2026, 9, 4),
    evidence_refs=(
        "web:yoke-current-holdings-page-2026-09-04",
        "live:yoke-current-holdings-page-2026-09-04-blocked",
    ),
    next_action=(
        "Periodically re-test the official YOKE page; promote only after complete table access "
        "succeeds through the application client."
    ),
)
_register_non_tier_0_audits(
    ("FUNL",),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="epwa",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:epwa-cornercap-funl-route-audit-2026-09-03",),
    next_action=(
        "Re-test the official FUNL domains after access recovery; promote only after a complete "
        "current artifact, mapping, parser fixture, and bounded live proof are available."
    ),
)
_register_non_tier_0_audits(
    ("PRAE", "PRMN"),
    outcome=UNAVAILABLE,
    evidence_state="non_executable_public_source",
    provider_identity="planrock",
    investigated_at=date(2026, 9, 3),
    evidence_refs=("web:planrock-prae-prmn-current-pages-2026-09-03",),
    next_action=(
        "Re-test PlanRock fund-details and declared download routes; promote only after a complete "
        "current artifact, symbol mapping, parser fixture, and live evidence are available."
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
    normalized_observations: dict[str, list[Mapping[str, Any]]] = {}
    for raw_symbol, observations in observations_by_symbol.items():
        normalized_symbol = str(raw_symbol).strip().upper()
        if not normalized_symbol or not isinstance(observations, Sequence):
            continue
        normalized_observations.setdefault(normalized_symbol, []).extend(
            observation for observation in observations if isinstance(observation, Mapping)
        )
    silent_violations: list[dict[str, Any]] = []
    eligible_checks = 0
    passing_checks = 0
    observed_symbols: set[str] = set()
    missing_symbols: list[str] = []
    max_consecutive_missed = 0
    missed_by_symbol: dict[str, int] = {}

    for raw_symbol in sorted(requested_symbols):
        symbol = raw_symbol.upper()
        observations = normalized_observations.get(symbol) or ()
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
                or source_tier not in _CURRENT_SOURCE_TIERS
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
                and source_tier in _CURRENT_SOURCE_TIERS
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
    future_snapshot_reason = _future_snapshot_reason(snapshot, now=now)
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
    last_canary_at = _metadata_datetime(state_metadata, "last_canary_at")
    last_canary_status = (
        str(state_metadata["last_canary_status"])
        if state_metadata.get("last_canary_status") is not None
        else None
    )
    last_canary_latency_ms = _metadata_float(state_metadata, "last_canary_latency_ms")
    last_canary_recovered = _metadata_bool(state_metadata, "last_canary_recovered")
    circuit_state = (
        str(state_metadata["circuit_state"])
        if state_metadata.get("circuit_state") is not None
        else None
    )
    circuit_open_until = _metadata_datetime(state_metadata, "circuit_open_until")
    complete = bool(snapshot and snapshot.completeness_status in _COMPLETE_STATUSES)
    has_snapshot = snapshot is not None
    identity_verified = _identity_verified(snapshot, state)
    state_status = str(state.status if state else "").lower()
    failure_reason = state.failure_reason if state else None
    failure_class = None
    if state is not None and state_status in {
        "failure",
        "needs_issuer_route",
        "holdings_adapter_unresolved",
        "circuit_open",
    }:
        raw_failure_class = state_metadata.get("last_failure_class")
        if raw_failure_class is None:
            raw_failure_class = state_metadata.get("last_canary_failure_class")
        if raw_failure_class:
            failure_class = str(raw_failure_class)
    schema_fingerprint = state_metadata.get("schema_fingerprint")
    controlled_fixture = bool(
        settings.E2E_SEED_MARKET_DATA
        and snapshot is not None
        and snapshot.provenance == "controlled_fixture"
        and snapshot.source_provider == "e2e_reference"
    )

    if controlled_fixture:
        # The opt-in browser fixture is deterministic test data, not a source
        # entitlement. Allow it to exercise current-analysis UI contracts only
        # while the explicit E2E setting is enabled; production and normal
        # workstation reads continue through the strict source-tier gate below.
        availability = CURRENT
        reason = "Controlled E2E fixture is enabled for browser acceptance."
    elif future_snapshot_reason is not None:
        availability = DEGRADED
        reason = future_snapshot_reason
    elif not profile.adapter_key or profile.adapter_key == "unresolved":
        availability = UNKNOWN if not has_snapshot else STALE
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
    elif source_tier not in _CURRENT_SOURCE_TIERS:
        availability = DEGRADED
        reason = "The latest holdings artifact has no recognized current-data source tier."
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
    usable = availability == CURRENT and (
        source_tier in _CURRENT_SOURCE_TIERS or controlled_fixture
    )
    return ETFHoldingsCapability(
        availability=availability,
        source_tier=source_tier,
        identity_verified=identity_verified,
        usable_for_current_analysis=usable,
        displayable_last_known=has_snapshot,
        adapter_key=profile.adapter_key,
        source_provider=_source_provider(profile, snapshot, state),
        transport_kind=_transport_kind(snapshot, state),
        expected_cadence=cadence if has_snapshot or state is not None else None,
        composition_date=composition_date,
        published_at=snapshot.published_at if snapshot else None,
        last_checked_at=state.last_checked_at if state else None,
        last_success_at=state.last_success_at if state else success,
        last_failure_at=state.last_failure_at if state else failure,
        last_canary_at=last_canary_at,
        last_canary_status=last_canary_status,
        last_canary_latency_ms=last_canary_latency_ms,
        last_canary_recovered=last_canary_recovered,
        circuit_state=circuit_state,
        circuit_open_until=circuit_open_until,
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
        failure_class=failure_class,
        consecutive_failures=_failure_streak(state_metadata, state_status=state_status),
        schema_fingerprint=str(schema_fingerprint) if schema_fingerprint else None,
        reason=reason,
        symbol_audit=symbol_audit,
    )
