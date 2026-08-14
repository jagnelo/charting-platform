from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instrument_reconciliation import InstrumentReconciliationIssue


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def record_discovery_ambiguities(
    db: AsyncSession,
    *,
    data_source_id: int,
    provider_symbol_rows: list[dict[str, Any]],
    quote_type: str,
    offset: int,
    observed_at: datetime | None = None,
) -> int:
    """Upsert ambiguity issues found in one provider discovery page."""
    observed_at = observed_at or datetime.now(UTC)
    recorded = 0
    for row in provider_symbol_rows:
        candidates = row.get("identity_ambiguity")
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or not candidates:
            continue
        issue_payload = {
            "quote_type": quote_type,
            "offset": offset,
            "symbol": symbol,
            "exchange": row.get("exchange"),
            "sec_cik": row.get("sec_cik"),
            "candidates": candidates,
        }
        fingerprint = _fingerprint(issue_payload)
        issue = (
            await db.execute(
                select(InstrumentReconciliationIssue).where(
                    InstrumentReconciliationIssue.data_source_id == data_source_id,
                    InstrumentReconciliationIssue.provider_symbol == symbol,
                    InstrumentReconciliationIssue.issue_type == "ambiguous_ticker_issuer",
                    InstrumentReconciliationIssue.fingerprint == fingerprint,
                )
            )
        ).scalar_one_or_none()
        if issue is None:
            db.add(
                InstrumentReconciliationIssue(
                    data_source_id=data_source_id,
                    provider_symbol=symbol,
                    issue_type="ambiguous_ticker_issuer",
                    fingerprint=fingerprint,
                    status="open",
                    candidates=candidates,
                    payload=issue_payload,
                    observed_at=observed_at,
                )
            )
            recorded += 1
        elif issue.status == "open":
            issue.observed_at = observed_at
            issue.candidates = candidates
            issue.payload = issue_payload
    if recorded:
        await db.flush()
    return recorded


async def list_reconciliation_issues(
    db: AsyncSession,
    *,
    status: str = "open",
    limit: int = 200,
) -> list[InstrumentReconciliationIssue]:
    safe_limit = max(1, min(limit, 500))
    result = await db.execute(
        select(InstrumentReconciliationIssue)
        .options(
            selectinload(InstrumentReconciliationIssue.data_source),
            selectinload(InstrumentReconciliationIssue.resolved_by),
        )
        .where(InstrumentReconciliationIssue.status == status)
        .order_by(
            InstrumentReconciliationIssue.observed_at.desc(),
            InstrumentReconciliationIssue.id.desc(),
        )
        .limit(safe_limit)
    )
    return list(result.scalars().all())


async def resolve_reconciliation_issue(
    db: AsyncSession,
    issue: InstrumentReconciliationIssue,
    *,
    status: str,
    resolution: dict[str, Any] | None = None,
    resolved_by_user_id: int | None = None,
) -> InstrumentReconciliationIssue:
    if status not in {"open", "resolved", "ignored"}:
        raise ValueError("status must be open, resolved, or ignored")
    issue.status = status
    issue.resolution = resolution
    issue.resolved_at = datetime.now(UTC) if status != "open" else None
    issue.resolved_by_user_id = resolved_by_user_id if status != "open" else None
    await db.flush()
    return issue
