"""Batched, quota-governed stable identity for discovered US equity listings.

Universe discovery (SEC EDGAR, Nasdaq Trader, FINRA OTC, ...) creates tens of
thousands of exchange-qualified US listings that carry only a ticker, venue
and at most an issuer CIK. A CIK is issuer-scoped and never a security
identity, and none of the enabled metadata profiles returns a security-level
identifier, so the per-symbol acquire flow cannot resolve them.

OpenFIGI maps an exact ticker on the Bloomberg US composite (``exchCode=US``)
to the composite FIGI, the same key the platform already uses as a domain key.
One mapping request carries up to the reviewed ``max_jobs_per_request`` jobs
and is charged as exactly one unit of the OpenFIGI mapping request pool through
``execute_provider_call``; no request bypasses quota admission.

A mapping is accepted only when it is unambiguous (exactly one US composite
for that exact ticker), consistent with the discovered name, and not already
owned by another canonical instrument. Collisions are quarantined for review;
nothing is merged or reassigned here.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import IdentityStatus, MarketRefreshJob
from app.models.provider_observation import InstrumentIdentifierSnapshot
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.providers.base import IdentifierRecord
from app.providers.errors import ProviderRateLimitError
from app.services.instrument_mastering import register_identifier
from app.services.market_data_identity import (
    apply_domain_identity,
    make_domain_key,
    quarantine_identity_candidate,
)
from app.services.provider_observations import store_identifier_snapshot
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

logger = logging.getLogger(__name__)

OPENFIGI_PROVIDER = "openfigi"
# The batched request is the same reviewed operation family (one mapping
# request == one unit) as the single-ticker identifier lookup.
OPENFIGI_OPERATION = "fetch_stable_identifiers"
DEFAULT_OPENFIGI_JOBS_PER_REQUEST = 5
_MAX_OPENFIGI_JOBS_PER_REQUEST = 100
_IDENTITY_ASSET_CLASSES = ("Equity", "Exchange Traded Product")
_UNRESOLVED_STATUSES = (IdentityStatus.PROVISIONAL.value, IdentityStatus.QUARANTINED.value)
_PLAIN_US_TICKER = re.compile(r"^[A-Z]{1,5}$")
_CLASS_US_TICKER = re.compile(r"^([A-Z]{1,5})[./-]([A-Z])$")
# Short admission waits (a per-minute pool rolling over) are slept through;
# anything longer ends the pass and the next scheduled pass resumes.
_MAX_ADMISSION_WAIT_SECONDS = 75.0
_NAME_STOPWORDS = frozenset(
    {
        "A",
        "ADR",
        "AG",
        "AND",
        "B",
        "C",
        "CL",
        "CLASS",
        "CO",
        "COM",
        "COMMON",
        "COMPANY",
        "CORP",
        "CORPORATION",
        "DE",
        "ETF",
        "FUND",
        "GROUP",
        "HLDGS",
        "HOLDING",
        "HOLDINGS",
        "INC",
        "LIMITED",
        "LLC",
        "LP",
        "LTD",
        "NEW",
        "NV",
        "OF",
        "ORD",
        "ORDINARY",
        "PLC",
        "SA",
        "SE",
        "SHARES",
        "SHS",
        "SPON",
        "SPONSORED",
        "STOCK",
        "THE",
        "TRUST",
    }
)


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    instrument: Instrument
    ticker: str
    listing_mic: str | None


def openfigi_us_ticker(symbol: str | None) -> str | None:
    """Return the OpenFIGI ticker for a plain or single-letter class US ticker.

    Share classes are written ``BRK/B`` by OpenFIGI. Preferreds, warrants,
    units and other suffix conventions differ across directories and are left
    to the ordinary acquire flow rather than guessed.
    """

    text = str(symbol or "").strip().upper()
    if _PLAIN_US_TICKER.fullmatch(text):
        return text
    match = _CLASS_US_TICKER.fullmatch(text)
    if match is not None:
        return f"{match.group(1)}/{match.group(2)}"
    return None


def _name_tokens(value: str | None) -> list[str]:
    text = str(value or "").upper().replace("&", " AND ")
    return [
        token
        for token in re.split(r"[^A-Z0-9]+", text)
        if len(token) >= 2 and token not in _NAME_STOPWORDS
    ]


def names_compatible(discovered_name: str | None, figi_name: str | None, symbol: str) -> bool:
    """Loose guard against a stale/reused ticker mapping to another company.

    Directory names ("Apple Inc. - Common Stock") and Bloomberg short names
    ("APPLE INC") differ in form, so only require one shared significant
    token (or a 3+ character prefix relation). A missing or ticker-only name is
    not evidence either way.
    """

    discovered = str(discovered_name or "").strip()
    if not discovered or discovered.upper() == symbol.upper() or not str(figi_name or "").strip():
        return True
    left, right = _name_tokens(discovered), _name_tokens(figi_name)
    if not left or not right:
        return True
    if set(left) & set(right):
        return True
    for a in left:
        for b in right:
            shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
            if len(shorter) >= 3 and longer.startswith(shorter):
                return True
    return False


async def openfigi_jobs_per_request(db: AsyncSession) -> int:
    """Read the reviewed per-request job ceiling from the live provider policy."""

    contract = (
        await db.execute(
            select(ProviderPolicy.quota_contract)
            .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
            .where(
                DataSource.name == OPENFIGI_PROVIDER,
                ProviderPolicy.capability == ProviderCapability.INSTRUMENT_IDENTIFIERS,
            )
        )
    ).scalar_one_or_none()
    raw = (
        ((contract or {}).get("endpoint_constraints") or {}).get("mapping") or {}
        if isinstance(contract, dict)
        else {}
    ).get("max_jobs_per_request")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return DEFAULT_OPENFIGI_JOBS_PER_REQUEST
    return min(raw, _MAX_OPENFIGI_JOBS_PER_REQUEST)


async def select_identity_candidates(
    db: AsyncSession,
    *,
    data_source_id: int,
    limit: int,
    attempted_since: datetime,
    exclude_ids: set[int] | None = None,
) -> list[IdentityCandidate]:
    """Unresolved, active US-venue equity listings not mapped recently."""

    # Every attempt (including negative outcomes) leaves a snapshot, so an
    # unmappable listing is retried only after ``retry_after``.
    recently_attempted = (
        select(InstrumentIdentifierSnapshot.id)
        .where(
            InstrumentIdentifierSnapshot.instrument_id == Instrument.id,
            InstrumentIdentifierSnapshot.data_source_id == data_source_id,
            InstrumentIdentifierSnapshot.observed_at >= attempted_since,
        )
        .exists()
    )
    query = (
        select(Instrument, InstrumentListing.ticker, Exchange.mic)
        .join(InstrumentType, InstrumentType.id == Instrument.instrument_type_id)
        .join(AssetClass, AssetClass.id == InstrumentType.asset_class_id)
        .join(
            InstrumentListing,
            and_(
                InstrumentListing.instrument_id == Instrument.id,
                InstrumentListing.is_active.is_(True),
                InstrumentListing.is_primary.is_(True),
            ),
        )
        .join(Exchange, Exchange.id == InstrumentListing.exchange_id)
        .where(
            Instrument.is_active.is_(True),
            Instrument.is_synthetic.is_(False),
            Instrument.domain_key.is_(None),
            Instrument.identity_status.in_(_UNRESOLVED_STATUSES),
            AssetClass.name.in_(_IDENTITY_ASSET_CLASSES),
            Exchange.country_code == "US",
            InstrumentListing.ticker == Instrument.symbol,
            ~recently_attempted,
        )
        .order_by(Instrument.id, InstrumentListing.id)
        .limit(max(1, limit) * 4)
    )
    if exclude_ids:
        query = query.where(Instrument.id.not_in(sorted(exclude_ids)))
    candidates: list[IdentityCandidate] = []
    seen: set[int] = set()
    for instrument, ticker, mic in (await db.execute(query)).all():
        if instrument.id in seen:
            continue
        seen.add(instrument.id)
        candidates.append(
            IdentityCandidate(instrument=instrument, ticker=str(ticker or ""), listing_mic=mic)
        )
        if len(candidates) >= limit:
            break
    return candidates


async def _record_attempt(
    db: AsyncSession,
    candidate: IdentityCandidate,
    *,
    data_source_id: int,
    observed_at: datetime,
    outcome: str,
    identifiers: list[IdentifierRecord] | None = None,
    detail: str | None = None,
    openfigi_ticker: str | None = None,
) -> None:
    await store_identifier_snapshot(
        db,
        instrument_id=candidate.instrument.id,
        data_source_id=data_source_id,
        provider_symbol=openfigi_ticker or candidate.ticker,
        identifiers=identifiers or [],
        observed_at=observed_at,
        fetched_at=observed_at,
        outcome={
            "status": outcome,
            "operation": "map_us_ticker_composite",
            **({"detail": detail} if detail else {}),
        },
    )


async def apply_openfigi_mapping(
    db: AsyncSession,
    candidate: IdentityCandidate,
    mapping: Any,
    *,
    data_source_id: int,
    observed_at: datetime,
) -> str:
    """Apply one job outcome; return resolved/no_match/ambiguous/conflict codes."""

    instrument = candidate.instrument
    openfigi_ticker = mapping.ticker
    if mapping.status != "matched" or not mapping.composite_figi:
        status = mapping.status if mapping.status in {"no_match", "ambiguous"} else "error"
        await _record_attempt(
            db,
            candidate,
            data_source_id=data_source_id,
            observed_at=observed_at,
            outcome=status,
            detail=mapping.detail,
            openfigi_ticker=openfigi_ticker,
        )
        return status
    composite = mapping.composite_figi
    payload = {
        "source": OPENFIGI_PROVIDER,
        "operation": "map_us_ticker_composite",
        "ticker": openfigi_ticker,
        "exch_code": "US",
        "composite_figi": composite,
        "name": mapping.name,
        "security_type": mapping.security_type,
        "security_type2": mapping.security_type2,
    }
    if not names_compatible(instrument.name, mapping.name, instrument.symbol):
        await quarantine_identity_candidate(
            db,
            instrument,
            proposed_domain_key=None,
            provider_name=OPENFIGI_PROVIDER,
            provider_symbol=candidate.ticker,
            exchange_mic=candidate.listing_mic,
            reason="OpenFIGI US composite name does not match the discovered listing name",
            candidate_payload=payload,
        )
        await _record_attempt(
            db,
            candidate,
            data_source_id=data_source_id,
            observed_at=observed_at,
            outcome="name_mismatch",
            openfigi_ticker=openfigi_ticker,
        )
        return "name_mismatch"

    domain_key = make_domain_key(InstrumentIdentifierType.COMPOSITE_FIGI, composite)
    domain_owner = (
        await db.execute(
            select(Instrument.id).where(
                Instrument.domain_key == domain_key,
                Instrument.id != instrument.id,
            )
        )
    ).scalar_one_or_none()
    identifier_owner = (
        await db.execute(
            select(InstrumentIdentifier.instrument_id)
            .where(
                InstrumentIdentifier.identifier_type.in_(
                    [InstrumentIdentifierType.COMPOSITE_FIGI, InstrumentIdentifierType.FIGI]
                ),
                InstrumentIdentifier.identifier_value == composite,
                InstrumentIdentifier.instrument_id != instrument.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    own_other_composite = (
        await db.execute(
            select(InstrumentIdentifier.identifier_value)
            .where(
                InstrumentIdentifier.instrument_id == instrument.id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.COMPOSITE_FIGI,
                InstrumentIdentifier.is_active.is_(True),
                InstrumentIdentifier.identifier_value != composite,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    conflict_owner = domain_owner or identifier_owner
    if conflict_owner is not None or own_other_composite is not None:
        reason = (
            f"stable key is already owned by instrument {conflict_owner}"
            if conflict_owner is not None
            else "instrument already carries a different composite FIGI"
        )
        await quarantine_identity_candidate(
            db,
            instrument,
            proposed_domain_key=domain_key,
            provider_name=OPENFIGI_PROVIDER,
            provider_symbol=candidate.ticker,
            exchange_mic=candidate.listing_mic,
            reason=reason,
            candidate_payload=payload,
        )
        await _record_attempt(
            db,
            candidate,
            data_source_id=data_source_id,
            observed_at=observed_at,
            outcome="identity_conflict",
            detail=reason,
            openfigi_ticker=openfigi_ticker,
        )
        return "identity_conflict"

    record = IdentifierRecord(
        identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI.value.upper(),
        identifier_value=composite,
        is_primary=True,
        source=OPENFIGI_PROVIDER,
        extra_data={
            "ticker": openfigi_ticker,
            "exchange_code": "US",
            "security_type": mapping.security_type,
            "share_class_figi": mapping.share_class_figi,
            "name": mapping.name,
        },
        raw_payload=dict(mapping.raw_row or {}),
    )
    await register_identifier(db, instrument, OPENFIGI_PROVIDER, record)
    resolved_key = await apply_domain_identity(
        db,
        instrument,
        identifiers={InstrumentIdentifierType.COMPOSITE_FIGI: composite},
        provider_name=OPENFIGI_PROVIDER,
        provider_symbol=candidate.ticker,
        exchange_mic=candidate.listing_mic,
        candidate_payload=payload,
    )
    if resolved_key is None:
        await _record_attempt(
            db,
            candidate,
            data_source_id=data_source_id,
            observed_at=observed_at,
            outcome="identity_conflict",
            identifiers=[record],
            openfigi_ticker=openfigi_ticker,
        )
        return "identity_conflict"
    # The composite FIGI is now the primary identifier; demote the internal
    # placeholder so exactly one identifier row is primary.
    for row in (
        (
            await db.execute(
                select(InstrumentIdentifier).where(
                    InstrumentIdentifier.instrument_id == instrument.id,
                    InstrumentIdentifier.is_primary.is_(True),
                    InstrumentIdentifier.identifier_type != InstrumentIdentifierType.COMPOSITE_FIGI,
                )
            )
        )
        .scalars()
        .all()
    ):
        row.is_primary = False
    await _record_attempt(
        db,
        candidate,
        data_source_id=data_source_id,
        observed_at=observed_at,
        outcome="resolved",
        identifiers=[record],
        openfigi_ticker=openfigi_ticker,
    )
    return "resolved"


async def wake_identity_jobs_for_instruments(
    db: AsyncSession, instrument_ids: set[int], *, now: datetime
) -> int:
    """Make waiting identity children of newly resolved instruments due now.

    Their acquire step short-circuits on the now-qualified canonical row
    without provider I/O, which releases history children that were waiting
    on a held identity (sometimes until a 30-day provider pool reset).
    """

    if not instrument_ids:
        return 0
    jobs = (
        (
            await db.execute(
                select(MarketRefreshJob).where(
                    MarketRefreshJob.capability == ProviderCapability.INSTRUMENT_METADATA.value,
                    MarketRefreshJob.instrument_id.in_(sorted(instrument_ids)),
                    MarketRefreshJob.status.in_(["queued", "retry", "deferred"]),
                    MarketRefreshJob.next_attempt_at > now,
                )
            )
        )
        .scalars()
        .all()
    )
    woken = 0
    for job in jobs:
        child = (job.metadata_payload or {}).get("data_preparation_child") or {}
        if child.get("kind") != "identity_profile":
            continue
        job.next_attempt_at = now
        woken += 1
    if woken:
        await db.flush()
    return woken


async def release_long_held_identity_jobs(
    db: AsyncSession,
    *,
    now: datetime,
    defer_limit: timedelta,
    max_jobs: int,
) -> int:
    """Re-evaluate identity children parked far beyond the held-defer bound.

    Children deferred before the bound existed can sit until a 30-day pool
    resets while their history children wait. Making a bounded number due now
    lets the ordinary handler re-run them under the current rules (resolve,
    or complete as a recoverable terminal hold); every provider call they make
    is still admitted by the runtime.
    """

    if max_jobs <= 0:
        return 0
    jobs = (
        (
            await db.execute(
                select(MarketRefreshJob)
                .where(
                    MarketRefreshJob.capability == ProviderCapability.INSTRUMENT_METADATA.value,
                    MarketRefreshJob.status == "deferred",
                    MarketRefreshJob.next_attempt_at > now + defer_limit,
                )
                .order_by(MarketRefreshJob.priority, MarketRefreshJob.id)
                .limit(max_jobs * 2)
            )
        )
        .scalars()
        .all()
    )
    released = 0
    for job in jobs:
        child = (job.metadata_payload or {}).get("data_preparation_child") or {}
        summary = job.result_summary or {}
        if child.get("kind") != "identity_profile" or summary.get("preparation_status") != "held":
            continue
        job.next_attempt_at = now
        released += 1
        if released >= max_jobs:
            break
    if released:
        await db.flush()
    return released


BaselineEnsurer = Callable[[AsyncSession], Awaitable[str | None]]


async def resolve_us_listed_equity_identities(
    db: AsyncSession,
    *,
    ensure_native_baseline: BaselineEnsurer,
    max_requests: int,
    max_seconds: float,
    retry_after: timedelta,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Resolve discovered US listings in quota-admitted OpenFIGI batches.

    ``ensure_native_baseline`` returns ``None`` when the OpenFIGI mapping pool
    may be reserved, or a hold reason (for example when native usage refresh is
    not enabled for OpenFIGI). Every mapping request goes through
    ``execute_provider_call`` with the normal resolver, reservation and
    request-log accounting.
    """

    from app.services.provider_runtime import (
        ProviderNotConfiguredError,
        ProviderQuotaUnknownError,
        ProviderRequestScopeDeniedError,
        bind_explicit_provider_acquisition,
        execute_provider_call,
    )

    stats: Counter[str] = Counter()
    result: dict[str, Any] = {"requests": 0}
    source = (
        await db.execute(select(DataSource).where(DataSource.name == OPENFIGI_PROVIDER))
    ).scalar_one_or_none()
    if source is None:
        return {**result, "status": "held", "reason_code": "provider_source_missing"}
    jobs_per_request = await openfigi_jobs_per_request(db)
    deadline = clock() + max(0.0, float(max_seconds))
    processed: set[int] = set()
    resolved_ids: set[int] = set()
    status, reason_code = "complete", None
    quota_unknown_retries = 0
    while result["requests"] < max_requests and clock() < deadline:
        current = now()
        candidates = await select_identity_candidates(
            db,
            data_source_id=source.id,
            limit=jobs_per_request,
            attempted_since=current - retry_after,
            exclude_ids=processed,
        )
        if not candidates:
            status = "exhausted"
            break
        mappable: list[tuple[IdentityCandidate, str]] = []
        for candidate in candidates:
            processed.add(candidate.instrument.id)
            ticker = openfigi_us_ticker(candidate.ticker)
            if ticker is None:
                await _record_attempt(
                    db,
                    candidate,
                    data_source_id=source.id,
                    observed_at=current,
                    outcome="unsupported_ticker",
                )
                stats["unsupported_ticker"] += 1
                continue
            mappable.append((candidate, ticker))
        if not mappable:
            await db.commit()
            continue
        hold = await ensure_native_baseline(db)
        if hold:
            for candidate, _ticker in mappable:
                processed.discard(candidate.instrument.id)
            status, reason_code = "held", hold
            break
        tickers = [ticker for _candidate, ticker in mappable]
        try:
            with bind_explicit_provider_acquisition(
                request_id=f"identity-batch:{OPENFIGI_PROVIDER}:{mappable[0][0].instrument.id}",
                operations=frozenset(
                    {(ProviderCapability.INSTRUMENT_IDENTIFIERS, OPENFIGI_OPERATION)}
                ),
                provider_names=frozenset({OPENFIGI_PROVIDER}),
            ):
                execution = await execute_provider_call(
                    db,
                    ProviderCapability.INSTRUMENT_IDENTIFIERS,
                    OPENFIGI_OPERATION,
                    provider_name=OPENFIGI_PROVIDER,
                    usage_identity=f"us-composite-batch:{len(tickers)}",
                    invoke=lambda provider, _symbol: provider.map_us_tickers(tickers),
                    response_items=lambda mapped: sum(
                        1 for item in mapped if item.status == "matched"
                    ),
                    treat_empty_as_failure=False,
                )
        except (ProviderQuotaAdmissionError, ProviderRateLimitError) as exc:
            await db.commit()
            for candidate, _ticker in mappable:
                processed.discard(candidate.instrument.id)
            retry_at = getattr(exc, "retry_at", None)
            wait = (
                max(1.0, (retry_at - now()).total_seconds())
                if isinstance(retry_at, datetime)
                else 5.0
            )
            if wait > _MAX_ADMISSION_WAIT_SECONDS or clock() + wait >= deadline:
                status, reason_code = "deferred", "provider_quota_admission_denied"
                result["retry_at"] = retry_at.isoformat() if retry_at else None
                break
            stats["admission_waits"] += 1
            await sleep(wait)
            continue
        except ProviderQuotaUnknownError:
            await db.commit()
            for candidate, _ticker in mappable:
                processed.discard(candidate.instrument.id)
            quota_unknown_retries += 1
            if quota_unknown_retries > 1:
                status, reason_code = "held", "provider_quota_contract_unknown"
                break
            continue
        except (ProviderRequestScopeDeniedError, ProviderNotConfiguredError) as exc:
            await db.commit()
            status, reason_code = "held", type(exc).__name__
            break
        except Exception as exc:  # noqa: BLE001 - one failed request ends this pass only.
            await db.rollback()
            logger.warning(
                "identity batch: OpenFIGI mapping request failed (%s)", type(exc).__name__
            )
            status, reason_code = "failed", type(exc).__name__
            break
        quota_unknown_retries = 0
        result["requests"] += 1
        mappings = list(execution.result or [])
        if len(mappings) != len(mappable):
            await db.rollback()
            status, reason_code = "failed", "mapping_response_length_mismatch"
            break
        observed_at = now()
        for (candidate, _ticker), mapping in zip(mappable, mappings, strict=True):
            outcome = await apply_openfigi_mapping(
                db,
                candidate,
                mapping,
                data_source_id=source.id,
                observed_at=observed_at,
            )
            stats[outcome] += 1
            if outcome == "resolved":
                resolved_ids.add(candidate.instrument.id)
        await db.commit()
    if resolved_ids:
        result["identity_jobs_woken"] = await wake_identity_jobs_for_instruments(
            db, resolved_ids, now=now()
        )
        await db.commit()
    result.update(
        {
            "status": status,
            "reason_code": reason_code,
            "jobs_per_request": jobs_per_request,
            "outcomes": dict(stats),
        }
    )
    return result
