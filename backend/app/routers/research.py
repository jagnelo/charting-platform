"""Study Lab run lifecycle; only the isolated runner executes source."""

from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.research import CodeAsset, CodeVersion, ResearchRun
from app.models.user import User
from app.schemas.code import ResearchBatchResultOut, ResearchRunCreate, ResearchRunOut
from app.services.research_jobs import (
    cancel_research_run,
    collect_research_result,
    enqueue_research_run,
    read_research_progress,
)

router = APIRouter(prefix="/research", tags=["research"])

# Interactive workstation lists may contain 10,000 symbols. Batch execution is
# bounded independently from a single-instrument study: enough daily history for
# normal column/condition lookbacks, but never an unbounded 10,000 × full-history
# JSON payload handed to the isolated worker.
MAX_BATCH_SYMBOLS = 10_000
BATCH_HISTORY_LIMIT = 500
BATCH_QUERY_SIZE = 500
RESEARCH_ADJUSTMENTS = {"split_adjusted": True, "raw": False}


def _parse_dataset_bound(value: object, *, end: bool) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_dataset_date", "value": text},
            ) from exc
        parsed = datetime.combine(parsed_date, time.max if end else time.min)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _dataset_options(run_config: dict, manifest: dict) -> dict:
    timeframe_value = str(
        run_config.get("timeframe") or manifest.get("timeframe") or Timeframe.D1.value
    ).upper()
    try:
        timeframe = Timeframe(timeframe_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_dataset_timeframe", "value": timeframe_value},
        ) from exc

    adjustment = str(
        run_config.get("adjustment") or manifest.get("adjustment") or "split_adjusted"
    ).lower()
    if adjustment not in RESEARCH_ADJUSTMENTS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_dataset_adjustment",
                "value": adjustment,
                "supported": sorted(RESEARCH_ADJUSTMENTS),
            },
        )

    session = str(run_config.get("session") or manifest.get("session") or "regular").lower()
    if session not in {"regular", "all"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "unsupported_dataset_session", "value": session},
        )
    start = _parse_dataset_bound(run_config.get("start_date") or manifest.get("start_date"), end=False)
    end = _parse_dataset_bound(run_config.get("end_date") or manifest.get("end_date"), end=True)
    if start and end and start > end:
        raise HTTPException(
            status_code=422,
            detail={"code": "dataset_date_range_reversed", "start_date": start.date().isoformat(), "end_date": end.date().isoformat()},
        )
    benchmark = run_config.get("benchmark") or manifest.get("benchmark")
    if benchmark is not None and (not isinstance(benchmark, str) or not benchmark.strip()):
        raise HTTPException(status_code=422, detail={"code": "invalid_dataset_benchmark"})
    return {
        "timeframe": timeframe,
        "adjustment": adjustment,
        "is_adjusted": RESEARCH_ADJUSTMENTS[adjustment],
        "session": session,
        "start": start,
        "end": end,
        "benchmark": benchmark.strip().upper() if isinstance(benchmark, str) else None,
    }


def _dataset_manifest_fields(manifest: dict, options: dict) -> dict:
    fields = {
        **manifest,
        "source": "canonical_database",
        "timeframe": options["timeframe"].value,
        "adjustment": options["adjustment"],
        "session": options["session"],
    }
    if options["benchmark"]:
        fields["benchmark"] = options["benchmark"]
    if options["start"]:
        fields["start_date"] = options["start"].date().isoformat()
    if options["end"]:
        fields["end_date"] = options["end"].date().isoformat()
    return fields


