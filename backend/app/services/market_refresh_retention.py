"""Bounded retention for finished data-preparation tracking parents.

``create_data_preparation_request`` persists one ``market_refresh_job`` row with
``status='tracking'`` per request (system maintenance requests mint ~100k a day).
Tracking parents never change status: their progress is recomputed from their
child jobs on read, so no row ever becomes "terminal" by itself and nothing
removed them. This module deletes a system-maintenance tracking parent once

* it has not been touched for the retention window, and
* every child job it references (``dependencies[].job_ids`` and
  ``background_job_ids``) is terminal or already gone.

Children are never deleted here. Request-key dedup lives on the children
(``prep-history:...`` / identity keys) and on the parent's own key; a deleted
parent's key is only reused when the same maintenance idempotency key is sent
again after the window, which simply creates a fresh parent. Everything that
reads ``parent_refs`` tolerates a missing parent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import MarketRefreshJob

logger = logging.getLogger(__name__)

TERMINAL_CHILD_STATUSES = frozenset({"completed", "failed", "expired", "cancelled"})
_SELECT_CHUNK = 1000


def _child_job_ids(payload: dict | None) -> set[int]:
    data = (payload or {}).get("data_preparation") or {}
    ids: set[int] = set()
    for dependency in data.get("dependencies") or []:
        for key in ("job_ids", "background_job_ids"):
            for value in dependency.get(key) or []:
                try:
                    ids.add(int(value))
                except (TypeError, ValueError):
                    continue
    return ids


async def _prune_batch(
    db: AsyncSession, *, cutoff: datetime, after_id: int, batch_size: int
) -> tuple[int, int, int | None]:
    """Delete one batch. Returns (scanned, deleted, last_scanned_id)."""

    from app.services.data_preparation import _SYSTEM_TRACKING_ROLE, _TRACKING_CAPABILITY

    candidates = (
        await db.execute(
            select(MarketRefreshJob.id, MarketRefreshJob.metadata_payload)
            .where(
                MarketRefreshJob.id > after_id,
                MarketRefreshJob.capability == _TRACKING_CAPABILITY,
                MarketRefreshJob.status == "tracking",
                MarketRefreshJob.updated_at < cutoff,
                MarketRefreshJob.metadata_payload["data_preparation"]["role"].as_string()
                == _SYSTEM_TRACKING_ROLE,
            )
            .order_by(MarketRefreshJob.id)
            .limit(batch_size)
        )
    ).all()
    if not candidates:
        return 0, 0, None
    children_by_parent = {row.id: _child_job_ids(row.metadata_payload) for row in candidates}
    all_child_ids = sorted(set().union(*children_by_parent.values()))
    open_children: set[int] = set()
    for start in range(0, len(all_child_ids), _SELECT_CHUNK):
        chunk = all_child_ids[start : start + _SELECT_CHUNK]
        rows = await db.execute(
            select(MarketRefreshJob.id, MarketRefreshJob.status).where(
                MarketRefreshJob.id.in_(chunk)
            )
        )
        open_children.update(
            row.id for row in rows.all() if row.status not in TERMINAL_CHILD_STATUSES
        )
    deletable = [
        parent_id
        for parent_id, children in children_by_parent.items()
        if not (children & open_children)
    ]
    deleted = 0
    if deletable:
        # Re-assert the predicate so a parent touched since the SELECT survives.
        result = await db.execute(
            delete(MarketRefreshJob)
            .where(
                MarketRefreshJob.id.in_(deletable),
                MarketRefreshJob.capability == _TRACKING_CAPABILITY,
                MarketRefreshJob.status == "tracking",
                MarketRefreshJob.updated_at < cutoff,
            )
            .execution_options(synchronize_session=False)
        )
        deleted = int(result.rowcount or 0)
    return len(candidates), deleted, int(candidates[-1].id)


async def prune_finished_tracking_parents(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    *,
    retention_days: float,
    batch_size: int = 5000,
    max_seconds: float = 240.0,
    now: datetime | None = None,
) -> dict:
    """Delete finished tracking parents in short transactions within a time budget.

    Idempotent: a second run finds only what the first left (parents with open
    children, or rows inside the window). Keyset-paged so parents that must be
    kept do not stall the scan.
    """

    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=float(retention_days))
    deadline = time.monotonic() + float(max_seconds)
    scanned = deleted = batches = 0
    after_id = 0
    budget_exhausted = False
    while True:
        if time.monotonic() >= deadline:
            budget_exhausted = True
            break
        async with session_factory() as db:
            batch_scanned, batch_deleted, last_id = await _prune_batch(
                db, cutoff=cutoff, after_id=after_id, batch_size=int(batch_size)
            )
            await db.commit()
        if last_id is None:
            break
        batches += 1
        scanned += batch_scanned
        deleted += batch_deleted
        after_id = last_id
        if batch_scanned < int(batch_size):
            break
    return {
        "scanned": scanned,
        "deleted": deleted,
        "kept": scanned - deleted,
        "batches": batches,
        "budget_exhausted": budget_exhausted,
        "retention_days": float(retention_days),
    }
