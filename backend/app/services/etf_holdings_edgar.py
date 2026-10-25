from __future__ import annotations

import asyncio
import contextvars
import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx as _httpx
from sqlalchemy import case, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHoldingsBackfillFiling,
    ETFHoldingsBackfillJob,
    ETFHoldingsRawArtifact,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers.errors import bounded_redact_provider_message
from app.services.etf_holdings import _hash_payload, ingest_holdings_snapshot
from app.services.etf_holdings_provider_bridge import (
    ETF_SEC_ADAPTER_KEY,
    ETF_SEC_ATTEMPT_TIMEOUT_SECONDS,
    ETF_SEC_FUND_DEADLINE_SECONDS,
    ETF_SEC_MAX_PHYSICAL_ATTEMPTS,
    ETF_SEC_MAX_REDIRECTS_PER_GET,
    ETFHoldingsRequestIdentity,
    ETFHoldingsRouteHeldError,
    ETFSECExecutionBudget,
    ProviderBackedHTTPXClient,
    _review_attempt_context,
    _sec_request_matches_profile_cik,
    bind_etf_holdings_sec_request_context,
    current_etf_holdings_request_identity,
    require_unbound_etf_holdings_context,
)
from app.services.etf_holdings_sec import parse_sec_legacy_holdings_xml, parse_sec_nport_xml
from app.services.provider_quota_coordinator import account_scope_for_provider
from app.services.provider_runtime import (
    _ETF_INITIAL_QUALIFICATION_OPERATIONS,
    _new_etf_initial_qualification_authority,
    record_entitlement_revision,
)


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
SEC_INITIAL_QUALIFICATION_JOB_TYPE = "sec_nport_initial_qualification"


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
        initial_qualification_authority=sec_budget.initial_qualification_authority,
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


