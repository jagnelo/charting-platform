from __future__ import annotations

import asyncio
import contextvars
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx as _httpx
from sqlalchemy import case, select
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
from app.services.etf_holdings_provider_bridge import (
    ETF_SEC_ADAPTER_KEY,
    ETF_SEC_ATTEMPT_TIMEOUT_SECONDS,
    ETF_SEC_FUND_DEADLINE_SECONDS,
    ETF_SEC_MAX_REDIRECTS_PER_GET,
    ETFHoldingsRequestIdentity,
    ETFHoldingsRouteHeldError,
    ETFSECExecutionBudget,
    ProviderBackedHTTPXClient,
    bind_etf_holdings_sec_request_context,
    current_etf_holdings_request_identity,
    require_unbound_etf_holdings_context,
)
from app.services.etf_holdings_sec import parse_sec_legacy_holdings_xml, parse_sec_nport_xml


class _SECHTTPXNamespace:
    """Keep SEC HTTPX calls on the existing per-attempt Provider bridge."""

    def AsyncClient(self, *_args, **_kwargs):
        if _args:
            raise ETFHoldingsRouteHeldError(
                "SEC shared-admission clients require keyword-only configuration"
            )
        return ProviderBackedHTTPXClient(**_kwargs)

    def __getattr__(self, name):
        return getattr(_httpx, name)


httpx = _SECHTTPXNamespace()
_SEC_FUND_BUDGET: contextvars.ContextVar[ETFSECExecutionBudget | None] = contextvars.ContextVar(
    "etf_sec_fund_execution_budget", default=None
)

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{file_name}"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
NPORT_FORMS = {"NPORT-P", "N-PORT", "NPORT-EX"}
LEGACY_HOLDINGS_FORMS = {"N-Q", "NQ", "N-CSR", "N-CSRS", "NCSR", "NCSRS"}


@dataclass(frozen=True, slots=True)
class _EdgarETFHoldingsAdapter:
    source_provider: str = "edgar"
    adapter_key: str = ETF_SEC_ADAPTER_KEY

    async def fetch_latest(self, **_kwargs):
        raise ETFHoldingsRouteHeldError(
            "EDGAR ETF requests are available only through the dedicated per-attempt bridge"
        )

    async def fetch_for_date(self, **_kwargs):
        raise ETFHoldingsRouteHeldError(
            "EDGAR ETF requests are available only through the dedicated per-attempt bridge"
        )


_EDGAR_ETF_HOLDINGS_ADAPTER = _EdgarETFHoldingsAdapter()


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


