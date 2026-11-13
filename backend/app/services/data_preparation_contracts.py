"""Shared Provider-owned contracts for durable preparation workers and ETF hooks.

This module contains types only. It deliberately has no adapter registration or
success fallback: an absent ETF implementation remains unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.schemas.data_preparation import PreparationDataset

PreparationPriority = Literal["visible", "default", "background"]
PreparationStatus = Literal["ready", "partial", "waiting", "unavailable", "failed"]


@dataclass(frozen=True, slots=True)
class DatasetPreparationContext:
    request_id: str
    dependency_id: str
    dataset: PreparationDataset
    timeframe: Timeframe
    adjusted: bool
    requested_start: datetime | None
    requested_end: datetime | None
    priority: PreparationPriority
    deadline: datetime


@dataclass(frozen=True, slots=True)
class DatasetPreparationResult:
    status: PreparationStatus
    covered_start: datetime | None = None
    covered_end: datetime | None = None
    reason_code: str | None = None
    retry_at: datetime | None = None
    acquired_version: int | None = None


class ETFHoldingsPreparer(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        instrument: Instrument,
        *,
        context: DatasetPreparationContext,
    ) -> DatasetPreparationResult: ...
