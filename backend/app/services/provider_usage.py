from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import quantiles
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaIdentity, ProviderQuotaWindow
from app.models.provider_runtime import ProviderPolicy, ProviderRequestLog
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


def _strict_positive_window_seconds(value: Any) -> int | None:
    """Return a durable quota-window duration only when its type is exact."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _response_bytes(log: ProviderRequestLog) -> int:
    """Return observed transport bytes, preserving unknown as zero for sums."""
    return max(0, int(log.response_bytes or 0))


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


def _next_calendar_month(started_at: datetime, timezone: ZoneInfo) -> datetime:
    """Return the next first-of-month boundary in a provider's timezone."""

    local = started_at.astimezone(timezone)
    if local.month == 12:
        next_year, next_month = local.year + 1, 1
    else:
        next_year, next_month = local.year, local.month + 1
    return datetime(next_year, next_month, 1, tzinfo=timezone).astimezone(UTC)


def _window_end_for_reset(
    started_at: datetime,
    *,
    window_seconds: int,
    reset: str | None,
) -> datetime:
    """Calculate an observability end boundary without flattening calendar windows.

    Quota admission stores the provider's explicit window start and a nominal
    duration.  Calendar months and Eastern-time resets cannot use that fixed
    duration safely because month lengths and daylight-saving transitions vary.
    Unknown/fixed/rolling resets retain the durable duration semantics.
    """

    normalized = str(reset or "").strip().lower()
    if "calendar_month_est" in normalized:
        return _next_calendar_month(started_at, ZoneInfo("America/New_York"))
    if "calendar_month" in normalized:
        return _next_calendar_month(started_at, UTC)
    if normalized == "calendar_day_est":
        timezone = ZoneInfo("America/New_York")
        eastern = started_at.astimezone(timezone)
        next_date = eastern.date() + timedelta(days=1)
        next_local = datetime(
            next_date.year,
            next_date.month,
            next_date.day,
            tzinfo=timezone,
        )
        return next_local.astimezone(UTC)
    if normalized in {"calendar_day_utc", "calendar_day_gmt"}:
        utc_start = started_at.astimezone(UTC)
        return (utc_start + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if normalized.startswith("09:30"):
        timezone = ZoneInfo("America/New_York")
        eastern = started_at.astimezone(timezone)
        next_date = eastern.date() + timedelta(days=1)
        next_local = datetime(
            next_date.year,
            next_date.month,
            next_date.day,
            9,
            30,
            tzinfo=timezone,
        )
        return next_local.astimezone(UTC)
    return started_at + timedelta(seconds=window_seconds)


def _live_usage_ledger_path() -> Path:
    configured = str(getattr(settings, "PROVIDER_LIVE_USAGE_LEDGER", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "charting-platform" / "provider-live-usage.jsonl"


def _empty_live_usage() -> dict[str, Any]:
    return {
        "status": "no_observations",
        "runs": 0,
        "failed_runs": 0,
        "process_failed_runs": 0,
        "failed_operations": 0,
        "operations": 0,
        "http_requests": 0,
        "response_bytes": 0,
        "runs_24h": 0,
        "operations_24h": 0,
        "http_requests_24h": 0,
        "response_bytes_24h": 0,
        "failed_operations_24h": 0,
        "process_failed_runs_24h": 0,
        "runs_7d": 0,
        "operations_7d": 0,
        "http_requests_7d": 0,
        "response_bytes_7d": 0,
        "failed_operations_7d": 0,
        "process_failed_runs_7d": 0,
        "runs_30d": 0,
        "operations_30d": 0,
        "http_requests_30d": 0,
        "response_bytes_30d": 0,
        "failed_operations_30d": 0,
        "process_failed_runs_30d": 0,
        "last_observation_at": None,
        "usage_scopes": [],
        "last_response_headers": {},
    }


_LIVE_CAPACITY_HEADERS = {
    "api-credits-left",
    "api-credits-request",
    "api-credits-used",
    "x-api-ratelimit-limit",
    "x-api-ratelimit-remaining",
    "x-api-ratelimit-reset",
    "x-api-ratelimit-consumed",
    "content-length",
    "record-limit",
    "record-max-limit",
    "record-offset",
    "record-total",
    "total-records-on-page",
    "response-payload-max-size",
    "retry-after",
    "x-bapi-limit",
    "x-bapi-limit-reset-timestamp",
    "x-bapi-limit-status",
    "x-mbx-order-count-1m",
    "x-mbx-used-weight-1m",
    "x-rate-limit-limit",
    "x-rate-limit-remaining",
    "x-rate-limit-reset",
    "x-ratelimit-allowed",
    "x-ratelimit-available",
    "x-ratelimit-expiry",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-used",
}


def read_live_usage_ledger(*, now: datetime | None = None) -> dict[str, Any]:
    """Read redacted direct-live usage without making it a routing dependency.

    The live suite writes one JSON object per provider/run outside Git and the
    application database.  This reader deliberately accepts only the numeric
    aggregate fields emitted by ``tests/live/live_usage.py``.  Malformed rows
    are counted and ignored; credentials, payloads, run IDs, and filesystem
    paths are never returned.
    """

    current = now or _now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)
    path = _live_usage_ledger_path()
    if not path.is_file():
        return {
            "status": "unavailable",
            "reason": "ledger_missing",
            "rows": 0,
            "invalid_rows": 0,
            "last_observation_at": None,
            "providers": {},
        }

    last_24h = current - timedelta(hours=24)
    last_7d = current - timedelta(days=7)
    last_30d = current - timedelta(days=30)
    providers: dict[str, dict[str, Any]] = defaultdict(_empty_live_usage)
    rows = 0
    invalid_rows = 0
    latest: datetime | None = None

    def _nonnegative_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and value.strip().isdigit():
            parsed = int(value.strip())
        else:
            return None
        return parsed if parsed >= 0 else None

    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    provider = str(row.get("provider") or "").strip()
                    usage_scope = str(row.get("usage_scope") or "unspecified").strip()
                    if not usage_scope or len(usage_scope) > 128 or not usage_scope.isprintable():
                        raise ValueError("invalid live usage scope")
                    observed_at = datetime.fromisoformat(str(row.get("at") or ""))
                    if observed_at.tzinfo is None:
                        observed_at = observed_at.replace(tzinfo=UTC)
                    else:
                        observed_at = observed_at.astimezone(UTC)
                    operations = _nonnegative_int(row.get("operations"))
                    requests = _nonnegative_int(row.get("http_requests"))
                    response_bytes = _nonnegative_int(row.get("response_bytes"))
                    exit_status = _nonnegative_int(row.get("exit_status"))
                    failed_operations = _nonnegative_int(row.get("failed_operations", 0))
                    process_exit_status = _nonnegative_int(
                        row.get("process_exit_status", exit_status)
                    )
                    response_headers = row.get("response_headers")
                    if response_headers is None:
                        response_headers = {}
                    if not isinstance(response_headers, dict) or len(response_headers) > 32:
                        raise ValueError("invalid live usage headers")
                    safe_headers: dict[str, str] = {}
                    for raw_name, raw_value in response_headers.items():
                        name = str(raw_name).strip().lower()
                        value = str(raw_value).strip()
                        if (
                            name not in _LIVE_CAPACITY_HEADERS
                            or not name.isprintable()
                            or not value
                            or len(value) > 256
                            or not value.isprintable()
                        ):
                            raise ValueError("invalid live usage header")
                        safe_headers[name] = value
                    if (
                        not provider
                        or len(provider) > 128
                        or not provider.isprintable()
                        or operations is None
                        or requests is None
                        or response_bytes is None
                        or exit_status is None
                        or failed_operations is None
                        or process_exit_status is None
                        or failed_operations > operations
                    ):
                        raise ValueError("invalid live usage row")
                except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                    invalid_rows += 1
                    continue

                rows += 1
                latest = max(latest, observed_at) if latest else observed_at
                summary = providers[provider]
                if usage_scope not in summary["usage_scopes"]:
                    summary["usage_scopes"].append(usage_scope)
                summary["status"] = "available"
                summary["runs"] += 1
                summary["failed_runs"] += int(exit_status not in (None, 0))
                summary["process_failed_runs"] += int(process_exit_status not in (None, 0))
                summary["failed_operations"] += failed_operations
                summary["operations"] += operations
                summary["http_requests"] += requests
                summary["response_bytes"] += response_bytes
                prior_observation = summary["last_observation_at"]
                if prior_observation is None or observed_at >= prior_observation:
                    # A merged ledger is not guaranteed to be line-ordered.
                    # Keep the header snapshot attached to the chronologically
                    # latest observation, including an empty snapshot when the
                    # latest provider response exposed no capacity headers.
                    summary["last_response_headers"] = safe_headers
                    summary["last_observation_at"] = observed_at
                if observed_at >= last_24h:
                    summary["runs_24h"] += 1
                    summary["process_failed_runs_24h"] += int(process_exit_status not in (None, 0))
                    summary["failed_operations_24h"] += failed_operations
                    summary["operations_24h"] += operations
                    summary["http_requests_24h"] += requests
                    summary["response_bytes_24h"] += response_bytes
                if observed_at >= last_7d:
                    summary["runs_7d"] += 1
                    summary["process_failed_runs_7d"] += int(process_exit_status not in (None, 0))
                    summary["failed_operations_7d"] += failed_operations
                    summary["operations_7d"] += operations
                    summary["http_requests_7d"] += requests
                    summary["response_bytes_7d"] += response_bytes
                if observed_at >= last_30d:
                    summary["runs_30d"] += 1
                    summary["process_failed_runs_30d"] += int(process_exit_status not in (None, 0))
                    summary["failed_operations_30d"] += failed_operations
                    summary["operations_30d"] += operations
                    summary["http_requests_30d"] += requests
                    summary["response_bytes_30d"] += response_bytes
    except OSError:
        return {
            "status": "unavailable",
            "reason": "ledger_unreadable",
            "rows": 0,
            "invalid_rows": 0,
            "last_observation_at": None,
            "providers": {},
        }

    return {
        "status": "available" if rows else "empty",
        "rows": rows,
        "invalid_rows": invalid_rows,
        "last_observation_at": latest,
        "providers": {
            provider: {
                **summary,
                "usage_scopes": sorted(summary["usage_scopes"]),
            }
            for provider, summary in providers.items()
        },
    }


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
    window_logs = [
        log for log in logs if (_ensure_aware(log.requested_at) or started_at) >= started_at
    ]
    return (
        started_at,
        now,
        len(window_logs),
        sum(_to_float(log.usage_units) for log in window_logs),
    )


async def summarize_provider_usage(db: AsyncSession) -> list[dict[str, Any]]:
    await seed_provider_runtime(db)
    now = _now_utc()
    live_usage_ledger = read_live_usage_ledger(now=now)
    live_usage_by_provider = live_usage_ledger.get("providers") or {}
    retention_days = max(int(settings.PROVIDER_REQUEST_LOG_RETENTION_DAYS or 30), 7)
    retained_since = now - timedelta(days=retention_days)
    last_24h_since = now - timedelta(hours=24)
    last_7d_since = now - timedelta(days=7)

    data_sources = (
        (await db.execute(select(DataSource).order_by(DataSource.name.asc()))).scalars().all()
    )
    logs = (
        (
            await db.execute(
                select(ProviderRequestLog)
                .where(ProviderRequestLog.requested_at >= retained_since)
                .order_by(ProviderRequestLog.requested_at.asc())
            )
        )
        .scalars()
        .all()
    )
    quota_windows = (
        (
            await db.execute(
                select(ProviderQuotaWindow)
                .where(
                    ProviderQuotaWindow.window_started_at <= now,
                    ProviderQuotaWindow.window_started_at >= now - timedelta(days=400),
                )
                .order_by(ProviderQuotaWindow.data_source_id, ProviderQuotaWindow.dimension)
            )
        )
        .scalars()
        .all()
    )
    policies = (await db.execute(select(ProviderPolicy))).scalars().all()
    reset_by_source_group_dimension: dict[tuple[int, str, str], str] = {}
    reset_by_source_capability_dimension: dict[tuple[int, str, str], str] = {}
    for policy in policies:
        contract = policy.quota_contract or {}
        if not isinstance(contract, dict):
            continue
        contract_reset = str(contract.get("reset") or "").strip()
        capability = getattr(policy.capability, "value", policy.capability)
        for dimension in contract.get("dimensions") or []:
            if not isinstance(dimension, dict):
                continue
            dimension_name = str(dimension.get("name") or "").strip()
            if not dimension_name:
                continue
            quota_group = str(dimension.get("quota_group") or capability).strip()
            reset = str(dimension.get("reset") or contract_reset).strip()
            reset_by_source_group_dimension[
                (policy.data_source_id, quota_group, dimension_name)
            ] = reset
            reset_by_source_capability_dimension[
                (policy.data_source_id, str(capability), dimension_name)
            ] = reset
    quota_identities = (
        (
            await db.execute(
                select(ProviderQuotaIdentity).where(
                    ProviderQuotaIdentity.window_started_at <= now,
                    ProviderQuotaIdentity.window_started_at >= now - timedelta(days=400),
                )
            )
        )
        .scalars()
        .all()
    )

    logs_by_source: dict[int, list[ProviderRequestLog]] = defaultdict(list)
    for log in logs:
        if log.data_source_id is not None:
            logs_by_source[log.data_source_id].append(log)

    active_windows_by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    invalid_windows_by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    identity_counts: Counter[tuple[int, str, str, datetime, int]] = Counter(
        (
            identity.data_source_id,
            str(identity.quota_group or identity.capability),
            identity.dimension,
            _ensure_aware(identity.window_started_at),
            int(identity.window_seconds),
        )
        for identity in quota_identities
        if _ensure_aware(identity.window_started_at) is not None
    )
    for window in quota_windows:
        started_at = _ensure_aware(window.window_started_at)
        if started_at is None:
            continue
        window_seconds = _strict_positive_window_seconds(window.window_seconds)
        if window_seconds is None:
            invalid_windows_by_source[window.data_source_id].append(
                {
                    "id": window.id,
                    "dimension": str(window.dimension),
                    "reason": "window_seconds must be a positive integer",
                }
            )
            continue
        capability = getattr(window.capability, "value", window.capability)
        quota_group = str(window.quota_group or capability)
        reset = reset_by_source_capability_dimension.get(
            (window.data_source_id, str(capability), str(window.dimension))
        )
        reset = reset_by_source_group_dimension.get(
            (window.data_source_id, quota_group, str(window.dimension)), reset
        )
        ends_at = _window_end_for_reset(
            started_at,
            window_seconds=window_seconds,
            reset=reset,
        )
        if ends_at <= now:
            continue
        active_windows_by_source[window.data_source_id].append(
            {
                "dimension": window.dimension,
                "quota_group": quota_group,
                "capability": str(capability),
                "window_started_at": started_at,
                "window_ends_at": ends_at,
                "window_seconds": window_seconds,
                "limit_units": int(window.limit_units),
                "reserved_units": int(window.reserved_units),
                "consumed_units": int(window.consumed_units),
                "available_units": max(
                    0,
                    int(window.limit_units)
                    - int(window.reserved_units)
                    - int(window.consumed_units),
                ),
                "distinct_identity_count": identity_counts.get(
                    (
                        window.data_source_id,
                        quota_group,
                        window.dimension,
                        started_at,
                        window_seconds,
                    ),
                    0,
                ),
            }
        )

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
        last_24h_logs = [
            log
            for log in provider_logs
            if (_ensure_aware(log.requested_at) or last_24h_since) >= last_24h_since
        ]
        last_7d_logs = [
            log
            for log in provider_logs
            if (_ensure_aware(log.requested_at) or last_7d_since) >= last_7d_since
        ]
        failures_24h = [log for log in last_24h_logs if not log.success]
        timeout_24h = [
            log
            for log in last_24h_logs
            if (log.error_type or "").lower().endswith("timeout")
            or "timeout" in (log.error_type or "").lower()
        ]
        latency_24h = [int(log.latency_ms) for log in last_24h_logs if log.latency_ms is not None]
        quota_limit = tracking.get("quota_limit")
        estimated_quota_limit = tracking.get("estimated_quota_limit")
        quota_window_seconds = tracking.get("quota_window_seconds")
        (
            current_window_started_at,
            current_window_ends_at,
            current_window_requests,
            current_window_units,
        ) = _window_usage(
            provider_logs,
            now=now,
            quota_window_seconds=int(quota_window_seconds) if quota_window_seconds else None,
        )
        current_window_logs = [
            log
            for log in provider_logs
            if quota_window_seconds
            and (_ensure_aware(log.requested_at) or now)
            >= now - timedelta(seconds=int(quota_window_seconds))
        ]
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
                    "response_bytes": 0,
                    "failures": 0,
                    "successes": 0,
                },
            )
            row["requests"] += 1
            row["units"] += _to_float(log.usage_units)
            row["response_bytes"] += _response_bytes(log)
            row["successes"] += 1 if log.success else 0
            row["failures"] += 0 if log.success else 1

        capability_agg: dict[str, dict[str, Any]] = {}
        for log in last_7d_logs:
            row = capability_agg.setdefault(
                log.capability.value,
                {
                    "capability": log.capability.value,
                    "requests": 0,
                    "units": 0.0,
                    "response_bytes": 0,
                    "failures": 0,
                },
            )
            row["requests"] += 1
            row["units"] += _to_float(log.usage_units)
            row["response_bytes"] += _response_bytes(log)
            row["failures"] += 0 if log.success else 1

        error_counts = Counter(
            (log.error_type or "UnknownError") for log in last_7d_logs if not log.success
        )

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
                "current_window_response_bytes": sum(
                    _response_bytes(log) for log in current_window_logs
                ),
                "retained_requests": len(provider_logs),
                "retained_units": sum(_to_float(log.usage_units) for log in provider_logs),
                "retained_response_bytes": sum(_response_bytes(log) for log in provider_logs),
                "requests_24h": len(last_24h_logs),
                "units_24h": sum(_to_float(log.usage_units) for log in last_24h_logs),
                "response_bytes_24h": sum(_response_bytes(log) for log in last_24h_logs),
                "requests_7d": len(last_7d_logs),
                "units_7d": sum(_to_float(log.usage_units) for log in last_7d_logs),
                "response_bytes_7d": sum(_response_bytes(log) for log in last_7d_logs),
                "success_rate_24h": _percent(
                    len(last_24h_logs) - len(failures_24h), len(last_24h_logs)
                ),
                "failure_rate_24h": _percent(len(failures_24h), len(last_24h_logs)),
                "timeout_rate_24h": _percent(len(timeout_24h), len(last_24h_logs)),
                "avg_latency_ms_24h": (sum(latency_24h) / len(latency_24h))
                if latency_24h
                else None,
                "p95_latency_ms_24h": _p95(latency_24h),
                "last_request_at": _ensure_aware(provider_logs[-1].requested_at)
                if provider_logs
                else None,
                # Headers are already filtered by provider telemetry. Expose
                # the latest snapshot so operators can inspect provider-native
                # credit/remaining/reset state without reading raw logs.
                "last_response_headers": dict(provider_logs[-1].response_headers or {})
                if provider_logs
                else {},
                "active_quota_windows": sorted(
                    active_windows_by_source.get(data_source.id, []),
                    key=lambda row: (row["dimension"], row["window_started_at"]),
                ),
                "invalid_quota_windows": sorted(
                    invalid_windows_by_source.get(data_source.id, []),
                    key=lambda row: (row["dimension"], row["id"] or 0),
                ),
                "last_success_at": max(
                    (
                        _ensure_aware(log.completed_at)
                        for log in provider_logs
                        if log.success and log.completed_at
                    ),
                    default=None,
                ),
                "last_failure_at": max(
                    (
                        _ensure_aware(log.completed_at)
                        for log in provider_logs
                        if not log.success and log.completed_at
                    ),
                    default=None,
                ),
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
                # Direct live probes consume provider accounts outside the
                # application DB. Keep their redacted ledger totals separate
                # from runtime request logs and quota reservations.
                "live_usage_ledger": {
                    "status": live_usage_ledger.get("status"),
                    "rows": live_usage_ledger.get("rows", 0),
                    "invalid_rows": live_usage_ledger.get("invalid_rows", 0),
                    "last_observation_at": live_usage_ledger.get("last_observation_at"),
                },
                "live_test_usage": live_usage_by_provider.get(
                    data_source.name, _empty_live_usage()
                ),
            }
        )
    return summaries
