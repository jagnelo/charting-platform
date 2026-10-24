"""Durable, bounded SEC EDGAR issuer-universe pipeline scanning."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import (
    Issuer,
    MarketEventScanState,
    SecIssuerDirectoryCandidate,
)
from app.models.provider_runtime import ProviderCapability
from app.providers.errors import bounded_redact_provider_message
from app.services.market_events import refresh_edgar_ipo_pipeline
from app.services.provider_runtime import execute_provider_call

_SCAN_KEY = "edgar:ipo_pipeline:issuer_universe"
_DIRECTORY_SCAN_KEY = "edgar:ipo_pipeline:sec_directory"
_PROVIDER = "edgar"
_OPERATION = "fetch_ipo_pipeline_events"
_DIRECTORY_OPERATION = "discover_issuer_ciks_page"
_ISSUER_MATERIALIZATION_MODES = frozenset({"disabled", "create_missing"})


class _DirectoryCheckpointFailure(Exception):
    """Signal that a validated issuer row could not be durably checkpointed."""

    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__(str(response.get("reason") or "SEC issuer checkpoint failed"))
        self.response = response


def _validate_limit(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 500:
        raise ValueError(f"{name} must be between 1 and 500")


def _validate_issuer_materialization_mode(value: str) -> str:
    """Validate the explicit SEC directory issuer-materialization policy."""

    mode = str(value or "").strip().lower()
    if mode not in _ISSUER_MATERIALIZATION_MODES:
        allowed = ", ".join(sorted(_ISSUER_MATERIALIZATION_MODES))
        raise ValueError(f"issuer_materialization_mode must be one of: {allowed}")
    return mode


def _sec_directory_candidate_payload_names(payload: dict[str, Any]) -> list[str] | None:
    raw_names = payload.get("name_candidates")
    if raw_names is None:
        return []
    if not isinstance(raw_names, list) or any(
        not isinstance(name, str) or not name.strip() for name in raw_names
    ):
        return None
    return sorted({name.strip() for name in raw_names}, key=lambda name: (name.casefold(), name))


def _sec_directory_candidate_payload_name(payload: dict[str, Any]) -> str | None:
    raw_name = payload.get("name")
    if raw_name is not None and not isinstance(raw_name, str):
        return None
    names = _sec_directory_candidate_payload_names(payload)
    if names is None:
        return None
    conformed_name = (raw_name or (names[0] if names else "")).strip()
    return conformed_name or None


def _sec_directory_candidate_payload_tickers(payload: dict[str, Any]) -> list[str] | None:
    raw_tickers = payload.get("tickers")
    if raw_tickers is None:
        return []
    if not isinstance(raw_tickers, list) or any(
        not isinstance(ticker, str) or not ticker.strip() for ticker in raw_tickers
    ):
        return None
    return sorted({ticker.strip().upper() for ticker in raw_tickers})


async def _materialize_directory_issuers(
    db: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    mode: str,
    observed_at: datetime,
    cycle_number: int,
    directory_offset: int,
    directory_total: int,
    source_fingerprint: str,
) -> dict[str, Any]:
    """Persist reviewable row decisions and create only conflict-free issuers.

    The SEC directory provides issuer-level CIK/name evidence, not a complete
    security master. This policy therefore creates *only* missing ``Issuer``
    rows, never instruments/listings, never changes existing legal names, and
    never deactivates anything. ``disabled`` persists the per-row report but
    never creates issuer, instrument, or listing rows.
    """

    if not rows:
        return {
            "missing_issuer_candidates": 0,
            "existing_issuers": 0,
            "identity_conflicts": [],
            "issuers_materialized": 0,
            "candidate_rows": [],
        }

    page_ciks = [str(row.get("cik") or "").strip() for row in rows]
    previously_reported_ciks = (
        (
            await db.execute(
                select(SecIssuerDirectoryCandidate.cik).where(
                    SecIssuerDirectoryCandidate.cycle_number == cycle_number,
                    SecIssuerDirectoryCandidate.cik.in_(page_ciks),
                )
            )
        )
        .scalars()
        .all()
    )
    if previously_reported_ciks:
        raise ValueError("SEC issuer directory repeated a CIK across pages in one cycle")

    names_by_cik: dict[str, str] = {}
    name_candidates_by_cik: dict[str, list[str]] = {}
    tickers_by_cik: dict[str, list[str]] = {}
    source_payloads_by_cik: dict[str, dict[str, Any]] = {}
    source_identity_conflicts: set[str] = set()
    for row in rows:
        cik = str(row.get("cik") or "").strip()
        name_candidates = row.get("name_candidates")
        if name_candidates is not None and (
            not isinstance(name_candidates, list)
            or any(
                not isinstance(candidate, str) or not candidate.strip()
                for candidate in name_candidates
            )
        ):
            raise ValueError("SEC issuer directory returned invalid name candidates")
        normalized_names = sorted(
            {candidate.strip() for candidate in name_candidates or []},
            key=lambda candidate: (candidate.casefold(), candidate),
        )
        if len(normalized_names) > 1:
            source_identity_conflicts.add(cik)
        name = str(row.get("name") or (normalized_names[0] if normalized_names else "")).strip()
        if not name or len(name) > 300:
            raise ValueError(
                "SEC issuer directory materialization requires a non-empty name "
                "of at most 300 characters"
            )
        names_by_cik[cik] = name
        name_candidates_by_cik[cik] = normalized_names
        source_payloads_by_cik[cik] = dict(row)
        raw_tickers = row.get("tickers")
        if raw_tickers is not None and (
            not isinstance(raw_tickers, list)
            or any(not isinstance(ticker, str) or not ticker.strip() for ticker in raw_tickers)
        ):
            raise ValueError("SEC issuer directory materialization returned invalid tickers")
        tickers_by_cik[cik] = sorted({str(ticker).strip().upper() for ticker in raw_tickers or []})

    ciks = list(names_by_cik)
    existing_rows = (await db.execute(select(Issuer).where(Issuer.cik.in_(ciks)))).scalars().all()
    existing_by_cik = {str(issuer.cik): issuer for issuer in existing_rows if issuer.cik}
    domain_rows = (
        (
            await db.execute(
                select(Issuer).where(Issuer.domain_key.in_([f"cik:{cik}" for cik in ciks]))
            )
        )
        .scalars()
        .all()
    )
    domain_owners = {issuer.domain_key: issuer for issuer in domain_rows}

    identity_conflicts: list[str] = sorted(source_identity_conflicts)
    missing_candidate_count = 0
    candidate_rows: list[dict[str, Any]] = []
    source_row_offsets = {cik: directory_offset + index for index, cik in enumerate(names_by_cik)}
    for cik, name in names_by_cik.items():
        existing = existing_by_cik.get(cik)
        if existing is not None:
            candidate_rows.append(
                {
                    "cik": cik,
                    "name": name,
                    "name_candidates": name_candidates_by_cik[cik],
                    "tickers": tickers_by_cik[cik],
                    "source_payload": source_payloads_by_cik[cik],
                    "admission_decision": (
                        "existing_source_name_conflict"
                        if cik in source_identity_conflicts
                        else "already_exists"
                    ),
                    "decision_reason": (
                        "CIK matches an existing issuer, but SEC supplies multiple distinct "
                        "names; the existing legal name is unchanged."
                        if cik in source_identity_conflicts
                        else "CIK already matches an issuer; its legal name is unchanged."
                    ),
                    "matched_issuer": existing,
                }
            )
            continue
        missing_candidate_count += 1
        if cik in source_identity_conflicts:
            candidate_rows.append(
                {
                    "cik": cik,
                    "name": name,
                    "name_candidates": name_candidates_by_cik[cik],
                    "tickers": tickers_by_cik[cik],
                    "source_payload": source_payloads_by_cik[cik],
                    "admission_decision": "blocked_conflicting_names",
                    "decision_reason": (
                        "SEC directory contains multiple distinct names for this CIK."
                    ),
                    "matched_issuer": None,
                }
            )
            continue
        domain_key = f"cik:{cik}"
        owner = domain_owners.get(domain_key)
        if owner is not None and owner.cik != cik:
            identity_conflicts.append(cik)
            candidate_rows.append(
                {
                    "cik": cik,
                    "name": name,
                    "name_candidates": name_candidates_by_cik[cik],
                    "tickers": tickers_by_cik[cik],
                    "source_payload": source_payloads_by_cik[cik],
                    "admission_decision": "blocked_domain_key_collision",
                    "decision_reason": (
                        "The canonical cik domain key is already owned by a different CIK."
                    ),
                    "matched_issuer": owner,
                }
            )
            continue
        candidate_rows.append(
            {
                "cik": cik,
                "name": name,
                "name_candidates": name_candidates_by_cik[cik],
                "tickers": tickers_by_cik[cik],
                "source_payload": source_payloads_by_cik[cik],
                "admission_decision": "would_create",
                "decision_reason": (
                    "No issuer matches this CIK; this candidate is eligible for issuer-only "
                    "creation after the exact clean dry-run cycle is reviewed."
                ),
                "matched_issuer": None,
            }
        )

    materialized = 0
    # Validate the whole page before adding anything: a later identity conflict
    # must never leave a partially materialized batch in the transaction.
    if mode == "create_missing" and not identity_conflicts:
        for candidate in candidate_rows:
            if candidate["admission_decision"] != "would_create":
                continue
            cik = candidate["cik"]
            name = candidate["name"]
            domain_key = f"cik:{cik}"
            issuer = Issuer(
                domain_key=domain_key,
                legal_name=name,
                cik=cik,
                # SEC's CIK directory includes foreign private issuers;
                # a CIK is not evidence of US domicile.
                country_code=None,
                provenance={
                    "source": _PROVIDER,
                    "directory": "SEC company-ticker association directory",
                    "name_source": (
                        "SEC directory conformed company name; not independently verified"
                    ),
                    "observed_at": observed_at.isoformat(),
                    "tickers": tickers_by_cik.get(cik, []),
                    "materialization_policy": mode,
                },
            )
            db.add(issuer)
            candidate["matched_issuer"] = issuer
            candidate["admission_decision"] = "created"
            candidate["decision_reason"] = (
                "Created an issuer row after the exact clean disabled-mode cycle was reviewed."
            )
            materialized += 1
        if materialized:
            await db.flush()

    elif mode == "create_missing" and identity_conflicts:
        for candidate in candidate_rows:
            if candidate["admission_decision"] == "would_create":
                candidate["admission_decision"] = "blocked_by_page_conflict"
                candidate["decision_reason"] = (
                    "No rows were created because another CIK on this page has an identity "
                    "conflict; page materialization is atomic and fail-closed."
                )

    for candidate in candidate_rows:
        issuer = candidate["matched_issuer"]
        db.add(
            SecIssuerDirectoryCandidate(
                cycle_number=cycle_number,
                directory_offset=source_row_offsets[candidate["cik"]],
                directory_total=directory_total,
                source_fingerprint=source_fingerprint,
                materialization_mode=mode,
                cik=candidate["cik"],
                conformed_name=candidate["name"],
                name_candidates=candidate["name_candidates"],
                tickers=candidate["tickers"],
                source_payload=dict(candidate.get("source_payload") or {}),
                admission_decision=candidate["admission_decision"],
                decision_reason=candidate["decision_reason"],
                matched_issuer_id=issuer.id if issuer is not None else None,
                matched_issuer_domain_key=issuer.domain_key if issuer is not None else None,
                matched_issuer_legal_name=issuer.legal_name if issuer is not None else None,
                observed_at=observed_at,
            )
        )
    await db.flush()
    return {
        "missing_issuer_candidates": missing_candidate_count,
        "existing_issuers": len(existing_by_cik),
        "identity_conflicts": identity_conflicts,
        "issuers_materialized": materialized,
        "candidate_rows": candidate_rows,
    }


async def materialize_sec_directory_issuer_report(
    db: AsyncSession,
    *,
    reviewed_cycle_count: int,
    max_candidates: int = 500,
) -> dict[str, Any]:
    """Create issuer-only rows from a clean persisted SEC report, without refetching it."""

    if (
        isinstance(reviewed_cycle_count, bool)
        or not isinstance(reviewed_cycle_count, int)
        or reviewed_cycle_count < 1
    ):
        raise ValueError("reviewed_cycle_count must be a positive integer")
    _validate_limit(max_candidates, "max_candidates")

    state = (
        await db.execute(
            select(MarketEventScanState)
            .where(MarketEventScanState.scan_key == _DIRECTORY_SCAN_KEY)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if state is None:
        return {"status": "blocked", "reason": "no SEC directory scan is recorded"}

    provenance = dict(state.provenance) if isinstance(state.provenance, dict) else {}
    report_cycle = provenance.get("last_completed_report_cycle_number")
    fingerprint = provenance.get("last_completed_source_fingerprint")
    total = provenance.get("last_completed_directory_total")
    clean_report = (
        state.status == "complete"
        and state.cycle_count == reviewed_cycle_count
        and provenance.get("last_completed_cycle_number") == reviewed_cycle_count
        and provenance.get("last_completed_cycle_clean") is True
        and provenance.get("last_completed_materialization_mode") == "disabled"
        and isinstance(report_cycle, int)
        and not isinstance(report_cycle, bool)
        and report_cycle >= 1
        and isinstance(fingerprint, str)
        and len(fingerprint) == 64
        and isinstance(total, int)
        and not isinstance(total, bool)
        and total >= 1
    )
    if not clean_report:
        return {
            "status": "blocked",
            "reason": "materialization requires the exact latest clean disabled-mode report",
            "completed_cycle_count": state.cycle_count,
            "required_reviewed_cycle_count": state.cycle_count,
            "report_cycle_number": report_cycle,
        }

    rows = (
        (
            await db.execute(
                select(SecIssuerDirectoryCandidate)
                .where(SecIssuerDirectoryCandidate.cycle_number == report_cycle)
                .order_by(SecIssuerDirectoryCandidate.directory_offset)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != total:
        return {
            "status": "blocked",
            "reason": "persisted SEC candidate count does not match the directory total",
            "report_cycle_number": report_cycle,
            "directory_total": total,
            "candidate_count": len(rows),
        }
    allowed_decisions = {
        "would_create",
        "created",
        "already_exists",
        "blocked_conflicting_names",
        "blocked_domain_key_collision",
        "blocked_by_page_conflict",
    }
    for offset, row in enumerate(rows):
        if (
            row.directory_offset != offset
            or row.directory_total != total
            or row.source_fingerprint != fingerprint
            or row.cycle_status != "complete"
            or row.cycle_complete is not True
            or row.cycle_clean is not True
            or row.cycle_failure_count != 0
            or row.admission_decision not in allowed_decisions
        ):
            return {
                "status": "blocked",
                "reason": "persisted SEC report has incomplete, dirty, or inconsistent row evidence",
                "report_cycle_number": report_cycle,
                "directory_offset": offset,
            }

    pending = [row for row in rows if row.admission_decision == "would_create"]
    if any(
        len(str(row.cik)) != 10
        or not str(row.cik).isdigit()
        or not isinstance(row.conformed_name, str)
        or not row.conformed_name.strip()
        or len(row.conformed_name) > 300
        or not isinstance(row.name_candidates, list)
        or any(not isinstance(name, str) or not name.strip() for name in row.name_candidates)
        or len(set(row.name_candidates)) != 1
        or row.name_candidates[0].strip() != row.conformed_name.strip()
        or not isinstance(row.tickers, list)
        or any(not isinstance(ticker, str) or not ticker.strip() for ticker in row.tickers)
        or not isinstance(row.source_payload, dict)
        or str(row.source_payload.get("cik") or "").strip() != row.cik
        or _sec_directory_candidate_payload_name(row.source_payload) != row.conformed_name
        or _sec_directory_candidate_payload_names(row.source_payload) != row.name_candidates
        or _sec_directory_candidate_payload_tickers(row.source_payload) != row.tickers
        for row in pending
    ):
        return {
            "status": "blocked",
            "reason": (
                "one or more would-create rows failed source-payload CIK/name/ticker "
                "consistency validation"
            ),
            "report_cycle_number": report_cycle,
        }

    batch = pending[:max_candidates]
    created = 0
    already_exists = 0
    conflicts = 0
    if batch:
        ciks = [row.cik for row in batch]
        domain_keys = [f"cik:{cik}" for cik in ciks]
        existing_rows = (
            (await db.execute(select(Issuer).where(Issuer.cik.in_(ciks)))).scalars().all()
        )
        existing_by_cik = {str(issuer.cik): issuer for issuer in existing_rows if issuer.cik}
        domain_rows = (
            (await db.execute(select(Issuer).where(Issuer.domain_key.in_(domain_keys))))
            .scalars()
            .all()
        )
        domain_owners = {issuer.domain_key: issuer for issuer in domain_rows}
        new_issuers: list[tuple[SecIssuerDirectoryCandidate, Issuer]] = []

        for candidate in batch:
            existing = existing_by_cik.get(candidate.cik)
            if existing is not None:
                candidate.admission_decision = "already_exists"
                candidate.decision_reason = (
                    "CIK already matches an issuer at materialization time; legal name unchanged."
                )
                candidate.matched_issuer_id = existing.id
                candidate.matched_issuer_domain_key = existing.domain_key
                candidate.matched_issuer_legal_name = existing.legal_name
                already_exists += 1
                continue

            domain_key = f"cik:{candidate.cik}"
            domain_owner = domain_owners.get(domain_key)
            if domain_owner is not None and domain_owner.cik != candidate.cik:
                candidate.admission_decision = "blocked_domain_key_collision"
                candidate.decision_reason = (
                    "A different CIK owns the canonical domain key at materialization time."
                )
                candidate.matched_issuer_id = domain_owner.id
                candidate.matched_issuer_domain_key = domain_owner.domain_key
                candidate.matched_issuer_legal_name = domain_owner.legal_name
                conflicts += 1
                continue

            issuer = Issuer(
                domain_key=domain_key,
                legal_name=candidate.conformed_name,
                cik=candidate.cik,
                country_code=None,
                provenance={
                    "source": _PROVIDER,
                    "directory": "SEC company-ticker association directory",
                    "name_source": (
                        "SEC directory conformed company name; not independently verified"
                    ),
                    "observed_at": candidate.observed_at.isoformat(),
                    "tickers": candidate.tickers,
                    "materialization_policy": "reviewed_persisted_directory_report",
                    "directory_report_cycle": report_cycle,
                    "source_fingerprint": fingerprint,
                },
            )
            db.add(issuer)
            new_issuers.append((candidate, issuer))

        if new_issuers:
            await db.flush()
            for candidate, issuer in new_issuers:
                candidate.admission_decision = "created"
                candidate.decision_reason = (
                    "Created issuer-only row from the exact clean persisted SEC report; "
                    "no instrument or listing was created."
                )
                candidate.matched_issuer_id = issuer.id
                candidate.matched_issuer_domain_key = issuer.domain_key
                candidate.matched_issuer_legal_name = issuer.legal_name
            created = len(new_issuers)

    await db.flush()
    remaining = int(
        (
            await db.execute(
                select(func.count(SecIssuerDirectoryCandidate.id)).where(
                    SecIssuerDirectoryCandidate.cycle_number == report_cycle,
                    SecIssuerDirectoryCandidate.admission_decision == "would_create",
                )
            )
        ).scalar_one()
    )
    provenance.update(
        {
            "last_materialization_report_cycle_number": report_cycle,
            "last_materialization_source_fingerprint": fingerprint,
            "last_materialization_at": datetime.now(UTC).isoformat(),
            "last_materialization_created": int(provenance.get("last_materialization_created", 0))
            + created,
            "last_materialization_existing": int(provenance.get("last_materialization_existing", 0))
            + already_exists,
            "last_materialization_conflicts": int(
                provenance.get("last_materialization_conflicts", 0)
            )
            + conflicts,
            "last_materialization_complete": remaining == 0,
        }
    )
    state.provenance = {**provenance}
    await db.commit()
    return {
        "status": "complete" if remaining == 0 else "partial",
        "report_cycle_number": report_cycle,
        "reviewed_cycle_count": reviewed_cycle_count,
        "source_fingerprint": fingerprint,
        "processed": len(batch),
        "created": created,
        "already_exists": already_exists,
        "identity_conflicts_quarantined": conflicts,
        "remaining_would_create": remaining,
        "provider_http_requests": 0,
        "instrument_rows_created": 0,
        "listing_rows_created": 0,
    }


async def refresh_edgar_ipo_pipeline_for_issuer_universe(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    max_issuers: int = 50,
    max_events_per_issuer: int = 100,
) -> dict[str, Any]:
    """Scan persisted SEC issuers in durable batches without hidden fan-out.

    EDGAR has no global IPO-calendar endpoint. This workflow therefore walks
    only issuers already present in the canonical ``issuer`` table, persists a
    cursor across worker/session restarts, and reports partial cycles instead
    of claiming global completeness when the bounded batch has not wrapped.
    """

    _validate_limit(max_issuers, "max_issuers")
    _validate_limit(max_events_per_issuer, "max_events_per_issuer")
    if start is not None and end is not None and end < start:
        raise ValueError("end must be on or after start")

    state = (
        await db.execute(
            select(MarketEventScanState)
            .where(MarketEventScanState.scan_key == _SCAN_KEY)
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if state is None:
        state = MarketEventScanState(
            scan_key=_SCAN_KEY,
            provider=_PROVIDER,
            operation=_OPERATION,
            cycle_started_at=now,
            status="running",
            provenance={"algorithm": "edgar_ipo_pipeline_issuer_scan_v1"},
        )
        db.add(state)
        await db.flush()

    # A completed cycle starts the next invocation from the beginning.  Keep
    # this explicit in the response so operators can distinguish a fresh
    # cycle from the first ever scan, even though both use a NULL cursor.
    wrapped = (
        state.cursor_issuer_id is None and state.cycle_count > 0 and state.status == "complete"
    )
    if wrapped:
        state.cycle_started_at = now

    query = select(Issuer).where(Issuer.cik.is_not(None)).order_by(Issuer.id)
    if state.cursor_issuer_id is not None:
        query = query.where(Issuer.id > state.cursor_issuer_id)
    issuer_rows = (await db.execute(query.limit(max_issuers + 1))).scalars().all()
    if not issuer_rows and state.cursor_issuer_id is not None:
        wrapped = True
        state.cursor_issuer_id = None
        state.cycle_started_at = now
        issuer_rows = (
            (
                await db.execute(
                    select(Issuer)
                    .where(Issuer.cik.is_not(None))
                    .order_by(Issuer.id)
                    .limit(max_issuers + 1)
                )
            )
            .scalars()
            .all()
        )

    truncated = len(issuer_rows) > max_issuers
    issuer_rows = issuer_rows[:max_issuers]
    if not issuer_rows:
        state.status = "complete"
        state.last_scanned_at = now
        state.last_batch_count = 0
        state.last_event_count = 0
        state.last_failure_count = 0
        state.last_error = None
        await db.commit()
        return {
            "status": "complete",
            "scan_key": _SCAN_KEY,
            "issuers_considered": 0,
            "events": 0,
            "failures": 0,
            "cursor_issuer_id": None,
            "cycle_complete": True,
            "wrapped": wrapped,
        }

    batch_ids: list[int] = []
    batch_ciks: list[str] = []
    batch_results: list[dict[str, Any]] = []
    batch_failures: list[dict[str, Any]] = []
    total_events = 0
    total_persisted = 0
    total_linked = 0
    total_unlinked = 0
    cycle_complete = False
    result_status = "no_events"
    scan_superseded = False
    reconciliation: dict[str, Any] = {}

    for index, issuer in enumerate(issuer_rows):
        cik = str(issuer.cik)
        result = await refresh_edgar_ipo_pipeline(
            db,
            [cik],
            start=start,
            end=end,
            max_ciks=1,
            max_events_per_issuer=max_events_per_issuer,
            commit=False,
        )
        issuer_results = result.get("issuers")
        issuer_result = (
            issuer_results[0]
            if isinstance(issuer_results, list)
            and len(issuer_results) == 1
            and isinstance(issuer_results[0], dict)
            and issuer_results[0].get("cik") == cik
            else None
        )
        failed = (
            int(result.get("failures", 0)) > 0
            or issuer_result is None
            or issuer_result.get("status") != "refreshed"
        )
        if issuer_result is None:
            issuer_result = {
                "cik": cik,
                "status": "failed",
                "events": 0,
                "linked": 0,
                "unlinked": 0,
                "error": {
                    "error_type": "IncompleteIssuerResult",
                    "error": "SEC issuer scan returned no matching per-CIK outcome",
                },
            }

        batch_ids.append(issuer.id)
        batch_ciks.append(cik)
        batch_results.append(issuer_result)
        if isinstance(result.get("reconciliation"), dict):
            reconciliation = result["reconciliation"]
        total_events += int(issuer_result.get("events", 0))
        total_persisted += int(result.get("persisted", 0))
        total_linked += int(issuer_result.get("linked", 0))
        total_unlinked += int(issuer_result.get("unlinked", 0))
        if failed:
            batch_failures.append(issuer_result)

        # Persist the CIK's event/request-log result and its resume cursor in
        # one transaction. On a failed CIK, leave the cursor at the preceding
        # successful issuer and stop; restart therefore retries only that CIK
        # and does not replay earlier committed work or skip later issuers.
        last_cik = index == len(issuer_rows) - 1
        cycle_complete = last_cik and not truncated and not failed
        if not failed:
            state.cursor_issuer_id = None if cycle_complete else issuer.id
            state.scanned_count += 1
        state.cycle_count += 1 if cycle_complete else 0
        state.last_batch_count = len(batch_ids)
        state.last_event_count = total_events
        state.last_failure_count = len(batch_failures)
        state.last_scanned_at = datetime.now(UTC)
        state.status = "complete" if cycle_complete else "partial"
        state.last_error = "one or more issuer pipeline reads failed" if batch_failures else None
        state.provenance = {
            **(state.provenance if isinstance(state.provenance, dict) else {}),
            "algorithm": "edgar_ipo_pipeline_issuer_scan_v2",
            "issuer_table_scope": "cik_not_null",
            "last_batch_issuer_ids": list(batch_ids),
            "last_batch_ciks": list(batch_ciks),
            "last_batch_results": list(batch_results),
            "last_batch_failed_ciks": [item["cik"] for item in batch_failures],
            "window": {
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
            },
            "wrapped": wrapped,
            "bounded": True,
        }
        await db.commit()
        if failed:
            result_status = "failed"
            break
        if int(result.get("events", 0)):
            result_status = "refreshed"
        if index < len(issuer_rows) - 1:
            # Each per-CIK commit releases the row lock. Reacquire it before
            # the next provider call and verify that no other worker advanced
            # the cursor while this worker was between transactions.
            state = (
                await db.execute(
                    select(MarketEventScanState)
                    .where(MarketEventScanState.scan_key == _SCAN_KEY)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            if state.cursor_issuer_id != issuer.id:
                scan_superseded = True
                result_status = "superseded"
                break

    return {
        "status": result_status,
        "provider": _PROVIDER,
        "requested_ciks": len(batch_ciks),
        "invalid_ciks": 0,
        "events": total_events,
        "persisted": total_persisted,
        "linked": total_linked,
        "unlinked": total_unlinked,
        "failures": len(batch_failures),
        "issuers": batch_results,
        "reconciliation": reconciliation,
        "scan_key": _SCAN_KEY,
        "issuers_considered": len(batch_ciks),
        "cursor_issuer_id": state.cursor_issuer_id,
        "cycle_complete": cycle_complete,
        "wrapped": wrapped,
        "scan_superseded": scan_superseded,
    }


async def refresh_edgar_ipo_pipeline_for_sec_directory(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    max_issuers: int = 50,
    max_events_per_issuer: int = 100,
    max_submissions_requests: int = 0,
    issuer_materialization_mode: str = "disabled",
    issuer_materialization_reviewed_cycle_count: int = 0,
) -> dict[str, Any]:
    """Scan SEC's ticker-association directory in durable bounded pages.

    SEC states that ticker-association files do not guarantee accuracy or
    scope; traversing one fully is not complete US-listed-security
    reconciliation. A durable source fingerprint pins each cycle to one
    snapshot. Issuer materialization is permitted only after an operator
    supplies the exact count of a prior complete, clean, disabled-mode review
    cycle against the same source snapshot.
    """

    _validate_limit(max_issuers, "max_issuers")
    _validate_limit(max_events_per_issuer, "max_events_per_issuer")
    issuer_materialization_mode = _validate_issuer_materialization_mode(issuer_materialization_mode)
    if (
        not isinstance(issuer_materialization_reviewed_cycle_count, int)
        or isinstance(issuer_materialization_reviewed_cycle_count, bool)
        or issuer_materialization_reviewed_cycle_count < 0
    ):
        raise ValueError("issuer_materialization_reviewed_cycle_count must be non-negative")
    if (
        not isinstance(max_submissions_requests, int)
        or isinstance(max_submissions_requests, bool)
        or not 1 <= max_submissions_requests <= 500
    ):
        raise ValueError("max_submissions_requests must be between 1 and 500")
    if max_issuers > max_submissions_requests:
        raise ValueError("max_issuers cannot exceed max_submissions_requests")
    if start is not None and end is not None and end < start:
        raise ValueError("end must be on or after start")

    state = (
        await db.execute(
            select(MarketEventScanState)
            .where(MarketEventScanState.scan_key == _DIRECTORY_SCAN_KEY)
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if state is None:
        state = MarketEventScanState(
            scan_key=_DIRECTORY_SCAN_KEY,
            provider=_PROVIDER,
            operation=_DIRECTORY_OPERATION,
            cycle_started_at=now,
            status="running",
            provenance={
                "algorithm": "edgar_ipo_pipeline_sec_directory_v1",
                "directory_offset": 0,
                "submissions_request_bound": max_submissions_requests,
            },
        )
        db.add(state)
        await db.flush()

    # SQLAlchemy's JSON columns do not track in-place mutations by default.
    # Copy the object so the later assignment marks the durable cursor/state
    # as dirty; otherwise a worker restart replays the previous page and the
    # duplicate-CIK guard correctly rejects it.
    provenance = dict(state.provenance) if isinstance(state.provenance, dict) else {}
    raw_offset = provenance.get("directory_offset", 0)
    if isinstance(raw_offset, bool) or not isinstance(raw_offset, int) or raw_offset < 0:
        raise ValueError("SEC directory scan state contains an invalid directory offset")
    offset = raw_offset
    active_cycle_number = provenance.get("active_cycle_number")
    active_mode = provenance.get("active_materialization_mode")
    start_new_cycle = active_cycle_number is None or state.status in {"complete", "failed"}
    if not start_new_cycle and (
        isinstance(active_cycle_number, bool)
        or not isinstance(active_cycle_number, int)
        or active_cycle_number < 1
    ):
        raise ValueError("SEC directory scan state contains an invalid active cycle number")
    if offset > 0 and active_mode != issuer_materialization_mode:
        if issuer_materialization_mode == "disabled":
            # Turning materialization off immediately stops writes and starts a
            # fresh dry scan. A partially completed create cycle is never
            # silently continued under a different policy.
            start_new_cycle = True
            offset = 0
        else:
            return {
                "status": "blocked",
                "reason": "SEC directory scan materialization mode changed mid-cycle",
                "scan_key": _DIRECTORY_SCAN_KEY,
                "directory_offset": offset,
                "issuer_materialization_mode": active_mode,
                "cycle_complete": False,
            }

    if start_new_cycle and issuer_materialization_mode == "create_missing":
        last_reviewed_clean = (
            state.status == "complete"
            and state.cycle_count > 0
            and provenance.get("last_completed_cycle_number") == state.cycle_count
            and provenance.get("last_completed_cycle_clean") is True
            and provenance.get("last_completed_materialization_mode") == "disabled"
        )
        if (
            not last_reviewed_clean
            or issuer_materialization_reviewed_cycle_count != state.cycle_count
        ):
            return {
                "status": "blocked",
                "reason": (
                    "create_missing requires the exact count of the latest complete, "
                    "clean disabled-mode SEC directory review cycle"
                ),
                "scan_key": _DIRECTORY_SCAN_KEY,
                "completed_cycle_count": state.cycle_count,
                "required_reviewed_cycle_count": state.cycle_count if last_reviewed_clean else None,
                "issuer_materialization_mode": issuer_materialization_mode,
                "cycle_complete": False,
            }

    if not start_new_cycle and active_mode != issuer_materialization_mode:
        return {
            "status": "blocked",
            "reason": "SEC directory scan materialization mode does not match active cycle",
            "scan_key": _DIRECTORY_SCAN_KEY,
            "directory_offset": offset,
            "issuer_materialization_mode": active_mode,
            "cycle_complete": False,
        }

    if not start_new_cycle and issuer_materialization_mode == "create_missing":
        if (
            provenance.get("active_reviewed_cycle_count")
            != issuer_materialization_reviewed_cycle_count
        ):
            return {
                "status": "blocked",
                "reason": "reviewed SEC directory cycle count changed during materialization",
                "scan_key": _DIRECTORY_SCAN_KEY,
                "directory_offset": offset,
                "cycle_complete": False,
            }

    if start_new_cycle:
        offset = 0
        prior_cycle_sequence = provenance.get("directory_cycle_sequence")
        if (
            isinstance(prior_cycle_sequence, bool)
            or not isinstance(prior_cycle_sequence, int)
            or prior_cycle_sequence < 0
        ):
            prior_cycle_sequence = provenance.get("active_cycle_number")
        if (
            isinstance(prior_cycle_sequence, bool)
            or not isinstance(prior_cycle_sequence, int)
            or prior_cycle_sequence < 0
        ):
            prior_cycle_sequence = state.cycle_count
        active_cycle_number = max(state.cycle_count, prior_cycle_sequence) + 1
        provenance = {
            **provenance,
            # Attempt sequence is monotonic even when a failed partial cycle
            # is restarted without incrementing the completed-cycle count.
            "directory_cycle_sequence": active_cycle_number,
            "active_cycle_number": active_cycle_number,
            "active_materialization_mode": issuer_materialization_mode,
            "active_reviewed_cycle_count": (
                issuer_materialization_reviewed_cycle_count
                if issuer_materialization_mode == "create_missing"
                else None
            ),
            "active_source_fingerprint": None,
            "active_directory_total": None,
            "active_cycle_failed": False,
            "active_cycle_missing_issuer_candidates": 0,
            "active_cycle_existing_issuers": 0,
            "active_cycle_issuers_materialized": 0,
            "active_cycle_identity_conflicts": 0,
            "active_cycle_failures": 0,
            "active_cycle_failed_ciks": [],
            "directory_offset": 0,
        }
        # Candidate reports are durable source evidence. Never prune prior
        # cycles for storage fairness: later reconciliation and audit passes
        # must be able to inspect every observed directory row.
        state.cycle_started_at = now
    wrapped = start_new_cycle and state.cycle_count > 0
    state.status = "running"
    state.last_error = None

    async def failed_response(reason: str) -> dict[str, Any]:
        state.status = "failed"
        state.last_scanned_at = now
        state.last_batch_count = 0
        state.last_event_count = 0
        state.last_failure_count = 1
        state.last_error = bounded_redact_provider_message(reason, max_length=500)
        state.provenance = {
            **provenance,
            "algorithm": "edgar_ipo_pipeline_sec_directory_v1",
            "directory_offset": 0,
            "active_cycle_failed": True,
            "active_cycle_failures": int(provenance.get("active_cycle_failures", 0)) + 1,
            "submissions_request_bound": max_submissions_requests,
        }
        if (
            isinstance(active_cycle_number, int)
            and not isinstance(active_cycle_number, bool)
            and active_cycle_number > 0
        ):
            await db.execute(
                update(SecIssuerDirectoryCandidate)
                .where(SecIssuerDirectoryCandidate.cycle_number == active_cycle_number)
                .values(
                    cycle_status="failed",
                    cycle_complete=False,
                    cycle_clean=False,
                    cycle_failure_count=int(provenance.get("active_cycle_failures", 0)) + 1,
                )
            )
        return {
            "status": "failed",
            "reason": state.last_error,
            "scan_key": _DIRECTORY_SCAN_KEY,
            "issuers_considered": 0,
            "events": 0,
            "failures": 1,
            "directory_offset": 0,
            "submissions_request_bound": max_submissions_requests,
            "issuer_materialization_mode": issuer_materialization_mode,
            "issuers_materialized": 0,
            "existing_issuers": 0,
            "missing_issuer_candidates": 0,
            "identity_conflicts": [],
            "cycle_complete": False,
            "wrapped": wrapped,
        }

    # A failed submissions read must be retried before advancing the directory
    # cursor again. The queue is durable in scan provenance and each request is
    # identified by CIK in ProviderRequestLog. Retry-only invocations keep the
    # existing page cursor untouched, so they cannot exceed the configured
    # submissions request budget or lose a failed issuer across restarts.
    pending_retry_ciks = provenance.get("active_cycle_failed_ciks", [])
    if not isinstance(pending_retry_ciks, list) or any(
        not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit()
        for cik in pending_retry_ciks
    ):
        raise ValueError("SEC directory scan state contains an invalid failed-CIK retry queue")
    if pending_retry_ciks:
        retry_ciks = pending_retry_ciks[:max_submissions_requests]
        retry_checkpointed: list[str] = []

        async def checkpoint_retry(outcome: dict[str, Any]) -> None:
            cik = outcome.get("cik")
            failed = outcome.get("status") == "failed"
            currently_queued = provenance.get("active_cycle_failed_ciks", pending_retry_ciks)
            remaining = [
                queued for queued in currently_queued if queued != cik or (queued == cik and failed)
            ]
            provenance["active_cycle_failed_ciks"] = remaining
            provenance["active_cycle_failed"] = bool(remaining) or bool(
                provenance.get("active_cycle_identity_conflicts", 0)
            )
            if failed:
                provenance["active_cycle_failures"] = (
                    int(provenance.get("active_cycle_failures", 0)) + 1
                )
            provenance["last_batch_failed_ciks"] = [cik] if failed and isinstance(cik, str) else []
            state.provenance = {**provenance}
            state.status = "partial"
            state.last_scanned_at = now
            state.last_batch_count = 1
            state.last_event_count = int(outcome.get("events", 0))
            state.last_failure_count = int(failed)
            state.last_error = (
                "one or more SEC issuer pipeline reads remain queued for retry" if failed else None
            )
            await db.commit()
            if isinstance(cik, str):
                retry_checkpointed.append(cik)

        retry_result = await refresh_edgar_ipo_pipeline(
            db,
            retry_ciks,
            start=start,
            end=end,
            max_ciks=len(retry_ciks),
            max_events_per_issuer=max_events_per_issuer,
            commit=False,
            after_issuer=checkpoint_retry,
        )
        retry_failures = {
            item.get("cik")
            for item in retry_result.get("issuers", [])
            if isinstance(item, dict) and item.get("status") == "failed"
        }
        if retry_result.get("failures", 0) and not retry_failures:
            # An unsupported/malformed result cannot prove which issuer was
            # recovered. Retain every attempted CIK and fail closed.
            retry_failures = set(retry_ciks)
        remaining_retries = [cik for cik in pending_retry_ciks if cik in retry_failures]
        provenance.update(
            {
                "active_cycle_failed_ciks": remaining_retries,
                "active_cycle_failed": bool(remaining_retries),
                "active_cycle_failures": int(provenance.get("active_cycle_failures", 0))
                + (int(retry_result.get("failures", 0)) if not retry_checkpointed else 0),
                "last_batch_failed_ciks": [cik for cik in retry_ciks if cik in retry_failures],
                "directory_offset": offset,
                "submissions_request_bound": max_submissions_requests,
            }
        )
        state.provenance = {**provenance}
        state.status = "partial"
        state.last_scanned_at = now
        state.last_batch_count = len(retry_ciks)
        state.last_event_count = int(retry_result.get("events", 0))
        state.last_failure_count = len(retry_failures)
        state.last_error = (
            "one or more SEC issuer pipeline reads remain queued for retry"
            if remaining_retries
            else None
        )
        await db.commit()
        return {
            **retry_result,
            "status": state.status,
            "scan_key": _DIRECTORY_SCAN_KEY,
            "issuers_considered": len(retry_ciks),
            "directory_offset": offset,
            "submissions_request_bound": max_submissions_requests,
            "pending_retry_ciks": remaining_retries,
            "cycle_complete": False,
            "cycle_failed": bool(remaining_retries),
            "cycle_clean": None,
            "wrapped": False,
        }

    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.MARKET_EVENTS,
            _DIRECTORY_OPERATION,
            provider_name=_PROVIDER,
            invoke=lambda provider, _provider_symbol: provider.discover_issuer_ciks_page(
                offset, limit=max_issuers
            ),
            response_items=lambda result: len(result.get("issuers") or [])
            if isinstance(result, dict)
            else None,
            treat_empty_as_failure=False,
        )
        page = execution.result
        if not isinstance(page, dict):
            raise ValueError("SEC issuer directory returned a malformed page")
        total = page.get("total")
        page_offset = page.get("offset")
        rows = page.get("issuers")
        source_fingerprint = page.get("source_fingerprint")
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or isinstance(page_offset, bool)
            or not isinstance(page_offset, int)
            or page_offset != offset
            or not isinstance(rows, list)
            or len(rows) > max_issuers
            or not isinstance(source_fingerprint, str)
            or len(source_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in source_fingerprint)
        ):
            raise ValueError("SEC issuer directory returned invalid pagination metadata")
        active_fingerprint = provenance.get("active_source_fingerprint")
        if active_fingerprint is None:
            provenance["active_source_fingerprint"] = source_fingerprint
            provenance["active_directory_total"] = total
        elif active_fingerprint != source_fingerprint:
            raise ValueError(
                "SEC issuer directory source fingerprint changed during the durable cycle"
            )
        if provenance.get("active_directory_total") != total:
            raise ValueError("SEC issuer directory total changed during the durable cycle")
        if start_new_cycle and issuer_materialization_mode == "create_missing":
            reviewed_fingerprint = provenance.get("last_completed_source_fingerprint")
            if reviewed_fingerprint != source_fingerprint:
                raise ValueError(
                    "SEC issuer directory source changed since the reviewed disabled-mode cycle"
                )
        ciks: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("SEC issuer directory returned a malformed issuer row")
            cik = str(row.get("cik") or "").strip()
            if len(cik) != 10 or not cik.isdigit() or int(cik) <= 0 or cik in seen:
                raise ValueError("SEC issuer directory returned an invalid or duplicate CIK")
            seen.add(cik)
            ciks.append(cik)
        if offset > total or offset + len(rows) > total:
            raise ValueError("SEC issuer directory page exceeds the remaining directory total")
        if offset < total and not rows:
            raise ValueError("SEC issuer directory returned a non-progressing page")
    except Exception as exc:  # noqa: BLE001 - persist bounded scan failure.
        response = await failed_response(str(exc))
        await db.commit()
        return response

    incremental_checkpointing = False
    page_issuer_summaries: list[dict[str, Any]] = []
    if not ciks:
        if offset < total:
            response = await failed_response("SEC issuer directory returned a non-progressing page")
            await db.commit()
            return response
        result: dict[str, Any] = {"status": "no_events", "events": 0, "failures": 0}
    else:
        incremental_checkpointing = issuer_materialization_mode == "disabled"
        if incremental_checkpointing:
            provenance.update(
                {
                    "last_batch_event_count": 0,
                    "last_batch_missing_issuer_candidates": 0,
                    "last_batch_existing_issuers": 0,
                    "last_batch_issuers_materialized": 0,
                    "last_batch_identity_conflicts": [],
                }
            )
        page_completed: list[int] = []

        async def checkpoint_directory_issuer(outcome: dict[str, Any]) -> None:
            index = len(page_completed)
            row = rows[index]
            try:
                summary = await _materialize_directory_issuers(
                    db,
                    [row],
                    mode="disabled",
                    observed_at=now,
                    cycle_number=int(active_cycle_number),
                    directory_offset=offset + index,
                    directory_total=total,
                    source_fingerprint=source_fingerprint,
                )
            except Exception as exc:  # noqa: BLE001 - persist bounded checkpoint failure.
                response = await failed_response(str(exc))
                await db.commit()
                raise _DirectoryCheckpointFailure(response) from exc
            page_issuer_summaries.append(summary)
            page_completed.append(index)
            cik = outcome.get("cik")
            failed = outcome.get("status") == "failed"
            retry_ciks = list(provenance.get("active_cycle_failed_ciks", []))
            if failed and isinstance(cik, str) and cik not in retry_ciks:
                retry_ciks.append(cik)
            identity_conflicts = summary["identity_conflicts"]
            provenance.update(
                {
                    "algorithm": "edgar_ipo_pipeline_sec_directory_v3",
                    "directory_offset": offset + index + 1,
                    "directory_total": total,
                    "last_batch_ciks": ciks,
                    "last_batch_failed_ciks": retry_ciks,
                    "last_batch_event_count": int(provenance.get("last_batch_event_count", 0))
                    + int(outcome.get("events", 0)),
                    "active_source_fingerprint": source_fingerprint,
                    "active_directory_total": total,
                    "active_cycle_failed_ciks": retry_ciks,
                    "active_cycle_failed": bool(retry_ciks)
                    or bool(provenance.get("active_cycle_identity_conflicts", 0))
                    or bool(identity_conflicts),
                    "active_cycle_failures": int(provenance.get("active_cycle_failures", 0))
                    + int(failed),
                    "active_cycle_missing_issuer_candidates": int(
                        provenance.get("active_cycle_missing_issuer_candidates", 0)
                    )
                    + summary["missing_issuer_candidates"],
                    "active_cycle_existing_issuers": int(
                        provenance.get("active_cycle_existing_issuers", 0)
                    )
                    + summary["existing_issuers"],
                    "active_cycle_issuers_materialized": int(
                        provenance.get("active_cycle_issuers_materialized", 0)
                    )
                    + summary["issuers_materialized"],
                    "active_cycle_identity_conflicts": int(
                        provenance.get("active_cycle_identity_conflicts", 0)
                    )
                    + len(identity_conflicts),
                    "last_batch_missing_issuer_candidates": int(
                        provenance.get("last_batch_missing_issuer_candidates", 0)
                    )
                    + summary["missing_issuer_candidates"],
                    "last_batch_existing_issuers": int(
                        provenance.get("last_batch_existing_issuers", 0)
                    )
                    + summary["existing_issuers"],
                    "last_batch_issuers_materialized": int(
                        provenance.get("last_batch_issuers_materialized", 0)
                    )
                    + summary["issuers_materialized"],
                    "last_batch_identity_conflicts": list(
                        provenance.get("last_batch_identity_conflicts", [])
                    )
                    + identity_conflicts,
                    "window": {
                        "start": start.isoformat() if start else None,
                        "end": end.isoformat() if end else None,
                    },
                    "bounded": True,
                    "submissions_request_bound": max_submissions_requests,
                }
            )
            state.provenance = {**provenance}
            state.cursor_issuer_id = None
            state.scanned_count += 1
            state.last_batch_count = index + 1
            state.last_event_count = int(provenance["last_batch_event_count"])
            state.last_failure_count = int(failed) + len(identity_conflicts)
            state.last_scanned_at = now
            state.status = "partial"
            state.last_error = (
                "one or more SEC issuer pipeline reads or identity checks failed"
                if failed or identity_conflicts
                else None
            )
            await db.commit()

        try:
            result = await refresh_edgar_ipo_pipeline(
                db,
                ciks,
                start=start,
                end=end,
                max_ciks=max_issuers,
                max_events_per_issuer=max_events_per_issuer,
                commit=False,
                after_issuer=checkpoint_directory_issuer if incremental_checkpointing else None,
            )
        except _DirectoryCheckpointFailure as exc:
            return exc.response

    if incremental_checkpointing and len(page_issuer_summaries) == len(ciks):
        issuer_summary = {
            "missing_issuer_candidates": sum(
                summary["missing_issuer_candidates"] for summary in page_issuer_summaries
            ),
            "existing_issuers": sum(
                summary["existing_issuers"] for summary in page_issuer_summaries
            ),
            "identity_conflicts": [
                cik for summary in page_issuer_summaries for cik in summary["identity_conflicts"]
            ],
            "issuers_materialized": sum(
                summary["issuers_materialized"] for summary in page_issuer_summaries
            ),
        }
    else:
        try:
            issuer_summary = await _materialize_directory_issuers(
                db,
                rows,
                mode=issuer_materialization_mode,
                observed_at=now,
                cycle_number=int(active_cycle_number),
                directory_offset=offset,
                directory_total=total,
                source_fingerprint=source_fingerprint,
            )
        except Exception as exc:  # noqa: BLE001 - persist bounded scan failure.
            response = await failed_response(str(exc))
            await db.commit()
            return response
    next_offset = offset + len(ciks)
    cycle_complete = next_offset >= total
    page_failures = int(result.get("failures", 0)) + len(issuer_summary["identity_conflicts"])
    failed_ciks = [
        item["cik"]
        for item in result.get("issuers", [])
        if isinstance(item, dict)
        and item.get("status") == "failed"
        and isinstance(item.get("cik"), str)
    ]
    if int(result.get("failures", 0)) > len(failed_ciks):
        # If the pipeline reports failures without a per-CIK outcome, retry the
        # whole page rather than allow an unidentified failure to disappear.
        failed_ciks = list(ciks)
    existing_retry_ciks = provenance.get("active_cycle_failed_ciks", [])
    failed_ciks = list(dict.fromkeys([*existing_retry_ciks, *failed_ciks]))
    page_checkpointed = incremental_checkpointing and len(page_issuer_summaries) == len(ciks)
    cumulative_failures = int(provenance.get("active_cycle_failures", 0)) + (
        0 if page_checkpointed else page_failures
    )
    cycle_failed = (
        bool(provenance.get("active_cycle_failed"))
        if page_checkpointed
        else bool(provenance.get("active_cycle_failed")) or page_failures > 0
    )
    missing_candidates = int(provenance.get("active_cycle_missing_issuer_candidates", 0)) + (
        0 if page_checkpointed else issuer_summary["missing_issuer_candidates"]
    )
    existing_issuers = int(provenance.get("active_cycle_existing_issuers", 0)) + (
        0 if page_checkpointed else issuer_summary["existing_issuers"]
    )
    materialized_issuers = int(provenance.get("active_cycle_issuers_materialized", 0)) + (
        0 if page_checkpointed else issuer_summary["issuers_materialized"]
    )
    identity_conflicts_count = int(provenance.get("active_cycle_identity_conflicts", 0)) + (
        0 if page_checkpointed else len(issuer_summary["identity_conflicts"])
    )
    provenance.update(
        {
            "algorithm": "edgar_ipo_pipeline_sec_directory_v2",
            "directory_offset": 0 if cycle_complete else next_offset,
            "directory_total": total,
            "last_batch_ciks": ciks,
            "window": {
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
            },
            "bounded": True,
            "cycle_complete": cycle_complete,
            "submissions_request_bound": max_submissions_requests,
            "active_source_fingerprint": source_fingerprint,
            "active_directory_total": total,
            "active_cycle_failed": cycle_failed,
            "active_cycle_failed_ciks": failed_ciks,
            "active_cycle_failures": cumulative_failures,
            "active_cycle_missing_issuer_candidates": missing_candidates,
            "active_cycle_existing_issuers": existing_issuers,
            "active_cycle_issuers_materialized": materialized_issuers,
            "active_cycle_identity_conflicts": identity_conflicts_count,
            "last_batch_missing_issuer_candidates": issuer_summary["missing_issuer_candidates"],
            "last_batch_existing_issuers": issuer_summary["existing_issuers"],
            "last_batch_issuers_materialized": issuer_summary["issuers_materialized"],
            "last_batch_identity_conflicts": issuer_summary["identity_conflicts"],
            "last_batch_failed_ciks": failed_ciks,
        }
    )
    state.cursor_issuer_id = None
    state.cycle_count += 1 if cycle_complete else 0
    if not page_checkpointed:
        state.scanned_count += len(ciks)
    state.last_batch_count = len(ciks)
    state.last_event_count = int(result.get("events", 0))
    state.last_failure_count = page_failures
    state.last_scanned_at = now
    state.status = "complete" if cycle_complete else "partial"
    state.last_error = (
        "one or more SEC issuer pipeline reads or identity checks failed"
        if state.last_failure_count
        else None
    )
    cycle_clean = not cycle_failed and issuer_materialization_mode == "disabled"
    await db.execute(
        update(SecIssuerDirectoryCandidate)
        .where(SecIssuerDirectoryCandidate.cycle_number == active_cycle_number)
        .values(
            cycle_status=state.status,
            cycle_complete=cycle_complete,
            cycle_clean=cycle_clean if cycle_complete else None,
            cycle_failure_count=cumulative_failures,
        )
    )
    if cycle_complete:
        clean = cycle_clean
        provenance.update(
            {
                "last_completed_cycle_number": state.cycle_count,
                "last_completed_report_cycle_number": active_cycle_number,
                "last_completed_cycle_clean": clean,
                "last_completed_materialization_mode": issuer_materialization_mode,
                "last_completed_source_fingerprint": source_fingerprint,
                "last_completed_directory_total": total,
                "last_completed_cycle_failures": cumulative_failures,
                "last_completed_missing_issuer_candidates": missing_candidates,
                "last_completed_existing_issuers": existing_issuers,
                "last_completed_issuers_materialized": materialized_issuers,
                "last_completed_identity_conflicts": identity_conflicts_count,
            }
        )
    state.provenance = {**provenance}
    await db.commit()
    return {
        **result,
        "scan_key": _DIRECTORY_SCAN_KEY,
        "issuers_considered": len(ciks),
        "directory_offset": 0 if cycle_complete else next_offset,
        "submissions_request_bound": max_submissions_requests,
        "issuer_materialization_mode": issuer_materialization_mode,
        "issuers_materialized": materialized_issuers,
        "existing_issuers": existing_issuers,
        "missing_issuer_candidates": issuer_summary["missing_issuer_candidates"],
        "cycle_missing_issuer_candidates": missing_candidates,
        "identity_conflicts": issuer_summary["identity_conflicts"],
        "cycle_identity_conflicts": identity_conflicts_count,
        "cycle_failed": cycle_failed,
        "cycle_clean": (
            not cycle_failed and issuer_materialization_mode == "disabled"
            if cycle_complete
            else None
        ),
        "completed_cycle_count": state.cycle_count,
        "source_fingerprint": source_fingerprint,
        "cycle_complete": cycle_complete,
        "wrapped": wrapped,
    }
