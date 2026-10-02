"""Provider-native account usage observations.

The request ledger remains the authoritative local accounting source.  This
module stores provider-reported counters as separate observations so operators
can compare the external account window with local usage across sessions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderAccountUsageObservation, ProviderCapability
from app.providers.base import ProviderAccountUsage, ProviderAccountUsageDimension
from app.providers.errors import bounded_redact_provider_message
from app.services.provider_quota_coordinator import reconcile_provider_quota_baseline
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain

# Native account-usage snapshots are only eligible to seed a coordinator
# baseline when the provider's response can be matched to one exact reviewed
# dimension.  Keep this allow-list provider-specific; a generic
# ``limit - remaining`` conversion would be unsafe for providers whose
# counters use different windows, units, or endpoint pools.
_NATIVE_BASELINE_DIMENSIONS: dict[str, dict[str, str]] = {
    "marketdata_app": {
        "credits_per_day": ProviderCapability.ACCOUNT_USAGE.value,
    },
    # EODHD's documented /user endpoint reports the current daily-call
    # counter and the account's daily limit.  Its midnight-GMT boundary is
    # accepted only when the response identifies the current UTC usage date;
    # minute-rate observations remain observation-only while the provider's
    # official sources disagree on the exact plan limit.
    "eodhd": {
        "calls_per_day": ProviderCapability.ACCOUNT_USAGE.value,
        # EODHD's current API-limits documentation states that the minute
        # request pool resets every minute. The adapter derives the next
        # minute boundary from the observation timestamp; admission still
        # requires the operator-reviewed active account limit/evidence.
        "requests_per_minute": ProviderCapability.ACCOUNT_USAGE.value,
    },
    # Twelve Data's /api_usage response exposes the current minute pool via
    # provider-native used/left headers. Reconcile only that exact reviewed
    # dimension. The official credits documentation gives the daily pool an
    # exact UTC-midnight reset, but no daily consumed counter is exposed, so
    # the durable daily baseline remains required before ordinary reads.
    "twelve_data": {
        "credits_per_minute": ProviderCapability.ACCOUNT_USAGE.value,
    },
    # Binance's public /api/v3/time response exposes the cumulative request
    # weight for the current fixed one-minute window.  The adapter supplies
    # the exact next-minute reset boundary and the reviewed 6,000-weight cap.
    "binance": {
        "request_weight_per_minute": ProviderCapability.ACCOUNT_USAGE.value,
    },
    # OpenFIGI exposes the exact active mapping dimension in its native
    # headers. The dimension is anonymous 25/minute or keyed 25/6-seconds,
    # selected by provider_rate_limit_seed at runtime.
    "openfigi": {
        "mapping_requests_per_minute": ProviderCapability.ACCOUNT_USAGE.value,
    },
    # Alpaca's native market-data headers expose the active 200-request pool
    # and the next quota-change epoch. The reviewed contract uses a rolling
    # 60-second safety envelope because Alpaca does not publish a fixed
    # calendar-minute boundary; the native snapshot is therefore required to
    # establish the current durable baseline before metered reads.
    "alpaca": {
        "market_data_requests_per_minute": ProviderCapability.ACCOUNT_USAGE.value,
    },
}


def _usage_payload(observation: ProviderAccountUsageObservation, provider: str) -> dict[str, Any]:
    return {
        "id": observation.id,
        "provider": provider,
        "dimension": observation.dimension,
        "observed_at": observation.observed_at,
        "unit": observation.unit,
        "limit": observation.limit,
        "remaining": observation.remaining,
        "consumed": observation.consumed,
        "reset_at": observation.reset_at,
        "options_data_permissions": observation.options_data_permissions,
        "account_plan": observation.account_plan,
        "payload": observation.payload,
        "response_headers": observation.response_headers,
    }


def _validate_dimension(dimension: ProviderAccountUsageDimension) -> None:
    if not str(dimension.name or "").strip():
        raise ValueError("provider returned an empty account-usage dimension")
    if not str(dimension.unit or "").strip():
        raise ValueError("provider returned an empty account-usage unit")
    for field in ("limit", "remaining", "consumed"):
        value = getattr(dimension, field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(f"provider returned an invalid account-usage {field}")
    if (
        dimension.limit is not None
        and dimension.remaining is not None
        and dimension.remaining > dimension.limit
    ):
        raise ValueError("provider returned account-usage remaining above limit")
    if dimension.reset_at is not None and dimension.reset_at.tzinfo is None:
        raise ValueError("provider returned a timezone-naive account-usage reset")


def _usage_dimensions(
    usage: ProviderAccountUsage, provider_name: str
) -> tuple[ProviderAccountUsageDimension, ...]:
    """Return named dimensions while preserving legacy adapter contracts."""

    dimensions = tuple(usage.dimensions or ())
    if dimensions:
        return dimensions
    # MarketData.app was the first account endpoint and its legacy typed
    # object represented the one reviewed daily credit pool at the top level.
    # Give that existing shape its provider-specific name during migration;
    # unknown legacy providers remain explicitly ``default``.
    name = "credits_per_day" if provider_name == "marketdata_app" else "default"
    return (
        ProviderAccountUsageDimension(
            name=name,
            unit=usage.unit,
            limit=usage.limit,
            remaining=usage.remaining,
            consumed=usage.consumed,
            reset_at=usage.reset_at,
        ),
    )


def _validate_usage(usage: ProviderAccountUsage, provider_name: str) -> tuple[ProviderAccountUsageDimension, ...]:
    dimensions = _usage_dimensions(usage, provider_name)
    names: set[str] = set()
    for dimension in dimensions:
        _validate_dimension(dimension)
        normalized_name = dimension.name.strip()
        if normalized_name in names:
            raise ValueError("provider returned duplicate account-usage dimensions")
        names.add(normalized_name)
    if not str(usage.unit or "").strip():
        # ``unit`` is retained for backward-compatible top-level consumers;
        # named providers are validated through each dimension above.
        if usage.dimensions:
            raise ValueError("provider returned an empty account-usage unit")
    if usage.reset_at is not None and usage.reset_at.tzinfo is None:
        raise ValueError("provider returned a timezone-naive account-usage reset")
    if not isinstance(usage.raw_payload, dict):
        raise ValueError("provider returned a non-object raw account-usage payload")
    if not isinstance(usage.response_headers, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in usage.response_headers.items()
    ):
        raise ValueError("provider returned invalid account-usage response headers")
    return dimensions


def _native_baseline_candidate(
    execution: Any,
    dimension: ProviderAccountUsageDimension,
    observed_at: datetime,
) -> tuple[str, str, int, datetime, str] | None:
    """Return an exact native baseline candidate, or refuse to infer one.

    The provider policy remains authoritative for the dimension, limit, reset,
    and account scope.  Native values are accepted only when the returned
    limit matches that reviewed contract and the provider supplies a current
    reset timestamp plus a non-negative consumed value (or an equivalent
    limit/remaining pair).
    """

    provider_name = str(getattr(execution, "provider_name", "") or "").strip()
    configured_dimensions = _NATIVE_BASELINE_DIMENSIONS.get(provider_name)
    policy = getattr(execution, "policy", None)
    if configured_dimensions is None or policy is None:
        return None
    dimension_name = str(getattr(dimension, "name", "") or "").strip()
    capability = configured_dimensions.get(dimension_name)
    if capability is None:
        # Preserve the historical anonymous OpenFIGI alias: the provider's
        # keyed contract names the active dimension per six seconds, while
        # the usage adapter exposes the same native mapping counter under its
        # stable minute label for compatibility.
        if (
            provider_name == "openfigi"
            and dimension_name == "mapping_requests_per_6_seconds"
        ):
            capability = configured_dimensions.get("mapping_requests_per_minute")
        else:
            return None
    contract = getattr(policy, "quota_contract", None)
    if not isinstance(contract, dict):
        return None
    dimensions = [
        item
        for item in contract.get("dimensions", [])
        if isinstance(item, dict)
        and (
            item.get("name") == dimension_name
            or (
                provider_name == "openfigi"
                and dimension_name == "mapping_requests_per_minute"
                and item.get("name") == "mapping_requests_per_6_seconds"
            )
        )
    ]
    if len(dimensions) != 1 or contract.get("unknown_dimensions"):
        return None
    policy_dimension = dimensions[0]
    dimension_name = str(policy_dimension.get("name") or dimension_name)
    limit = policy_dimension.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        return None
    if dimension.limit != limit or dimension.reset_at is None:
        return None
    reset_at = dimension.reset_at
    if observed_at.tzinfo is None or reset_at.tzinfo is None:
        return None
    if reset_at <= observed_at:
        # Alpaca's documented reset header is an integer Unix timestamp.  A
        # response that straddles that second can therefore arrive with a
        # reset value a fraction of a second behind the client-side
        # observation instant.  The reviewed Alpaca contract explicitly
        # permits this bounded timestamp-precision skew while its rolling
        # safety envelope anchors the snapshot at ``observed_at``.  No other
        # provider receives this exception, and a stale response beyond the
        # provider-specific bound remains unadmitted.
        skew_limit = policy_dimension.get("native_reset_skew_seconds")
        if (
            provider_name != "alpaca"
            or isinstance(skew_limit, bool)
            or not isinstance(skew_limit, int | float)
            or skew_limit < 0
            or (observed_at - reset_at).total_seconds() > float(skew_limit)
        ):
            return None
    consumed = dimension.consumed
    if consumed is None and dimension.remaining is not None:
        consumed = limit - dimension.remaining
    if (
        isinstance(consumed, bool)
        or not isinstance(consumed, int)
        or consumed < 0
        or consumed > limit
    ):
        return None
    evidence_date = observed_at.astimezone(UTC).date().isoformat()
    evidence_provider = provider_name.replace("_", "-")
    evidence_reference = f"account-usage:{evidence_provider}:{evidence_date}"
    return dimension_name, capability, consumed, observed_at, evidence_reference


async def refresh_provider_account_usage(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
) -> dict[str, Any]:
    """Fetch and persist one provider-native usage observation.

    Admission still goes through the normal provider runtime, including
    credentials, reviewed quota contracts, live-probe status, and the explicit
    operation cost for ``fetch_account_usage``.  A provider that does not
    expose this surface is not guessed or synthesized.
    """

    chain = await resolve_provider_chain(
        db,
        ProviderCapability.ACCOUNT_USAGE,
        operation="fetch_account_usage",
    )
    if provider_name:
        chain = [item for item in chain if item.provider_name == provider_name]
    if not chain:
        return {"status": "no_qualified_provider", "providers": [], "observations": []}

    observations: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    baseline_reconciliations: list[dict[str, Any]] = []
    for resolved in chain:
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.ACCOUNT_USAGE,
                "fetch_account_usage",
                provider_name=resolved.provider_name,
                invoke=lambda provider, _symbol: provider.fetch_account_usage(),
                response_items=lambda value: 1 if value is not None else 0,
                treat_empty_as_failure=True,
            )
            usage = execution.result
            if not isinstance(usage, ProviderAccountUsage):
                raise TypeError("provider returned an invalid account-usage observation")
            dimensions = _validate_usage(usage, execution.provider_name)
            observed_at = usage.observed_at
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)
            for dimension in dimensions:
                row = ProviderAccountUsageObservation(
                    data_source_id=execution.data_source.id,
                    dimension=dimension.name.strip(),
                    observed_at=observed_at,
                    unit=dimension.unit,
                    limit=dimension.limit,
                    remaining=dimension.remaining,
                    consumed=dimension.consumed,
                    reset_at=dimension.reset_at,
                    options_data_permissions=usage.options_data_permissions,
                    account_plan=usage.account_plan,
                    payload=dict(usage.raw_payload or {}),
                    response_headers=dict(usage.response_headers or {}),
                )
                db.add(row)
                await db.flush()
                observations.append(_usage_payload(row, execution.provider_name))
                baseline_candidate = _native_baseline_candidate(execution, dimension, observed_at)
                if baseline_candidate is not None:
                    (
                        dimension_name,
                        baseline_capability,
                        used_units,
                        baseline_observed_at,
                        evidence_reference,
                    ) = baseline_candidate
                    try:
                        baseline_reconciliations.append(
                            reconcile_provider_quota_baseline(
                                provider_name=execution.provider_name,
                                capability=baseline_capability,
                                policy=execution.policy,
                                dimension_name=dimension_name,
                                used_units=used_units,
                                observed_at=baseline_observed_at,
                                evidence_reference=evidence_reference,
                                source="provider_account_observation",
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 - preserve observation, expose redacted admission failure.
                        failures.append(
                            {
                                "provider": execution.provider_name,
                                "error": "native baseline reconciliation: "
                                + bounded_redact_provider_message(exc, max_length=500),
                            }
                        )
            # One provider is selected by the runtime for this account-scoped
            # observation. Do not call lower-priority providers in the same
            # request and spend another account quota window.
            break
        except Exception as exc:  # noqa: BLE001 - retain redacted admin evidence upstream.
            failures.append(
                {
                    "provider": resolved.provider_name,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                }
            )

    await db.commit()
    result = {
        "status": "refreshed" if observations else ("failed" if failures else "no_observation"),
        "providers": [item["provider"] for item in observations],
        "observations": observations,
        "failures": failures,
    }
    if baseline_reconciliations:
        result["baseline_reconciliations"] = baseline_reconciliations
    return result


async def list_provider_account_usage(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent durable native-usage observations."""

    bounded_limit = max(1, min(int(limit), 500))
    query = (
        select(ProviderAccountUsageObservation, DataSource.name)
        .join(DataSource, DataSource.id == ProviderAccountUsageObservation.data_source_id)
        .order_by(ProviderAccountUsageObservation.observed_at.desc())
        .limit(bounded_limit)
    )
    if provider_name:
        query = query.where(DataSource.name == provider_name)
    rows = (await db.execute(query)).all()
    return [_usage_payload(observation, provider) for observation, provider in rows]
