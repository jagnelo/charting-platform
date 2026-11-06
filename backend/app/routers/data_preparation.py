"""Authenticated API for durable selected-data preparation requests."""

from __future__ import annotations

import logging
from uuid import uuid4

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.data_preparation import DataEnsureRequest, DataEnsureResponse
from app.services.data_preparation import (
    create_data_preparation_request,
    get_data_preparation_response,
    load_owner_request,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["data-preparation"])


async def _wake_refresh_worker() -> None:
    """Wake the registered queue consumer; durable DB rows survive Redis failure."""

    redis = None
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job(
            "task_process_refresh_jobs",
            _job_id=f"data-preparation-wakeup:{uuid4().hex}",
            _expires=600,
        )
    except Exception as exc:  # the committed database queue remains authoritative
        logger.warning("Could not prompt data-preparation worker: %s", type(exc).__name__)
    finally:
        if redis is not None:
            await redis.aclose()


@router.post(
    "/ensure",
    response_model=DataEnsureResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ensure_data(
    request: DataEnsureRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataEnsureResponse:
    parent = await create_data_preparation_request(
        db,
        owner_user_id=current_user.id,
        request=request,
        idempotency_key=idempotency_key,
    )
    await db.commit()
    response = await get_data_preparation_response(
        db, parent=parent, owner_user_id=current_user.id
    )
    if response.status in {"queued", "partial"}:
        await _wake_refresh_worker()
    return response


@router.get("/requests/{request_id}", response_model=DataEnsureResponse)
async def get_data_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataEnsureResponse:
    parent = await load_owner_request(
        db, request_id=request_id, owner_user_id=current_user.id
    )
    return await get_data_preparation_response(
        db, parent=parent, owner_user_id=current_user.id
    )