async def _resolve_request_identity(
    *,
    db: AsyncSession | None = None,
    profile: ETFProfile | None = None,
    request_identity: ETFHoldingsRequestIdentity | None = None,
) -> ETFHoldingsRequestIdentity:
    """Resolve a committed ETF identity before opening any SEC request scope."""

    if request_identity is not None:
        active_identity = current_etf_holdings_request_identity()
        if active_identity is not None and (
            active_identity.db is not request_identity.db
            or active_identity.profile_id != request_identity.profile_id
            or active_identity.instrument_id != request_identity.instrument_id
            or active_identity.provider_symbol.strip().upper()
            != request_identity.provider_symbol.strip().upper()
        ):
            raise ETFHoldingsRouteHeldError(
                "SEC request profile differs from the active ETF fetch identity"
            )
    if request_identity is not None:
        if db is not None and request_identity.db is not db:
            raise ETFHoldingsRouteHeldError("SEC request database differs from its bound identity")
        if profile is not None and profile.id != request_identity.profile_id:
            raise ETFHoldingsRouteHeldError("SEC request profile differs from its bound identity")
        db = request_identity.db
        profile_id = request_identity.profile_id
        instrument_id = request_identity.instrument_id
        provider_symbol = request_identity.provider_symbol
        active_identity = current_etf_holdings_request_identity()
        if active_identity is not None and (
            active_identity.db is not db
            or active_identity.profile_id != profile_id
            or active_identity.instrument_id != instrument_id
            or active_identity.provider_symbol.strip().upper() != provider_symbol.strip().upper()
        ):
            raise ETFHoldingsRouteHeldError(
                "SEC request profile differs from the active ETF fetch identity"
            )
    elif db is not None and profile is not None:
        profile_id = int(profile.id or 0)
        instrument_id = int(profile.instrument_id or 0)
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None or instrument.id != instrument_id:
            raise ETFHoldingsRouteHeldError("SEC request instrument is not linked to its profile")
        provider_symbol = str(instrument.symbol or "").strip()
        active_identity = current_etf_holdings_request_identity()
        if active_identity is not None and (
            active_identity.db is not db
            or active_identity.profile_id != profile_id
            or active_identity.instrument_id != instrument_id
            or active_identity.provider_symbol.strip().upper() != provider_symbol.upper()
        ):
            raise ETFHoldingsRouteHeldError(
                "SEC request profile differs from the active ETF fetch identity"
            )
    else:
        raise ETFHoldingsRouteHeldError(
            "SEC holdings requests require an explicit committed ETF request identity"
        )

    if db is None or profile_id <= 0 or instrument_id <= 0 or not provider_symbol:
        raise ETFHoldingsRouteHeldError("SEC holdings request identity is incomplete")
    if not callable(getattr(db, "get", None)):
        raise ETFHoldingsRouteHeldError(
            "SEC request identity cannot be loaded from the caller database session"
        )
    committed_profile = await db.get(ETFProfile, profile_id)
    if committed_profile is None or committed_profile.instrument_id != instrument_id:
        raise ETFHoldingsRouteHeldError(
            "SEC request identity must resolve to a committed ETF profile and instrument"
        )
    committed_instrument = await db.get(Instrument, instrument_id)
    if (
        committed_instrument is None
        or committed_instrument.symbol.strip().upper() != provider_symbol.strip().upper()
    ):
        raise ETFHoldingsRouteHeldError(
            "SEC request symbol does not match its committed ETF instrument"
        )
    if not committed_profile.sec_cik:
        raise ETFHoldingsRouteHeldError("SEC request profile has no committed CIK")
    return ETFHoldingsRequestIdentity(
        db=db,
        profile_id=profile_id,
        instrument_id=instrument_id,
        provider_symbol=provider_symbol,
    )


async def _sec_get(
    request_identity: ETFHoldingsRequestIdentity,
    *,
    operation: str,
    url: str,
) -> _httpx.Response:
    """Perform one logical SEC GET; the facade admits every physical redirect hop."""

    sec_budget = _SEC_FUND_BUDGET.get()
    if sec_budget is None:
        raise ETFHoldingsRouteHeldError(
            "SEC request is missing its bounded one-fund execution context"
        )

    with bind_etf_holdings_sec_request_context(
        db=request_identity.db,
        adapter=_EDGAR_ETF_HOLDINGS_ADAPTER,
        profile_id=request_identity.profile_id,
        instrument_id=request_identity.instrument_id,
        provider_symbol=request_identity.provider_symbol,
        operation=operation,
        sec_budget=sec_budget,
    ) as request_binding:
        async with httpx.AsyncClient(
            timeout=ETF_SEC_ATTEMPT_TIMEOUT_SECONDS,
            follow_redirects=True,
            max_redirects=ETF_SEC_MAX_REDIRECTS_PER_GET,
        ) as client:
            response = await client.get(
                url,
                headers=_headers(),
                follow_redirects=True,
                max_redirects=ETF_SEC_MAX_REDIRECTS_PER_GET,
            )
            extensions = getattr(response, "extensions", None)
            if extensions is not None:
                extensions["etf_holdings_request_binding"] = request_binding
            return response


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


def _known_at(
    filing: EdgarNportFiling,
    *,
    observed_at: datetime | None = None,
) -> datetime:
    # SEC acceptance is filing metadata, not proof of the exact time the filing
    # became publicly available. Record knowledge only after this process has
    # observed the response; never backdate it to acceptance or filingDate.
    return observed_at or datetime.now(UTC)


def _sec_filing_identity_for_profile(
    profile: ETFProfile,
    raw_document: str,
) -> tuple[bool, dict[str, str], str]:
    """Require committed SEC series and class identity before backfill ingest."""

    from app.services.etf_holdings_adapters import (  # noqa: PLC0415
        _sec_nport_identity_match,
    )

    if not profile.sec_series_id or not profile.sec_class_id:
        from app.services.etf_holdings_sec import (  # noqa: PLC0415
            extract_sec_nport_filing_identity,
        )

        return (
            False,
            extract_sec_nport_filing_identity(raw_document),
            "missing_committed_series_or_class_id",
        )
    return _sec_nport_identity_match(
        raw_document,
        identifiers={
            "sec_series_id": profile.sec_series_id,
            "sec_class_id": profile.sec_class_id,
        },
    )


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


