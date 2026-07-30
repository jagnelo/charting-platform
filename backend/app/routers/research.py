"""Study Lab run lifecycle; only the isolated runner executes source."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
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
)

router = APIRouter(prefix="/research", tags=["research"])


async def _materialize_instrument_dataset(db: AsyncSession, instrument: Instrument, manifest: dict) -> dict:
    bars = (
        (
            await db.execute(
                select(OHLCVBar)
                .where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(True),
                )
                .order_by(OHLCVBar.ts.desc())
                .limit(5000)
            )
        )
        .scalars()
        .all()
    )
    bars.reverse()
    return {
        **manifest,
        "source": "canonical_database",
        "symbol": instrument.symbol,
        "instrument_id": instrument.id,
        "timeframe": Timeframe.D1.value,
        "adjustment": "split_adjusted",
        "timestamps": [bar.ts.isoformat() for bar in bars],
        "closes": [float(bar.close) for bar in bars],
    }


async def _materialize_declared_dataset(db: AsyncSession, manifest: dict, run_config: dict) -> dict:
    """Materialize only an explicitly declared canonical local dataset for the runner."""
    symbols = run_config.get("symbols")
    if isinstance(symbols, list):
        requested = list(dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip()))
        if not requested:
            return {**manifest, "source": "canonical_database", "datasets": [], "exclusions": []}
        if len(requested) > 1_000:
            raise HTTPException(status_code=422, detail={"code": "batch_universe_too_large", "maximum": 1000})
        instruments = (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(requested)))
        ).scalars().all()
        by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
        datasets = [await _materialize_instrument_dataset(db, by_symbol[symbol], {}) for symbol in requested if symbol in by_symbol]
        return {
            **manifest,
            "source": "canonical_database",
            "datasets": datasets,
            "requested_symbols": requested,
            "exclusions": [{"symbol": symbol, "code": "declared_instrument_not_found"} for symbol in requested if symbol not in by_symbol],
        }
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
    return await _materialize_instrument_dataset(db, instrument, manifest)


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
