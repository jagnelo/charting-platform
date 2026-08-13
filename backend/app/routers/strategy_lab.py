from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.research import CodeAsset, CodeVersion
from app.models.strategy import StrategyDefinition, StrategyRun, StrategyRunBatch, StrategyVersion
from app.models.user import User
from app.schemas.strategy import (
    StrategyCoveragePreviewOut,
    StrategyCoveragePreviewRequest,
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
from app.services.strategy_lab import (
    _refresh_python_signal_research,
    execute_strategy_run,
    preview_strategy_coverage,
)

router = APIRouter(prefix="/strategy-lab", tags=["strategy-lab"])


def _definition_query_for_user(user_id: int):
    return (
        select(StrategyDefinition)
        .where(StrategyDefinition.user_id == user_id)
        .options(
            selectinload(StrategyDefinition.versions),
            selectinload(StrategyDefinition.run_batches),
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


@router.post("/signals/from-code/{code_version_id}", response_model=StrategyDefinitionDetailOut, status_code=201)
async def promote_code_signal(
    code_version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist a unified-Python signal as a Strategy Lab definition.

    The strategy snapshot stores the immutable code-version id rather than copying
    source text. This keeps Study Lab promotion user-scoped and reproducible while
    leaving execution to the Strategy Lab engine's existing capability contract.
    """
    version = (
        await db.execute(
            select(CodeVersion)
            .join(CodeAsset)
            .where(
                CodeVersion.id == code_version_id,
                CodeAsset.user_id == current_user.id,
                CodeAsset.kind.in_(["signal", "study"]),
                CodeAsset.is_archived.is_(False),
            )
            .options(selectinload(CodeVersion.asset))
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Signal code version not found")
    if version.output_contract not in {"boolean", "events"}:
        raise HTTPException(status_code=422, detail="Signal code must produce Boolean or event output")

    base_name = f"{version.asset.name} Strategy Signal"
    name = base_name
    suffix = 2
    while (
        await db.execute(
            select(func.count())
            .select_from(StrategyDefinition)
            .where(
                StrategyDefinition.user_id == current_user.id,
                func.lower(StrategyDefinition.name) == name.lower(),
            )
        )
    ).scalar_one():
        name = f"{base_name} ({suffix})"
        suffix += 1

    strategy = StrategyDefinition(
        user_id=current_user.id,
        name=name,
        description="Unified-Python signal promoted from Study Lab.",
        source_type="custom",
        definition_type="python",
        is_active=True,
        tags=["study-lab", "python-signal"],
        metadata_json={
            "origin": "study_lab_promotion",
            "code_asset_id": version.code_asset_id,
            "code_version_id": version.id,
            "output_contract": version.output_contract,
        },
    )
    strategy.versions.append(
        StrategyVersion(
            version_number=1,
            definition_snapshot={
                "kind": "python_signal",
                "code_version_id": version.id,
                "output_contract": version.output_contract,
            },
            parameter_schema=version.parameter_schema or {},
            default_parameters=version.default_parameters or {},
            notes="Immutable unified-Python signal reference promoted from Study Lab.",
            is_current=True,
        )
    )
    db.add(strategy)
    await db.commit()
    return await _load_definition_or_404(db, strategy_id=strategy.id, user_id=current_user.id)


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
    runs = result.scalars().all()
    for run in runs:
        await _refresh_python_signal_research(db, run)
    await db.flush()
    return runs


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
    await _refresh_python_signal_research(db, run)
    await db.flush()
    return run


@router.post("/coverage-preview", response_model=StrategyCoveragePreviewOut)
async def get_coverage_preview(
    body: StrategyCoveragePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    return await preview_strategy_coverage(
        db,
        source_type=body.source_type.value,
        timeframe_value=body.timeframe,
        date_from=body.date_from,
        date_to=body.date_to,
        universe_config=body.universe_config,
        benchmark_config=body.benchmark_config,
    )


def _expand_parameter_grid(raw_grid: dict | None) -> tuple[list[dict], list[dict]]:
    if not isinstance(raw_grid, dict):
        return [], []

    dimensions: list[dict] = []
    for raw_dimension in raw_grid.get("parameters") or raw_grid.get("dimensions") or []:
        if not isinstance(raw_dimension, dict):
            continue
        key = str(raw_dimension.get("key") or "").strip()
        if not key:
            continue
        values = raw_dimension.get("values")
        if not isinstance(values, list):
            values = []
        normalized_values = [
            value for value in values
            if value is not None and value != "" and isinstance(value, int | float | str | bool)
        ]
        if not normalized_values:
            continue
        dimensions.append({
            "key": key,
            "label": str(raw_dimension.get("label") or key),
            "values": normalized_values[:50],
        })

    if not dimensions:
        return [], []

    combinations: list[dict] = [{}]
    for dimension in dimensions:
        combinations = [
            {**existing, str(dimension["key"]): value}
            for existing in combinations
            for value in dimension["values"]
        ]
        if len(combinations) > 250:
            raise HTTPException(
                status_code=422,
                detail="Parameter grid is too large. Narrow the ranges to 250 combinations or fewer.",
            )

    return dimensions, combinations


def _parameter_batch_label(dimensions: list[dict]) -> str:
    labels = [str(dimension.get("label") or dimension.get("key")) for dimension in dimensions]
    if not labels:
        return "Single run"
    if len(labels) <= 3:
        return " × ".join(labels)
    return f"{' × '.join(labels[:3])} + {len(labels) - 3} more"


def _batch_status_for_runs(runs: list[StrategyRun]) -> str:
    if any(run.status == "failed" for run in runs):
        return "failed"
    if all(run.status == "completed" for run in runs):
        return "completed"
    if any(run.status == "running" for run in runs):
        return "running"
    return "queued"


def _run_metric(run: StrategyRun, key: str) -> float | None:
    value = (run.result_summary or {}).get("performance", {}).get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _run_summary_ref(run: StrategyRun, metric: str) -> dict | None:
    value = _run_metric(run, metric)
    if value is None:
        return None
    return {
        "run_id": run.id,
        "value": value,
        "parameter_diff": run.parameter_diff or run.parameter_values or {},
    }


def _best_run_by_metric(runs: list[StrategyRun], metric: str, *, reverse: bool = True) -> dict | None:
    ranked = [run for run in runs if _run_metric(run, metric) is not None]
    if not ranked:
        return None
    selected = sorted(ranked, key=lambda run: _run_metric(run, metric) or 0, reverse=reverse)[0]
    return _run_summary_ref(selected, metric)


def _summarize_run_batch(
    runs: list[StrategyRun],
    *,
    parameter_dimensions: list[dict],
) -> dict:
    completed = [run for run in runs if run.status == "completed"]
    failed = [run for run in runs if run.status == "failed"]
    return {
        "run_count": len(runs),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "parameter_count": len(parameter_dimensions),
        "best_marked_return": _best_run_by_metric(completed, "net_return_pct", reverse=True),
        "best_realized_return": _best_run_by_metric(completed, "realized_net_return_pct", reverse=True),
        "worst_marked_return": _best_run_by_metric(completed, "net_return_pct", reverse=False),
        "least_drawdown": _best_run_by_metric(completed, "max_drawdown_pct", reverse=False),
        "best_profit_factor": _best_run_by_metric(completed, "profit_factor", reverse=True),
    }


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

    parameter_dimensions, parameter_combinations = _expand_parameter_grid(body.parameter_grid)
    if len(parameter_combinations) > 1:
        batch = StrategyRunBatch(
            strategy_id=version.strategy_id,
            strategy_version_id=version.id,
            requested_by_user_id=current_user.id,
            label=_parameter_batch_label(parameter_dimensions),
            test_mode=body.test_mode.value,
            status="running",
            parameter_dimensions=parameter_dimensions,
            parameter_grid=parameter_combinations,
            summary={},
        )
        db.add(batch)
        await db.flush()

        runs: list[StrategyRun] = []
        for combination in parameter_combinations:
            run = StrategyRun(
                strategy_id=version.strategy_id,
                strategy_version_id=version.id,
                requested_by_user_id=current_user.id,
                run_batch_id=batch.id,
                engine_type=version.engine_type,
                test_mode=body.test_mode.value,
                status="queued",
                timeframe=body.timeframe,
                date_from=body.date_from,
                date_to=body.date_to,
                parameter_values={**body.parameter_values, **combination},
                parameter_diff=combination,
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
            runs.append(run)

        batch.status = _batch_status_for_runs(runs)
        batch.summary = _summarize_run_batch(runs, parameter_dimensions=parameter_dimensions)
        await db.commit()
        await db.refresh(runs[0])
        return StrategyRunSubmitOut.model_validate(runs[0])

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
        parameter_diff=body.parameter_values,
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
    if (run.result_summary or {}).get("result_kind") == "python_signal_research":
        await _refresh_python_signal_research(db, run)
        await db.commit()
        await db.refresh(run)
        return StrategyRunSubmitOut.model_validate(run)
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