@asynccontextmanager
async def sec_fund_execution_scope():
    """Share one bounded envelope across all SEC calls for the same fund."""
    active_budget = _SEC_FUND_BUDGET.get()
    if active_budget is not None:
        active_budget._check_deadline()
        yield active_budget
        return

    budget = ETFSECExecutionBudget()
    token = _SEC_FUND_BUDGET.set(budget)
    try:
        async with asyncio.timeout(ETF_SEC_FUND_DEADLINE_SECONDS):
            yield budget
    except TimeoutError as exc:
        raise ETFHoldingsRouteHeldError("SEC one-fund execution deadline exceeded") from exc
    finally:
        _SEC_FUND_BUDGET.reset(token)


async def _run_in_sec_fund_scope(coro_factory):
    async with sec_fund_execution_scope():
        return await coro_factory()


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
    db: AsyncSession | None = None,
    profile: ETFProfile | None = None,
    request_identity: ETFHoldingsRequestIdentity | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarNportFiling]:
    return await discover_holdings_filings(
        cik=cik,
        db=db,
        profile=profile,
        request_identity=request_identity,
        forms=NPORT_FORMS,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
    )


async def discover_legacy_holdings_filings(
    *,
    cik: str | int,
    db: AsyncSession | None = None,
    profile: ETFProfile | None = None,
    request_identity: ETFHoldingsRequestIdentity | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarHoldingsFiling]:
    return await discover_holdings_filings(
        cik=cik,
        db=db,
        profile=profile,
        request_identity=request_identity,
        forms=LEGACY_HOLDINGS_FORMS,
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
    )


