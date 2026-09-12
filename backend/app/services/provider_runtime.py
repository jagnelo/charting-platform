from __future__ import annotations

import asyncio
import contextvars
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    marketdata_app_reviewed_plan,
    provider_positive_integer,
    provider_rate_limit_seed,
    settings,
)
from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderCapacityEvent,
    ProviderEntitlement,
    ProviderEntitlementRevision,
    ProviderHealthState,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers import (
    ensure_data_source,
    get_provider,
    list_provider_capabilities,
    provider_configuration_required,
    provider_is_configured,
    provider_missing_routing_controls,
    provider_missing_settings,
    provider_required_settings,
    provider_routing_control_settings,
    provider_supports_adjustment,
    provider_supports_instrument,
    supported_provider_names,
)
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    bounded_redact_provider_message,
    provider_retry_at_from_headers,
)
from app.providers.telemetry import activate as activate_provider_telemetry
from app.providers.telemetry import deactivate as deactivate_provider_telemetry
from app.services.provider_support import (
    SUPPORT_STATUS_SUPPORTED,
    SUPPORT_STATUS_UNKNOWN,
    SUPPORT_STATUS_UNSUPPORTED,
    get_provider_binding_ids,
    get_provider_support_map,
    record_provider_support,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

_ALPHA = Decimal("0.2")
_token_buckets: dict[tuple[str, str], tuple[tuple[int, int], TokenBucket]] = {}
_semaphores: dict[tuple[str, str], tuple[int, asyncio.Semaphore]] = {}
_DEFAULT_SCORE_FLOOR = Decimal("0")
_DEFAULT_SCORE_CEILING = Decimal("100")
_DEFAULT_LEARNED_WEIGHT = Decimal("0")
_DEFAULT_EFFECTIVE_SCORE = Decimal("0")
_DEFAULT_BASE_PRIORITY = 100

_ENTITLEMENT_FIELDS = (
    "configured_plan",
    "is_free",
    "authentication_required",
    "usage_terms",
    "redistribution_allowed",
    "quota_policy",
    "history_depth",
    "venue_coverage",
    "freshness_semantics",
    "enabled_environments",
    "effective_at",
    "review_due_at",
    "live_probe_status",
)


async def record_entitlement_revision(
    db: AsyncSession,
    entitlement: ProviderEntitlement,
    *,
    change_reason: str | None = None,
) -> ProviderEntitlementRevision:
    """Persist the current entitlement state once for its immutable revision."""
    revision = int(entitlement.revision or 1)
    existing = (
        await db.execute(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == entitlement.data_source_id,
                ProviderEntitlementRevision.capability == entitlement.capability,
                ProviderEntitlementRevision.revision == revision,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    snapshot = ProviderEntitlementRevision(
        data_source_id=entitlement.data_source_id,
        capability=entitlement.capability,
        revision=revision,
        **{
            field_name: (
                dict(getattr(entitlement, field_name) or {})
                if field_name == "quota_policy"
                else list(getattr(entitlement, field_name) or [])
                if field_name == "enabled_environments"
                else getattr(entitlement, field_name)
            )
            for field_name in _ENTITLEMENT_FIELDS
        },
        change_reason=change_reason,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive datetimes before entitlement comparisons."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(slots=True)
class ResolvedProvider:
    provider_name: str
    provider: Any
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState
    support_status: str = SUPPORT_STATUS_UNKNOWN
    has_symbol_binding: bool = False
    entitlement: ProviderEntitlement | None = None


@dataclass(slots=True)
class ProviderExecutionResult:
    provider_name: str
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState
    result: Any


class ProviderNoDataError(LookupError):
    """Raised when providers resolve successfully but none return usable data."""


class ProviderQuotaUnknownError(RuntimeError):
    """Raised when no documentation-backed quota contract is available."""


def _operation_family(operation: str) -> str:
    return operation.split(":", 1)[0].strip() or operation


def _is_positive_operation_cost(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        parsed = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return False
    return parsed.is_finite() and parsed > 0


def _positive_integer_cost(value: Any) -> int | None:
    """Return a positive integral reservation amount, otherwise ``None``."""

    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if not parsed.is_finite() or parsed <= 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


_DIMENSION_RATE_UNITS = {
    "request",
    "requests",
    "credit",
    "credits",
    "weight",
    "symbol",
    "symbols",
    "unique_symbol",
    "unique_symbols",
}
_IN_FLIGHT_UNITS = {"concurrent_requests", "concurrency"}


def _entitlement_seed(provider_name: str, capability: ProviderCapability) -> dict[str, Any]:
    """Return the reviewed free-source declaration for one capability."""
    raw = settings.PROVIDER_ENTITLEMENT_SEEDS.get(provider_name) or {}
    if not isinstance(raw, dict):
        return {}
    base = {key: value for key, value in raw.items() if key != "capabilities"}
    capability_overrides = raw.get("capabilities")
    if isinstance(capability_overrides, dict):
        override = capability_overrides.get(capability.value)
        if isinstance(override, dict):
            base.update(override)
    if provider_name == "marketdata_app":
        reviewed_plan = marketdata_app_reviewed_plan()
        if reviewed_plan is None:
            base["configured_plan"] = "unreviewed"
            base["usage_terms"] = (
                "MarketData.app plan, credits, and licensing terms require explicit account review."
            )
        else:
            plan, _ = reviewed_plan
            base["configured_plan"] = f"marketdata-{plan}-operator-reviewed"
            base["usage_terms"] = (
                f"MarketData.app {plan} account plan; provider credits and licensing terms apply."
            )
    base.setdefault(
        "live_probe_status",
        settings.PROVIDER_LIVE_PROBE_STATUS_SEEDS.get(provider_name, "not_run"),
    )
    return {
        key: value
        for key, value in base.items()
        if key
        in {
            "configured_plan",
            "is_free",
            "authentication_required",
            "usage_terms",
            "redistribution_allowed",
            "quota_policy",
            "history_depth",
            "venue_coverage",
            "freshness_semantics",
            "enabled_environments",
            "effective_at",
            "review_due_at",
            "live_probe_status",
        }
    }


def _usage_tracking_config(data_source: DataSource) -> dict[str, Any]:
    config = dict(data_source.config or {})
    tracking = config.get("usage_tracking") or {}
    return tracking if isinstance(tracking, dict) else {}


def _usage_cost_for_operation(
    data_source: DataSource,
    operation: str,
    policy: ProviderPolicy | None = None,
    *,
    operation_cost_override: int | Decimal | None = None,
) -> tuple[str, str, Decimal]:
    tracking = _usage_tracking_config(data_source)
    mode = str(tracking.get("mode") or "call_count")
    unit_label = str(tracking.get("unit_label") or "requests")
    contract = dict(policy.quota_contract or {}) if policy is not None else {}
    operation_costs = tracking.get("operation_costs") or contract.get("operation_costs") or {}
    family = _operation_family(operation)
    if operation_cost_override is not None:
        raw_cost = operation_cost_override
    elif isinstance(operation_costs, dict):
        raw_cost = operation_costs.get(family, operation_costs.get(operation))
    else:
        raw_cost = None
    if not _is_positive_operation_cost(raw_cost):
        raise ProviderQuotaUnknownError(
            f"No valid reviewed operation cost for {data_source.name}/{operation}"
        )
    cost = Decimal(str(raw_cost))
    return mode, unit_label, cost


def _dimension_costs_for_operation(
    policy: ProviderPolicy,
    data_source: DataSource,
    operation: str,
    default_units: Decimal,
) -> dict[str, int]:
    """Return conservative per-dimension reservation units for one call.

    Request/credit/weight dimensions use the operation's ordinary cost. A
    provider may declare dimensions with a different unit (for example bytes)
    and provide an explicit operation-specific upper bound in
    ``usage_tracking.dimension_costs``. Missing bounds are rejected by
    ``provider_contract_operation_cost_known`` rather than guessed here.
    """
    tracking = _usage_tracking_config(data_source)
    contract = dict(policy.quota_contract or {})
    explicit = tracking.get("dimension_costs") or contract.get("dimension_costs")
    result: dict[str, int] = {}
    family = _operation_family(operation)
    for dimension in quota_dimensions(policy):
        name = str(dimension["name"])
        unit = str(dimension.get("unit") or "").strip().lower()
        raw_map = explicit.get(name) if isinstance(explicit, dict) else None
        if unit in {"concurrent_requests", "concurrency"} and raw_map is None:
            result[name] = 1
            continue
        if raw_map is not None:
            if not isinstance(raw_map, dict):
                raise ProviderQuotaUnknownError(
                    f"No valid reviewed dimension cost for {data_source.name}/{operation}/{name}"
                )
            if not raw_map:
                # An explicitly empty map means that the dimension does not
                # apply to this operation (for example IBKR's historical
                # concurrency budget on a metadata lookup, or FINRA's async
                # download budget on a synchronous POST). Never infer a unit
                # for a dimension the reviewed contract explicitly excludes.
                result[name] = 0
                continue
            else:
                raw_value = raw_map.get(family, raw_map.get(operation))
                if isinstance(raw_value, dict):
                    if not raw_value:
                        result[name] = 0
                        continue
                    raise ProviderQuotaUnknownError(
                        f"No valid reviewed dimension cost for {data_source.name}/{operation}/{name}"
                    )
                if raw_value is not None:
                    parsed = _positive_integer_cost(raw_value)
                    if parsed is None:
                        raise ProviderQuotaUnknownError(
                            f"No valid reviewed dimension cost for {data_source.name}/{operation}/{name}"
                        )
                    result[name] = parsed
                    continue
                if unit in {"concurrent_requests", "concurrency"}:
                    # Concurrency is a release-only unit and always reserves
                    # one in-flight slot per invocation, independent of a
                    # multi-request operation's ordinary usage cost.
                    result[name] = 1
                    continue
                if contract.get("dimension_costs_required") and unit not in _DIMENSION_RATE_UNITS:
                    raise ProviderQuotaUnknownError(
                        f"No valid reviewed dimension cost for {data_source.name}/{operation}/{name}"
                    )
        result[name] = max(1, int(default_units))
    if contract.get("dimension_costs_required") and not explicit:
        return {}
    return result


def _consumed_dimension_costs(
    policy: ProviderPolicy,
    measurement: Any,
    reserved_units: dict[str, int],
) -> dict[str, int]:
    """Settle byte dimensions from observed transport, conservatively otherwise."""
    consumed: dict[str, int] = {}
    headers = {
        str(key).lower(): str(value)
        for key, value in (getattr(measurement, "response_headers", {}) or {}).items()
    }
    for dimension in quota_dimensions(policy):
        name = str(dimension["name"])
        unit = str(dimension.get("unit") or "").lower()
        raw_reserved = reserved_units.get(name, 1)
        try:
            raw_reserved_int = int(raw_reserved)
        except (TypeError, ValueError):
            raw_reserved_int = 0
        # An explicit zero means this dimension is not applicable to the
        # operation (for example an async-download budget on a synchronous
        # call). Preserve that decision during settlement instead of charging
        # the compatibility default of one unit.
        if raw_reserved_int <= 0:
            consumed[name] = 0
            continue
        reserved = raw_reserved_int
        if unit in {"byte", "bytes"}:
            # If an adapter did not emit telemetry, retain the full
            # reservation rather than under-reporting a bandwidth budget.
            observed_requests = int(getattr(measurement, "http_requests", 0) or 0)
            observed_bytes = int(getattr(measurement, "response_bytes", 0) or 0)
            consumed[name] = max(0, observed_bytes) if observed_requests else reserved
        elif (
            unit in {"credit", "credits"}
            and int(dimension.get("window_seconds", 0) or 0) == 86400
            and "marketdata.app" in str(dimension.get("source") or "").lower()
        ):
            # MarketData.app reports the charge for this response explicitly.
            # Use it when it is a non-negative integer; otherwise retain the
            # pre-call reservation rather than guessing from response size.
            try:
                observed = int(headers["x-api-ratelimit-consumed"])
            except (KeyError, TypeError, ValueError):
                observed = None
            consumed[name] = observed if observed is not None and observed >= 0 else reserved
        else:
            consumed[name] = reserved
    return consumed


def _observed_dimension_totals(policy: ProviderPolicy, measurement: Any) -> dict[str, int]:
    """Translate provider-native cumulative credit headers into safe totals.

    Twelve Data returns the current credit usage and remaining credits after
    each request. Tradier returns an allowed/used/available token-window
    snapshot, and Binance returns cumulative one-minute request weight. Each
    observation is restricted to its provider-specific contract shape; a
    header that does not prove the configured limit is kept as telemetry but
    cannot safely alter quota accounting.
    """

    headers = {
        str(key).lower(): str(value)
        for key, value in (getattr(measurement, "response_headers", {}) or {}).items()
    }
    try:
        used = int(headers["api-credits-used"])
        left = int(headers["api-credits-left"])
    except (KeyError, TypeError, ValueError):
        used = left = None
    if used is not None and (used < 0 or left is None or left < 0):
        used = left = None
    totals: dict[str, int] = {}
    for dimension in quota_dimensions(policy):
        name = str(dimension["name"])
        source = str(dimension.get("source") or "").lower()
        unit = str(dimension.get("unit") or "").lower()
        limit = int(dimension["limit"])
        window_seconds = int(dimension["window_seconds"])
        if (
            unit in {"credit", "credits"}
            and window_seconds == 60
            and "twelvedata.com" in source
        ):
            if used is not None and left is not None and used + left == limit:
                totals[name] = min(used, limit)
            continue
        if (
            unit in {"request", "requests"}
            and window_seconds == 60
            and "tradier.com" in source
        ):
            try:
                allowed = int(headers["x-ratelimit-allowed"])
                token_used = int(headers["x-ratelimit-used"])
                available = int(headers["x-ratelimit-available"])
            except (KeyError, TypeError, ValueError):
                continue
            if (
                allowed == limit
                and token_used >= 0
                and available >= 0
                and token_used + available == allowed
            ):
                totals[name] = min(token_used, limit)
            continue
        if unit == "weight" and window_seconds == 60 and "binance.com" in source:
            try:
                weight_used = int(headers["x-mbx-used-weight-1m"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= weight_used <= limit:
                totals[name] = weight_used
            continue
        if (
            unit in {"request", "requests"}
            and window_seconds == 60
            and "about-market-data-api" in source
            and "alpaca.markets" in source
        ):
            # Alpaca's market-data responses expose the current request
            # window on X-RateLimit-Limit/Remaining/Reset. Reconcile only
            # when the response proves the exact reviewed Basic/Algo limit;
            # Broker API correspondent limits are deliberately excluded from
            # this market-data contract because Alpaca does not publish a
            # fixed numeric Broker API allowance.
            try:
                header_limit = int(headers["x-ratelimit-limit"])
                remaining = int(headers["x-ratelimit-remaining"])
            except (KeyError, TypeError, ValueError):
                continue
            if header_limit == limit and 0 <= remaining <= header_limit:
                totals[name] = header_limit - remaining
            continue
        if (
            unit in {"credit", "credits"}
            and window_seconds == 86400
            and "marketdata.app" in source
        ):
            try:
                header_limit = int(headers["x-api-ratelimit-limit"])
                remaining = int(headers["x-api-ratelimit-remaining"])
            except (KeyError, TypeError, ValueError):
                continue
            # Remaining credits may be negative after a provider permits a
            # request with only one credit left but the response costs more.
            # Preserve that overspend as cumulative usage; never let a stale
            # or mismatched limit alter the local window.
            if header_limit == limit and remaining <= header_limit:
                totals[name] = max(0, header_limit - remaining)
            continue
        if (
            unit in {"request", "requests"}
            and "bybit-exchange.github.io" in source
            and window_seconds == 5
        ):
            # Bybit exposes the endpoint/UID limit and remaining status on
            # every V5 response. Reconcile only when the response confirms
            # the exact reviewed coarse contract; endpoint- and UID-specific
            # constraints remain separately untracked and therefore keep this
            # provider non-routable until those dimensions are modeled.
            try:
                header_limit = int(headers["x-bapi-limit"])
                remaining = int(headers["x-bapi-limit-status"])
            except (KeyError, TypeError, ValueError):
                continue
            if header_limit == limit and 0 <= remaining <= header_limit:
                totals[name] = header_limit - remaining
            continue
        if (
            unit in {"request", "requests"}
            and "gate.com/docs/developers/apiv4/en/" in source
            and window_seconds == 1
        ):
            # Gate documents a 5-qps/IP limit for each public TradFi stock
            # endpoint. The durable capability window intentionally applies
            # the same limit across the read-only stock capability, which is
            # conservative when multiple documented endpoints are polled at
            # once. Response counters are observational only; they are not a
            # prerequisite because the published contract is static.
            try:
                header_limit = int(headers["x-ratelimit-limit"])
                remaining = int(headers["x-ratelimit-remaining"])
            except (KeyError, TypeError, ValueError):
                continue
            if header_limit == limit and 0 <= remaining <= header_limit:
                totals[name] = header_limit - remaining
    return totals


def provider_contract_operation_cost_known(
    policy: ProviderPolicy,
    data_source: DataSource,
    operation: str | None = None,
    operation_cost_override: int | Decimal | None = None,
    usage_identity: str | None = None,
) -> bool:
    """Return whether a quota contract can be safely charged for this call.

    Every routable provider operation must have an explicit reviewed cost (or
    a caller-supplied estimate). Providers whose allowance is weighted per
    endpoint, whose contract explicitly requires credit costs, or whose
    operation map is incomplete must not silently fall back to one request ==
    one unit. They remain visible to operators but are non-routable until the
    operation-cost map is populated.
    """

    contract = dict(policy.quota_contract or {})
    tracking = _usage_tracking_config(data_source)
    costs = tracking.get("operation_costs") or contract.get("operation_costs")
    # A dimension-cost contract is also operation-specific: a request may
    # reserve a different unit count for a byte/record budget than for the
    # request-rate dimension. Do not infer a one-request charge for any
    # provider just because its contract happens to use a simple request unit.
    if operation_cost_override is None and (not isinstance(costs, dict) or not costs):
        return False
    if operation is None:
        # A provider may have a cost table while the caller has not named the
        # operation.  Selecting it anyway would silently charge one request
        # for an unknown endpoint weight, so generic workload selection stays
        # fail-closed.
        return False
    family = _operation_family(operation)
    if operation_cost_override is not None:
        if not _is_positive_operation_cost(operation_cost_override):
            return False
    else:
        cost_key = family if family in costs else operation if operation in costs else None
        if cost_key is None or not _is_positive_operation_cost(costs[cost_key]):
            return False
    if contract.get("dimension_costs_required"):
        dimension_costs = tracking.get("dimension_costs") or contract.get("dimension_costs")
        if not isinstance(dimension_costs, dict):
            return False
        for dimension in quota_dimensions(policy):
            raw = dimension_costs.get(str(dimension["name"]))
            unit = str(dimension.get("unit") or "").lower()
            if unit in {"concurrent_requests", "concurrency"}:
                continue
            if raw is None:
                if unit in _DIMENSION_RATE_UNITS:
                    continue
                return False
            if not isinstance(raw, dict):
                return False
            if not raw:
                if unit in _DIMENSION_RATE_UNITS:
                    continue
                return False
            if family in raw:
                dimension_cost = raw[family]
            elif operation in raw:
                dimension_cost = raw[operation]
            else:
                if unit in _DIMENSION_RATE_UNITS:
                    continue
                return False
            if isinstance(dimension_cost, dict):
                if not dimension_cost and unit in _DIMENSION_RATE_UNITS:
                    continue
                return False
            if _positive_integer_cost(dimension_cost) is None:
                return False
    if any(
        str(dimension.get("unit") or "").lower()
        in {"symbol", "symbols", "unique_symbol", "unique_symbols"}
        for dimension in quota_dimensions(policy)
    ) and not str(usage_identity or "").strip():
        return False
    return True


class TokenBucket:
    def __init__(self, rate_per_minute: int, burst_capacity: int):
        # A zero/negative value is an invalid provider contract, not a signal
        # to invent a one-token fallback.  Normal policy admission validates
        # these fields, but this guard also protects direct/stale policy rows.
        if (
            isinstance(rate_per_minute, bool)
            or not isinstance(rate_per_minute, int)
            or rate_per_minute <= 0
            or isinstance(burst_capacity, bool)
            or not isinstance(burst_capacity, int)
            or burst_capacity <= 0
        ):
            raise ProviderQuotaUnknownError(
                "provider minute bucket requires positive integer rate and burst limits"
            )
        self.rate_per_second = rate_per_minute / 60.0
        self.capacity = burst_capacity
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def try_acquire(self, units: int = 1) -> bool:
        units = max(int(units), 1)
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
        if self.tokens < units:
            return False
        self.tokens -= units
        return True


def _ewma(previous: Decimal, current: Decimal) -> Decimal:
    if previous == Decimal("0"):
        return current
    return (previous * (Decimal("1") - _ALPHA)) + (current * _ALPHA)


def _capability_seed_order() -> dict[ProviderCapability, list[str]]:
    seeds: dict[ProviderCapability, list[str]] = {
        ProviderCapability.INSTRUMENT_SEARCH: [settings.DEFAULT_METADATA_PROVIDER],
        ProviderCapability.INSTRUMENT_METADATA: [settings.DEFAULT_METADATA_PROVIDER],
        ProviderCapability.PRICE_HISTORY: [settings.DEFAULT_MARKET_DATA_PROVIDER],
        ProviderCapability.LATEST_PRICE: [settings.DEFAULT_MARKET_DATA_PROVIDER],
        ProviderCapability.INSTRUMENT_EVENTS: [settings.DEFAULT_EVENT_PROVIDER],
        ProviderCapability.INSTRUMENT_IDENTIFIERS: list(settings.IDENTIFIER_PROVIDER_PRIORITY),
        ProviderCapability.UNIVERSE_DISCOVERY: [settings.DEFAULT_DISCOVERY_PROVIDER],
        ProviderCapability.OPTION_CHAIN: [settings.DEFAULT_OPTIONS_PROVIDER],
        ProviderCapability.OPTION_QUOTE_HISTORY: list(
            settings.OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY
        )
        or [settings.DEFAULT_OPTIONS_PROVIDER],
        ProviderCapability.TOKENIZED_ASSETS: list(settings.TOKENIZED_PROVIDER_PRIORITY),
    }
    for key, providers in settings.PROVIDER_CHAIN_SEEDS.items():
        try:
            capability = ProviderCapability(key)
        except ValueError:
            continue
        seeds[capability] = providers
    return seeds


def _base_priority(provider_name: str, ordered_providers: list[str]) -> int:
    try:
        return (ordered_providers.index(provider_name) + 1) * 10
    except ValueError:
        return 999


def _decimal_or(value: Decimal | None, default: Decimal) -> Decimal:
    return default if value is None else value


def _int_or(value: int | None, default: int) -> int:
    return default if value is None else value


def _effective_score(policy: ProviderPolicy, health: ProviderHealthState) -> Decimal:
    base_priority = _int_or(policy.base_priority, _DEFAULT_BASE_PRIORITY)
    score_floor = _decimal_or(policy.score_floor, _DEFAULT_SCORE_FLOOR)
    score_ceiling = _decimal_or(policy.score_ceiling, _DEFAULT_SCORE_CEILING)
    base_score = Decimal(max(0, 100 - base_priority))
    if not policy.auto_weight_enabled:
        return max(score_floor, min(score_ceiling, base_score))

    success_rate = health.ewma_success_rate or Decimal("0")
    completeness = health.ewma_completeness or Decimal("0")
    freshness = health.ewma_freshness or Decimal("0")
    consistency = health.ewma_consistency or Decimal("0")
    learned_weight = _decimal_or(policy.learned_weight, _DEFAULT_LEARNED_WEIGHT)
    latency_ms = health.ewma_latency_ms or Decimal("0")
    latency_penalty = min(Decimal("30"), latency_ms / Decimal("1000"))
    health_bonus = (
        (success_rate * Decimal("25"))
        + (completeness * Decimal("20"))
        + (freshness * Decimal("10"))
        + (consistency * Decimal("10"))
        - latency_penalty
    )
    candidate = base_score + learned_weight + health_bonus
    return max(score_floor, min(score_ceiling, candidate))


def _apply_policy_defaults(
    policy: ProviderPolicy,
    *,
    provider_name: str,
    providers: list[str],
    freshness_seconds: int,
    rate_seed: dict[str, Any],
) -> None:
    if not policy.is_pinned:
        policy.base_priority = _base_priority(provider_name, providers)
    # Quota and concurrency values are external-provider facts, not local
    # tuning defaults.  Leave them NULL when the seed does not explicitly
    # declare a documented value; the resolver will then fail closed.
    for field_name in (
        "max_concurrency",
        "tokens_per_minute",
        "burst_capacity",
        "cooldown_seconds",
    ):
        if getattr(policy, field_name) is None and rate_seed.get(field_name) is not None:
            setattr(policy, field_name, rate_seed[field_name])
    seeded_contract = rate_seed.get("quota_contract")
    if seeded_contract:
        # Refresh contracts generated from the same repository/provider source
        # when deployment configuration changes (for example a reviewed
        # Tiingo byte-bound map is added). Never overwrite a contract whose
        # provenance differs or whose policy is explicitly pinned for manual
        # operator control.
        same_seed_source = policy.quota_source == rate_seed.get("quota_source")
        # New rows receive the seed contract at construction time below. Do
        # not treat an existing NULL contract as a missing default: an
        # operator may have deliberately removed it to quarantine routing,
        # and diagnostics must not silently restore admission on the next
        # seed pass. Existing, seed-owned contracts may still refresh when
        # deployment configuration changes.
        contract_refreshed = (
            policy.quota_contract is not None
            and same_seed_source
            and not policy.is_pinned
            and policy.quota_contract != seeded_contract
        )
        if contract_refreshed:
            policy.quota_contract = dict(seeded_contract)
            policy.quota_verified_at = (
                datetime.now(UTC)
                if not quota_contract_missing_dimensions(policy)
                else None
            )
    # Do not backfill missing policy-level provenance on an existing row. A
    # scope/source removal may be an intentional operator quarantine, and
    # restoring the seed here would make a subsequent diagnostics read appear
    # verified again without an explicit replacement contract. New rows get
    # both fields in ``seed_provider_runtime`` when they are created.
    if policy.quota_contract:
        contract_missing = quota_contract_missing_dimensions(policy)
        if contract_missing:
            # Existing rows may predate the explicit contract gate and carry
            # a stale timestamp. Unknown/untracked dimensions are evidence of
            # an unresolved contract, never a verified admission record.
            policy.quota_verified_at = None
        elif policy.quota_verified_at is None:
            policy.quota_verified_at = datetime.now(UTC)
    policy.freshness_seconds = _int_or(policy.freshness_seconds, freshness_seconds)
    if policy.score_floor is None:
        policy.score_floor = _DEFAULT_SCORE_FLOOR
    if policy.score_ceiling is None:
        policy.score_ceiling = _DEFAULT_SCORE_CEILING
    if policy.learned_weight is None:
        policy.learned_weight = _DEFAULT_LEARNED_WEIGHT
    if policy.effective_score is None:
        policy.effective_score = _DEFAULT_EFFECTIVE_SCORE


def _local_control_group(policy: ProviderPolicy, *, include_concurrency: bool = False) -> str:
    """Return the reviewed scope used by process-local admission controls.

    Durable reservations are authoritative, but the in-process token bucket and
    semaphore are still useful as an early back-pressure layer. They must use
    the same explicitly reviewed grouping as the durable contract; otherwise a
    provider-wide allowance would be multiplied once per capability inside one
    worker process. Request/credit/weight dimensions participate in the token
    bucket, while callers creating a semaphore may also include concurrent-
    request dimensions. A contract without a relevant dimension retains the
    capability compatibility key and therefore cannot accidentally share an
    unrelated local limiter.
    """

    capability = str(getattr(policy.capability, "value", policy.capability))
    groups: set[str] = set()
    for dimension in quota_dimensions(policy):
        unit = str(dimension.get("unit") or "").strip().lower()
        if unit not in _DIMENSION_RATE_UNITS and not (
            include_concurrency and unit in _IN_FLIGHT_UNITS
        ):
            continue
        if unit in _IN_FLIGHT_UNITS:
            configured = str(dimension.get("quota_group") or "").strip()
            groups.add(configured or capability)
            continue
        # ``tokens_per_minute`` is the legacy process-local bucket. Prefer a
        # provider dimension that represents that same short rate window and
        # avoid using a monthly/rolling identity or bandwidth pool as a token
        # bucket key.
        try:
            window_seconds = int(dimension.get("window_seconds") or 0)
        except (TypeError, ValueError):
            continue
        if window_seconds <= 60:
            configured = str(dimension.get("quota_group") or "").strip()
            groups.add(configured or capability)
    return "|".join(sorted(groups)) or capability


def _bucket_key(provider_name: str, policy: ProviderPolicy) -> tuple[str, str]:
    return (provider_name, _local_control_group(policy))


def _get_bucket(policy: ProviderPolicy, provider_name: str) -> TokenBucket:
    if (
        policy.tokens_per_minute is None
        or policy.burst_capacity is None
        or isinstance(policy.tokens_per_minute, bool)
        or isinstance(policy.burst_capacity, bool)
        or policy.tokens_per_minute <= 0
        or policy.burst_capacity <= 0
    ):
        raise ProviderQuotaUnknownError(
            f"{provider_name}/{policy.capability.value} has no verified positive minute bucket"
        )
    key = _bucket_key(provider_name, policy)
    config = (policy.tokens_per_minute, policy.burst_capacity)
    cached = _token_buckets.get(key)
    if cached is None or cached[0] != config:
        bucket = TokenBucket(policy.tokens_per_minute, policy.burst_capacity)
        _token_buckets[key] = (config, bucket)
        return bucket
    bucket = cached[1]
    return bucket


def _get_semaphore(policy: ProviderPolicy, provider_name: str) -> asyncio.Semaphore:
    # Serialising an unknown-concurrency provider is a local safety measure,
    # not a claim about the vendor's entitlement.  The external quota contract
    # remains the source of truth for admission and is never populated with 1.
    configured_concurrency = (
        policy.max_concurrency if policy.max_concurrency and policy.max_concurrency > 0 else 1
    )
    key = (provider_name, _local_control_group(policy, include_concurrency=True))
    cached = _semaphores.get(key)
    if cached is None or cached[0] != configured_concurrency:
        sem = asyncio.Semaphore(configured_concurrency)
        _semaphores[key] = (configured_concurrency, sem)
        return sem
    sem = cached[1]
    return sem


def quota_dimensions(policy: ProviderPolicy) -> list[dict[str, Any]]:
    """Return only complete, positive, explicitly documented dimensions.

    A partial contract is not safer than an unknown contract: silently
    discarding one malformed dimension could admit requests that exceed the
    provider's real allowance. Require reset semantics plus source/scope/unit
    evidence for every declared dimension before routing.
    """

    contract = policy.quota_contract or {}
    if not isinstance(contract, dict) or not str(contract.get("reset") or "").strip():
        return []
    dimensions = contract.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        return []
    result: list[dict[str, Any]] = []
    for item in dimensions:
        if not isinstance(item, dict):
            return []
        limit = provider_positive_integer(item.get("limit"))
        window_seconds = provider_positive_integer(item.get("window_seconds"))
        if limit is None or window_seconds is None:
            return []
        if (
            not str(item.get("name") or "").strip()
            or not str(item.get("unit") or "").strip()
            or not str(item.get("source") or "").strip()
            or not str(item.get("scope") or policy.quota_scope or "").strip()
        ):
            return []
        # A quota group is optional for backward compatibility, but an
        # explicitly supplied value must be non-blank.  Blank grouping would
        # silently collapse unrelated capabilities into an ambiguous bucket.
        if "quota_group" in item and not str(item.get("quota_group") or "").strip():
            return []
        result.append(
            {
                **item,
                "name": str(item["name"]),
                "limit": limit,
                "window_seconds": window_seconds,
                "unit": str(item.get("unit") or "requests"),
                "scope": str(item.get("scope") or policy.quota_scope or "unknown"),
            }
        )
    return result


def quota_contract_missing_dimensions(policy: ProviderPolicy) -> list[str]:
    """Return exact quota-contract fields that prevent safe admission."""

    contract = policy.quota_contract
    if not isinstance(contract, dict):
        return ["quota_contract", "quota_scope", "quota_source"]

    missing: list[str] = []
    # The policy-level provenance is part of the reviewed replacement
    # contract.  Dimension-level sources alone do not establish which
    # account/entitlement scope the policy represents, nor which reviewed
    # contract the runtime is allowed to enforce.  Keep this check in the
    # runtime admission path as well as the admin PATCH validator so policies
    # restored from an older database or edited outside the API fail closed.
    if not str(policy.quota_scope or "").strip():
        missing.append("quota_scope")
    if not str(policy.quota_source or "").strip():
        missing.append("quota_source")
    unknown_dimensions = contract.get("unknown_dimensions")
    if isinstance(unknown_dimensions, list):
        for item in unknown_dimensions:
            name = str(item or "unknown").strip()
            if name:
                missing.append(f"quota_contract.unknown_dimensions.{name}")
    untracked = contract.get("untracked_constraints")
    if isinstance(untracked, list):
        for item in untracked:
            if isinstance(item, dict):
                name = str(item.get("name") or "unknown").strip()
            else:
                name = str(item or "unknown").strip()
            missing.append(f"quota_contract.untracked_constraints.{name}")
    if not str(contract.get("reset") or "").strip():
        missing.append("quota_contract.reset")
    dimensions = contract.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        missing.append("quota_contract.dimensions")
        return missing

    for index, item in enumerate(dimensions):
        prefix = f"quota_contract.dimensions[{index}]"
        if not isinstance(item, dict):
            missing.append(prefix)
            continue
        for field_name in ("name", "limit", "window_seconds", "unit", "scope", "source"):
            value = item.get(field_name)
            if field_name in {"limit", "window_seconds"}:
                valid = provider_positive_integer(value) is not None
            else:
                valid = bool(str(value or "").strip())
            if not valid:
                missing.append(f"{prefix}.{field_name}")
    return missing


def provider_contract_operation_costs_configured(
    policy: ProviderPolicy, data_source: DataSource
) -> bool:
    """Whether a weighted/credit contract has an operation-cost map."""

    contract = dict(policy.quota_contract or {})
    if contract.get("dimension_costs_required"):
        tracking = _usage_tracking_config(data_source)
        dimension_costs = tracking.get("dimension_costs") or contract.get("dimension_costs")
        operation_costs = tracking.get("operation_costs") or contract.get("operation_costs")
        return bool(
            isinstance(operation_costs, dict)
            and operation_costs
            and isinstance(dimension_costs, dict)
        )
    if not (contract.get("dynamic_endpoint_weights") or contract.get("operation_costs_required")):
        return True
    tracking = _usage_tracking_config(data_source)
    costs = tracking.get("operation_costs") or contract.get("operation_costs")
    return bool(isinstance(costs, dict) and costs)


def policy_has_known_quota(policy: ProviderPolicy) -> bool:
    """Whether this policy has a complete contract suitable for routing."""

    # Keep the single completeness predicate authoritative.  In particular,
    # this includes policy-level scope/source provenance and prevents a
    # complete-looking JSON contract loaded from an older or externally edited
    # row from bypassing the same fail-closed checks used by admin updates.
    return not quota_contract_missing_dimensions(policy) and bool(quota_dimensions(policy))


def _retry_at_from_headers(headers: Any, *, now: datetime | None = None) -> datetime | None:
    """Parse standard retry/reset headers without inventing a provider delay."""

    return provider_retry_at_from_headers(headers, now=now)


def provider_rate_limit_error(
    provider_name: str, exc: Exception, *, scope: str | None = None
) -> ProviderRateLimitError | None:
    """Convert an HTTP 429/418/quota response to a typed capacity error."""

    if isinstance(exc, ProviderRateLimitError):
        if exc.scope is None:
            exc.scope = scope
        return exc
    response = exc.response if isinstance(exc, httpx.HTTPStatusError) else None
    status_code = getattr(response, "status_code", None)
    message = str(exc)
    lower = message.lower()
    is_quota = status_code in {418, 429} or any(
        marker in lower
        for marker in (
            "rate limit",
            "rate_limit",
            "too many requests",
            "quota exceeded",
            "quota limit",
        )
    )
    if not is_quota:
        return None
    headers = dict(getattr(response, "headers", {}) or {})
    return ProviderRateLimitError(
        provider_name,
        message or f"{provider_name} rate limit exceeded",
        retry_at=_retry_at_from_headers(headers),
        status_code=status_code,
        scope=scope,
        headers=headers,
    )


def _capacity_response_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Keep only non-sensitive rate-limit headers in durable capacity evidence."""

    if not headers:
        return {}
    allowed = {
        "retry-after",
        "api-credits-request",
        "api-credits-used",
        "api-credits-left",
        "x-api-ratelimit-limit",
        "x-api-ratelimit-remaining",
        "x-api-ratelimit-reset",
        "x-api-ratelimit-consumed",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-ratelimit-allowed",
        "x-ratelimit-used",
        "x-ratelimit-available",
        "x-ratelimit-expiry",
        "x-rate-limit-limit",
        "x-rate-limit-remaining",
        "x-rate-limit-reset",
        "x-mbx-used-weight-1m",
        "x-mbx-order-count-1m",
        "x-bapi-limit",
        "x-bapi-limit-status",
        "x-bapi-limit-reset-timestamp",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
    }
    return {
        str(key).lower(): str(value)[:240]
        for key, value in headers.items()
        if str(key).lower() in allowed
    }


async def seed_provider_runtime(db: AsyncSession) -> None:
    ordered = _capability_seed_order()
    for provider_name in supported_provider_names():
        await ensure_data_source(db, provider_name)

    capability_providers: dict[ProviderCapability, list[str]] = {
        capability: [] for capability in ProviderCapability
    }
    for provider_name in supported_provider_names():
        provider_capabilities = set(list_provider_capabilities(provider_name))
        for capability in ProviderCapability:
            if capability.value in provider_capabilities:
                capability_providers[capability].append(provider_name)

    # Provider adapters can lose a capability between deployments while the
    # policy row remains in the database. Disable those stale rows during the
    # normal seed pass so diagnostics and future resolution agree with the
    # registry; resolution also applies the same check defensively.
    existing_policies = (
        await db.execute(select(ProviderPolicy, DataSource).join(DataSource))
    ).all()
    for policy, data_source in existing_policies:
        if policy.capability.value not in set(
            list_provider_capabilities(data_source.name)
            if data_source.name in supported_provider_names()
            else []
        ):
            policy.is_enabled = False

    for capability, supported_providers in capability_providers.items():
        preferred_order = ordered.get(capability, [])
        providers = preferred_order + [
            provider_name
            for provider_name in supported_providers
            if provider_name not in preferred_order
        ]
        for provider_name in providers:
            data_source = await ensure_data_source(db, provider_name)
            entitlement_seed = _entitlement_seed(provider_name, capability)
            policy = (
                await db.execute(
                    select(ProviderPolicy).where(
                        ProviderPolicy.data_source_id == data_source.id,
                        ProviderPolicy.capability == capability,
                    )
                )
            ).scalar_one_or_none()
            rate_seed = provider_rate_limit_seed(provider_name)
            freshness = settings.PROVIDER_FRESHNESS_SEEDS.get(
                capability.value,
                3600
                if capability
                not in {ProviderCapability.PRICE_HISTORY, ProviderCapability.LATEST_PRICE}
                else 300,
            )
            if policy is None:
                policy = ProviderPolicy(
                    data_source_id=data_source.id,
                    capability=capability,
                    is_enabled=True,
                    base_priority=_base_priority(provider_name, providers),
                    max_concurrency=rate_seed.get("max_concurrency"),
                    tokens_per_minute=rate_seed.get("tokens_per_minute"),
                    burst_capacity=rate_seed.get("burst_capacity"),
                    cooldown_seconds=rate_seed.get("cooldown_seconds"),
                    quota_contract=rate_seed.get("quota_contract"),
                    quota_scope=rate_seed.get("quota_scope"),
                    quota_source=rate_seed.get("quota_source"),
                    quota_verified_at=None,
                    freshness_seconds=freshness,
                )
                if rate_seed.get("quota_contract") and not quota_contract_missing_dimensions(policy):
                    policy.quota_verified_at = datetime.now(UTC)
                db.add(policy)
            entitlement = (
                await db.execute(
                    select(ProviderEntitlement).where(
                        ProviderEntitlement.data_source_id == data_source.id,
                        ProviderEntitlement.capability == capability,
                    )
                )
            ).scalar_one_or_none()
            entitlement_was_new = entitlement is None
            if entitlement is None:
                entitlement = ProviderEntitlement(
                    data_source_id=data_source.id,
                    capability=capability,
                    configured_plan=str(entitlement_seed.get("configured_plan") or "unreviewed"),
                    # Unknown terms must never become an implicitly usable
                    # free source. Only an explicit entitlement seed opts a
                    # capability into a runtime chain.
                    is_free=bool(entitlement_seed.get("is_free", False)),
                    authentication_required=bool(
                        entitlement_seed.get("authentication_required", False)
                    ),
                    usage_terms=entitlement_seed.get("usage_terms"),
                    redistribution_allowed=bool(
                        entitlement_seed.get("redistribution_allowed", False)
                    ),
                    quota_policy=dict(entitlement_seed.get("quota_policy") or {}),
                    history_depth=entitlement_seed.get("history_depth"),
                    venue_coverage=entitlement_seed.get("venue_coverage"),
                    freshness_semantics=entitlement_seed.get("freshness_semantics"),
                    enabled_environments=list(entitlement_seed.get("enabled_environments") or []),
                    effective_at=entitlement_seed.get("effective_at"),
                    review_due_at=entitlement_seed.get("review_due_at"),
                    live_probe_status=str(entitlement_seed.get("live_probe_status") or "not_run"),
                )
                db.add(entitlement)
                await db.flush()
            if rate_seed.get("quota_contract"):
                quota_policy = dict(entitlement.quota_policy or {})
                quota_policy.setdefault("contract", dict(rate_seed["quota_contract"]))
                entitlement.quota_policy = quota_policy
            repository_seed_plans = {
                "unreviewed",
                "free-forever",
                "account-plan-review-required",
            }
            if (
                not entitlement_was_new
                and str(entitlement.configured_plan or "").strip().lower()
                in repository_seed_plans
                and entitlement_seed
            ):
                # Upgrade rows created by older builds without overwriting an
                # operator-reviewed entitlement.
                prior_values = {
                    field_name: getattr(entitlement, field_name) for field_name in entitlement_seed
                }
                for field_name, value in entitlement_seed.items():
                    setattr(entitlement, field_name, value)
                if any(
                    prior_values[field_name] != value
                    for field_name, value in entitlement_seed.items()
                ):
                    entitlement.revision = int(entitlement.revision or 1) + 1
            elif (
                not entitlement_was_new
                and str(entitlement.live_probe_status or "not_run").strip().lower()
                not in {"passed", "not_required"}
                and str(entitlement_seed.get("live_probe_status") or "not_run")
                in {"passed", "not_required"}
            ):
                # Promote only repository-recorded positive evidence. Never
                # downgrade or overwrite an operator-managed passing status.
                entitlement.live_probe_status = str(entitlement_seed["live_probe_status"])
                entitlement.revision = int(entitlement.revision or 1) + 1
            elif entitlement.revision is None or entitlement.revision < 1:
                entitlement.revision = 1
            if entitlement.revision is None or entitlement.revision < 1:
                entitlement.revision = 1
            await record_entitlement_revision(db, entitlement, change_reason="runtime_seed")
            _apply_policy_defaults(
                policy,
                provider_name=provider_name,
                providers=providers,
                freshness_seconds=freshness,
                rate_seed=rate_seed,
            )

            health = (
                await db.execute(
                    select(ProviderHealthState).where(
                        ProviderHealthState.data_source_id == data_source.id,
                        ProviderHealthState.capability == capability,
                    )
                )
            ).scalar_one_or_none()
            if health is None:
                health = ProviderHealthState(
                    data_source_id=data_source.id,
                    capability=capability,
                    observed_score=Decimal("0"),
                )
                db.add(health)
            if health.ewma_latency_ms is None:
                health.ewma_latency_ms = Decimal("0")
            if health.ewma_success_rate is None:
                health.ewma_success_rate = Decimal("1")
            if health.ewma_completeness is None:
                health.ewma_completeness = Decimal("1")
            if health.ewma_freshness is None:
                health.ewma_freshness = Decimal("1")
            if health.ewma_consistency is None:
                health.ewma_consistency = Decimal("1")
            if health.observed_score is None:
                health.observed_score = Decimal("0")
            policy.effective_score = _effective_score(policy, health)
            health.observed_score = policy.effective_score

    await db.flush()


async def resolve_provider_chain(
    db: AsyncSession,
    capability: ProviderCapability,
    *,
    instrument_id: int | None = None,
    operation: str | None = None,
    operation_cost_overrides: dict[str, int] | None = None,
    adjusted: bool | None = None,
) -> list[ResolvedProvider]:
    await seed_provider_runtime(db)
    rows = (
        await db.execute(
            select(ProviderPolicy, ProviderHealthState, DataSource, ProviderEntitlement)
            .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
            .join(
                ProviderEntitlement,
                (ProviderEntitlement.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderEntitlement.capability == ProviderPolicy.capability),
            )
            .join(
                ProviderHealthState,
                (ProviderHealthState.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderHealthState.capability == ProviderPolicy.capability),
            )
            .where(
                ProviderPolicy.capability == capability,
                ProviderPolicy.is_enabled.is_(True),
                or_(
                    ProviderEntitlement.is_free.is_(True),
                    settings.ALLOW_PAID_PROVIDER_ROUTING,
                ),
            )
        )
    ).all()
    now = datetime.now(UTC)
    support_map = (
        await get_provider_support_map(db, instrument_id, capability)
        if instrument_id is not None
        else {}
    )
    binding_ids = (
        await get_provider_binding_ids(db, instrument_id) if instrument_id is not None else set()
    )
    instrument_routing: tuple[str, str] | None = None
    if instrument_id is not None:
        instrument_routing = (
            await db.execute(
                select(AssetClass.name, InstrumentType.name)
                .join(InstrumentType, InstrumentType.asset_class_id == AssetClass.id)
                .join(Instrument, Instrument.instrument_type_id == InstrumentType.id)
                .where(Instrument.id == instrument_id)
            )
        ).one_or_none()
    resolved: list[ResolvedProvider] = []
    current_environment = settings.APP_ENV.strip().lower()
    for policy, health, data_source, entitlement in rows:
        if capability == ProviderCapability.PRICE_HISTORY and not provider_supports_adjustment(
            data_source.name, adjusted
        ):
            continue
        # ``ALLOW_PAID_PROVIDER_ROUTING`` only controls whether a *reviewed*
        # paid plan may participate.  It must never turn an unreviewed
        # descriptor (the default for optional adapters) into a usable route.
        # Keep this guard in the resolver rather than relying only on the
        # ``is_free`` query predicate so a broad paid-routing switch cannot
        # bypass the operator entitlement review boundary.
        configured_plan = str(entitlement.configured_plan or "").strip().lower()
        if not configured_plan or configured_plan == "unreviewed":
            continue
        if str(entitlement.live_probe_status or "not_run").strip().lower() not in {
            "passed",
            "not_required",
        }:
            continue
        if (
            provider_configuration_required(data_source.name)
            and not provider_is_configured(data_source.name, operation=operation)
        ) or (
            entitlement.authentication_required
            and not provider_is_configured(data_source.name, operation=operation)
        ):
            continue
        # Non-secret provider safety controls (reviewed byte bounds, operation
        # costs, terms/polling gates, and similar provider-specific admission
        # inputs) are part of routing eligibility. Diagnostics still expose
        # the exact missing names, but a configured credential/source alone
        # must never bypass these controls.
        routing_controls = provider_missing_routing_controls(data_source.name, operation)
        # An operation-less chain is used by capability discovery and ordering
        # tests; it cannot claim a response-priced endpoint. Defer Alpaca's
        # event-only page-bound gate until the named operation is resolved.
        if operation is None and data_source.name == "alpaca":
            routing_controls = []
        if routing_controls:
            continue
        if (
            data_source.name == "yfinance"
            and capability
            not in {ProviderCapability.OPTION_CHAIN, ProviderCapability.OPTION_QUOTE_HISTORY}
            and not settings.ENABLE_LEGACY_YFINANCE_FALLBACK
        ):
            # Keep the legacy adapter registered for explicit compatibility and
            # options, but never let it become an implicit fallback for the new
            # workstation's identity, history, event, or universe paths.
            continue
        # Policies may outlive a provider capability after a configuration or
        # adapter change. Never let a stale row invoke a method the provider
        # does not implement (for example Alpaca has discovery, not search).
        try:
            provider = get_provider(data_source.name)
        except KeyError:
            continue
        if capability.value not in list_provider_capabilities(data_source.name):
            continue
        if instrument_routing is not None and not provider_supports_instrument(
            data_source.name,
            asset_class=instrument_routing[0],
            instrument_type=instrument_routing[1],
        ):
            # Method-level compatibility (for example ``fetch_ohlcv``) does
            # not imply that the provider understands this instrument.  Keep
            # routing class-aware so equity symbols cannot fall through to a
            # crypto-only exchange adapter.
            continue
        allowed_environments = {
            str(value).strip().lower() for value in entitlement.enabled_environments
        }
        if allowed_environments and current_environment not in allowed_environments:
            continue
        if entitlement.review_due_at and _as_utc(entitlement.review_due_at) <= now:
            continue
        if not policy_has_known_quota(policy):
            # An adapter may be perfectly valid code while its current plan,
            # key/IP scope, or window is unknown.  That is an observable
            # configuration state, never a reason to guess a safe default.
            continue
        if operation is not None and not provider_contract_operation_cost_known(
            policy,
            data_source,
            operation,
            (operation_cost_overrides or {}).get(data_source.name),
        ):
            # Weighted/credit providers are not candidates until this exact
            # operation has a documented charge in the local usage profile.
            continue
        if health.circuit_open_until and health.circuit_open_until > now:
            continue
        support_state = support_map.get(data_source.id)
        effective_support = (
            support_state.status if support_state is not None else SUPPORT_STATUS_UNKNOWN
        )
        if effective_support == SUPPORT_STATUS_UNSUPPORTED:
            continue
        policy.effective_score = _effective_score(policy, health)
        health.observed_score = policy.effective_score
        resolved.append(
            ResolvedProvider(
                provider_name=data_source.name,
                provider=provider,
                data_source=data_source,
                policy=policy,
                health=health,
                support_status=effective_support,
                has_symbol_binding=data_source.id in binding_ids,
                entitlement=entitlement,
            )
        )
    resolved.sort(
        key=lambda item: (
            0 if item.policy.is_pinned else 1,
            0 if item.support_status == SUPPORT_STATUS_SUPPORTED else 1,
            0 if item.has_symbol_binding else 1,
            -float(item.policy.effective_score),
            item.policy.base_priority,
            item.provider_name,
        )
    )
    return resolved


async def _record_result(
    db: AsyncSession,
    *,
    resolved: ResolvedProvider,
    log_row: ProviderRequestLog,
    success: bool,
    latency_ms: int,
    response_items: int | None = None,
    error: Exception | None = None,
) -> None:
    health = resolved.health
    policy = resolved.policy
    now = datetime.now(UTC)

    log_row.completed_at = now
    log_row.latency_ms = latency_ms
    log_row.success = success
    log_row.response_items = response_items
    if error is not None:
        log_row.error_type = error.__class__.__name__
        log_row.error_message = bounded_redact_provider_message(error, max_length=4000)

    health.ewma_latency_ms = _ewma(health.ewma_latency_ms, Decimal(str(latency_ms)))
    health.ewma_success_rate = _ewma(
        health.ewma_success_rate, Decimal("1") if success else Decimal("0")
    )
    health.ewma_completeness = _ewma(
        health.ewma_completeness,
        Decimal("1") if (response_items or 0) > 0 else Decimal("0.35" if success else "0"),
    )
    health.ewma_freshness = _ewma(health.ewma_freshness, Decimal("1") if success else Decimal("0"))
    health.ewma_consistency = _ewma(
        health.ewma_consistency, Decimal("1") if success else Decimal("0.25")
    )

    if success:
        health.failure_streak = 0
        health.last_success_at = now
        health.circuit_open_until = None
        policy.learned_weight = _ewma(policy.learned_weight, Decimal("2"))
    else:
        health.failure_streak += 1
        health.last_failure_at = now
        health.last_error_type = error.__class__.__name__ if error else "ProviderError"
        health.last_error_message = (
            bounded_redact_provider_message(error) if error else "Provider call failed"
        )
        policy.learned_weight = _ewma(policy.learned_weight, Decimal("-4"))
        if health.failure_streak >= 3 and policy.cooldown_seconds:
            health.circuit_open_until = now + timedelta(seconds=policy.cooldown_seconds)

    policy.effective_score = _effective_score(policy, health)
    health.observed_score = policy.effective_score
    await db.flush()


async def execute_provider_call(
    db: AsyncSession,
    capability: ProviderCapability,
    operation: str,
    *,
    instrument_id: int | None = None,
    provider_symbol: str | None = None,
    usage_identity: str | Callable[[str], str | None] | None = None,
    provider_name: str | None = None,
    operation_cost_overrides: dict[str, int] | None = None,
    adjusted: bool | None = None,
    invoke: Callable[[Any, str | None], T],
    response_items: Callable[[T], int | None] | None = None,
    treat_empty_as_failure: bool = False,
) -> ProviderExecutionResult:
    chain = await resolve_provider_chain(
        db,
        capability,
        instrument_id=instrument_id,
        operation=operation,
        operation_cost_overrides=operation_cost_overrides,
        adjusted=adjusted,
    )
    if provider_name is not None:
        chain = [resolved for resolved in chain if resolved.provider_name == provider_name]
    loop = asyncio.get_event_loop()
    last_error: Exception | None = None

    for resolved in chain:
        resolved_usage_identity = (
            usage_identity(resolved.provider_name)
            if callable(usage_identity)
            else usage_identity
        )
        if resolved_usage_identity is None:
            resolved_usage_identity = provider_symbol
        if not provider_contract_operation_cost_known(
            resolved.policy,
            resolved.data_source,
            operation,
            (operation_cost_overrides or {}).get(resolved.provider_name),
            resolved_usage_identity,
        ):
            continue
        override = (operation_cost_overrides or {}).get(resolved.provider_name)
        usage_mode, usage_unit_label, usage_units = _usage_cost_for_operation(
            resolved.data_source,
            operation,
            resolved.policy,
            operation_cost_override=override,
        )
        dimension_units = _dimension_costs_for_operation(
            resolved.policy,
            resolved.data_source,
            operation,
            usage_units,
        )
        if quota_dimensions(resolved.policy) and not dimension_units:
            continue
        distinct_dimensions = {
            str(dimension["name"])
            for dimension in quota_dimensions(resolved.policy)
            if str(dimension.get("unit") or "").lower()
            in {"symbol", "symbols", "unique_symbol", "unique_symbols"}
        }
        release_only_dimensions = {
            str(dimension["name"])
            for dimension in quota_dimensions(resolved.policy)
            if str(dimension.get("unit") or "").lower()
            in {"concurrent_requests", "concurrency"}
        }
        # A runtime call participates in the same durable multi-dimensional
        # budget used by queued workloads.  This prevents concurrent workers
        # from multiplying a provider/IP/key allowance in process-local
        # buckets.  The import is intentionally lazy because provider_routing
        # imports the resolver for its candidate selection.
        from app.services.provider_routing import (
            reserve_provider_contract,
            settle_provider_contract,
        )

        reservations = await reserve_provider_contract(
            db,
            resolved=resolved,
            capability=capability.value,
            units=max(1, int(usage_units.to_integral_value())),
            dimension_units=dimension_units,
            usage_identity=resolved_usage_identity,
            now=datetime.now(UTC),
        )
        if reservations is None:
            continue
        if (
            resolved.policy.tokens_per_minute is not None
            and resolved.policy.burst_capacity is not None
        ):
            if not _get_bucket(resolved.policy, resolved.provider_name).try_acquire(
                max(1, int(usage_units.to_integral_value()))
            ):
                settle_provider_contract(
                    reservations,
                    units=max(1, int(usage_units.to_integral_value())),
                    success=False,
                    reserved_dimension_units=dimension_units,
                    consumed_dimension_units={name: 0 for name in dimension_units},
                    consume_on_failure_dimensions=distinct_dimensions,
                    release_only_dimensions=release_only_dimensions,
                )
                continue
        log_row = ProviderRequestLog(
            data_source_id=resolved.data_source.id,
            capability=capability,
            operation=operation,
            operation_family=_operation_family(operation),
            instrument_id=instrument_id,
            provider_symbol=provider_symbol,
            requested_at=datetime.now(UTC),
            usage_mode=usage_mode,
            usage_unit_label=usage_unit_label,
            usage_units=usage_units,
        )
        db.add(log_row)
        await db.flush()

        semaphore = _get_semaphore(resolved.policy, resolved.provider_name)
        started = time.perf_counter()
        measurement, measurement_token = activate_provider_telemetry()
        try:
            async with semaphore:
                # ``run_in_executor`` does not propagate ContextVar state by
                # itself.  Copy the context after activation so synchronous
                # adapters can report transport bytes from their worker
                # thread without changing their domain return types.
                invocation_context = contextvars.copy_context()
                result = await loop.run_in_executor(
                    None,
                    invocation_context.run,
                    lambda: invoke(resolved.provider, provider_symbol),
                )
            log_row.http_requests = measurement.http_requests
            log_row.response_bytes = measurement.response_bytes
            log_row.response_headers = dict(measurement.response_headers)
            count = response_items(result) if response_items is not None else None
            is_empty = result is None or count == 0
            if treat_empty_as_failure and is_empty:
                raise ProviderNoDataError(
                    f"{resolved.provider_name} returned no usable data for {operation}"
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
            await _record_result(
                db,
                resolved=resolved,
                log_row=log_row,
                success=True,
                latency_ms=latency_ms,
                response_items=count,
            )
            settle_provider_contract(
                reservations,
                units=max(1, int(usage_units.to_integral_value())),
                success=True,
                reserved_dimension_units=dimension_units,
                consumed_dimension_units=_consumed_dimension_costs(
                    resolved.policy, measurement, dimension_units
                ),
                consume_on_failure_dimensions=distinct_dimensions,
                observed_dimension_totals=_observed_dimension_totals(
                    resolved.policy, measurement
                ),
                release_only_dimensions=release_only_dimensions,
            )
            if instrument_id is not None:
                await record_provider_support(
                    db,
                    instrument_id=instrument_id,
                    data_source_id=resolved.data_source.id,
                    capability=capability,
                    status=SUPPORT_STATUS_SUPPORTED,
                    provider_symbol=provider_symbol,
                )
            return ProviderExecutionResult(
                provider_name=resolved.provider_name,
                data_source=resolved.data_source,
                policy=resolved.policy,
                health=resolved.health,
                result=result,
            )
        except Exception as exc:
            log_row.http_requests = measurement.http_requests
            log_row.response_bytes = measurement.response_bytes
            log_row.response_headers = dict(measurement.response_headers)
            rate_error = provider_rate_limit_error(
                resolved.provider_name,
                exc,
                scope=resolved.policy.quota_scope,
            )
            if rate_error is not None:
                exc = rate_error
                last_error = rate_error
                db.add(
                    ProviderCapacityEvent(
                        data_source_id=resolved.data_source.id,
                        capability=capability,
                        operation=operation,
                        scope=rate_error.scope or resolved.policy.quota_scope,
                        status_code=rate_error.status_code,
                        error_type=rate_error.__class__.__name__,
                        message=bounded_redact_provider_message(rate_error, max_length=4000),
                        retry_at=rate_error.retry_at,
                        response_headers=_capacity_response_headers(rate_error.headers),
                        observed_at=datetime.now(UTC),
                        request_log_id=log_row.id,
                    )
                )
                await db.flush()
                # A provider-supplied reset is authoritative.  Do not sleep
                # blindly or retry the same provider in a tight loop.
                if rate_error.retry_at is not None:
                    resolved.health.circuit_open_until = rate_error.retry_at
                else:
                    resolved.health.circuit_open_until = (
                        datetime.now(UTC) + timedelta(seconds=resolved.policy.cooldown_seconds or 0)
                        if resolved.policy.cooldown_seconds
                        else None
                    )
            last_error = exc
            settle_provider_contract(
                reservations,
                units=max(1, int(usage_units.to_integral_value())),
                success=False,
                reserved_dimension_units=dimension_units,
                consumed_dimension_units=_consumed_dimension_costs(
                    resolved.policy, measurement, dimension_units
                ),
                consume_on_failure_dimensions=distinct_dimensions,
                release_only_dimensions=release_only_dimensions,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            await _record_result(
                db,
                resolved=resolved,
                log_row=log_row,
                success=False,
                latency_ms=latency_ms,
                response_items=0,
                error=exc,
            )
            should_mark_unsupported = (
                instrument_id is not None
                and isinstance(exc, ProviderNoDataError)
                and (
                    capability != ProviderCapability.PRICE_HISTORY
                    or operation.startswith("fetch_latest_ohlcv:")
                    or operation.startswith("bulk_fetch:")
                )
            )
            if should_mark_unsupported:
                await record_provider_support(
                    db,
                    instrument_id=instrument_id,
                    data_source_id=resolved.data_source.id,
                    capability=capability,
                    status=SUPPORT_STATUS_UNSUPPORTED,
                    provider_symbol=provider_symbol,
                    error_type=exc.__class__.__name__,
                    error_message=bounded_redact_provider_message(exc),
                )
            remaining = [
                r.provider_name for r in chain if r.provider_name != resolved.provider_name
            ]
            if remaining:
                logger.warning(
                    "provider_runtime: %s failed for %s/%s (%s) — falling back to [%s]",
                    resolved.provider_name,
                    capability.value,
                    operation,
                    bounded_redact_provider_message(exc),
                    ", ".join(remaining),
                )
            else:
                logger.warning(
                    "provider_runtime: %s failed for %s/%s (%s) — no further providers in chain",
                    resolved.provider_name,
                    capability.value,
                    operation,
                    bounded_redact_provider_message(exc),
                )
            if not isinstance(exc, ProviderRateLimitError | ProviderNotConfiguredError):
                await asyncio.sleep(
                    min(1.0, 0.2 * (resolved.health.failure_streak + 1)) + random.random() * 0.15
                )
            continue
        finally:
            deactivate_provider_telemetry(measurement_token)

    if not chain and instrument_id is not None:
        raise ProviderNoDataError(
            f"No currently-supported providers available for {capability.value}/{operation}"
        )
    if last_error is not None:
        # Exhaustion is an expected, user-visible coverage outcome when every
        # entitled provider has no usable observations. Keep it distinguishable
        # from an unhandled runtime fault while preserving the original typed
        # exception for the caller's structured unavailable/partial response.
        log_method = logger.warning if isinstance(last_error, ProviderNoDataError) else logger.error
        log_method(
            "provider_runtime: all providers exhausted for %s/%s — last error: %s",
            capability.value,
            operation,
            bounded_redact_provider_message(last_error),
        )
        raise last_error
    raise RuntimeError(f"No enabled providers available for capability '{capability.value}'")


async def list_provider_status(db: AsyncSession) -> list[dict[str, Any]]:
    await seed_provider_runtime(db)
    rows = (
        await db.execute(
            select(ProviderPolicy, ProviderHealthState, DataSource, ProviderEntitlement)
            .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
            .join(
                ProviderEntitlement,
                (ProviderEntitlement.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderEntitlement.capability == ProviderPolicy.capability),
            )
            .join(
                ProviderHealthState,
                (ProviderHealthState.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderHealthState.capability == ProviderPolicy.capability),
            )
            .order_by(DataSource.name, ProviderPolicy.capability)
        )
    ).all()
    status_rows = []
    for policy, health, data_source, entitlement in rows:
        # Keep operation-specific controls accurate in diagnostics as well as
        # in resolver admission. Alpaca's page bound applies only to events;
        # use a non-event marker for the other capability rows.
        diagnostic_operation = (
            "fetch_instrument_events"
            if policy.capability == ProviderCapability.INSTRUMENT_EVENTS
            else "__capability__"
        )
        routing_control_settings = provider_routing_control_settings(
            data_source.name, diagnostic_operation
        )
        missing_routing_controls = provider_missing_routing_controls(
            data_source.name, diagnostic_operation
        )
        status_rows.append(
            {
            "provider": data_source.name,
            "capability": policy.capability.value,
            "supported_capabilities": data_source.supported_capabilities or [],
            "is_enabled": policy.is_enabled,
            "is_pinned": policy.is_pinned,
            "auto_weight_enabled": policy.auto_weight_enabled,
            "base_priority": policy.base_priority,
            "effective_score": float(policy.effective_score),
            "learned_weight": float(policy.learned_weight),
            "max_concurrency": policy.max_concurrency,
            "tokens_per_minute": policy.tokens_per_minute,
            "burst_capacity": policy.burst_capacity,
            "cooldown_seconds": policy.cooldown_seconds,
            "quota_contract": policy.quota_contract,
            "quota_scope": policy.quota_scope,
            "quota_source": policy.quota_source,
            "quota_verified_at": policy.quota_verified_at,
            "quota_state": "known" if policy_has_known_quota(policy) else "unknown",
            "quota_missing_dimensions": quota_contract_missing_dimensions(policy),
            "operation_costs_configured": provider_contract_operation_costs_configured(
                policy, data_source
            ),
            "credentials_configured": provider_is_configured(data_source.name),
            "required_environment_variables": list(provider_required_settings(data_source.name)),
            "missing_environment_variables": provider_missing_settings(data_source.name),
            "required_routing_control_variables": list(routing_control_settings),
            "missing_routing_control_variables": missing_routing_controls,
            "entitlement_state": (
                "reviewed"
                if str(entitlement.configured_plan or "").strip().lower() != "unreviewed"
                else "unreviewed"
            ),
            "live_probe_status": entitlement.live_probe_status,
            "routing_eligible": bool(
                policy.is_enabled
                and policy_has_known_quota(policy)
                and provider_is_configured(data_source.name)
                and not missing_routing_controls
                and str(entitlement.configured_plan or "").strip().lower() != "unreviewed"
                and str(entitlement.live_probe_status or "not_run").strip().lower()
                in {"passed", "not_required"}
                and (entitlement.is_free or settings.ALLOW_PAID_PROVIDER_ROUTING)
                and provider_contract_operation_costs_configured(policy, data_source)
            ),
            "freshness_seconds": policy.freshness_seconds,
            "failure_streak": health.failure_streak,
            "last_success_at": health.last_success_at,
            "last_failure_at": health.last_failure_at,
            "circuit_open_until": health.circuit_open_until,
            "ewma_latency_ms": float(health.ewma_latency_ms),
            "ewma_success_rate": float(health.ewma_success_rate),
            "ewma_completeness": float(health.ewma_completeness),
            "ewma_freshness": float(health.ewma_freshness),
            "ewma_consistency": float(health.ewma_consistency),
            "last_error_type": health.last_error_type,
            "last_error_message": health.last_error_message,
            }
        )
    return status_rows
