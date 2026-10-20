"""Per-attempt adapter into the shared Provider runtime.

Callers must invoke this once for each physical HTTP request (including every
redirect, retry, page, and fallback request). It deliberately accepts a
single-attempt transport callable rather than wrapping a logical refresh.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_recurring_cost import (
    ProviderRecurringCostBudget,
    ProviderRecurringCostCommitment,
)
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderPolicy,
)
from app.providers.telemetry import observe_response
from app.services.provider_quota_coordinator import account_scope_for_provider
from app.services.provider_recurring_costs import provider_recurring_cost_status
from app.services.provider_runtime import ProviderExecutionResult, execute_provider_call

T = TypeVar("T")

_ETF_OPERATIONS = frozenset({"fetch_etf_holdings_latest", "fetch_etf_holdings_for_date"})


class ETFHoldingsRouteHeldError(PermissionError):
    """The publisher route is unknown or lacks reviewed admission evidence."""


@dataclass(frozen=True)
class LoopLocalHTTPXAttempt:
    """One HTTPX request with a fresh client created inside the worker loop.

    Only configuration values are accepted, never a client instance or client
    factory, so a caller-loop AsyncClient cannot be passed into asyncio.run.
    Request arguments must be loop-neutral values, such as bytes rather than
    an async body iterator captured from another event loop. A supplied
    transport factory must create a fresh transport when called in this loop.
    """

    method: str
    url: str
    request_kwargs: dict[str, Any]
    client_kwargs: dict[str, Any]
    transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None

    async def execute(self) -> httpx.Response:
        if "follow_redirects" in self.request_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts must not follow redirects; admit each hop separately"
            )
        if "transport" in self.client_kwargs or "follow_redirects" in self.client_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts cannot override the per-attempt transport boundary"
            )
        transport = self.transport_factory() if self.transport_factory is not None else None
        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            **self.client_kwargs,
        ) as client:
            response = await client.request(
                self.method,
                self.url,
                follow_redirects=False,
                **self.request_kwargs,
            )
            await response.aread()
            return response


def _normalized_host(url: str) -> str:
    parsed = urlsplit(str(url))
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ETFHoldingsRouteHeldError("ETF holdings requests require a reviewed HTTPS host")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ETFHoldingsRouteHeldError("ETF holdings request URL is not a valid publisher URL")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ETFHoldingsRouteHeldError("ETF holdings request URL has an invalid port") from exc
    return parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")


async def _review_attempt_context(
    db: AsyncSession,
    *,
    provider_name: str,
    operation: str,
    request_url: str,
) -> tuple[DataSource, ProviderPolicy, str]:
    if operation not in _ETF_OPERATIONS:
        raise ETFHoldingsRouteHeldError("ETF holdings operation is not in the reviewed contract")
    request_host = _normalized_host(request_url)
    data_source = await db.scalar(select(DataSource).where(DataSource.name == provider_name))
    if data_source is None:
        raise ETFHoldingsRouteHeldError("ETF publisher has no shared Provider source record")
    policy = await db.scalar(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
        )
    )
    if policy is None or not policy.is_enabled:
        raise ETFHoldingsRouteHeldError("ETF publisher capability is not explicitly enabled")

    config = data_source.config if isinstance(data_source.config, dict) else {}
    review = config.get("etf_holdings_review")
    if not isinstance(review, dict):
        raise ETFHoldingsRouteHeldError("ETF publisher review evidence is missing")
    hosts = review.get("https_hosts")
    if not isinstance(hosts, list) or request_host not in {
        str(value).strip().lower().rstrip(".") for value in hosts if isinstance(value, str)
    }:
        raise ETFHoldingsRouteHeldError("ETF publisher host is not in the reviewed host allowlist")
    operation_evidence = review.get("operations")
    operation_record = (
        operation_evidence.get(operation) if isinstance(operation_evidence, dict) else None
    )
    if not isinstance(operation_record, dict) or not all(
        isinstance(operation_record.get(field), str) and operation_record[field].strip()
        for field in ("evidence_source", "evidence_version", "reviewed_at")
    ):
        raise ETFHoldingsRouteHeldError("ETF publisher operation review evidence is incomplete")

    entitlement = await db.scalar(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
        )
    )
    if entitlement is None:
        raise ETFHoldingsRouteHeldError("ETF publisher entitlement review is missing")

    quota_scope = str(policy.quota_scope or "").strip()
    account_scope_map = settings.PROVIDER_QUOTA_ACCOUNT_SCOPES
    account_scope_key = f"{provider_name}:{quota_scope}" if quota_scope else ""
    if not isinstance(account_scope_map, dict) or not (
        account_scope_key in account_scope_map or provider_name in account_scope_map
    ):
        raise ETFHoldingsRouteHeldError(
            "ETF publisher account binding is not explicitly configured"
        )
    try:
        account_scope = account_scope_for_provider(provider_name, quota_scope)
    except Exception as exc:  # noqa: BLE001 - malformed scope remains a closed route.
        raise ETFHoldingsRouteHeldError("ETF publisher account binding is invalid") from exc
    if review.get("account_scope") != account_scope:
        raise ETFHoldingsRouteHeldError(
            "ETF publisher review is bound to a different account scope"
        )

    now = datetime.now(UTC)
    digest = hashlib.sha256(account_scope.strip().encode("utf-8")).hexdigest()

    def recurring_cost_is_admitted(sync_session) -> bool:
        budget_status = provider_recurring_cost_status(sync_session)
        budget = sync_session.get(ProviderRecurringCostBudget, 1)
        commitment = sync_session.scalar(
            select(ProviderRecurringCostCommitment).where(
                ProviderRecurringCostCommitment.data_source_id == data_source.id,
                ProviderRecurringCostCommitment.environment == settings.APP_ENV.strip().lower(),
                ProviderRecurringCostCommitment.billing_account_scope_digest == digest,
            )
        )
        if not budget_status.allowed or budget is None or commitment is None:
            return False
        commitment_is_active = commitment.state == "active" and (
            commitment.ends_at is None or commitment.ends_at > now
        )
        return bool(
            commitment_is_active
            and Decimal(commitment.monthly_equivalent) == Decimal("0")
            and Decimal(commitment.amount) == Decimal("0")
            and commitment.post_trial_amount is None
        )

    if not await db.run_sync(recurring_cost_is_admitted):
        raise ETFHoldingsRouteHeldError(
            "ETF publisher lacks an active verified-free shared recurring-cost commitment"
        )
    return data_source, policy, account_scope


async def execute_etf_holdings_request_attempt(
    db: AsyncSession,
    *,
    adapter: Any,
    instrument_id: int,
    provider_symbol: str,
    operation: str,
    request_url: str,
    single_attempt: Callable[[], Any] | LoopLocalHTTPXAttempt,
) -> ProviderExecutionResult:
    """Run exactly one publisher request under the shared Provider ledger.

    A request is either a synchronous requests-style callable or a
    LoopLocalHTTPXAttempt. The latter creates its AsyncClient inside the
    Provider worker loop and disables automatic redirects, so each hop is
    separately admitted. Raw async closures are rejected before admission.
    The AsyncSession remains on its owning loop. The request runs once only
    after shared policy, entitlement, operation holds, quota, and aggregate
    recurring-cost admission succeed.
    """

    provider_name = str(getattr(adapter, "source_provider", "")).strip().lower()
    if not provider_name:
        raise ETFHoldingsRouteHeldError("ETF adapter has no bound publisher identity")
    if isinstance(single_attempt, LoopLocalHTTPXAttempt):
        if "follow_redirects" in single_attempt.request_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts must not follow redirects; admit each hop separately"
            )
        if _normalized_host(single_attempt.url) != _normalized_host(request_url):
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempt URL does not match its reviewed request host"
            )
    elif inspect.iscoroutinefunction(single_attempt) or inspect.iscoroutinefunction(
        getattr(single_attempt, "__call__", None)
    ):
        raise ETFHoldingsRouteHeldError("async HTTPX attempts must use LoopLocalHTTPXAttempt")
    await _review_attempt_context(
        db,
        provider_name=provider_name,
        operation=operation,
        request_url=request_url,
    )
    if instrument_id <= 0 or not str(provider_symbol).strip():
        raise ETFHoldingsRouteHeldError("ETF instrument and publisher symbol binding are required")

    invoke = _sync_provider_invoke(single_attempt)

    return await execute_provider_call(
        db,
        ProviderCapability.ETF_HOLDINGS,
        operation,
        instrument_id=instrument_id,
        provider_symbol=provider_symbol,
        usage_identity=provider_symbol,
        provider_name=provider_name,
        invoke=invoke,
        etf_holdings_adapters={provider_name: adapter},
        capture_response_payloads=True,
    )


def _sync_provider_invoke(
    single_attempt: Callable[[], Any] | LoopLocalHTTPXAttempt,
) -> Callable[[Any, str | None], Any]:
    """Adapt one attempt to Provider's sync callback without cross-loop waits."""

    def invoke(_adapter: Any, _symbol: str | None) -> Any:
        if isinstance(single_attempt, LoopLocalHTTPXAttempt):

            async def run_httpx_attempt() -> Any:
                response = await single_attempt.execute()
                observe_response(response)
                return response

            return asyncio.run(run_httpx_attempt())

        value = single_attempt()
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise TypeError(
                "async Provider attempts must use LoopLocalHTTPXAttempt; "
                "the sync callback cannot return an awaitable"
            )
        observe_response(value)
        return value

    return invoke
