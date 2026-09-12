"""Provider-neutral coverage preflight for broad evaluators.

Evaluators must decide whether their local OHLCV inputs are usable before they
start calculating signals or performance.  This module deliberately performs
only database reads and optional durable refresh-job enqueueing; provider
selection and provider I/O remain worker responsibilities.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_runtime import ProviderCapability
from app.services.market_refresh_queue import enqueue_refresh_job
from app.services.ohlcv_coverage import (
    CalendarName,
    CoverageStatus,
    assess_ohlcv_coverage,
)

EvaluatorPreflightStatus = Literal[
    "full",
    "partial",
    "deferred",
    "stale-blocked",
    "provider-unavailable",
    "empty",
]


@dataclass(frozen=True, slots=True)
class EvaluatorCoverageItem:
    """Coverage decision for one instrument/timeframe request."""

    instrument_id: int
    timeframe: Timeframe
    status: CoverageStatus
    required_start: datetime | None
    required_end: datetime | None
    covered_start: datetime | None
    covered_end: datetime | None
    bar_count: int
    missing_slices: tuple[tuple[datetime, datetime], ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe.value,
            "status": self.status.value,
            "required_start": self.required_start.isoformat() if self.required_start else None,
            "required_end": self.required_end.isoformat() if self.required_end else None,
            "covered_start": self.covered_start.isoformat() if self.covered_start else None,
            "covered_end": self.covered_end.isoformat() if self.covered_end else None,
            "bar_count": self.bar_count,
            "missing_slices": [
                {"start": start.isoformat(), "end": end.isoformat()}
                for start, end in self.missing_slices
            ],
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class EvaluatorPreflight:
    """Bounded, serializable result shared by an evaluator run."""

    status: EvaluatorPreflightStatus
    evaluator: str
    items: tuple[EvaluatorCoverageItem, ...]
    queued_request_keys: tuple[str, ...]
    queue_repairs: bool
    observed_at: datetime

    @property
    def ready_instrument_ids(self) -> frozenset[int]:
        return frozenset(
            item.instrument_id
            for item in self.items
            if item.status == CoverageStatus.READY
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evaluator": self.evaluator,
            "queue_repairs": self.queue_repairs,
            "queued_request_keys": list(self.queued_request_keys),
            "observed_at": self.observed_at.isoformat(),
            "item_count": len(self.items),
            "ready_instrument_count": len(self.ready_instrument_ids),
            "items": [item.to_dict() for item in self.items],
        }


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _aggregate_status(items: list[EvaluatorCoverageItem]) -> EvaluatorPreflightStatus:
    if not items:
        return "empty"
    statuses = {item.status for item in items}
    ready_count = sum(item.status == CoverageStatus.READY for item in items)
    if ready_count == len(items):
        return "full"
    if CoverageStatus.STALE in statuses and ready_count == 0:
        return "stale-blocked"
    if ready_count:
        return "partial"
    return "deferred"


async def preflight_ohlcv(
    db: AsyncSession,
    *,
    evaluator: str,
    instrument_ids: list[int] | tuple[int, ...],
    timeframe: Timeframe,
    date_from: datetime | None,
    date_to: datetime | None,
    mode: Literal["historical", "latest"] = "historical",
    freshness_seconds: int | None = None,
    calendar: CalendarName | None = None,
    queue_repairs: bool = False,
    now: datetime | None = None,
    adjusted: bool | None = None,
    cached_bars: Mapping[int, Sequence[OHLCVBar]] | None = None,
    minimum_bars: int | None = None,
) -> EvaluatorPreflight:
    """Assess exact local coverage and optionally enqueue missing slices.

    A bounded historical request uses its supplied dates.  If either bound is
    absent, the local observed extent becomes the bound for instruments that
    have data; a completely cold instrument remains unresolved because there
    is no safe range to invent.  Latest-mode freshness is delegated to the
    shared coverage planner and never receives an invented retry delay.
    """

    observed_at = _as_utc(now or datetime.now(UTC))
    ordered_ids = list(dict.fromkeys(int(value) for value in instrument_ids))
    if not ordered_ids:
        return EvaluatorPreflight(
            status="empty",
            evaluator=evaluator,
            items=(),
            queued_request_keys=(),
            queue_repairs=queue_repairs,
            observed_at=observed_at,
        )

    if cached_bars is None:
        statement = (
            select(OHLCVBar)
            .where(
                OHLCVBar.instrument_id.in_(ordered_ids),
                OHLCVBar.timeframe == timeframe,
            )
            .order_by(OHLCVBar.instrument_id.asc(), OHLCVBar.ts.asc())
        )
        if date_from is not None:
            statement = statement.where(OHLCVBar.ts >= date_from)
        if date_to is not None:
            statement = statement.where(OHLCVBar.ts <= date_to)
        if adjusted is not None:
            statement = statement.where(OHLCVBar.is_adjusted.is_(adjusted))
        rows = list((await db.execute(statement)).scalars().all())
        bars_by_instrument: dict[int, list[OHLCVBar]] = defaultdict(list)
        for row in rows:
            bars_by_instrument[int(row.instrument_id)].append(row)
    else:
        bars_by_instrument = {
            instrument_id: [
                bar
                for bar in cached_bars.get(instrument_id, ())
                if (date_from is None or _as_utc(bar.ts) >= _as_utc(date_from))
                and (date_to is None or _as_utc(bar.ts) <= _as_utc(date_to))
                and (adjusted is None or bool(bar.is_adjusted) is adjusted)
            ]
            for instrument_id in ordered_ids
        }

    items: list[EvaluatorCoverageItem] = []
    for instrument_id in ordered_ids:
        bars = bars_by_instrument.get(instrument_id, [])
        observed_start = _as_utc(bars[0].ts) if bars else None
        observed_end = _as_utc(bars[-1].ts) if bars else None
        required_start = _as_utc(date_from) if date_from else observed_start
        required_end = _as_utc(date_to) if date_to else observed_end

        if required_start is None or required_end is None:
            status = CoverageStatus.MISSING
            missing_slices: tuple[tuple[datetime, datetime], ...] = ()
            explanation = "No local bars exist and no bounded repair window was supplied."
            covered_start = observed_start
            covered_end = observed_end
            bar_count = len(bars)
        else:
            assessment = assess_ohlcv_coverage(
                bars,
                timeframe,
                required_start,
                required_end,
                mode=mode,
                freshness_seconds=freshness_seconds,
                now=observed_at,
                calendar=calendar,
            )
            status = assessment.status
            missing_slices = assessment.missing_slices
            explanation = assessment.explanation
            covered_start = assessment.covered_start
            covered_end = assessment.covered_end
            bar_count = assessment.bar_count

        if (
            status == CoverageStatus.READY
            and minimum_bars is not None
            and bar_count < max(1, minimum_bars)
        ):
            status = CoverageStatus.PARTIAL
            explanation = (
                f"Only {bar_count} local bars are available; at least "
                f"{minimum_bars} are required by this evaluator."
            )

        items.append(
            EvaluatorCoverageItem(
                instrument_id=instrument_id,
                timeframe=timeframe,
                status=status,
                required_start=required_start,
                required_end=required_end,
                covered_start=covered_start,
                covered_end=covered_end,
                bar_count=bar_count,
                missing_slices=missing_slices,
                explanation=explanation,
            )
        )

    queued: list[str] = []
    if queue_repairs:
        for item in items:
            if item.status != CoverageStatus.READY:
                slices = item.missing_slices
                if not slices and item.required_start and item.required_end:
                    slices = ((item.required_start, item.required_end),)
            else:
                slices = ()
            for slice_start, slice_end in slices:
                request_key = (
                    f"evaluator:{evaluator}:{item.instrument_id}:{item.timeframe.value}:"
                    f"{slice_start.isoformat()}:{slice_end.isoformat()}"
                )
                await enqueue_refresh_job(
                    db,
                    request_key=request_key,
                    capability=ProviderCapability.PRICE_HISTORY.value,
                    instrument_id=item.instrument_id,
                    timeframe=item.timeframe.value,
                    start_at=slice_start,
                    end_at=slice_end,
                    priority=75,
                    metadata_payload={
                        "schedule": "evaluator_coverage_preflight",
                        "evaluator": evaluator,
                        "coverage_status": item.status.value,
                        "requested_at": observed_at.isoformat(),
                    },
                    now=observed_at,
                )
                queued.append(request_key)

    return EvaluatorPreflight(
        status=_aggregate_status(items),
        evaluator=evaluator,
        items=tuple(items),
        queued_request_keys=tuple(queued),
        queue_repairs=queue_repairs,
        observed_at=observed_at,
    )