async def _load_instrument_bars(
    db: AsyncSession, instrument: Instrument, options: dict, *, limit: int
) -> list[OHLCVBar]:
    conditions = [
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == options["timeframe"],
        OHLCVBar.is_adjusted.is_(options["is_adjusted"]),
    ]
    if options["session"] == "regular":
        conditions.append(OHLCVBar.session == "regular")
    if options["start"]:
        conditions.append(OHLCVBar.ts >= options["start"])
    if options["end"]:
        conditions.append(OHLCVBar.ts <= options["end"])
    bars = (
        (
            await db.execute(
                select(OHLCVBar).where(*conditions).order_by(OHLCVBar.ts.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    bars.reverse()
    return bars


async def _materialize_instrument_dataset(
    db: AsyncSession, instrument: Instrument, manifest: dict, options: dict
) -> dict:
    bars = await _load_instrument_bars(db, instrument, options, limit=5000)
    return {
        **_dataset_manifest_fields(manifest, options),
        "symbol": instrument.symbol,
        "instrument_id": instrument.id,
        "timestamps": [bar.ts.isoformat() for bar in bars],
        "closes": [float(bar.close) for bar in bars],
    }


async def _materialize_benchmark_dataset(
    db: AsyncSession, options: dict
) -> dict | None:
    benchmark = options["benchmark"]
    if not benchmark:
        return None
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == benchmark))
    ).scalar_one_or_none()
    if instrument is None:
        return {
            "status": "unavailable",
            "symbol": benchmark,
            "reason": "benchmark_instrument_not_found",
        }
    bars = await _load_instrument_bars(db, instrument, options, limit=5000)
    if not bars:
        return {
            "status": "unavailable",
            "symbol": benchmark,
            "instrument_id": instrument.id,
            "reason": "benchmark_history_unavailable",
        }
    return {
        "status": "ready",
        "source": "canonical_database",
        "symbol": instrument.symbol,
        "instrument_id": instrument.id,
        "timeframe": options["timeframe"].value,
        "adjustment": options["adjustment"],
        "session": options["session"],
        "timestamps": [bar.ts.isoformat() for bar in bars],
        "closes": [float(bar.close) for bar in bars],
    }


async def _materialize_declared_dataset(db: AsyncSession, manifest: dict, run_config: dict) -> dict:
    """Materialize only an explicitly declared canonical local dataset for the runner."""
    options = _dataset_options(run_config, manifest)
    benchmark_dataset = await _materialize_benchmark_dataset(db, options)
    symbols = run_config.get("symbols")
    if isinstance(symbols, list):
        requested = list(dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip()))
        if not requested:
            result = {
                **_dataset_manifest_fields(manifest, options),
                "datasets": [],
                "exclusions": [],
            }
            if benchmark_dataset is not None:
                result["benchmark_coverage"] = benchmark_dataset
            return result
        if len(requested) > MAX_BATCH_SYMBOLS:
            raise HTTPException(
                status_code=422,
                detail={"code": "batch_universe_too_large", "maximum": MAX_BATCH_SYMBOLS},
            )
        instruments: list[Instrument] = []
        for offset in range(0, len(requested), BATCH_QUERY_SIZE):
            instruments.extend(
                (
                    await db.execute(
                        select(Instrument).where(
                            Instrument.symbol.in_(requested[offset : offset + BATCH_QUERY_SIZE])
                        )
                    )
                ).scalars().all()
            )
        by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
        bars_by_instrument: dict[int, list[OHLCVBar]] = {}
        instrument_ids = [instrument.id for instrument in instruments]
        for offset in range(0, len(instrument_ids), BATCH_QUERY_SIZE):
            ids = instrument_ids[offset : offset + BATCH_QUERY_SIZE]
            bar_conditions = [
                OHLCVBar.instrument_id.in_(ids),
                OHLCVBar.timeframe == options["timeframe"],
                OHLCVBar.is_adjusted.is_(options["is_adjusted"]),
            ]
            if options["session"] == "regular":
                bar_conditions.append(OHLCVBar.session == "regular")
            if options["start"]:
                bar_conditions.append(OHLCVBar.ts >= options["start"])
            if options["end"]:
                bar_conditions.append(OHLCVBar.ts <= options["end"])
            ranked_bars = (
                select(
                    OHLCVBar.id.label("bar_id"),
                    func.row_number()
                    .over(
                        partition_by=OHLCVBar.instrument_id,
                        order_by=OHLCVBar.ts.desc(),
                    )
                    .label("bar_rank"),
                )
                .where(*bar_conditions)
                .subquery()
            )
            bars = (
                await db.execute(
                    select(OHLCVBar)
                    .join(ranked_bars, OHLCVBar.id == ranked_bars.c.bar_id)
                    .where(ranked_bars.c.bar_rank <= BATCH_HISTORY_LIMIT)
                    .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
                )
            ).scalars().all()
            for bar in bars:
                bars_by_instrument.setdefault(bar.instrument_id, []).append(bar)
        datasets = []
        exclusions = []
        for symbol in requested:
            instrument = by_symbol.get(symbol)
            if instrument is None:
                exclusions.append({"symbol": symbol, "code": "declared_instrument_not_found"})
                continue
            bars = bars_by_instrument.get(instrument.id, [])
            if not bars:
                exclusions.append({"symbol": symbol, "instrument_id": instrument.id, "code": "declared_history_unavailable"})
                continue
            datasets.append(
                {
                    "source": "canonical_database",
                    "symbol": instrument.symbol,
                    "instrument_id": instrument.id,
                    "timeframe": options["timeframe"].value,
                    "adjustment": options["adjustment"],
                    "session": options["session"],
                    "timestamps": [bar.ts.isoformat() for bar in bars],
                    "closes": [float(bar.close) for bar in bars],
                    **(
                        {"benchmark_dataset": benchmark_dataset}
                        if benchmark_dataset and benchmark_dataset.get("status") == "ready"
                        else {}
                    ),
                }
            )
        result = {
            **_dataset_manifest_fields(manifest, options),
            "datasets": datasets,
            "requested_symbols": requested,
            "batch_history_limit": BATCH_HISTORY_LIMIT,
            "exclusions": exclusions,
        }
        if benchmark_dataset is not None:
            result["benchmark_coverage"] = benchmark_dataset
        return result
    symbol = str(run_config.get("symbol") or manifest.get("symbol") or "").upper()
    if not symbol:
        return dict(manifest)
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            status_code=422, detail={"code": "declared_instrument_not_found", "symbol": symbol}
        )
    result = await _materialize_instrument_dataset(db, instrument, manifest, options)
    if benchmark_dataset is not None:
        result["benchmark_coverage"] = benchmark_dataset
        if benchmark_dataset.get("status") == "ready":
            result["benchmark_dataset"] = benchmark_dataset
    return result


