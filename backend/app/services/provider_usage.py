from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import quantiles
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderRequestLog
from app.services.provider_runtime import seed_provider_runtime


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _usage_tracking_config(data_source: DataSource) -> dict[str, Any]:
    config = dict(data_source.config or {})
    tracking = config.get("usage_tracking") or {}
    return tracking if isinstance(tracking, dict) else {}


def _to_float(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100.0


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _bucket_start(ts: datetime, *, span: str) -> datetime:
    if span == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def _iter_buckets(start: datetime, count: int, *, span: str) -> list[datetime]:
    step = timedelta(hours=1) if span == "hour" else timedelta(days=1)
    return [start + (step * idx) for idx in range(count)]


def _p95(values: list[int]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    return float(quantiles(values, n=20, method="inclusive")[18])


def _window_usage(
    logs: list[ProviderRequestLog],
    *,
    now: datetime,
    quota_window_seconds: int | None,
) -> tuple[datetime | None, datetime | None, int | None, float | None]:
    if not quota_window_seconds or quota_window_seconds <= 0:
        return None, None, None, None
    started_at = now - timedelta(seconds=quota_window_seconds)
    window_logs = [log for log in logs if (_ensure_aware(log.requested_at) or started_at) >= started_at]
    return (
        started_at,
        now,
        len(window_logs),
        sum(_to_float(log.usage_units) for log in window_logs),
    )


async def summarize_provider_usage(db: AsyncSession) -> list[dict[str, Any]]:
    await seed_provider_runtime(db)
    now = _now_utc()
    retention_days = max(int(settings.PROVIDER_REQUEST_LOG_RETENTION_DAYS or 30), 7)
    retained_since = now - timedelta(days=retention_days)
    last_24h_since = now - timedelta(hours=24)
    last_7d_since = now - timedelta(days=7)

    data_sources = (
        await db.execute(select(DataSource).order_by(DataSource.name.asc()))
    ).scalars().all()
    logs = (
        await db.execute(
            select(ProviderRequestLog)
            .where(ProviderRequestLog.requested_at >= retained_since)
            .order_by(ProviderRequestLog.requested_at.asc())
        )
    ).scalars().all()

    logs_by_source: dict[int, list[ProviderRequestLog]] = defaultdict(list)
    for log in logs:
        if log.data_source_id is not None:
            logs_by_source[log.data_source_id].append(log)

    hourly_starts = _iter_buckets(
        (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0),
        24,
        span="hour",
    )
    daily_starts = _iter_buckets(
        (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0),
        7,
        span="day",
    )

    summaries: list[dict[str, Any]] = []
    for data_source in data_sources:
        tracking = _usage_tracking_config(data_source)
        provider_logs = logs_by_source.get(data_source.id, [])
        last_24h_logs = [log for log in provider_logs if (_ensure_aware(log.requested_at) or last_24h_since) >= last_24h_since]
        last_7d_logs = [log for log in provider_logs if (_ensure_aware(log.requested_at) or last_7d_since) >= last_7d_since]
        failures_24h = [log for log in last_24h_logs if not log.success]
        timeout_24h = [
            log for log in last_24h_logs if (log.error_type or "").lower().endswith("timeout") or "timeout" in (log.error_type or "").lower()
        ]
        latency_24h = [int(log.latency_ms) for log in last_24h_logs if log.latency_ms is not None]
        quota_limit = tracking.get("quota_limit")
        estimated_quota_limit = tracking.get("estimated_quota_limit")
        quota_window_seconds = tracking.get("quota_window_seconds")
        current_window_started_at, current_window_ends_at, current_window_requests, current_window_units = _window_usage(
            provider_logs,
            now=now,
            quota_window_seconds=int(quota_window_seconds) if quota_window_seconds else None,
        )
        denominator_limit = quota_limit or estimated_quota_limit
        current_window_utilization = (
            (current_window_units / float(denominator_limit)) * 100.0
            if denominator_limit and current_window_units is not None
            else None
        )

        operation_agg: dict[str, dict[str, Any]] = {}
        for log in last_7d_logs:
            row = operation_agg.setdefault(
                log.operation_family,
                {
                    "operation_family": log.operation_family,
                    "requests": 0,
                    "units": 0.0,
                    "failures": 0,
                    "successes": 0,
                },
            )
            row["requests"] += 1
            row["units"] += _to_float(log.usage_units)
            row["successes"] += 1 if log.success else 0
            row["failures"] += 0 if log.success else 1

        capability_agg: dict[str, dict[str, Any]] = {}
        for log in last_7d_logs:
            row = capability_agg.setdefault(
                log.capability.value,
                {"capability": log.capability.value, "requests": 0, "units": 0.0, "failures": 0},
            )
            row["requests"] += 1
            row["units"] += _to_float(log.usage_units)
            row["failures"] += 0 if log.success else 1

        error_counts = Counter((log.error_type or "UnknownError") for log in last_7d_logs if not log.success)

        hourly_map: dict[datetime, dict[str, Any]] = {
            bucket: {"bucket_start": bucket, "requests": 0, "units": 0.0, "failures": 0}
            for bucket in hourly_starts
        }
        for log in last_24h_logs:
            requested_at = _ensure_aware(log.requested_at)
            if requested_at is None:
                continue
            bucket = _bucket_start(requested_at.astimezone(UTC), span="hour")
            if bucket in hourly_map:
                hourly_map[bucket]["requests"] += 1
                hourly_map[bucket]["units"] += _to_float(log.usage_units)
                hourly_map[bucket]["failures"] += 0 if log.success else 1

        daily_map: dict[datetime, dict[str, Any]] = {
            bucket: {"bucket_start": bucket, "requests": 0, "units": 0.0, "failures": 0}
            for bucket in daily_starts
        }
        for log in last_7d_logs:
            requested_at = _ensure_aware(log.requested_at)
            if requested_at is None:
                continue
            bucket = _bucket_start(requested_at.astimezone(UTC), span="day")
            if bucket in daily_map:
                daily_map[bucket]["requests"] += 1
                daily_map[bucket]["units"] += _to_float(log.usage_units)
                daily_map[bucket]["failures"] += 0 if log.success else 1

        summaries.append(
            {
                "provider": data_source.name,
                "base_url": data_source.base_url,
                "description": data_source.description,
                "usage_mode": tracking.get("mode") or "call_count",
                "usage_unit_label": tracking.get("unit_label") or "requests",
                "limit_kind": tracking.get("limit_kind") or "unknown",
                "quota_limit": quota_limit,
                "estimated_quota_limit": estimated_quota_limit,
                "quota_window_seconds": quota_window_seconds,
                "current_window_started_at": current_window_started_at,
                "current_window_ends_at": current_window_ends_at,
                "current_window_requests": current_window_requests,
                "current_window_units": current_window_units,
                "current_window_utilization_pct": current_window_utilization,
                "retained_requests": len(provider_logs),
                "retained_units": sum(_to_float(log.usage_units) for log in provider_logs),
                "requests_24h": len(last_24h_logs),
                "units_24h": sum(_to_float(log.usage_units) for log in last_24h_logs),
                "requests_7d": len(last_7d_logs),
                "units_7d": sum(_to_float(log.usage_units) for log in last_7d_logs),
                "success_rate_24h": _percent(len(last_24h_logs) - len(failures_24h), len(last_24h_logs)),
                "failure_rate_24h": _percent(len(failures_24h), len(last_24h_logs)),
                "timeout_rate_24h": _percent(len(timeout_24h), len(last_24h_logs)),
                "avg_latency_ms_24h": (sum(latency_24h) / len(latency_24h)) if latency_24h else None,
                "p95_latency_ms_24h": _p95(latency_24h),
                "last_request_at": _ensure_aware(provider_logs[-1].requested_at) if provider_logs else None,
                "last_success_at": max((_ensure_aware(log.completed_at) for log in provider_logs if log.success and log.completed_at), default=None),
                "last_failure_at": max((_ensure_aware(log.completed_at) for log in provider_logs if not log.success and log.completed_at), default=None),
                "top_operations": sorted(
                    operation_agg.values(),
                    key=lambda row: (-row["units"], -row["requests"], row["operation_family"]),
                )[:8],
                "capability_breakdown": sorted(
                    capability_agg.values(),
                    key=lambda row: (-row["units"], -row["requests"], row["capability"]),
                ),
                "error_breakdown": [
                    {"error_type": error_type, "count": count}
                    for error_type, count in error_counts.most_common(6)
                ],
                "hourly_buckets": list(hourly_map.values()),
                "daily_buckets": list(daily_map.values()),
            }
        )
    return summaries
