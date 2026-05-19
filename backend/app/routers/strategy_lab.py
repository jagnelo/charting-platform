from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.strategy import StrategyDefinition, StrategyRun, StrategyVersion
from app.models.user import User
from app.schemas.strategy import (
    StrategyDefinitionCreate,
    StrategyDefinitionDetailOut,
    StrategyDefinitionSummaryOut,
    StrategyDefinitionUpdate,
    StrategyRunCreate,
    StrategyRunOut,
    StrategyRunSubmitOut,
    StrategyVersionCreate,
    StrategyVersionOut,
    StrategyVersionUpdate,
)
from app.services.strategy_lab import execute_strategy_run

router = APIRouter(prefix="/strategy-lab", tags=["strategy-lab"])


def _definition_query_for_user(user_id: int):
    return (
        select(StrategyDefinition)
        .where(StrategyDefinition.user_id == user_id)
        .options(
            selectinload(StrategyDefinition.versions),
            selectinload(StrategyDefinition.runs),
        )
        .order_by(StrategyDefinition.updated_at.desc(), StrategyDefinition.name)
    )


async def _load_definition_or_404(
    db: AsyncSession,
    *,
    strategy_id: int,
    user_id: int,
) -> StrategyDefinition:
    strategy = (
        await db.execute(
            _definition_query_for_user(user_id).where(StrategyDefinition.id == strategy_id)
        )
    ).scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy definition not found")
    return strategy


@router.get("/definitions", response_model=list[StrategyDefinitionSummaryOut])
async def list_definitions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(_definition_query_for_user(current_user.id))
    return result.scalars().all()