@router.post("/runs", response_model=ResearchRunOut, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: ResearchRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version = (
        await db.execute(
            select(CodeVersion)
            .join(CodeAsset)
            .where(CodeVersion.id == body.code_version_id, CodeAsset.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Code version not found")
    dataset_manifest = await _materialize_declared_dataset(
        db, body.dataset_manifest, body.run_config
    )
    run = ResearchRun(
        user_id=current_user.id,
        code_version_id=version.id,
        run_config=body.run_config,
        dataset_manifest=dataset_manifest,
    )
    run.code_version = version
    db.add(run)
    await db.flush()
    enqueue_research_run(run)
    return run


@router.get("/runs", response_model=list[ResearchRunOut])
async def list_runs(
    limit: int = 25,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the current user's newest persisted research runs for result panes."""
    bounded_limit = max(1, min(limit, 100))
    runs = (
        (
            await db.execute(
                select(ResearchRun)
                .options(selectinload(ResearchRun.artifacts))
                .where(ResearchRun.user_id == current_user.id)
                .order_by(desc(ResearchRun.created_at), desc(ResearchRun.id))
                .limit(bounded_limit)
            )
        )
        .scalars()
        .all()
    )
    for run in runs:
        collect_research_result(run)
        run.progress = read_research_progress(run.id)
    await db.flush()
    return runs


@router.get("/runs/{run_id}", response_model=ResearchRunOut)
async def get_run(
    run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    run = (
        await db.execute(
            select(ResearchRun)
            .options(selectinload(ResearchRun.artifacts))
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    collect_research_result(run)
    run.progress = read_research_progress(run.id)
    await db.flush()
    return run


@router.get("/runs/{run_id}/batch-results", response_model=ResearchBatchResultOut)
async def get_batch_results(
    run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    run = (
        await db.execute(
            select(ResearchRun)
            .options(selectinload(ResearchRun.artifacts))
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    collect_research_result(run)
    version = (await db.execute(select(CodeVersion).where(CodeVersion.id == run.code_version_id))).scalar_one()
    artifact = next((item for item in run.artifacts if item.artifact_type == "batch" and item.name == "batch_cells"), None)
    payload = artifact.payload.get("value", {}) if artifact else {}
    cells = payload.get("cells", []) if isinstance(payload, dict) else []
    await db.flush()
    return ResearchBatchResultOut(
        run_id=run.id,
        code_version_id=run.code_version_id,
        output_contract=version.output_contract,
        status=run.status,
        cells=cells if isinstance(cells, list) else [],
        dataset_manifest=run.dataset_manifest,
        progress=read_research_progress(run.id),
    )


@router.post(
    "/runs/{run_id}/rerun", response_model=ResearchRunOut, status_code=status.HTTP_202_ACCEPTED
)
async def rerun(
    run_id: int,
    snapshot: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a new immutable run using an exact snapshot or newly materialized local data."""
    source = (
        await db.execute(
            select(ResearchRun).where(
                ResearchRun.id == run_id, ResearchRun.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    manifest = (
        dict(source.dataset_manifest)
        if snapshot
        else await _materialize_declared_dataset(db, {}, dict(source.run_config))
    )
    run = ResearchRun(
        user_id=current_user.id,
        code_version_id=source.code_version_id,
        run_config=dict(source.run_config),
        dataset_manifest=manifest,
    )
    db.add(run)
    await db.flush()
    enqueue_research_run(run)
    return run


@router.post("/runs/{run_id}/cancel", response_model=ResearchRunOut)
async def cancel_run(
    run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    run = (
        await db.execute(
            select(ResearchRun)
            .options(selectinload(ResearchRun.artifacts))
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if run.status in {"completed", "failed", "canceled"}:
        raise HTTPException(
            status_code=409, detail={"code": "research_run_terminal", "status": run.status}
        )
    cancel_research_run(run)
    await db.flush()
    return run
