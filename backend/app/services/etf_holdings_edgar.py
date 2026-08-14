from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.etf_holdings import (
    ETFHoldingsBackfillFiling,
    ETFHoldingsBackfillJob,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.services.etf_holdings import ingest_holdings_snapshot
from app.services.etf_holdings_sec import parse_sec_legacy_holdings_xml, parse_sec_nport_xml

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{file_name}"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
NPORT_FORMS = {"NPORT-P", "N-PORT", "NPORT-EX"}
LEGACY_HOLDINGS_FORMS = {"N-Q", "NQ", "N-CSR", "N-CSRS", "NCSR", "NCSRS"}


@dataclass(slots=True)
class EdgarHoldingsFiling:
    accession_number: str
    form: str
    filing_date: date | None
    report_date: date | None
    acceptance_datetime: datetime | None
    primary_document: str
    filing_url: str


EdgarNportFiling = EdgarHoldingsFiling


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.EDGAR_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }


def normalize_cik(cik: str | int) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits:
        raise ValueError("SEC CIK is required for EDGAR holdings backfill.")
    return digits.zfill(10)


def _archive_cik(cik: str) -> str:
    return str(int(cik))


def _accession_path(accession_number: str) -> str:
    return accession_number.replace("-", "")


def _date_or_none(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _acceptance_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _known_at(filing: EdgarNportFiling) -> datetime:
    if filing.acceptance_datetime is not None:
        return filing.acceptance_datetime
    if filing.filing_date is not None:
        return datetime.combine(filing.filing_date, time.min, tzinfo=UTC)
    return datetime.now(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _job_summary(
    job: ETFHoldingsBackfillJob,
    *,
    status: str,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": status,
        "discovered": job.discovered_count,
        "ingested": job.ingested_count,
        "skipped": job.skipped_count,
        "failed": job.failed_count,
        "failures": failures,
    }


async def _filing_state_for_accession(
    db: AsyncSession,
    *,
    profile_id: int,
    filing: EdgarNportFiling,
    job_id: int,
) -> ETFHoldingsBackfillFiling:
    state = (
        await db.execute(
            select(ETFHoldingsBackfillFiling).where(
                ETFHoldingsBackfillFiling.etf_profile_id == profile_id,
                ETFHoldingsBackfillFiling.accession_number == filing.accession_number,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ETFHoldingsBackfillFiling(
            etf_profile_id=profile_id,
            accession_number=filing.accession_number,
            form=filing.form,
            status="discovered",
        )
        db.add(state)
    state.last_job_id = job_id
    state.form = filing.form
    state.filing_date = filing.filing_date
    state.report_date = filing.report_date
    state.acceptance_datetime = filing.acceptance_datetime
    state.primary_document = filing.primary_document
    state.filing_url = filing.filing_url
    return state


def parse_nport_filings_from_submissions(
    submissions: dict[str, Any],
    *,
    cik: str | int,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarNportFiling]:
    """Extract recent N-PORT filings from SEC submissions JSON."""

    return parse_holdings_filings_from_submissions(
        submissions,
        cik=cik,
        forms=NPORT_FORMS,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
    )


def parse_holdings_filings_from_submissions(
    submissions: dict[str, Any],
    *,
    cik: str | int,
    forms: set[str],
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarHoldingsFiling]:
    """Extract holdings filings from SEC submissions JSON for a target form set."""

    normalized_cik = normalize_cik(cik)
    recent = submissions.get("filings", {}).get("recent") or submissions
    form_values = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    acceptance_times = recent.get("acceptanceDateTime") or []
    primary_documents = recent.get("primaryDocument") or []

    normalized_forms = {form.upper() for form in forms}
    filings: list[EdgarHoldingsFiling] = []
    for idx, form in enumerate(form_values):
        normalized_form = str(form or "").upper()
        if normalized_form not in normalized_forms:
            continue
        accession_number = str(accessions[idx] if idx < len(accessions) else "").strip()
        primary_document = str(
            primary_documents[idx] if idx < len(primary_documents) else ""
        ).strip()
        if not accession_number or not primary_document:
            continue
        filing_date = _date_or_none(filing_dates[idx] if idx < len(filing_dates) else None)
        report_date = _date_or_none(report_dates[idx] if idx < len(report_dates) else None)
        comparison_date = report_date or filing_date
        if start_date and comparison_date and comparison_date < start_date:
            continue
        if end_date and comparison_date and comparison_date > end_date:
            continue
        acceptance_datetime = _acceptance_datetime(
            acceptance_times[idx] if idx < len(acceptance_times) else None
        )
        filings.append(
            EdgarHoldingsFiling(
                accession_number=accession_number,
                form=normalized_form,
                filing_date=filing_date,
                report_date=report_date,
                acceptance_datetime=acceptance_datetime,
                primary_document=primary_document,
                filing_url=SEC_ARCHIVES_BASE_URL.format(
                    cik=_archive_cik(normalized_cik),
                    accession=_accession_path(accession_number),
                    document=primary_document,
                ),
            )
        )
        if len(filings) >= max_filings:
            break
    return filings


def parse_legacy_holdings_filings_from_submissions(
    submissions: dict[str, Any],
    *,
    cik: str | int,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarHoldingsFiling]:
    """Extract recent legacy N-Q/N-CSR-style filings from SEC submissions JSON."""

    return parse_holdings_filings_from_submissions(
        submissions,
        cik=cik,
        forms=LEGACY_HOLDINGS_FORMS,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
    )


async def discover_nport_filings(
    *,
    cik: str | int,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarNportFiling]:
    return await discover_holdings_filings(
        cik=cik,
        forms=NPORT_FORMS,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
    )


async def discover_legacy_holdings_filings(
    *,
    cik: str | int,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarHoldingsFiling]:
    return await discover_holdings_filings(
        cik=cik,
        forms=LEGACY_HOLDINGS_FORMS,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
    )


async def discover_holdings_filings(
    *,
    cik: str | int,
    forms: set[str],
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarHoldingsFiling]:
    normalized_cik = normalize_cik(cik)
    async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
        response = await client.get(
            SEC_SUBMISSIONS_URL.format(cik=normalized_cik),
            headers=_headers(),
            follow_redirects=True,
        )
        response.raise_for_status()
        submissions = response.json()
        filings = parse_holdings_filings_from_submissions(
            submissions,
            cik=normalized_cik,
            forms=forms,
            start_date=start_date,
            end_date=end_date,
            max_filings=max_filings,
        )
        seen_accessions = {filing.accession_number for filing in filings}
        archived_files = submissions.get("filings", {}).get("files") or []

        for archived_file in archived_files:
            if len(filings) >= max_filings:
                break
            file_from = _date_or_none(archived_file.get("filingFrom"))
            file_to = _date_or_none(archived_file.get("filingTo"))
            if end_date and file_from and file_from > end_date:
                continue
            if start_date and file_to and file_to < start_date:
                continue
            file_name = str(archived_file.get("name") or "").strip()
            if not file_name:
                continue
            archived_response = await client.get(
                SEC_SUBMISSIONS_FILE_URL.format(file_name=file_name),
                headers=_headers(),
                follow_redirects=True,
            )
            archived_response.raise_for_status()
            archived_filings = parse_holdings_filings_from_submissions(
                archived_response.json(),
                cik=normalized_cik,
                forms=forms,
                start_date=start_date,
                end_date=end_date,
                max_filings=max_filings - len(filings),
            )
            for filing in archived_filings:
                if filing.accession_number in seen_accessions:
                    continue
                filings.append(filing)
                seen_accessions.add(filing.accession_number)
                if len(filings) >= max_filings:
                    break

    return filings


async def backfill_sec_nport_holdings(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
    requested_by_user_id: int | None = None,
) -> dict[str, Any]:
    return await _backfill_sec_holdings(
        db,
        profile=profile,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
        requested_by_user_id=requested_by_user_id,
        job_type="sec_nport_recent",
        discover_filings=discover_nport_filings,
        parse_xml=parse_sec_nport_xml,
        provenance="sec_nport_reconstructed_holdings",
        parser_version="sec-nport-v1",
        source_format="nport_xml",
        missing_date_reason="N-PORT XML did not expose a report date.",
        no_rows_reason="N-PORT XML did not contain parseable holdings rows.",
        notes="Reconstructed from SEC EDGAR N-PORT filing.",
    )


async def backfill_sec_legacy_holdings(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
    requested_by_user_id: int | None = None,
) -> dict[str, Any]:
    return await _backfill_sec_holdings(
        db,
        profile=profile,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
        requested_by_user_id=requested_by_user_id,
        job_type="sec_legacy_recent",
        discover_filings=discover_legacy_holdings_filings,
        parse_xml=parse_sec_legacy_holdings_xml,
        provenance="sec_legacy_reconstructed_holdings",
        parser_version="sec-legacy-v1",
        source_format="legacy_xml_table",
        missing_date_reason="Legacy SEC filing XML did not expose a report date.",
        no_rows_reason="Legacy SEC filing XML did not contain parseable holdings rows.",
        notes="Reconstructed from SEC EDGAR legacy N-Q/N-CSR-style filing.",
    )


async def _backfill_sec_holdings(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    start_date: date | None,
    end_date: date | None,
    max_filings: int,
    requested_by_user_id: int | None,
    job_type: str,
    discover_filings,
    parse_xml,
    provenance: str,
    parser_version: str,
    source_format: str,
    missing_date_reason: str,
    no_rows_reason: str,
    notes: str,
) -> dict[str, Any]:
    job = ETFHoldingsBackfillJob(
        etf_profile_id=profile.id,
        requested_by_user_id=requested_by_user_id,
        source_provider="sec",
        job_type=job_type,
        status="running",
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
        started_at=_now(),
        discovered_count=0,
        ingested_count=0,
        skipped_count=0,
        failed_count=0,
    )
    db.add(job)
    await db.flush()

    if not profile.sec_cik:
        failures = [{"reason": "ETF profile does not have sec_cik configured."}]
        job.status = "failed"
        job.completed_at = _now()
        job.failure_reason = failures[0]["reason"]
        job.summary = _job_summary(job, status="missing_sec_cik", failures=failures)
        await db.flush()
        return job.summary

    if profile.instrument is None:
        profile = (
            await db.execute(
                select(ETFProfile)
                .options(selectinload(ETFProfile.instrument))
                .where(ETFProfile.id == profile.id)
            )
        ).scalar_one()
    failures: list[dict[str, Any]] = []
    ingested = 0
    skipped = 0
    failed = 0

    try:
        filings = await discover_filings(
            cik=profile.sec_cik,
            start_date=start_date,
            end_date=end_date,
            max_filings=max_filings,
        )
    except Exception as exc:  # noqa: BLE001 - user-facing job state should preserve discovery failure.
        failures.append({"reason": str(exc)})
        job.status = "failed"
        job.failed_count = 1
        job.completed_at = _now()
        job.failure_reason = str(exc)
        job.summary = _job_summary(job, status="failed", failures=failures)
        await db.flush()
        return job.summary

    job.discovered_count = len(filings)

    async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
        for filing in filings:
            state = await _filing_state_for_accession(
                db,
                profile_id=profile.id,
                filing=filing,
                job_id=job.id,
            )
            if state.snapshot_id is not None and state.ingested_at is not None:
                skipped += 1
                state.status = "duplicate"
                state.failure_reason = None
                state.extra_data = {
                    **(state.extra_data or {}),
                    "last_skip_reason": "accession_already_ingested",
                }
                continue

            try:
                state.status = "fetching"
                state.failure_reason = None
                await db.flush()
                response = await client.get(
                    filing.filing_url,
                    headers=_headers(),
                    follow_redirects=True,
                )
                response.raise_for_status()
                composition_date, rows = parse_xml(response.text)
                composition_date = composition_date or filing.report_date
                if composition_date is None:
                    skipped += 1
                    reason = missing_date_reason
                    state.status = "skipped"
                    state.failure_reason = reason
                    failures.append({"accession_number": filing.accession_number, "reason": reason})
                    continue
                if not rows:
                    skipped += 1
                    reason = no_rows_reason
                    state.status = "skipped"
                    state.failure_reason = reason
                    failures.append({"accession_number": filing.accession_number, "reason": reason})
                    continue
                snapshot = await ingest_holdings_snapshot(
                    db,
                    etf_instrument=profile.instrument,
                    rows=rows,
                    composition_date=composition_date,
                    as_of_date=filing.report_date or composition_date,
                    known_at=_known_at(filing),
                    published_at=_known_at(filing),
                    provenance=provenance,
                    source_provider="sec",
                    source_url=filing.filing_url,
                    source_identifier=filing.accession_number,
                    source_quality="filing_reconstructed_holdings",
                    completeness_status="filing_reconstructed",
                    parser_version=parser_version,
                    raw_payload_text=response.text,
                    legal_metadata={
                        "source_access": "sec_filing",
                        "source_format": source_format,
                        "accession_number": filing.accession_number,
                        "form": filing.form,
                    },
                    notes=notes,
                    # SEC reconstruction already has a dated, filing-scoped
                    # identity. Keep each filing transaction bounded and
                    # leave optional identifier enrichment to a separate job.
                    allow_provider_enrichment=False,
                )
                state.snapshot_id = snapshot.id
                state.status = "ingested"
                state.failure_reason = None
                state.ingested_at = _now()
                state.extra_data = {
                    **(state.extra_data or {}),
                    "composition_date": composition_date.isoformat(),
                    "row_count": len(rows),
                }
                ingested += 1
            except Exception as exc:  # noqa: BLE001 - backfill summary should preserve per-filing failures.
                failed += 1
                state.status = "failed"
                state.failure_reason = str(exc)
                failures.append(
                    {
                        "accession_number": filing.accession_number,
                        "filing_url": filing.filing_url,
                        "reason": str(exc),
                    }
                )

    job.ingested_count = ingested
    job.skipped_count = skipped
    job.failed_count = failed
    job.completed_at = _now()
    if failed:
        job.status = "partial" if ingested or skipped else "failed"
    else:
        job.status = "completed"
    job.summary = _job_summary(job, status=job.status, failures=failures)
    await db.flush()
    return job.summary


async def list_sec_nport_backfill_jobs(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    limit: int = 25,
) -> list[ETFHoldingsBackfillJob]:
    rows = (
        (
            await db.execute(
                select(ETFHoldingsBackfillJob)
                .options(selectinload(ETFHoldingsBackfillJob.filings))
                .where(
                    ETFHoldingsBackfillJob.etf_profile_id == profile.id,
                    ETFHoldingsBackfillJob.job_type.in_(["sec_nport_recent", "sec_legacy_recent"]),
                )
                .order_by(ETFHoldingsBackfillJob.started_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_sec_nport_backfill_job(
    db: AsyncSession,
    *,
    job_id: int,
) -> ETFHoldingsBackfillJob | None:
    return (
        await db.execute(
            select(ETFHoldingsBackfillJob)
            .options(selectinload(ETFHoldingsBackfillJob.filings))
            .where(ETFHoldingsBackfillJob.id == job_id)
        )
    ).scalar_one_or_none()


async def backfill_all_sec_nport_holdings(
    db: AsyncSession,
    *,
    symbols: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_profiles: int = 50,
    max_filings_per_etf: int = 20,
    requested_by_user_id: int | None = None,
) -> dict[str, Any]:
    symbol_filters = [symbol.strip().upper() for symbol in symbols or [] if symbol.strip()]
    stmt = (
        select(ETFProfile)
        .join(Instrument, Instrument.id == ETFProfile.instrument_id)
        .options(selectinload(ETFProfile.instrument))
        .where(ETFProfile.sec_cik.is_not(None))
        .order_by(Instrument.symbol.asc())
        .limit(max_profiles)
    )
    if symbol_filters:
        stmt = stmt.where(Instrument.symbol.in_(symbol_filters))

    profiles = list((await db.execute(stmt)).scalars().all())
    summaries: list[dict[str, Any]] = []
    totals = {
        "profiles": len(profiles),
        "discovered": 0,
        "ingested": 0,
        "skipped": 0,
        "failed": 0,
    }

    for profile in profiles:
        symbol = profile.instrument.symbol if profile.instrument else str(profile.instrument_id)
        try:
            summary = await backfill_sec_nport_holdings(
                db,
                profile=profile,
                start_date=start_date,
                end_date=end_date,
                max_filings=max_filings_per_etf,
                requested_by_user_id=requested_by_user_id,
            )
        except Exception as exc:  # noqa: BLE001 - bulk jobs should continue across ETF-level failures.
            summary = {
                "job_id": None,
                "status": "failed",
                "discovered": 0,
                "ingested": 0,
                "skipped": 0,
                "failed": 1,
                "failures": [{"reason": str(exc)}],
            }
        summaries.append({"symbol": symbol, **summary})
        totals["discovered"] += int(summary.get("discovered") or 0)
        totals["ingested"] += int(summary.get("ingested") or 0)
        totals["skipped"] += int(summary.get("skipped") or 0)
        totals["failed"] += int(summary.get("failed") or 0)

    return {
        "status": "completed" if totals["failed"] == 0 else "partial",
        **totals,
        "results": summaries,
    }


async def backfill_all_sec_legacy_holdings(
    db: AsyncSession,
    *,
    symbols: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_profiles: int = 50,
    max_filings_per_etf: int = 20,
    requested_by_user_id: int | None = None,
) -> dict[str, Any]:
    symbol_filters = [symbol.strip().upper() for symbol in symbols or [] if symbol.strip()]
    stmt = (
        select(ETFProfile)
        .join(Instrument, Instrument.id == ETFProfile.instrument_id)
        .options(selectinload(ETFProfile.instrument))
        .where(ETFProfile.sec_cik.is_not(None))
        .order_by(Instrument.symbol.asc())
        .limit(max_profiles)
    )
    if symbol_filters:
        stmt = stmt.where(Instrument.symbol.in_(symbol_filters))

    profiles = list((await db.execute(stmt)).scalars().all())
    summaries: list[dict[str, Any]] = []
    totals = {
        "profiles": len(profiles),
        "discovered": 0,
        "ingested": 0,
        "skipped": 0,
        "failed": 0,
    }

    for profile in profiles:
        symbol = profile.instrument.symbol if profile.instrument else str(profile.instrument_id)
        try:
            summary = await backfill_sec_legacy_holdings(
                db,
                profile=profile,
                start_date=start_date,
                end_date=end_date,
                max_filings=max_filings_per_etf,
                requested_by_user_id=requested_by_user_id,
            )
        except Exception as exc:  # noqa: BLE001 - bulk jobs should continue across ETF-level failures.
            summary = {
                "job_id": None,
                "status": "failed",
                "discovered": 0,
                "ingested": 0,
                "skipped": 0,
                "failed": 1,
                "failures": [{"reason": str(exc)}],
            }
        summaries.append({"symbol": symbol, **summary})
        totals["discovered"] += int(summary.get("discovered") or 0)
        totals["ingested"] += int(summary.get("ingested") or 0)
        totals["skipped"] += int(summary.get("skipped") or 0)
        totals["failed"] += int(summary.get("failed") or 0)

    return {
        "status": "completed" if totals["failed"] == 0 else "partial",
        **totals,
        "results": summaries,
    }
