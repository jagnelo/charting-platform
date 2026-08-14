from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.etf_holdings import ETFHoldingsAdapterState
from app.models.user import User
from app.schemas.basket import BasketOut
from app.schemas.etf_holdings import (
    BenchmarkFamilyHoldingsDatedRefreshRequest,
    BenchmarkFamilyHoldingsDatedRefreshSummary,
    ETFConstituentTimelinePoint,
    ETFHoldingsAdapterCatalogOut,
    ETFHoldingsAdapterProbeOut,
    ETFHoldingsAdapterStateOut,
    ETFHoldingsBackfillJobOut,
    ETFHoldingsCoverageRequest,
    ETFHoldingsCoverageSummary,
    ETFHoldingsCSVIngestRequest,
    ETFHoldingsDatedRefreshRequest,
    ETFHoldingsDateOut,
    ETFHoldingsDiffOut,
    ETFHoldingsDiscoveryRequest,
    ETFHoldingsDiscoverySummary,
    ETFHoldingsIngestRequest,
    ETFHoldingsOverlapMatrixOut,
    ETFHoldingsOverlapMatrixRequest,
    ETFHoldingsOverlapRequest,
    ETFHoldingsOverlapSummaryOut,
    ETFHoldingsPageOut,
    ETFHoldingsSECBackfillRequest,
    ETFHoldingsSECBackfillSummary,
    ETFHoldingsSECBulkBackfillRequest,
    ETFHoldingsSECBulkBackfillSummary,
    ETFHoldingsSECIngestRequest,
    ETFHoldingsSECLegacyIngestRequest,
    ETFHoldingsSnapshotOut,
    ETFHoldingsTransitionTimelineOut,
    ETFHoldingsWeightEvolutionOut,
    ETFProfileBootstrapOut,
    ETFProfileBootstrapRequest,
    ETFProfileOut,
    ETFProfileUpdateRequest,
    ETFUnresolvedHoldingOut,
)
from app.services.baskets import basket_to_out, materialize_etf_holdings_basket
from app.services.etf_holdings import (
    coverage_summary,
    ensure_etf_profile,
    ensure_lightweight_etf_instrument,
    get_constituent_timeline,
    get_etf_profile_for_instrument,
    get_holdings_diff,
    get_holdings_overlap_matrix,
    get_holdings_overlap_summary,
    get_holdings_page,
    get_holdings_transition_timeline,
    get_latest_snapshot,
    get_nearest_snapshot,
    get_unresolved_holdings,
    get_weight_evolution,
    ingest_holdings_snapshot,
    list_available_dates,
    list_etfs_with_holdings,
    profile_to_out,
    snapshot_to_out,
)
from app.services.etf_holdings_adapters import (
    get_holdings_adapter,
    holdings_adapter_catalog,
    parse_holdings_csv,
)
from app.services.etf_holdings_edgar import (
    backfill_all_sec_legacy_holdings,
    backfill_all_sec_nport_holdings,
    backfill_sec_legacy_holdings,
    backfill_sec_nport_holdings,
    get_sec_nport_backfill_job,
    list_sec_nport_backfill_jobs,
)
from app.services.etf_holdings_refresh import (
    ETFHoldingsRouteNotReadyError,
    bootstrap_etf_holdings_profile,
    discover_etf_profiles_from_issuer_feed,
    discover_etf_profiles_from_sec_fund_tickers,
    probe_etf_holdings_adapter_route,
    refresh_all_known_etf_holdings,
    refresh_benchmark_family_holdings_for_date,
    refresh_etf_holdings_for_date,
)
from app.services.etf_holdings_sec import parse_sec_legacy_holdings_xml, parse_sec_nport_xml

router = APIRouter(prefix="/etf-holdings", tags=["etf-holdings"])


