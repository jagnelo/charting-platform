"""Authenticated API for durable selected-data preparation requests."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.data_preparation import DataEnsureRequest, DataEnsureResponse
from app.services.arq_pool import get_shared_arq_pool
from app.services.data_preparation import (
    create_data_preparation_request,
    get_data_preparation_response,
    load_owner_request,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["data-preparation"])


# The durable database queue is authoritative. The Redis wake is a best-effort
# hint, so it must never hold a request, a transaction or a lock.
_WAKE_TIMEOUT_SECONDS = 1.0
_wake_tasks: set[asyncio.Task] = set()


async def _enqueue_worker_wake() -> None:
    pool = await get_shared_arq_pool()
    await pool.enqueue_job(
        "task_process_refresh_jobs",
        _job_id=f"data-preparation-wakeup:{uuid4().hex}",
        _expires=600,
    )


async def _wake_refresh_worker() -> None:
    """Enqueue one worker wake within a fixed bound; failures are logged, never raised."""

    try:
        await asyncio.wait_for(_enqueue_worker_wake(), timeout=_WAKE_TIMEOUT_SECONDS)
    except Exception as exc:  # the committed database queue remains authoritative
        logger.warning("Could not prompt data-preparation worker: %s", type(exc).__name__)


def _schedule_worker_wake() -> None:
    """Start the wake without delaying the HTTP response."""

    task = asyncio.create_task(_wake_refresh_worker())
    _wake_tasks.add(task)
    task.add_done_callback(_wake_tasks.discard)


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
    response = await get_data_preparation_response(db, parent=parent, owner_user_id=current_user.id)
    # Close the read transaction before any Redis I/O, so no lock or
    # transaction is held while the worker is woken.
    await db.commit()
    if response.status in {"queued", "partial"}:
        _schedule_worker_wake()
    return response


@router.get("/requests/{request_id}", response_model=DataEnsureResponse)
async def get_data_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataEnsureResponse:
    parent = await load_owner_request(db, request_id=request_id, owner_user_id=current_user.id)
    return await get_data_preparation_response(db, parent=parent, owner_user_id=current_user.id)
