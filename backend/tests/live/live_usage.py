"""Quota admission and external usage receipts for direct live provider probes.

Live adapters reserve their reviewed provider-specific quota in the durable
coordinator before transport. This owner-managed ledger separately records
observed provider/request/byte counts and bounded operation names; it never
stores credentials or response bodies and is not itself quota admission.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections import defaultdict
from collections.abc import Mapping
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

DEFAULT_LEDGER = Path.home() / ".config" / "charting-platform" / "provider-live-usage.jsonl"
_CAPACITY_HEADERS = {
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
_observations: list[
    tuple[
        str,
        str,
        int,
        int,
        dict[str, str],
        bool,
        str,
        str,
        int | None,
        str | None,
    ]
] = []
_PROCESS_RUN_ID = str(uuid4())
_CURRENT_CASE_ID: ContextVar[str] = ContextVar("provider_live_case_id", default="")
_ACTIVE_REQUEST_ADMISSION: ContextVar[bool] = ContextVar(
    "provider_live_request_admission", default=False
)


def ledger_path() -> Path:
    """Return the owner-managed live-usage ledger path."""

    configured = os.getenv("PROVIDER_LIVE_USAGE_LEDGER", "").strip()
    return Path(configured or DEFAULT_LEDGER).expanduser()


def activate_case(case_id: str) -> Token[str]:
    """Attach observations to the currently executing pytest node."""

    return _CURRENT_CASE_ID.set(str(case_id).strip())


def deactivate_case(token: Token[str]) -> None:
    """Restore the previous pytest node context."""

    _CURRENT_CASE_ID.reset(token)


def activate_request_admission() -> Token[bool]:
    """Mark the current operation as durably admitted for outbound HTTP."""

    return _ACTIVE_REQUEST_ADMISSION.set(True)


def deactivate_request_admission(token: Token[bool]) -> None:
    """Restore the previous live-request admission context."""

    _ACTIVE_REQUEST_ADMISSION.reset(token)


def require_request_admission() -> None:
    """Reject a live HTTP request unless its operation reserved quota first."""

    if os.getenv("RUN_LIVE_PROVIDER_TESTS") == "1" and not _ACTIVE_REQUEST_ADMISSION.get():
        raise RuntimeError(
            "live provider HTTP request blocked: no active durable quota reservation"
        )


def install_httpx_quota_admission_guard(*, patcher=None) -> None:
    """Guard sync and async HTTPX transports before any request is sent.

    Every registered market-data adapter currently uses HTTPX. Installing this
    at pytest session start means a future direct/unwrapped HTTPX call is blocked
    before transport instead of being discovered only by missing receipt data.
    A supplied pytest monkeypatch object makes the same guard directly testable
    and automatically reversible in unit tests.
    """

    import httpx

    def set_attribute(target, name: str, value) -> None:
        if patcher is None:
            setattr(target, name, value)
        else:
            patcher.setattr(target, name, value)

    sync_send = httpx.Client.send
    if not getattr(sync_send, "_provider_live_quota_guard", False):

        def guarded_sync_send(self, request, *args, **kwargs):
            require_request_admission()
            return sync_send(self, request, *args, **kwargs)

        guarded_sync_send._provider_live_quota_guard = True
        set_attribute(httpx.Client, "send", guarded_sync_send)

    async_send = httpx.AsyncClient.send
    if not getattr(async_send, "_provider_live_quota_guard", False):

        async def guarded_async_send(self, request, *args, **kwargs):
            require_request_admission()
            return await async_send(self, request, *args, **kwargs)

        guarded_async_send._provider_live_quota_guard = True
        set_attribute(httpx.AsyncClient, "send", guarded_async_send)


def ensure_ledger_writable() -> Path:
    """Verify the live ledger can be opened before any provider calls run.

    Direct live tests consume external quota outside the application runtime.
    A teardown-only write check can otherwise allow calls to happen and then
    lose their usage receipt to a permissions error.  This preflight performs
    only a zero-byte append/open and never writes credentials or payloads.
    """

    path = ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8"):
            pass
        # Usage receipts can contain provider-native capacity observations.
        # Keep the owner-managed file private even when it pre-existed with a
        # permissive mode or was created under a different umask.
        os.chmod(path, 0o600)
    except OSError as exc:
        raise RuntimeError(f"provider live usage ledger is not writable: {path}") from exc
    return path


def ensure_usage_scope_configured() -> str:
    """Require a bounded non-secret scope label for live usage attribution."""

    scope = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip()
    if not scope or len(scope) > 128 or not scope.isprintable():
        raise RuntimeError(
            "provider live usage scope is missing or invalid; set "
            "PROVIDER_LIVE_USAGE_SCOPE before running live tests"
        )
    return scope


def _safe_headers(headers: Mapping[str, object] | None) -> dict[str, str]:
    """Keep only bounded provider-capacity headers, never auth/payload data."""

    if not headers:
        return {}
    result: dict[str, str] = {}
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        value = str(raw_value).strip()
        if (
            name in _CAPACITY_HEADERS
            and name.isprintable()
            and value
            and len(value) <= 256
            and value.isprintable()
        ):
            result[name] = value
    return result


def record_observation(
    provider: str,
    *,
    operation: str = "unspecified",
    http_requests: int,
    response_bytes: int,
    response_headers: Mapping[str, object] | None = None,
    success: bool = True,
    disposition: str | None = None,
    response_status_code: int | None = None,
    case_id: str | None = None,
    reservation_id: str | None = None,
) -> None:
    """Accumulate one measured live operation without retaining payload data.

    ``success`` is operation/provider scoped. It must not be inferred from
    pytest's process-wide exit status because one expected credential or quota
    failure must not mark unrelated successful provider rows as failed.
    """

    normalized_operation = str(operation).strip() or "unspecified"
    if len(normalized_operation) > 128 or not normalized_operation.isprintable():
        raise ValueError("provider live usage operation is invalid")
    normalized_case_id = str(case_id if case_id is not None else _CURRENT_CASE_ID.get()).strip()
    if len(normalized_case_id) > 512 or not normalized_case_id.isprintable():
        raise ValueError("provider live usage case ID is invalid")
    normalized_disposition = str(
        disposition or ("observed" if success else "provider_error")
    ).strip()
    if normalized_disposition not in {
        "observed",
        "provider_error",
        "expected_entitlement_denial",
    }:
        raise ValueError("provider live usage disposition is invalid")
    normalized_reservation_id = None
    if reservation_id is not None:
        normalized_reservation_id = str(reservation_id).strip()
        if len(normalized_reservation_id) > 64 or not normalized_reservation_id.isprintable():
            raise ValueError("provider live reservation ID is invalid")
        run_id = os.getenv("PROVIDER_LIVE_RUN_ID", "").strip()
        usage_scope = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip()
        if not run_id or not usage_scope:
            raise RuntimeError(
                "provider live reservation receipts require PROVIDER_LIVE_RUN_ID and "
                "PROVIDER_LIVE_USAGE_SCOPE"
            )
        from app.services.provider_quota_coordinator import (
            QuotaReservation,
            register_live_receipt_reservation,
        )

        register_live_receipt_reservation(
            QuotaReservation(
                reservation_id=normalized_reservation_id,
                provider_name=str(provider).strip() or "unknown",
                account_scope="receipt",
            ),
            run_id=run_id,
            usage_scope=usage_scope,
            receipt_status=normalized_disposition,
        )
    _observations.append(
        (
            str(provider).strip() or "unknown",
            normalized_operation,
            max(0, int(http_requests)),
            max(0, int(response_bytes)),
            _safe_headers(response_headers),
            bool(success),
            normalized_case_id,
            normalized_disposition,
            (int(response_status_code) if response_status_code is not None else None),
            normalized_reservation_id,
        )
    )


def flush_observations(exit_status: int) -> Path | None:
    """Append this pytest process's aggregate usage receipt and clear memory."""

    if not _observations:
        return None
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "http_requests": 0,
            "response_bytes": 0,
            "operations": 0,
            "failed_operations": 0,
            "response_headers": {},
            "operation_usage": {},
            "case_usage": {},
        }
    )
    for (
        provider,
        operation,
        requests,
        response_bytes,
        response_headers,
        success,
        case_id,
        disposition,
        response_status_code,
        reservation_id,
    ) in _observations:
        grouped[provider]["http_requests"] += requests
        grouped[provider]["response_bytes"] += response_bytes
        grouped[provider]["operations"] += 1
        grouped[provider]["failed_operations"] += int(not success)
        grouped[provider]["response_headers"].update(response_headers)
        operation_rows = grouped[provider]["operation_usage"]
        operation_row = operation_rows.setdefault(
            operation,
            {
                "operations": 0,
                "http_requests": 0,
                "response_bytes": 0,
                "failed_operations": 0,
                "dispositions": {},
                "response_statuses": {},
            },
        )
        operation_row["operations"] += 1
        operation_row["http_requests"] += requests
        operation_row["response_bytes"] += response_bytes
        operation_row["failed_operations"] += int(not success)
        operation_row.setdefault("dispositions", {})[disposition] = (
            operation_row.setdefault("dispositions", {}).get(disposition, 0) + 1
        )
        if response_status_code is not None:
            operation_row.setdefault("response_statuses", {})[str(response_status_code)] = (
                operation_row.setdefault("response_statuses", {}).get(str(response_status_code), 0)
                + 1
            )
        if reservation_id:
            reservation_row = {
                "reservation_id": reservation_id,
                "operation": operation,
                "status": disposition,
            }
            reservations = grouped[provider].setdefault("reservations", [])
            if reservation_row not in reservations:
                reservations.append(reservation_row)
        if case_id:
            case_row = grouped[provider]["case_usage"].setdefault(
                case_id,
                {
                    "http_requests": 0,
                    "response_bytes": 0,
                    "operations": {},
                },
            )
            case_row["http_requests"] += requests
            case_row["response_bytes"] += response_bytes
            case_operation = case_row["operations"].setdefault(
                operation,
                {
                    "http_requests": 0,
                    "response_bytes": 0,
                    "failed_operations": 0,
                    "dispositions": {},
                    "response_statuses": {},
                },
            )
            case_operation["http_requests"] += requests
            case_operation["response_bytes"] += response_bytes
            case_operation["failed_operations"] += int(not success)
            case_operation["dispositions"][disposition] = (
                case_operation["dispositions"].get(disposition, 0) + 1
            )
            if response_status_code is not None:
                status_key = str(response_status_code)
                case_operation["response_statuses"][status_key] = (
                    case_operation["response_statuses"].get(status_key, 0) + 1
                )

    # The wrapper supplies an explicit run ID for CI/local manifest runs. A
    # direct pytest invocation must still get a fresh identity: process IDs can
    # be reused across sessions, and merging those rows would corrupt cross-day
    # usage attribution. Keep the generated value process-local and never
    # derive it from a credential or filesystem path.
    run_id = os.getenv("PROVIDER_LIVE_RUN_ID", "").strip() or _PROCESS_RUN_ID
    now = datetime.now(UTC).isoformat()
    usage_scope = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip() or "unspecified"
    rows = [
        {
            "at": now,
            "run_id": run_id,
            "usage_scope": usage_scope,
            "provider": provider,
            "operations": values["operations"],
            "http_requests": values["http_requests"],
            "response_bytes": values["response_bytes"],
            # This is the provider-row status, not pytest's process-wide
            # result. Keep the latter separately for matrix diagnostics.
            "exit_status": int(values["failed_operations"] > 0),
            "failed_operations": values["failed_operations"],
            "process_exit_status": max(0, int(exit_status)),
            "response_headers": dict(values["response_headers"]),
            "operation_usage": {
                operation: dict(operation_values)
                for operation, operation_values in sorted(values["operation_usage"].items())
            },
            **({"case_usage": values["case_usage"]} if values["case_usage"] else {}),
            **({"reservations": values["reservations"]} if values.get("reservations") else {}),
        }
        for provider, values in sorted(grouped.items())
    ]
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # The write itself succeeded; a mode change failure must not erase the
        # durable usage receipt. The startup preflight still reports mode/path
        # failures before provider calls in normal live-test operation.
        pass
    _observations.clear()
    return path


def _reset_for_test() -> None:
    """Clear process-local observations for unit tests."""

    _observations.clear()
    _CURRENT_CASE_ID.set("")