@router.post("/definitions", response_model=StrategyDefinitionDetailOut, status_code=201)
async def create_definition(
    body: StrategyDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    duplicate_count = (
        await db.execute(
            select(func.count())
            .select_from(StrategyDefinition)
            .where(
                StrategyDefinition.user_id == current_user.id,
                func.lower(StrategyDefinition.name) == body.name.lower(),
            )
        )
    ).scalar_one()
    if duplicate_count:
        raise HTTPException(
            status_code=409, detail=f"A strategy named '{body.name}' already exists"
        )

    strategy = StrategyDefinition(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        source_type=body.source_type.value,
        definition_type=body.definition_type.value,
        is_active=body.is_active,
        tags=body.tags,
        metadata_json=body.metadata,
    )
    version = StrategyVersion(
        version_number=1,
        definition_snapshot=body.initial_version.definition_snapshot,
        parameter_schema=body.initial_version.parameter_schema,
        default_parameters=body.initial_version.default_parameters,
        universe_config=body.initial_version.universe_config,
        benchmark_config=body.initial_version.benchmark_config,
        execution_model=body.initial_version.execution_model,
        notes=body.initial_version.notes,
        is_current=True,
    )
    strategy.versions.append(version)
    db.add(strategy)
    await db.commit()
    return await _load_definition_or_404(db, strategy_id=strategy.id, user_id=current_user.id)


@router.get("/definitions/{strategy_id}", response_model=StrategyDefinitionDetailOut)
async def get_definition(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _load_definition_or_404(db, strategy_id=strategy_id, user_id=current_user.id)


@router.patch("/definitions/{strategy_id}", response_model=StrategyDefinitionDetailOut)
async def update_definition(
    strategy_id: int,
    body: StrategyDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    strategy = await _load_definition_or_404(db, strategy_id=strategy_id, user_id=current_user.id)
    payload = body.model_dump(exclude_unset=True)
    if "source_type" in payload:
        payload["source_type"] = payload["source_type"].value
    if "definition_type" in payload:
        payload["definition_type"] = payload["definition_type"].value
    if "metadata" in payload:
        payload["metadata_json"] = payload.pop("metadata")
    for field, value in payload.items():
        setattr(strategy, field, value)
    await db.commit()
    return await _load_definition_or_404(db, strategy_id=strategy_id, user_id=current_user.id)


@router.delete("/definitions/{strategy_id}", status_code=204)
async def delete_definition(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    strategy = await _load_definition_or_404(db, strategy_id=strategy_id, user_id=current_user.id)
    await db.delete(strategy)
    await db.commit()


@router.post(
    "/definitions/{strategy_id}/versions", response_model=StrategyVersionOut, status_code=201
)
async def create_version(
    strategy_id: int,
    body: StrategyVersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    strategy = await _load_definition_or_404(db, strategy_id=strategy_id, user_id=current_user.id)
    next_version = max((version.version_number for version in strategy.versions), default=0) + 1
    for existing in strategy.versions:
        existing.is_current = False
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=next_version,
        definition_snapshot=body.definition_snapshot,
        parameter_schema=body.parameter_schema,
        default_parameters=body.default_parameters,
        universe_config=body.universe_config,
        benchmark_config=body.benchmark_config,
        execution_model=body.execution_model,
        notes=body.notes,
        is_current=True,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


@router.get("/definitions/{strategy_id}/versions", response_model=list[StrategyVersionOut])
async def list_versions(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    strategy = await _load_definition_or_404(db, strategy_id=strategy_id, user_id=current_user.id)
    return strategy.versions


@router.patch("/versions/{version_id}", response_model=StrategyVersionOut)
async def update_version(
    version_id: int,
    body: StrategyVersionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version_stmt = (
        select(StrategyVersion)
        .join(StrategyDefinition, StrategyDefinition.id == StrategyVersion.strategy_id)
        .where(StrategyDefinition.user_id == current_user.id, StrategyVersion.id == version_id)
    )
    version = (await db.execute(version_stmt)).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Strategy version not found")

    version.definition_snapshot = body.definition_snapshot
    version.parameter_schema = body.parameter_schema
    version.default_parameters = body.default_parameters
    version.universe_config = body.universe_config
    version.benchmark_config = body.benchmark_config
    version.execution_model = body.execution_model
    version.notes = body.notes

    await db.commit()
    await db.refresh(version)
    return version


@router.get("/runs", response_model=list[StrategyRunOut])
async def list_runs(
    strategy_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(StrategyRun)
        .join(StrategyDefinition, StrategyDefinition.id == StrategyRun.strategy_id)
        .where(StrategyDefinition.user_id == current_user.id)
        .order_by(StrategyRun.created_at.desc(), StrategyRun.id.desc())
        .limit(limit)
    )
    if strategy_id is not None:
        stmt = stmt.where(StrategyRun.strategy_id == strategy_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=StrategyRunOut)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(StrategyRun)
        .join(StrategyDefinition, StrategyDefinition.id == StrategyRun.strategy_id)
        .where(StrategyDefinition.user_id == current_user.id, StrategyRun.id == run_id)
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Strategy run not found")
    return run


@router.post("/versions/{version_id}/runs", response_model=StrategyRunSubmitOut, status_code=201)
async def submit_run(
    version_id: int,
    body: StrategyRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version_stmt = (
        select(StrategyVersion)
        .join(StrategyDefinition, StrategyDefinition.id == StrategyVersion.strategy_id)
        .where(StrategyDefinition.user_id == current_user.id, StrategyVersion.id == version_id)
        .options(selectinload(StrategyVersion.strategy))
    )
    version = (await db.execute(version_stmt)).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Strategy version not found")

    run = StrategyRun(
        strategy_id=version.strategy_id,
        strategy_version_id=version.id,
        requested_by_user_id=current_user.id,
        engine_type=version.engine_type,
        test_mode=body.test_mode.value,
        status="queued",
        timeframe=body.timeframe,
        date_from=body.date_from,
        date_to=body.date_to,
        parameter_values=body.parameter_values,
        universe_config=body.universe_config or {},
        benchmark_config=body.benchmark_config or {},
        execution_assumptions=body.execution_assumptions,
        result_summary={},
        artifact_manifest={},
        warning_log=[],
    )
    db.add(run)
    await db.flush()
    await execute_strategy_run(db, strategy=version.strategy, version=version, run=run)
    await db.commit()
    await db.refresh(run)
    return StrategyRunSubmitOut.model_validate(run)


@router.post("/runs/{run_id}/refresh", response_model=StrategyRunSubmitOut)
async def refresh_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run_stmt = (
        select(StrategyRun)
        .join(StrategyDefinition, StrategyDefinition.id == StrategyRun.strategy_id)
        .join(StrategyVersion, StrategyVersion.id == StrategyRun.strategy_version_id)
        .where(StrategyDefinition.user_id == current_user.id, StrategyRun.id == run_id)
        .options(
            selectinload(StrategyRun.strategy),
            selectinload(StrategyRun.strategy_version),
        )
    )
    run = (await db.execute(run_stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Strategy run not found")
    if run.test_mode != "paper_forward":
        raise HTTPException(status_code=409, detail="Only paper-forward runs can be refreshed")

    await execute_strategy_run(
        db,
        strategy=run.strategy,
        version=run.strategy_version,
        run=run,
    )
    await db.commit()
    await db.refresh(run)
    return StrategyRunSubmitOut.model_validate(run)