def _utc_timestamp(value: datetime) -> datetime:
    """Compare ORM timestamps consistently across PostgreSQL and SQLite."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
async def sec_fund_execution_scope(initial_qualification_authority=None):
    """Share one bounded envelope across all SEC calls for the same fund."""
    active_budget = _SEC_FUND_BUDGET.get()
    if active_budget is not None:
        if active_budget.initial_qualification_authority is not initial_qualification_authority:
            raise ETFHoldingsRouteHeldError(
                "SEC qualification context cannot be changed inside an active fund scope"
            )
        active_budget._check_deadline()
        yield active_budget
        return

    budget = ETFSECExecutionBudget(initial_qualification_authority)
    token = _SEC_FUND_BUDGET.set(budget)
    try:
        async with asyncio.timeout(ETF_SEC_FUND_DEADLINE_SECONDS):
            yield budget
    except TimeoutError as exc:
        raise ETFHoldingsRouteHeldError("SEC one-fund execution deadline exceeded") from exc
    finally:
        _SEC_FUND_BUDGET.reset(token)


async def _run_in_sec_fund_scope(coro_factory, *, initial_qualification_authority=None):
    async with sec_fund_execution_scope(initial_qualification_authority):
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
    qualification_job: ETFHoldingsBackfillJob | None = None,
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
                qualification_job=qualification_job,
            )
        )
    require_unbound_etf_holdings_context("SEC holdings backfill")
    if qualification_job is None:
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
    else:
        job = qualification_job
        if (
            job.etf_profile_id != profile.id
            or job.job_type != SEC_INITIAL_QUALIFICATION_JOB_TYPE
            or job.status != "running"
        ):
            raise ETFHoldingsRouteHeldError(
                "SEC initial qualification audit latch is not active for this fund"
            )
        job.max_filings = max_filings

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


def _qualification_advisory_key(account_scope: str) -> int:
    key = f"provider:edgar:ETF_HOLDINGS:{account_scope.strip()}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big", signed=True)


def _qualification_preflight_urls(profile: ETFProfile) -> dict[str, str]:
    cik = normalize_cik(profile.sec_cik or "")
    accession = "000000000000000001"
    return {
        "fetch_etf_holdings_sec_submissions": SEC_SUBMISSIONS_URL.format(cik=cik),
        "fetch_etf_holdings_sec_submissions_file": SEC_SUBMISSIONS_FILE_URL.format(
            file_name=f"CIK{cik}-submissions-0000000000.json"
        ),
        "fetch_etf_holdings_sec_filing": SEC_ARCHIVES_BASE_URL.format(
            cik=_archive_cik(cik),
            accession=accession,
            document="qualification-preflight.xml",
        ),
    }


async def _preflight_initial_qualification(db: AsyncSession, profile: ETFProfile) -> str:
    preflight_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    try:
        if not settings.PROVIDER_ROUTING_ENABLED:
            raise ETFHoldingsRouteHeldError("shared Provider routing is disabled")
        committed_profile = (
            await preflight_db.execute(
                select(ETFProfile)
                .options(selectinload(ETFProfile.instrument))
                .where(ETFProfile.id == profile.id)
            )
        ).scalar_one_or_none()
        if committed_profile is None or not committed_profile.instrument:
            raise ETFHoldingsRouteHeldError("committed ETF profile and instrument are required")
        if (
            not committed_profile.sec_cik
            or not committed_profile.sec_series_id
            or not committed_profile.sec_class_id
        ):
            raise ETFHoldingsRouteHeldError(
                "initial SEC qualification requires committed CIK, series, and class identity"
            )
        identity = await _resolve_request_identity(db=preflight_db, profile=committed_profile)
        source = await preflight_db.scalar(select(DataSource).where(DataSource.name == "edgar"))
        if source is None:
            raise ETFHoldingsRouteHeldError("EDGAR shared Provider source is missing")
        policy = await preflight_db.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        if policy is None or str(policy.quota_scope or "").strip().lower() != "ip":
            raise ETFHoldingsRouteHeldError("reviewed EDGAR shared IP policy is required")
        account_scope_map = settings.PROVIDER_QUOTA_ACCOUNT_SCOPES
        if (
            not isinstance(account_scope_map, dict)
            or not isinstance(account_scope_map.get("edgar:ip"), str)
            or not account_scope_map["edgar:ip"].strip()
        ):
            raise ETFHoldingsRouteHeldError("explicit edgar:ip account mapping is required")
        try:
            account_scope = account_scope_for_provider("edgar", "ip")
        except Exception as exc:  # noqa: BLE001 - unknown account scope is a hold.
            raise ETFHoldingsRouteHeldError("EDGAR shared account scope is unavailable") from exc
        if account_scope.strip() in {"*", "ALL", "ANY"}:
            raise ETFHoldingsRouteHeldError("wildcard EDGAR account scope is not eligible")

        # Validate every reviewed operation before consuming the durable
        # one-attempt latch. This temporary value remains in this private
        # transaction and is rolled back before any request can begin.
        policy.is_enabled = True
        for operation, request_url in _qualification_preflight_urls(committed_profile).items():
            _, _, observed_scope = await _review_attempt_context(
                preflight_db,
                provider_name="edgar",
                profile_id=identity.profile_id,
                instrument_id=identity.instrument_id,
                provider_symbol=identity.provider_symbol,
                adapter_key=ETF_SEC_ADAPTER_KEY,
                operation=operation,
                request_url=request_url,
                sec_request=True,
            )
            if observed_scope != account_scope:
                raise ETFHoldingsRouteHeldError(
                    "EDGAR operation review does not match its shared account scope"
                )
        return account_scope
    finally:
        await preflight_db.rollback()
        await preflight_db.close()


async def _finish_interrupted_qualification(
    bind,
    *,
    attempt_id: int,
    status: str,
    reason: str,
) -> None:
    session = AsyncSession(bind=bind, expire_on_commit=False)
    try:
        job = await session.get(ETFHoldingsBackfillJob, attempt_id)
        if job is not None and job.status == "running":
            job.status = status
            job.failure_reason = reason
            job.completed_at = _now()
            extra_data = dict(job.extra_data or {})
            extra_data["qualification_outcome"] = {
                "status": "not_qualified",
                "reason": reason,
            }
            job.extra_data = extra_data
        source = await session.scalar(select(DataSource).where(DataSource.name == "edgar"))
        if source is not None:
            policy = await session.scalar(
                select(ProviderPolicy).where(
                    ProviderPolicy.data_source_id == source.id,
                    ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
                )
            )
            if policy is not None:
                policy.is_enabled = False
        await session.commit()
    finally:
        await session.close()


async def _await_shielded_qualification_finalizer(coro) -> None:
    task = asyncio.create_task(coro)
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    task.result()


async def _qualification_success_evidence(
    db: AsyncSession,
    *,
    job: ETFHoldingsBackfillJob,
    profile: ETFProfile,
    summary: dict[str, Any],
) -> tuple[bool, str]:
    if summary.get("status") != "completed" or int(summary.get("ingested") or 0) != 1:
        return False, "qualification_requires_one_new_completed_snapshot"
    if summary.get("failures"):
        return False, "qualification_backfill_contains_failures"
    await db.flush()
    await db.refresh(job, attribute_names=["extra_data"])
    extra_data = dict(job.extra_data or {})
    request_log_ids = list(extra_data.get("provider_request_log_ids") or [])
    if not request_log_ids or len(request_log_ids) != len(set(request_log_ids)):
        return False, "qualification_request_audit_link_is_missing_or_ambiguous"

    filing_rows = (
        (
            await db.execute(
                select(ETFHoldingsBackfillFiling).where(
                    ETFHoldingsBackfillFiling.etf_profile_id == profile.id,
                    ETFHoldingsBackfillFiling.last_job_id == job.id,
                    ETFHoldingsBackfillFiling.snapshot_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(filing_rows) != 1:
        return False, "qualification_requires_exactly_one_new_filing_snapshot"
    filing = filing_rows[0]
    if filing.status != "ingested" or not filing.accession_number or not filing.filing_url:
        return False, "qualification_filing_lineage_is_incomplete"
    snapshot = await db.get(ETFHoldingsSnapshot, filing.snapshot_id)
    if (
        snapshot is None
        or snapshot.etf_profile_id != profile.id
        or snapshot.provenance != "sec_nport_reconstructed_holdings"
        or snapshot.source_provider != "sec"
        or snapshot.row_count <= 0
        or snapshot.source_artifact_id is None
        or not snapshot.source_url
        or not snapshot.source_identifier
        or not snapshot.known_at
        or snapshot.published_at is not None
        or snapshot.source_identifier != filing.accession_number
        or snapshot.source_url != filing.filing_url
    ):
        return False, "qualification_snapshot_provenance_is_incomplete"
    if not _sec_request_matches_profile_cik(
        snapshot.source_url, profile.sec_cik, "fetch_etf_holdings_sec_filing"
    ):
        return False, "qualification_snapshot_source_does_not_match_committed_cik"
    raw_artifact = await db.get(ETFHoldingsRawArtifact, snapshot.source_artifact_id)
    if (
        raw_artifact is None
        or raw_artifact.etf_profile_id != profile.id
        or raw_artifact.source_kind != snapshot.provenance
        or raw_artifact.content_hash != _hash_payload(raw_artifact.payload_text)
        or not raw_artifact.payload_text
        or raw_artifact.source_url != snapshot.source_url
        or _utc_timestamp(raw_artifact.fetched_at) < _utc_timestamp(job.started_at)
        or _utc_timestamp(snapshot.created_at) < _utc_timestamp(job.started_at)
        or _utc_timestamp(snapshot.known_at) < _utc_timestamp(job.started_at)
        or raw_artifact.source_identifier != snapshot.source_identifier
    ):
        return False, "qualification_raw_artifact_integrity_is_incomplete"
    raw_identity = (raw_artifact.legal_metadata or {}).get("fund_identity")
    if not isinstance(raw_identity, dict) or (
        raw_identity.get("series_id") != profile.sec_series_id
        or raw_identity.get("class_id") != profile.sec_class_id
    ):
        return False, "qualification_raw_artifact_fund_identity_does_not_match"

    logs = (
        (
            await db.execute(
                select(ProviderRequestLog).where(ProviderRequestLog.id.in_(request_log_ids))
            )
        )
        .scalars()
        .all()
    )
    source = await db.scalar(select(DataSource).where(DataSource.name == "edgar"))
    expected_symbol = str(profile.instrument.symbol if profile.instrument else "").strip().upper()
    allowed_operations = _ETF_INITIAL_QUALIFICATION_OPERATIONS
    if source is None or len(logs) != len(request_log_ids) or not logs:
        return False, "qualification_shared_request_audit_is_incomplete"
    observed_operations: set[str] = set()
    for log in logs:
        if (
            log.data_source_id != source.id
            or log.capability != ProviderCapability.ETF_HOLDINGS
            or log.operation not in allowed_operations
            or log.instrument_id != profile.instrument_id
            or str(log.provider_symbol or "").strip().upper() != expected_symbol
            or not log.success
            or log.completed_at is None
            or log.http_requests != 1
            or log.settled_usage_units is None
        ):
            return False, "qualification_shared_request_audit_is_not_successfully_settled"
        observed_operations.add(log.operation)
    if not {
        "fetch_etf_holdings_sec_submissions",
        "fetch_etf_holdings_sec_filing",
    }.issubset(observed_operations):
        return False, "qualification_shared_request_audit_does_not_cover_discovery_and_filing"
    extra_data["qualification_snapshot_id"] = snapshot.id
    extra_data["qualification_raw_artifact_id"] = raw_artifact.id
    extra_data["qualification_request_log_ids"] = request_log_ids
    job.extra_data = extra_data
    return True, "qualified"


async def qualify_sec_nport_fund(
    db: AsyncSession,
    *,
    profile_id: int,
    requested_by_user_id: int,
) -> dict[str, Any]:
    """Run one explicit, admin-only initial N-PORT qualification for a committed fund."""

    require_unbound_etf_holdings_context("SEC initial qualification")
    operation_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    lock_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    attempt: ETFHoldingsBackfillJob | None = None
    try:
        profile = (
            await operation_db.execute(
                select(ETFProfile)
                .options(selectinload(ETFProfile.instrument))
                .where(ETFProfile.id == profile_id)
            )
        ).scalar_one_or_none()
        if profile is None or profile.instrument is None:
            raise ETFHoldingsRouteHeldError(
                "initial qualification requires an existing ETF profile"
            )
        identity = await _resolve_request_identity(db=operation_db, profile=profile)
        account_scope = await _preflight_initial_qualification(operation_db, profile)

        if lock_db.get_bind().dialect.name != "postgresql":
            raise ETFHoldingsRouteHeldError(
                "cross-process SEC qualification serialization requires PostgreSQL"
            )
        lock_key = _qualification_advisory_key(account_scope)
        await lock_db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
        )

        source = await operation_db.scalar(select(DataSource).where(DataSource.name == "edgar"))
        if source is None:
            raise ETFHoldingsRouteHeldError("EDGAR shared Provider source is missing")
        policy = await operation_db.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        entitlement = await operation_db.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == source.id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        if policy is None or entitlement is None:
            raise ETFHoldingsRouteHeldError(
                "reviewed EDGAR ETF policy and entitlement are required"
            )

        unresolved_jobs = (
            (
                await operation_db.execute(
                    select(ETFHoldingsBackfillJob).where(
                        ETFHoldingsBackfillJob.job_type == SEC_INITIAL_QUALIFICATION_JOB_TYPE,
                        ETFHoldingsBackfillJob.status == "running",
                    )
                )
            )
            .scalars()
            .all()
        )
        if unresolved_jobs:
            for old_job in unresolved_jobs:
                old_job.status = "interrupted"
                old_job.failure_reason = (
                    "prior initial qualification was interrupted; replay denied"
                )
                old_job.completed_at = _now()
                old_extra = dict(old_job.extra_data or {})
                old_extra["qualification_outcome"] = {
                    "status": "not_qualified",
                    "reason": "interrupted_attempt_requires_operator_review",
                }
                old_job.extra_data = old_extra
            policy.is_enabled = False
            await operation_db.commit()
            raise ETFHoldingsRouteHeldError(
                "an interrupted SEC initial qualification is latched; replay is denied"
            )

        previous = await operation_db.scalar(
            select(ETFHoldingsBackfillJob.id)
            .where(
                ETFHoldingsBackfillJob.etf_profile_id == profile.id,
                ETFHoldingsBackfillJob.job_type == SEC_INITIAL_QUALIFICATION_JOB_TYPE,
            )
            .limit(1)
        )
        if previous is not None:
            raise ETFHoldingsRouteHeldError(
                "this fund already has a latched SEC initial qualification; replay is denied"
            )
        if policy.is_enabled:
            raise ETFHoldingsRouteHeldError(
                "EDGAR ETF policy is already enabled; initial qualification will not overwrite it"
            )
        if str(entitlement.live_probe_status or "not_run").strip().lower() != "not_run":
            raise ETFHoldingsRouteHeldError(
                "initial qualification is available only for an unprobed EDGAR ETF entitlement"
            )

        now = _now()
        attempt = ETFHoldingsBackfillJob(
            etf_profile_id=profile.id,
            requested_by_user_id=requested_by_user_id,
            source_provider="sec",
            job_type=SEC_INITIAL_QUALIFICATION_JOB_TYPE,
            status="running",
            max_filings=ETF_SEC_MAX_PHYSICAL_ATTEMPTS,
            started_at=now,
            discovered_count=0,
            ingested_count=0,
            skipped_count=0,
            failed_count=0,
            extra_data={
                "qualification_scope": {
                    "provider": "edgar",
                    "capability": ProviderCapability.ETF_HOLDINGS.value,
                    "operations": sorted(_ETF_INITIAL_QUALIFICATION_OPERATIONS),
                    "profile_id": profile.id,
                    "instrument_id": profile.instrument_id,
                    "account_scope": account_scope,
                },
                "qualification_outcome": {"status": "in_progress"},
            },
        )
        operation_db.add(attempt)
        policy.is_enabled = True
        await operation_db.flush()
        await operation_db.commit()

        authority = _new_etf_initial_qualification_authority(
            attempt_id=attempt.id,
            provider_name="edgar",
            capability=ProviderCapability.ETF_HOLDINGS,
            operations=_ETF_INITIAL_QUALIFICATION_OPERATIONS,
            profile_id=profile.id,
            instrument_id=profile.instrument_id,
            provider_symbol=identity.provider_symbol,
            account_scope=account_scope,
            expires_at=now + timedelta(seconds=ETF_SEC_FUND_DEADLINE_SECONDS),
        )
        summary = await _run_in_sec_fund_scope(
            lambda: _backfill_sec_holdings(
                operation_db,
                profile=profile,
                start_date=None,
                end_date=None,
                max_filings=ETF_SEC_MAX_PHYSICAL_ATTEMPTS,
                requested_by_user_id=requested_by_user_id,
                job_type=SEC_INITIAL_QUALIFICATION_JOB_TYPE,
                discover_filings=discover_nport_filings,
                parse_xml=parse_sec_nport_xml,
                provenance="sec_nport_reconstructed_holdings",
                parser_version="sec-nport-v1",
                source_format="nport_xml",
                missing_date_reason="N-PORT XML did not expose a report date.",
                no_rows_reason="N-PORT XML did not contain parseable holdings rows.",
                notes="Reconstructed from SEC EDGAR N-PORT filing under one-fund qualification.",
                qualification_job=attempt,
            ),
            initial_qualification_authority=authority,
        )

        qualified, qualification_reason = await _qualification_success_evidence(
            operation_db,
            job=attempt,
            profile=profile,
            summary=summary,
        )
        policy = await operation_db.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        entitlement = await operation_db.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == source.id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        if policy is None or entitlement is None:
            raise ETFHoldingsRouteHeldError(
                "EDGAR qualification state disappeared during execution"
            )
        policy.is_enabled = False
        extra_data = dict(attempt.extra_data or {})
        if qualified:
            entitlement.live_probe_status = "passed"
            entitlement.revision = int(entitlement.revision or 1) + 1
            attempt.status = "completed"
            attempt.failure_reason = None
            extra_data["qualification_outcome"] = {
                "status": "passed",
                "qualified_at": _now().isoformat(),
                "snapshot_id": extra_data.get("qualification_snapshot_id"),
            }
            attempt.extra_data = extra_data
            await operation_db.flush()
            await record_entitlement_revision(
                operation_db,
                entitlement,
                change_reason=f"sec_initial_qualification:{attempt.id}",
            )
        else:
            attempt.status = "failed" if summary.get("status") != "partial" else "partial"
            attempt.failure_reason = qualification_reason
            extra_data["qualification_outcome"] = {
                "status": "not_qualified",
                "reason": qualification_reason,
            }
            attempt.extra_data = extra_data
            if summary.get("status") == "completed":
                summary = {
                    **summary,
                    "status": "failed",
                    "failures": [
                        *list(summary.get("failures") or []),
                        {"reason": qualification_reason},
                    ],
                }
                attempt.summary = summary
        await operation_db.commit()
        return summary
    except asyncio.CancelledError:
        if attempt is not None:
            await operation_db.rollback()
            await _await_shielded_qualification_finalizer(
                _finish_interrupted_qualification(
                    db.bind,
                    attempt_id=attempt.id,
                    status="cancelled",
                    reason="SEC initial qualification was cancelled; replay denied",
                )
            )
        raise
    except BaseException as exc:
        if attempt is not None:
            await operation_db.rollback()
            await _await_shielded_qualification_finalizer(
                _finish_interrupted_qualification(
                    db.bind,
                    attempt_id=attempt.id,
                    status="failed",
                    reason=bounded_redact_provider_message(exc, max_length=1000),
                )
            )
        raise
    finally:
        await lock_db.close()
        await operation_db.close()


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
                    ETFHoldingsBackfillJob.job_type.in_(
                        [
                            "sec_nport_recent",
                            "sec_legacy_recent",
                            SEC_INITIAL_QUALIFICATION_JOB_TYPE,
                        ]
                    ),
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
