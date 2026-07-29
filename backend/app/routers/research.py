"""Study Lab run lifecycle; only the isolated runner executes source."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.research import CodeAsset, CodeVersion, ResearchRun
from app.models.user import User
from app.schemas.code import ResearchRunCreate, ResearchRunOut
from app.services.research_jobs import (
    cancel_research_run,
    collect_research_result,
    enqueue_research_run,
)

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/runs", response_model=ResearchRunOut, status_code=status.HTTP_202_ACCEPTED)
async def create_run(body: ResearchRunCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    version = (
        await db.execute(
            select(CodeVersion)
            .join(CodeAsset)
            .where(CodeVersion.id == body.code_version_id, CodeAsset.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Code version not found")
    run = ResearchRun(user_id=current_user.id, code_version_id=version.id, run_config=body.run_config, dataset_manifest=body.dataset_manifest)
    run.code_version = version
    db.add(run)
    await db.flush()
    enqueue_research_run(run)
    return run


@router.get("/runs/{run_id}", response_model=ResearchRunOut)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
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


@router.post("/runs/{run_id}/cancel", response_model=ResearchRunOut)
async def cancel_run(run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
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
        raise HTTPException(status_code=409, detail={"code": "research_run_terminal", "status": run.status})
    cancel_research_run(run)
    await db.flush()
    return run