async def discover_holdings_filings(
    *,
    cik: str | int,
    forms: set[str],
    db: AsyncSession | None = None,
    profile: ETFProfile | None = None,
    request_identity: ETFHoldingsRequestIdentity | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_filings: int = 20,
) -> list[EdgarHoldingsFiling]:
    if _SEC_FUND_BUDGET.get() is None:
        return await _run_in_sec_fund_scope(
            lambda: discover_holdings_filings(
                cik=cik,
                forms=forms,
                db=db,
                profile=profile,
                request_identity=request_identity,
                start_date=start_date,
                end_date=end_date,
                max_filings=max_filings,
            )
        )
    request_identity = await _resolve_request_identity(
        db=db,
        profile=profile,
        request_identity=request_identity,
    )
    normalized_cik = normalize_cik(cik)
    committed_profile = await request_identity.db.get(ETFProfile, request_identity.profile_id)
    if normalize_cik(committed_profile.sec_cik) != normalized_cik:
        raise ETFHoldingsRouteHeldError("SEC request CIK does not match the committed ETF profile")
    response = await _sec_get(
        request_identity,
        operation="fetch_etf_holdings_sec_submissions",
        url=SEC_SUBMISSIONS_URL.format(cik=normalized_cik),
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
        archived_response = await _sec_get(
            request_identity,
            operation="fetch_etf_holdings_sec_submissions_file",
            url=SEC_SUBMISSIONS_FILE_URL.format(file_name=file_name),
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
        # The reviewed first-use envelope permits one archived-submissions page.
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
    if _SEC_FUND_BUDGET.get() is None:
        return await _run_in_sec_fund_scope(
            lambda: _backfill_sec_holdings(
                db,
                profile=profile,
                start_date=start_date,
                end_date=end_date,
                max_filings=max_filings,
                requested_by_user_id=requested_by_user_id,
                job_type=job_type,
                discover_filings=discover_filings,
                parse_xml=parse_xml,
                provenance=provenance,
                parser_version=parser_version,
                source_format=source_format,
                missing_date_reason=missing_date_reason,
                no_rows_reason=no_rows_reason,
                notes=notes,
            )
        )
    require_unbound_etf_holdings_context("SEC holdings backfill")
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
    already_ingested = 0

    try:
        request_identity = await _resolve_request_identity(db=db, profile=profile)
        filings = await discover_filings(
            cik=profile.sec_cik,
            db=db,
            profile=profile,
            request_identity=request_identity,
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

    for filing in filings:
        state = await _filing_state_for_accession(
            db,
            profile_id=profile.id,
            filing=filing,
            job_id=job.id,
        )
        if state.snapshot_id is not None and state.ingested_at is not None:
            skipped += 1
            already_ingested += 1
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
            response = await _sec_get(
                request_identity,
                operation="fetch_etf_holdings_sec_filing",
                url=filing.filing_url,
            )
            response.raise_for_status()
            identity_matches, filing_identity, identity_status = _sec_filing_identity_for_profile(
                profile, response.text
            )
            if not identity_matches:
                reason = f"filing_fund_identity_rejected:{identity_status}"
                binding = getattr(response, "extensions", {}).get("etf_holdings_request_binding")
                if binding is not None:
                    from types import SimpleNamespace  # noqa: PLC0415

                    from app.services.etf_holdings_refresh import (  # noqa: PLC0415
                        _retain_rejected_fetch_artifact,
                    )

                    await _retain_rejected_fetch_artifact(
                        db,
                        profile,
                        _EDGAR_ETF_HOLDINGS_ADAPTER,
                        binding,
                        failure=ETFHoldingsRouteHeldError(reason),
                        fetch_result=SimpleNamespace(
                            raw_text=response.text,
                            source_url=filing.filing_url,
                            source_identifier=filing.accession_number,
                        ),
                        validation={
                            "reason": reason,
                            "expected_series_id": profile.sec_series_id,
                            "expected_class_id": profile.sec_class_id,
                            "observed_filing_identity": filing_identity,
                        },
                    )
                skipped += 1
                state.status = "skipped"
                state.failure_reason = reason
                state.extra_data = {
                    **(state.extra_data or {}),
                    "identity_validation": {
                        "expected_series_id": profile.sec_series_id,
                        "expected_class_id": profile.sec_class_id,
                        "observed": filing_identity,
                        "status": identity_status,
                    },
                }
                failures.append(
                    {
                        "accession_number": filing.accession_number,
                        "reason": reason,
                    }
                )
                continue
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
            observed_at = _now()
            snapshot = await ingest_holdings_snapshot(
                db,
                etf_instrument=profile.instrument,
                rows=rows,
                composition_date=composition_date,
                as_of_date=filing.report_date or composition_date,
                known_at=_known_at(filing, observed_at=observed_at),
                published_at=None,
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
                    "filing_acceptance_at": (
                        filing.acceptance_datetime.isoformat()
                        if filing.acceptance_datetime is not None
                        else None
                    ),
                    "public_availability_time": "unverified",
                    "fund_identity": filing_identity,
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
            # This one-fund execution may retain at most one accepted snapshot.
            break
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
    successful_filings = ingested + already_ingested
    if successful_filings == 0:
        reason = "no_qualifying_filing_within_reviewed_budget"
        failures.append({"reason": reason})
        job.failure_reason = reason
        job.status = "partial" if skipped else "failed"
    elif failed or failures:
        job.status = "partial"
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
    priority_symbols: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_profiles: int = 50,
    max_filings_per_etf: int = 20,
    requested_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Backfill SEC holdings, prioritising required platform universes when bounded.

    The scheduled SEC pass is deliberately bounded.  Without an explicit priority order, an
    alphabetically sorted ETF catalog can consume the profile budget before the benchmark-family
    legs needed by the workstation are reached.  Priority changes ordering only; it does not
    fabricate identities, bypass the caller's explicit symbol filter, or alter filing semantics.
    """

    symbol_filters = [symbol.strip().upper() for symbol in symbols or [] if symbol.strip()]
    normalized_priority = list(
        dict.fromkeys(symbol.strip().upper() for symbol in priority_symbols or [] if symbol.strip())
    )
    stmt = (
        select(ETFProfile)
        .join(Instrument, Instrument.id == ETFProfile.instrument_id)
        .options(selectinload(ETFProfile.instrument))
        .where(ETFProfile.sec_cik.is_not(None))
    )
    if symbol_filters:
        stmt = stmt.where(Instrument.symbol.in_(symbol_filters))
        stmt = stmt.order_by(Instrument.symbol.asc())
    elif normalized_priority:
        priority_order = case(
            *(
                (Instrument.symbol == symbol, index)
                for index, symbol in enumerate(normalized_priority)
            ),
            else_=len(normalized_priority),
        )
        stmt = stmt.order_by(priority_order, Instrument.symbol.asc())
    else:
        stmt = stmt.order_by(Instrument.symbol.asc())
    stmt = stmt.limit(max_profiles)

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
