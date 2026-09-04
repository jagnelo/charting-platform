"""Deterministic local OHLCV rollups from finer acquired bars."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.models.ohlcv import TIMEFRAME_SECONDS, Timeframe


def _bucket_timestamp(ts: datetime, target: Timeframe) -> datetime:
    value = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    if target in {Timeframe.D1, Timeframe.W1, Timeframe.MN}:
        if target == Timeframe.D1:
            return value.replace(hour=0, minute=0, second=0, microsecond=0)
        if target == Timeframe.W1:
            day = value.replace(hour=0, minute=0, second=0, microsecond=0)
            return day - timedelta(days=day.weekday())
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    seconds = TIMEFRAME_SECONDS[target]
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)


def aggregate_bars(bars: list[Any], target: Timeframe) -> list[dict[str, Any]]:
    """Roll up bars without manufacturing missing buckets.

    The function only emits buckets containing input observations.  Callers
    must use exchange-session coverage to decide whether a daily bucket is
    complete; this avoids silently fabricating D1 bars from partial data.
    """

    if not bars:
        return []
    grouped: dict[tuple[datetime, str], list[Any]] = defaultdict(list)
    for bar in sorted(bars, key=lambda item: item.ts):
        grouped[(_bucket_timestamp(bar.ts, target), str(getattr(bar, "session", "regular")))].append(bar)

    result: list[dict[str, Any]] = []
    for (bucket, session), rows in sorted(grouped.items()):
        first, last = rows[0], rows[-1]
        volumes = [row.volume for row in rows if row.volume is not None]
        result.append(
            {
                "ts": bucket,
                "session": session,
                "open": Decimal(str(first.open)),
                "high": max(Decimal(str(row.high)) for row in rows),
                "low": min(Decimal(str(row.low)) for row in rows),
                "close": Decimal(str(last.close)),
                "volume": sum((Decimal(str(value)) for value in volumes), Decimal("0")) if volumes else None,
                "vwap": None,
                "is_adjusted": bool(getattr(last, "is_adjusted", False)),
                "adjustment_basis": getattr(last, "adjustment_basis", "raw"),
                "adjustment_version": getattr(last, "adjustment_version", "legacy"),
                "provenance": {"derived_from": len(rows), "aggregation": target.value},
            }
        )
    return result