@router.post(
    "/benchmark-family/{family_key}/refresh-date",
    response_model=BenchmarkFamilyHoldingsDatedRefreshSummary,
)
async def refresh_benchmark_family_for_date(
    family_key: str,
    body: BenchmarkFamilyHoldingsDatedRefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        summary = await refresh_benchmark_family_holdings_for_date(
            db,
            family_key=family_key,
            requested_date=body.requested_date,
            roles=body.roles,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return summary


@router.get("", response_model=list[ETFProfileOut])
async def search_etfs_with_holdings(
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_etfs_with_holdings(db, q=q)


@router.post("/{symbol}/bootstrap", response_model=ETFProfileBootstrapOut)
async def bootstrap_holdings_profile(
    symbol: str,
    body: ETFProfileBootstrapRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await bootstrap_etf_holdings_profile(
        db,
        symbol=symbol,
        name=body.name,
    )
    await db.commit()
    profile = await profile_to_out(db, result.profile)
    latest_snapshot = None
    if profile.latest_snapshot_id is not None:
        latest_snapshot = await get_latest_snapshot(
            db,
            result.profile.instrument_id,
            include_holdings=False,
        )
    adapter = get_holdings_adapter(result.probe.adapter_key)
    return ETFProfileBootstrapOut(
        profile=profile,
        latest_snapshot=latest_snapshot,
        probe=ETFHoldingsAdapterProbeOut(
            symbol=profile.symbol,
            name=profile.name,
            adapter_key=result.probe.adapter_key,
            source_provider=adapter.source_provider if adapter else None,
            confidence=result.probe.confidence,
            status=result.probe.status,
            reason=result.probe.reason,
            source_url=result.probe.source_url,
            issuer_product_id=result.probe.issuer_product_id,
            required_identifiers=result.probe.required_identifiers,
        ),
        refresh_attempted=result.refresh_attempted,
        refresh_succeeded=result.refresh_succeeded,
        message=result.message,
    )


@router.get("/adapters", response_model=list[ETFHoldingsAdapterCatalogOut])
async def holdings_adapter_catalog_endpoint(
    current_user: User = Depends(require_admin),
):
    return holdings_adapter_catalog()


@router.get("/{symbol_or_id}/latest", response_model=ETFHoldingsSnapshotOut)
async def latest_holdings_snapshot(
    symbol_or_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snapshot = await get_latest_snapshot(db, symbol_or_id)
    if snapshot is None:
        raise HTTPException(404, "ETF holdings snapshot not found")
    return snapshot


@router.get("/{symbol_or_id}/basket", response_model=BasketOut)
async def materialized_holdings_basket(
    symbol_or_id: str,
    snapshot_id: int | None = Query(None),
    date_: date | None = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    basket = await materialize_etf_holdings_basket(
        db,
        symbol_or_id,
        snapshot_id=snapshot_id,
        snapshot_date=date_,
    )
    if basket is None:
        raise HTTPException(404, "ETF holdings basket could not be materialized")
    await db.commit()
    return basket_to_out(basket)


@router.get("/{symbol_or_id}/holdings", response_model=ETFHoldingsPageOut)
async def paged_holdings(
    symbol_or_id: str,
    snapshot_id: int | None = Query(None),
    date_: date | None = Query(None, alias="date"),
    point_in_time: bool = Query(True),
    q: str | None = Query(None),
    sort: str = Query(
        "position", pattern="^(position|weight|market_value|shares|symbol|name|resolved)$"
    ),
    direction: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = await get_holdings_page(
        db,
        symbol_or_id,
        snapshot_id=snapshot_id,
        snapshot_date=date_,
        point_in_time=point_in_time,
        q=q,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )
    if page is None:
        raise HTTPException(404, "ETF holdings snapshot not found")
    return page


@router.get("/{symbol_or_id}/diff", response_model=ETFHoldingsDiffOut)
async def holdings_diff(
    symbol_or_id: str,
    left_snapshot_id: int | None = Query(None),
    right_snapshot_id: int | None = Query(None),
    left_date: date | None = Query(None),
    right_date: date | None = Query(None),
    point_in_time: bool = Query(True),
    include_unchanged: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    diff = await get_holdings_diff(
        db,
        symbol_or_id,
        left_snapshot_id=left_snapshot_id,
        right_snapshot_id=right_snapshot_id,
        left_date=left_date,
        right_date=right_date,
        point_in_time=point_in_time,
        include_unchanged=include_unchanged,
    )
    if diff is None:
        raise HTTPException(404, "ETF holdings diff could not be produced")
    return diff


@router.get("/{symbol_or_id}/dates", response_model=list[ETFHoldingsDateOut])
async def holdings_dates(
    symbol_or_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_available_dates(db, symbol_or_id)


@router.get("/{symbol_or_id}/weight-evolution", response_model=ETFHoldingsWeightEvolutionOut)
async def holdings_weight_evolution(
    symbol_or_id: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    evolution = await get_weight_evolution(
        db,
        symbol_or_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if evolution is None:
        raise HTTPException(404, "ETF holdings weight evolution could not be produced")
    return evolution


@router.get("/{symbol_or_id}/transitions", response_model=ETFHoldingsTransitionTimelineOut)
async def holdings_transition_timeline(
    symbol_or_id: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    timeline = await get_holdings_transition_timeline(
        db,
        symbol_or_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if timeline is None:
        raise HTTPException(404, "ETF holdings transition timeline could not be produced")
    return timeline


@router.get("/{symbol_or_id}/nearest", response_model=ETFHoldingsSnapshotOut)
async def nearest_holdings_snapshot(
    symbol_or_id: str,
    date_: date = Query(..., alias="date"),
    point_in_time: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snapshot = await get_nearest_snapshot(
        db, symbol_or_id, requested_date=date_, point_in_time=point_in_time
    )
    if snapshot is None:
        raise HTTPException(404, "No usable ETF holdings snapshot found for that date")
    return snapshot


@router.get(
    "/{symbol_or_id}/constituents/{constituent_id}/timeline",
    response_model=list[ETFConstituentTimelinePoint],
)
async def constituent_timeline(
    symbol_or_id: str,
    constituent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_constituent_timeline(db, symbol_or_id, constituent_id)


@router.get("/{symbol_or_id}/unresolved", response_model=list[ETFUnresolvedHoldingOut])
async def unresolved_holdings(
    symbol_or_id: str,
    snapshot_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_unresolved_holdings(db, symbol_or_id, snapshot_id=snapshot_id)


@router.post("/coverage-summary", response_model=ETFHoldingsCoverageSummary)
async def holdings_coverage_summary(
    body: ETFHoldingsCoverageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await coverage_summary(
        db,
        etf_symbols=body.etf_symbols,
        etf_instrument_ids=body.etf_instrument_ids,
        start_date=body.start_date,
        end_date=body.end_date,
    )


@router.post("/overlap-summary", response_model=ETFHoldingsOverlapSummaryOut)
async def holdings_overlap_summary(
    body: ETFHoldingsOverlapRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_holdings_overlap_summary(
        db,
        etf_symbols=body.etf_symbols,
        etf_instrument_ids=body.etf_instrument_ids,
        snapshot_date=body.snapshot_date,
        point_in_time=body.point_in_time,
        top_n=body.top_n,
    )


@router.post("/overlap-matrix", response_model=ETFHoldingsOverlapMatrixOut)
async def holdings_overlap_matrix(
    body: ETFHoldingsOverlapMatrixRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_holdings_overlap_matrix(
        db,
        etf_symbols=body.etf_symbols,
        etf_instrument_ids=body.etf_instrument_ids,
        snapshot_date=body.snapshot_date,
        point_in_time=body.point_in_time,
        top_n=body.top_n,
        metric=body.metric,
        issuer=body.issuer,
        fund_family=body.fund_family,
        q=body.q,
        limit=body.limit,
    )


@router.post("/refresh", response_model=dict)
async def refresh_holdings_profiles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await refresh_all_known_etf_holdings(db)


@router.post("/discover", response_model=ETFHoldingsDiscoverySummary)
async def discover_holdings_profiles(
    body: ETFHoldingsDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    summary = await discover_etf_profiles_from_issuer_feed(
        db,
        adapter_key=body.adapter_key,
        source_url=body.source_url,
        issuer=body.issuer,
        fund_family=body.fund_family,
    )
    await db.commit()
    return summary


@router.post("/discover-sec-funds", response_model=ETFHoldingsDiscoverySummary)
async def discover_sec_fund_profiles(
    source_url: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    summary = await discover_etf_profiles_from_sec_fund_tickers(
        db,
        **({"source_url": source_url} if source_url else {}),
    )
    await db.commit()
    return summary


@router.post("/{symbol}/probe-adapter", response_model=ETFHoldingsAdapterProbeOut)
async def probe_holdings_adapter(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    instrument = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    profile = await ensure_etf_profile(db, instrument)
    probe = await probe_etf_holdings_adapter_route(db, profile)
    await db.flush()
    adapter = get_holdings_adapter(probe.adapter_key)
    return ETFHoldingsAdapterProbeOut(
        symbol=instrument.symbol,
        name=instrument.name,
        adapter_key=probe.adapter_key,
        source_provider=adapter.source_provider if adapter else None,
        confidence=probe.confidence,
        status=probe.status,
        reason=probe.reason,
        source_url=probe.source_url,
        issuer_product_id=probe.issuer_product_id,
        required_identifiers=probe.required_identifiers,
    )


@router.post("/{symbol}/refresh-date", response_model=ETFHoldingsSnapshotOut)
async def refresh_holdings_for_date(
    symbol: str,
    body: ETFHoldingsDatedRefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    instrument = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    profile = await ensure_etf_profile(db, instrument)
    probe = await probe_etf_holdings_adapter_route(db, profile)
    if probe.status != "ready":
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "code": probe.status,
                "symbol": instrument.symbol,
                "adapter_key": probe.adapter_key,
                "message": probe.reason or "No usable free holdings route is configured.",
                "required_identifiers": probe.required_identifiers,
            },
        )
    try:
        snapshot = await refresh_etf_holdings_for_date(
            db,
            profile,
            requested_date=body.requested_date,
        )
    except ETFHoldingsRouteNotReadyError as exc:
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "holdings_route_not_ready",
                "symbol": instrument.symbol,
                "adapter_key": profile.adapter_key,
                "message": str(exc),
            },
        ) from exc
    await db.commit()
    return snapshot_to_out(snapshot, instrument=instrument)


@router.get("/{symbol}/adapter-state", response_model=list[ETFHoldingsAdapterStateOut])
async def holdings_adapter_state(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    instrument = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    profile = await ensure_etf_profile(db, instrument)
    states = (
        (
            await db.execute(
                select(ETFHoldingsAdapterState)
                .where(ETFHoldingsAdapterState.etf_profile_id == profile.id)
                .order_by(ETFHoldingsAdapterState.adapter_key)
            )
        )
        .scalars()
        .all()
    )
    return states


@router.post("/backfill-sec-nport", response_model=ETFHoldingsSECBulkBackfillSummary)
async def bulk_backfill_sec_nport_holdings(
    body: ETFHoldingsSECBulkBackfillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    summary = await backfill_all_sec_nport_holdings(
        db,
        symbols=body.symbols,
        start_date=body.start_date,
        end_date=body.end_date,
        max_profiles=body.max_profiles,
        max_filings_per_etf=body.max_filings_per_etf,
        requested_by_user_id=current_user.id,
    )
    await db.commit()
    return summary


@router.post("/backfill-sec-legacy", response_model=ETFHoldingsSECBulkBackfillSummary)
async def bulk_backfill_sec_legacy_holdings(
    body: ETFHoldingsSECBulkBackfillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    summary = await backfill_all_sec_legacy_holdings(
        db,
        symbols=body.symbols,
        start_date=body.start_date,
        end_date=body.end_date,
        max_profiles=body.max_profiles,
        max_filings_per_etf=body.max_filings_per_etf,
        requested_by_user_id=current_user.id,
    )
    await db.commit()
    return summary


@router.patch("/{symbol}/profile", response_model=ETFProfileOut)
async def update_etf_profile(
    symbol: str,
    body: ETFProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    instrument = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    profile = await ensure_etf_profile(
        db,
        instrument,
        issuer=body.issuer,
        sponsor=body.sponsor,
        fund_family=body.fund_family,
        index_name=body.index_name,
        product_url=body.product_url,
        sec_cik=body.sec_cik,
        sec_series_id=body.sec_series_id,
        sec_class_id=body.sec_class_id,
        provider_aliases=body.provider_aliases,
        legal_metadata=body.legal_metadata,
    )
    await db.flush()
    return await profile_to_out(db, profile)


@router.post("/{symbol}/ingest", response_model=ETFHoldingsSnapshotOut)
async def ingest_holdings_rows(
    symbol: str,
    body: ETFHoldingsIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    etf = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    await ingest_holdings_snapshot(
        db,
        etf_instrument=etf,
        rows=body.rows,
        composition_date=body.composition_date,
        as_of_date=body.as_of_date,
        known_at=body.known_at,
        published_at=body.published_at,
        provenance=body.provenance,
        source_provider=body.source_provider,
        source_url=body.source_url,
        source_identifier=body.source_identifier,
        source_quality=body.source_quality,
        completeness_status=body.completeness_status,
        parser_version=body.parser_version,
        raw_payload_text=body.raw_payload_text,
        raw_payload_json=body.raw_payload_json,
        legal_metadata=body.legal_metadata,
        notes=body.notes,
    )
    loaded = await get_latest_snapshot(db, etf.id)
    if loaded is None:
        raise HTTPException(500, "Holdings were ingested but could not be reloaded")
    return loaded


@router.post("/{symbol}/ingest-csv", response_model=ETFHoldingsSnapshotOut)
async def ingest_holdings_csv(
    symbol: str,
    body: ETFHoldingsCSVIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    etf = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    rows = parse_holdings_csv(body.raw_csv)
    await ingest_holdings_snapshot(
        db,
        etf_instrument=etf,
        rows=rows,
        composition_date=body.composition_date,
        as_of_date=body.as_of_date,
        known_at=body.known_at,
        published_at=body.published_at,
        provenance=body.provenance,
        source_provider=body.source_provider,
        source_url=body.source_url,
        source_identifier=body.source_identifier,
        source_quality=body.source_quality,
        completeness_status=body.completeness_status,
        parser_version=body.parser_version,
        raw_payload_text=body.raw_csv,
        legal_metadata=body.legal_metadata,
        notes=body.notes,
    )
    loaded = await get_latest_snapshot(db, etf.id)
    if loaded is None:
        raise HTTPException(500, "Holdings were ingested but could not be reloaded")
    return loaded


@router.post("/{symbol}/ingest-sec-nport", response_model=ETFHoldingsSnapshotOut)
async def ingest_sec_nport_holdings(
    symbol: str,
    body: ETFHoldingsSECIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    parsed_report_date, rows = parse_sec_nport_xml(body.raw_xml)
    composition_date = body.composition_date or parsed_report_date
    if composition_date is None:
        raise HTTPException(
            400,
            "SEC filing XML did not expose a report date; provide composition_date explicitly.",
        )
    if not rows:
        raise HTTPException(400, "SEC filing XML did not contain parseable holdings rows.")

    etf = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    await ingest_holdings_snapshot(
        db,
        etf_instrument=etf,
        rows=rows,
        composition_date=composition_date,
        as_of_date=body.as_of_date or composition_date,
        known_at=body.known_at or body.published_at,
        published_at=body.published_at,
        provenance="sec_nport_reconstructed_holdings",
        source_provider=body.source_provider,
        source_url=body.filing_url,
        source_identifier=body.accession_number,
        source_quality="filing_reconstructed_holdings",
        completeness_status=body.completeness_status,
        parser_version=body.parser_version,
        raw_payload_text=body.raw_xml,
        legal_metadata={
            **(body.legal_metadata or {}),
            "source_access": "sec_filing",
            "accession_number": body.accession_number,
        },
        notes=body.notes or "Reconstructed from SEC N-PORT/N-PORT-P XML.",
    )
    loaded = await get_latest_snapshot(db, etf.id)
    if loaded is None:
        raise HTTPException(500, "Holdings were ingested but could not be reloaded")
    return loaded


@router.post("/{symbol}/ingest-sec-legacy", response_model=ETFHoldingsSnapshotOut)
async def ingest_sec_legacy_holdings(
    symbol: str,
    body: ETFHoldingsSECLegacyIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    parsed_report_date, rows = parse_sec_legacy_holdings_xml(body.raw_xml)
    composition_date = body.composition_date or parsed_report_date
    if composition_date is None:
        raise HTTPException(
            400,
            "Legacy SEC filing XML did not expose a report date; provide composition_date explicitly.",
        )
    if not rows:
        raise HTTPException(400, "Legacy SEC filing XML did not contain parseable holdings rows.")

    etf = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    await ingest_holdings_snapshot(
        db,
        etf_instrument=etf,
        rows=rows,
        composition_date=composition_date,
        as_of_date=body.as_of_date or composition_date,
        known_at=body.known_at or body.published_at,
        published_at=body.published_at,
        provenance="sec_legacy_reconstructed_holdings",
        source_provider=body.source_provider,
        source_url=body.filing_url,
        source_identifier=body.accession_number,
        source_quality="filing_reconstructed_holdings",
        completeness_status=body.completeness_status,
        parser_version=body.parser_version,
        raw_payload_text=body.raw_xml,
        legal_metadata={
            **(body.legal_metadata or {}),
            "source_access": "sec_filing",
            "source_format": "legacy_xml_table",
            "accession_number": body.accession_number,
        },
        notes=body.notes or "Reconstructed from legacy SEC N-Q/N-CSR-style XML.",
    )
    loaded = await get_latest_snapshot(db, etf.id)
    if loaded is None:
        raise HTTPException(500, "Holdings were ingested but could not be reloaded")
    return loaded


@router.post("/{symbol}/backfill-sec-nport", response_model=ETFHoldingsSECBackfillSummary)
async def backfill_sec_nport_holdings_for_etf(
    symbol: str,
    body: ETFHoldingsSECBackfillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    etf = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    profile = await get_etf_profile_for_instrument(db, etf.id)
    if profile is None:
        profile = await ensure_etf_profile(db, etf)
    summary = await backfill_sec_nport_holdings(
        db,
        profile=profile,
        start_date=body.start_date,
        end_date=body.end_date,
        max_filings=body.max_filings,
        requested_by_user_id=current_user.id,
    )
    await db.commit()
    return summary


@router.post("/{symbol}/backfill-sec-legacy", response_model=ETFHoldingsSECBackfillSummary)
async def backfill_sec_legacy_holdings_for_etf(
    symbol: str,
    body: ETFHoldingsSECBackfillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    etf = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    profile = await get_etf_profile_for_instrument(db, etf.id)
    if profile is None:
        profile = await ensure_etf_profile(db, etf)
    summary = await backfill_sec_legacy_holdings(
        db,
        profile=profile,
        start_date=body.start_date,
        end_date=body.end_date,
        max_filings=body.max_filings,
        requested_by_user_id=current_user.id,
    )
    await db.commit()
    return summary


@router.get("/{symbol}/backfills", response_model=list[ETFHoldingsBackfillJobOut])
async def list_etf_backfill_jobs(
    symbol: str,
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    etf = await ensure_lightweight_etf_instrument(db, symbol=symbol)
    profile = await get_etf_profile_for_instrument(db, etf.id)
    if profile is None:
        return []
    return await list_sec_nport_backfill_jobs(db, profile=profile, limit=limit)


@router.get("/backfill-jobs/{job_id}", response_model=ETFHoldingsBackfillJobOut)
async def get_etf_backfill_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    job = await get_sec_nport_backfill_job(db, job_id=job_id)
    if job is None:
        raise HTTPException(404, "ETF holdings backfill job not found")
    return job
