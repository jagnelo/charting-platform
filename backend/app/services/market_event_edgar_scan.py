"""Durable, bounded SEC EDGAR issuer-universe pipeline scanning."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, update
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
    wrapped = state.cursor_issuer_id is None and state.cycle_count > 0
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

    result = await refresh_edgar_ipo_pipeline(
        db,
        [str(issuer.cik) for issuer in issuer_rows if issuer.cik],
        start=start,
        end=end,
        max_ciks=max_issuers,
        max_events_per_issuer=max_events_per_issuer,
        commit=False,
    )
    cycle_complete = not truncated
    state.cursor_issuer_id = None if cycle_complete else issuer_rows[-1].id
    state.cycle_count += 1 if cycle_complete else 0
    state.scanned_count += len(issuer_rows)
    state.last_batch_count = len(issuer_rows)
    state.last_event_count = int(result.get("events", 0))
    state.last_failure_count = int(result.get("failures", 0))
    state.last_scanned_at = now
    state.status = "complete" if cycle_complete else "partial"
    state.last_error = (
        "one or more issuer pipeline reads failed" if state.last_failure_count else None
    )
    state.provenance = {
        "algorithm": "edgar_ipo_pipeline_issuer_scan_v1",
        "issuer_table_scope": "cik_not_null",
        "last_batch_issuer_ids": [issuer.id for issuer in issuer_rows],
        "last_batch_ciks": [str(issuer.cik) for issuer in issuer_rows],
        "window": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "wrapped": wrapped,
        "bounded": True,
    }
    await db.commit()
    return {
        **result,
        "scan_key": _SCAN_KEY,
        "issuers_considered": len(issuer_rows),
        "cursor_issuer_id": state.cursor_issuer_id,
        "cycle_complete": cycle_complete,
        "wrapped": wrapped,
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

    provenance = state.provenance if isinstance(state.provenance, dict) else {}
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

    if not ciks:
        if offset < total:
            response = await failed_response("SEC issuer directory returned a non-progressing page")
            await db.commit()
            return response
        result: dict[str, Any] = {"status": "no_events", "events": 0, "failures": 0}
    else:
        result = await refresh_edgar_ipo_pipeline(
            db,
            ciks,
            start=start,
            end=end,
            max_ciks=max_issuers,
            max_events_per_issuer=max_events_per_issuer,
            commit=False,
        )

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
    cumulative_failures = int(provenance.get("active_cycle_failures", 0)) + page_failures
    cycle_failed = bool(provenance.get("active_cycle_failed")) or page_failures > 0
    missing_candidates = (
        int(provenance.get("active_cycle_missing_issuer_candidates", 0))
        + issuer_summary["missing_issuer_candidates"]
    )
    existing_issuers = (
        int(provenance.get("active_cycle_existing_issuers", 0)) + issuer_summary["existing_issuers"]
    )
    materialized_issuers = (
        int(provenance.get("active_cycle_issuers_materialized", 0))
        + issuer_summary["issuers_materialized"]
    )
    identity_conflicts_count = int(provenance.get("active_cycle_identity_conflicts", 0)) + len(
        issuer_summary["identity_conflicts"]
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
            "active_cycle_failures": cumulative_failures,
            "active_cycle_missing_issuer_candidates": missing_candidates,
            "active_cycle_existing_issuers": existing_issuers,
            "active_cycle_issuers_materialized": materialized_issuers,
            "active_cycle_identity_conflicts": identity_conflicts_count,
            "last_batch_missing_issuer_candidates": issuer_summary["missing_issuer_candidates"],
            "last_batch_existing_issuers": issuer_summary["existing_issuers"],
            "last_batch_issuers_materialized": issuer_summary["issuers_materialized"],
            "last_batch_identity_conflicts": issuer_summary["identity_conflicts"],
        }
    )
    state.cursor_issuer_id = None
    state.cycle_count += 1 if cycle_complete else 0
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
    state.provenance = provenance
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
