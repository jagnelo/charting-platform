"""One-shot admin qualification for a reviewed native ETF holdings adapter."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHoldingsAdapterState,
    ETFHoldingsBackfillJob,
    ETFHoldingsRawArtifact,
    ETFHoldingsSnapshot,
    ETFIssuerCatalogCache,
    ETFProfile,
)
from app.models.provider_recurring_cost import (
    ProviderRecurringCostBudget,
    ProviderRecurringCostCommitment,
)
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers.errors import bounded_redact_provider_message
from app.services.etf_holdings import (
    ETF_HOLDINGS_INTERNAL_PROVIDER,
    _hash_payload,
    ingest_holdings_snapshot,
)
from app.services.etf_holdings_adapters import (
    ETFNativeSourceEvidenceError,
    HoldingsFetchResult,
    _table_to_text,
    get_holdings_adapter,
    parse_xlsx_table,
)
from app.services.etf_holdings_provider_bridge import (
    ETF_NATIVE_INITIAL_QUALIFICATION_DEADLINE_SECONDS,
    ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS,
    ETF_NATIVE_RESPONSE_BODY_WITNESS_KIND,
    ETFHoldingsRouteHeldError,
    _canonical_request_url,
    _has_explicit_account_scope_mapping,
    require_unbound_etf_holdings_context,
)
from app.services.etf_holdings_refresh import (
    _native_adapter_fetch_evidence,
    _refresh_adapter_route,
    _resolve_canonical_fund_instrument,
)
from app.services.etf_issuer_catalog import (
    ISHARES_US_CATALOG_CACHE_TTL,
    ISHARES_US_CATALOG_KEY,
    ISHARES_US_CATALOG_URL,
    IssuerCatalogError,
    IssuerCatalogProduct,
    _catalog_log_facts_are_trusted,
    _product_link,
    _validated_cached_catalog_content,
    catalog_product_matches_canonical_fund,
    parse_ishares_us_product_catalog,
)
from app.services.etf_issuer_catalog import (
    _origin as issuer_catalog_origin,
)
from app.services.provider_quota_coordinator import account_scope_for_provider
from app.services.provider_recurring_costs import provider_recurring_cost_status
from app.services.provider_runtime import (
    provider_entitlement_admission,
    record_entitlement_revision,
)

NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE = "native_etf_initial_qualification"
NATIVE_ETF_RETAINED_EVIDENCE_CONTINUATION_JOB_TYPE = (
    "native_etf_initial_qualification_retained_evidence"
)
NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION = "fetch_etf_holdings_latest"


def _native_provider_contract():
    """Load the exact separately-owned Producer API, failing closed pre-adoption."""

    try:
        from app.services.provider_runtime import (  # noqa: PLC0415
            bind_native_etf_initial_qualification,
            provider_native_etf_review_fingerprint,
        )
    except ImportError as exc:
        raise ETFHoldingsRouteHeldError(
            "native ETF initial qualification awaits the reviewed Provider contract"
        ) from exc
    return bind_native_etf_initial_qualification, provider_native_etf_review_fingerprint


def _qualification_lock_key(provider_name: str, instrument_id: int) -> int:
    material = f"provider:{provider_name}:ETF_HOLDINGS:native-initial:{instrument_id}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=True)


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _reviewed_native_route(
    *,
    profile: ETFProfile,
    source: DataSource,
    policy: ProviderPolicy,
    entitlement: ProviderEntitlement,
    adapter: Any,
) -> tuple[str, str]:
    """Validate current persisted route/review rows without changing them."""

    provider_name = str(getattr(adapter, "source_provider", "")).strip().lower()
    adapter_key = str(getattr(adapter, "adapter_key", "")).strip().lower()
    aliases = profile.provider_aliases if isinstance(profile.provider_aliases, dict) else {}
    profile_provider = (
        str(aliases.get("holdings_source_provider") or aliases.get("source_provider") or "")
        .strip()
        .lower()
    )
    if (
        not provider_name
        or provider_name in {"edgar", "sec", "vaneck"}
        or source.name != provider_name
        or not source.is_active
        or adapter_key != str(profile.adapter_key or "").strip().lower()
        or profile_provider != provider_name
        or not callable(getattr(adapter, "fetch_latest", None))
        or not callable(getattr(adapter, "fetch_for_date", None))
        or policy.data_source_id != source.id
        or policy.capability != ProviderCapability.ETF_HOLDINGS
        or policy.is_enabled
        or entitlement.data_source_id != source.id
        or entitlement.capability != ProviderCapability.ETF_HOLDINGS
        or str(entitlement.live_probe_status or "not_run").strip().lower() != "not_run"
    ):
        raise ETFHoldingsRouteHeldError(
            "native qualification requires the exact registered disabled ETF adapter and unprobed rows"
        )
    capabilities = source.supported_capabilities
    if not isinstance(capabilities, list) or ProviderCapability.ETF_HOLDINGS.value not in {
        str(value).strip().lower() for value in capabilities
    }:
        raise ETFHoldingsRouteHeldError("native publisher has not declared ETF holdings capability")
    admission = provider_entitlement_admission(
        entitlement,
        provider_name=provider_name,
        capability=ProviderCapability.ETF_HOLDINGS,
    )
    if admission.get("allowed") is not True:
        raise ETFHoldingsRouteHeldError(
            f"native publisher entitlement is held ({admission.get('reason_code') or 'unreviewed'})"
        )
    if entitlement.review_due_at is not None:
        due = entitlement.review_due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        if due.astimezone(UTC) <= datetime.now(UTC):
            raise ETFHoldingsRouteHeldError("native publisher entitlement review has expired")

    review = (
        (source.config or {}).get("etf_holdings_review")
        if isinstance(source.config, dict)
        else None
    )
    if not isinstance(review, dict):
        raise ETFHoldingsRouteHeldError("native publisher review evidence is missing")
    operation = NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION
    operations = review.get("operations")
    operation_review = operations.get(operation) if isinstance(operations, dict) else None
    if (
        not isinstance(operation_review, dict)
        or not all(
            isinstance(operation_review.get(field), str) and operation_review[field].strip()
            for field in ("evidence_source", "evidence_version", "reviewed_at")
        )
        or not isinstance(review.get("https_hosts"), list)
        or not review["https_hosts"]
    ):
        raise ETFHoldingsRouteHeldError("native publisher operation review is incomplete")
    quota_scope = str(policy.quota_scope or "").strip().lower()
    scope_mapping = settings.PROVIDER_QUOTA_ACCOUNT_SCOPES
    if not isinstance(scope_mapping, dict) or not _has_explicit_account_scope_mapping(
        provider_name, quota_scope, scope_mapping
    ):
        raise ETFHoldingsRouteHeldError("native publisher account mapping is not explicit")
    try:
        account_scope = account_scope_for_provider(provider_name, quota_scope)
    except Exception as exc:  # noqa: BLE001 - malformed persisted scope stays held.
        raise ETFHoldingsRouteHeldError("native publisher account mapping is invalid") from exc
    if account_scope in {"*", "ALL", "ANY"} or review.get("account_scope") != account_scope:
        raise ETFHoldingsRouteHeldError("native publisher review uses a different account scope")
    return provider_name, account_scope


def _attempt_scope(
    *,
    attempt_id: int,
    provider_name: str,
    data_source_id: int,
    profile: ETFProfile,
    account_scope: str,
    entitlement_revision: int,
    review_fingerprint: str,
    expires_at: datetime,
) -> dict[str, Any]:
    if profile.instrument is None:
        raise ETFHoldingsRouteHeldError(
            "native qualification requires a linked canonical instrument"
        )
    return {
        "attempt_id": attempt_id,
        "provider": provider_name,
        "data_source_id": data_source_id,
        "capability": ProviderCapability.ETF_HOLDINGS.value,
        "profile_id": profile.id,
        "instrument_id": profile.instrument_id,
        "provider_symbol": profile.instrument.symbol.strip().upper(),
        "operation": NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION,
        "account_scope": account_scope,
        "review_revision": entitlement_revision,
        "provider_review_fingerprint": review_fingerprint,
        "expires_at": expires_at.isoformat(),
        "max_physical_requests": ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS,
    }


def _require_one_shot_available(prior_jobs: list[ETFHoldingsBackfillJob]) -> None:
    if prior_jobs:
        raise ETFHoldingsRouteHeldError(
            "native ETF initial qualification is already latched; replay is denied"
        )


def _native_review_snapshot_still_matches(
    *,
    scope: dict[str, Any],
    profile: ETFProfile,
    source: DataSource,
    policy: ProviderPolicy,
    entitlement: ProviderEntitlement,
    adapter: Any,
    initial_adapter: Any,
    provider_name: str,
    account_scope: str,
    review_fingerprint: str,
    now: datetime,
) -> bool:
    """Keep a positive probe update tied to the exact pretransport review rows."""

    instrument = profile.instrument
    if instrument is None:
        return False
    try:
        expires_at = datetime.fromisoformat(str(scope.get("expires_at")))
    except ValueError:
        return False
    return bool(
        scope.get("profile_id") == profile.id
        and scope.get("capability") == ProviderCapability.ETF_HOLDINGS.value
        and scope.get("operation") == NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION
        and profile.instrument_id == scope.get("instrument_id")
        and source.id == scope.get("data_source_id")
        and provider_name == scope.get("provider")
        and instrument.symbol.strip().upper() == scope.get("provider_symbol")
        and account_scope == scope.get("account_scope")
        and adapter is initial_adapter
        and policy.data_source_id == source.id
        and policy.capability == ProviderCapability.ETF_HOLDINGS
        and not policy.is_enabled
        and entitlement.data_source_id == source.id
        and entitlement.capability == ProviderCapability.ETF_HOLDINGS
        and str(entitlement.live_probe_status or "not_run").strip().lower() == "not_run"
        and entitlement.revision == scope.get("review_revision")
        and review_fingerprint == scope.get("provider_review_fingerprint")
        and expires_at.tzinfo is not None
        and expires_at.astimezone(UTC) > now.astimezone(UTC)
    )


def _issuer_catalog_identity_claim(
    profile: ETFProfile, catalog_metadata: Any
) -> dict[str, Any] | None:
    """Extract a strict iShares identity claim for later durable-cache verification."""

    instrument = profile.instrument
    if instrument is None or not isinstance(catalog_metadata, dict):
        return None
    symbol = instrument.symbol.strip().upper()
    cache_id = catalog_metadata.get("catalog_cache_id")
    content_hash = catalog_metadata.get("catalog_content_sha256")
    product_id = str(catalog_metadata.get("issuer_product_id") or "").strip()
    ticker = str(catalog_metadata.get("ticker") or "").strip().upper()
    name = str(catalog_metadata.get("name") or "").strip()
    source_url = catalog_metadata.get("catalog_source_url")
    final_url = catalog_metadata.get("catalog_final_url")
    product_url = catalog_metadata.get("product_url")
    retrieved_at = catalog_metadata.get("catalog_retrieved_at")
    request_ids = catalog_metadata.get("catalog_request_log_ids")
    reported_total = catalog_metadata.get("catalog_reported_total")
    if (
        catalog_metadata.get("catalog_key") != ISHARES_US_CATALOG_KEY
        or isinstance(cache_id, bool)
        or not isinstance(cache_id, int)
        or cache_id <= 0
        or not isinstance(content_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", content_hash)
        or ticker != symbol
        or not product_id.isdigit()
        or int(product_id) <= 0
        or not name
        or not isinstance(source_url, str)
        or source_url != ISHARES_US_CATALOG_URL
        or not isinstance(final_url, str)
        or not isinstance(product_url, str)
        or catalog_metadata.get("catalog_complete") is not True
        or isinstance(reported_total, bool)
        or not isinstance(reported_total, int)
        or reported_total <= 0
        or not isinstance(request_ids, list)
        or not request_ids
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in request_ids
        )
        or len(request_ids) != len(set(request_ids))
        or not isinstance(retrieved_at, str)
    ):
        return None
    try:
        parsed_retrieved_at = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        if parsed_retrieved_at.tzinfo is None:
            return None
        if issuer_catalog_origin(final_url) != issuer_catalog_origin(ISHARES_US_CATALOG_URL):
            return None
        linked_product_id, _slug, normalized_product_url = _product_link(
            product_url,
            page_url=final_url,
        )
        if linked_product_id != product_id or normalized_product_url != product_url:
            return None
        product = IssuerCatalogProduct(
            ticker=ticker,
            name=name,
            product_id=product_id,
            product_url=product_url,
        )
    except (IssuerCatalogError, TypeError, ValueError):
        return None
    if not catalog_product_matches_canonical_fund(
        product=product,
        ticker=symbol,
        canonical_name=str(instrument.name or ""),
    ):
        return None
    return {
        "basis": "issuer_product_catalog",
        "catalog_key": ISHARES_US_CATALOG_KEY,
        "cache_id": cache_id,
        "content_sha256": content_hash,
        "retrieved_at": parsed_retrieved_at.astimezone(UTC).isoformat(),
        "source_url": source_url,
        "final_url": final_url,
        "ticker": ticker,
        "name": name,
        "product_id": product_id,
        "product_url": product_url,
        "catalog_complete": True,
        "catalog_reported_total": reported_total,
        "request_log_ids": list(request_ids),
        "cache_hit": catalog_metadata.get("catalog_cache_hit") is True,
    }


async def _verify_issuer_catalog_identity_evidence(
    db: AsyncSession,
    *,
    evidence: dict[str, Any],
    profile: ETFProfile,
    source: DataSource,
    job: ETFHoldingsBackfillJob,
) -> None:
    """Verify catalog identity against retained exact bytes and request lineage."""

    instrument = profile.instrument
    if instrument is None or evidence.get("basis") != "issuer_product_catalog":
        raise ETFHoldingsRouteHeldError("native catalog identity evidence is incomplete")
    cached = await db.get(ETFIssuerCatalogCache, evidence.get("cache_id"))
    if (
        cached is None
        or cached.provider_name != source.name
        or cached.catalog_key != evidence.get("catalog_key")
        or cached.data_source_id != source.id
        or cached.content_sha256 != evidence.get("content_sha256")
        or cached.source_url != evidence.get("source_url")
        or not isinstance(cached.raw_body_base64, str)
    ):
        raise ETFHoldingsRouteHeldError("native catalog cache identity does not match its source")
    if evidence.get("cache_hit") is True:
        if (
            cached.final_url != evidence.get("final_url")
            or datetime.now(UTC) - _utc_datetime(cached.fetched_at) > ISHARES_US_CATALOG_CACHE_TTL
        ):
            raise ETFHoldingsRouteHeldError("native cached catalog is stale or mismatched")
        if _validated_cached_catalog_content(cached, now=datetime.now(UTC)) is None:
            raise ETFHoldingsRouteHeldError("native cached catalog content is invalid")
    try:
        body = base64.b64decode(cached.raw_body_base64, validate=True)
        if (
            len(body) != cached.response_bytes
            or hashlib.sha256(body).hexdigest() != cached.content_sha256
            or cached.content_sha256 != evidence.get("content_sha256")
        ):
            raise ValueError("catalog content hash mismatch")
        catalog = parse_ishares_us_product_catalog(
            body.decode(cached.response_encoding, errors="strict"),
            page_url=evidence["final_url"],
        )
        stored_catalog = parse_ishares_us_product_catalog(
            body.decode(cached.response_encoding, errors="strict"),
            page_url=cached.final_url,
        )
    except (IssuerCatalogError, UnicodeDecodeError, ValueError, TypeError, LookupError) as exc:
        raise ETFHoldingsRouteHeldError("native catalog raw content failed verification") from exc
    product = catalog.product_for(instrument.symbol.strip().upper())
    if (
        not catalog.complete
        or catalog.reported_total != evidence.get("catalog_reported_total")
        or not cached.catalog_complete
        or cached.reported_total != stored_catalog.reported_total
        or [entry.as_json() for entry in stored_catalog.entries] != cached.parsed_entries
        or product is None
        or product.name != evidence.get("name")
        or product.product_id != evidence.get("product_id")
        or product.product_url != evidence.get("product_url")
        or not catalog_product_matches_canonical_fund(
            product=product,
            ticker=instrument.symbol.strip().upper(),
            canonical_name=str(instrument.name or ""),
        )
    ):
        raise ETFHoldingsRouteHeldError(
            "native catalog row does not exactly identify the canonical ETF"
        )

    retrieved_at = datetime.fromisoformat(str(evidence["retrieved_at"]))
    if retrieved_at.tzinfo is None:
        raise ETFHoldingsRouteHeldError("native catalog retrieval time is invalid")
    catalog_request_ids = evidence.get("request_log_ids")
    if evidence.get("cache_hit") is True:
        if cached.provider_request_log_ids != catalog_request_ids or _utc_datetime(
            cached.fetched_at
        ) != _utc_datetime(retrieved_at):
            raise ETFHoldingsRouteHeldError("native cached catalog lineage does not match its row")
        catalog_request_urls = cached.request_urls
        lineage_ids = cached.provider_request_log_ids
        lineage_time = cached.fetched_at
        lineage_symbol = cached.requested_symbol
    else:
        extra = job.extra_data if isinstance(job.extra_data, dict) else {}
        all_ids = extra.get("provider_request_log_ids")
        all_urls = extra.get("request_urls")
        if (
            not isinstance(all_ids, list)
            or not isinstance(all_urls, list)
            or len(all_ids) != len(all_urls)
            or any(value not in all_ids for value in catalog_request_ids)
        ):
            raise ETFHoldingsRouteHeldError(
                "native fresh catalog requests are absent from its attempt"
            )
        by_id = dict(zip(all_ids, all_urls, strict=True))
        catalog_request_urls = [by_id[value] for value in catalog_request_ids]
        lineage_ids = catalog_request_ids
        lineage_time = retrieved_at
        lineage_symbol = instrument.symbol.strip().upper()
        if not catalog_request_urls or catalog_request_urls[0] != ISHARES_US_CATALOG_URL:
            raise ETFHoldingsRouteHeldError("native fresh catalog URL lineage is invalid")
    catalog_logs = list(
        (
            await db.scalars(
                select(ProviderRequestLog).where(ProviderRequestLog.id.in_(lineage_ids))
            )
        ).all()
    )
    if not _catalog_log_facts_are_trusted(
        logs=catalog_logs,
        request_log_ids=lineage_ids,
        request_urls=catalog_request_urls,
        source_id=source.id,
        requested_symbol=lineage_symbol,
        retrieved_at=lineage_time,
    ):
        raise ETFHoldingsRouteHeldError("native catalog Provider request lineage is invalid")


async def _verify_invesco_catalog_identity_evidence(
    db: AsyncSession,
    *,
    evidence: dict[str, Any],
    profile: ETFProfile,
    source: DataSource,
    job: ETFHoldingsBackfillJob,
) -> None:
    """Tie an Invesco CUSIP route to the exact catalog response and request log."""

    instrument = profile.instrument
    adapter = get_holdings_adapter(profile.adapter_key)
    if (
        instrument is None
        or adapter is None
        or evidence.get("basis") != "invesco_product_catalog"
        or evidence.get("catalog_request_url") != getattr(adapter, "_PRODUCT_CATALOG_URL", None)
    ):
        raise ETFHoldingsRouteHeldError("native Invesco catalog evidence is incomplete")
    encoded_body = evidence.get("catalog_response_body_base64")
    content_hash = evidence.get("catalog_response_sha256")
    if not isinstance(encoded_body, str) or not isinstance(content_hash, str):
        raise ETFHoldingsRouteHeldError("native Invesco catalog response bytes are missing")
    try:
        body = base64.b64decode(encoded_body, validate=True)
        if hashlib.sha256(body).hexdigest() != content_hash:
            raise ValueError("catalog hash mismatch")
        payload = json.loads(body)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ETFHoldingsRouteHeldError(
            "native Invesco catalog response failed verification"
        ) from exc
    docs = payload.get("response", {}).get("docs") if isinstance(payload, dict) else None
    symbol = instrument.symbol.strip().upper()
    products = (
        [
            row
            for row in docs
            if isinstance(row, dict) and str(row.get("ticker") or "").strip().upper() == symbol
        ]
        if isinstance(docs, list)
        else []
    )
    if len(products) != 1:
        raise ETFHoldingsRouteHeldError("native Invesco catalog ticker is absent or ambiguous")
    product = products[0]
    cusip = str(product.get("cusip") or "").strip()
    account_name = str(product.get("accountName") or "").strip()
    if (
        not cusip
        or evidence.get("ticker") != symbol
        or evidence.get("cusip") != cusip
        or evidence.get("account_name") != account_name
        or evidence.get("holdings_source_url") != adapter._holdings_url(cusip)
        or evidence.get("source_identifier") != cusip
    ):
        raise ETFHoldingsRouteHeldError("native Invesco catalog row conflicts with the ETF route")

    extra = job.extra_data if isinstance(job.extra_data, dict) else {}
    request_ids = extra.get("provider_request_log_ids")
    request_urls = extra.get("request_urls")
    if (
        not isinstance(request_ids, list)
        or not isinstance(request_urls, list)
        or len(request_ids) != len(request_urls)
        or len(request_ids) != len(set(request_ids))
    ):
        raise ETFHoldingsRouteHeldError("native Invesco catalog request lineage is incomplete")
    catalog_ids = [
        request_id
        for request_id, request_url in zip(request_ids, request_urls, strict=True)
        if request_url == evidence.get("catalog_request_url")
    ]
    if len(catalog_ids) != 1:
        raise ETFHoldingsRouteHeldError("native Invesco catalog request is absent or ambiguous")
    log = await db.get(ProviderRequestLog, catalog_ids[0])
    payloads = log.response_payloads if log is not None else None
    if (
        log is None
        or log.data_source_id != source.id
        or log.capability != ProviderCapability.ETF_HOLDINGS
        or log.operation != NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION
        or log.instrument_id != profile.instrument_id
        or (log.provider_symbol or "").strip().upper() != symbol
        or not log.success
        or not isinstance(payloads, list)
        or payload not in payloads
    ):
        raise ETFHoldingsRouteHeldError(
            "native Invesco catalog bytes do not match their settled Provider request log"
        )


async def _current_native_rows(
    db: AsyncSession, *, profile_id: int
) -> tuple[
    ETFProfile,
    DataSource,
    ProviderPolicy,
    ProviderEntitlement,
    Any,
    str,
    str,
    str,
]:
    profile = (
        await db.execute(
            select(ETFProfile)
            .options(selectinload(ETFProfile.instrument))
            .where(ETFProfile.id == profile_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if profile is None or profile.instrument is None:
        raise ETFHoldingsRouteHeldError("committed ETF profile and instrument are required")
    instrument = await _resolve_canonical_fund_instrument(
        db, profile.instrument.symbol.strip().upper()
    )
    if instrument is None or instrument.id != profile.instrument_id:
        raise ETFHoldingsRouteHeldError(
            "native qualification requires the current canonical ETF row"
        )
    adapter = get_holdings_adapter(profile.adapter_key)
    if adapter is None:
        raise ETFHoldingsRouteHeldError("the ETF profile adapter is not registered")
    provider_name = str(getattr(adapter, "source_provider", "")).strip().lower()
    source = await db.scalar(
        select(DataSource)
        .where(DataSource.name == provider_name)
        .execution_options(populate_existing=True)
    )
    if source is None:
        raise ETFHoldingsRouteHeldError("native publisher shared Provider source row is missing")
    policy = await db.scalar(
        select(ProviderPolicy)
        .where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
        )
        .execution_options(populate_existing=True)
    )
    entitlement = await db.scalar(
        select(ProviderEntitlement)
        .where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
        )
        .execution_options(populate_existing=True)
    )
    if policy is None or entitlement is None:
        raise ETFHoldingsRouteHeldError("native publisher policy and entitlement rows are required")
    provider_name, account_scope = _reviewed_native_route(
        profile=profile,
        source=source,
        policy=policy,
        entitlement=entitlement,
        adapter=adapter,
    )
    bind_native, fingerprint = _native_provider_contract()
    del bind_native
    try:
        review_fingerprint = fingerprint(source, policy, entitlement)
    except Exception as exc:  # noqa: BLE001 - a broken review hash remains a hold.
        raise ETFHoldingsRouteHeldError(
            "Provider review fingerprint could not be computed"
        ) from exc
    if not isinstance(review_fingerprint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", review_fingerprint
    ):
        raise ETFHoldingsRouteHeldError("Provider review fingerprint is invalid")
    revision = entitlement.revision
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ETFHoldingsRouteHeldError("native publisher entitlement revision is invalid")
    return (
        profile,
        source,
        policy,
        entitlement,
        adapter,
        provider_name,
        account_scope,
        review_fingerprint,
    )


async def _verify_qualification_snapshot(
    db: AsyncSession,
    *,
    snapshot_id: int,
    profile: ETFProfile,
    source: DataSource,
    job: ETFHoldingsBackfillJob,
) -> tuple[ETFHoldingsSnapshot, ETFHoldingsRawArtifact, list[ProviderRequestLog]]:
    await db.refresh(job, attribute_names=["extra_data"])
    holdings_store = await db.scalar(
        select(DataSource)
        .where(DataSource.name == ETF_HOLDINGS_INTERNAL_PROVIDER)
        .execution_options(populate_existing=True)
    )
    snapshot = await db.get(ETFHoldingsSnapshot, snapshot_id)
    if (
        holdings_store is None
        or snapshot is None
        or snapshot.etf_profile_id != profile.id
        or snapshot.data_source_id != holdings_store.id
        or snapshot.source_provider != source.name
        or snapshot.source_artifact_id is None
        or snapshot.row_count <= 0
        or snapshot.composition_date is None
        or snapshot.known_at is None
    ):
        raise ETFHoldingsRouteHeldError("native qualification snapshot is incomplete or mismatched")
    artifact = await db.get(ETFHoldingsRawArtifact, snapshot.source_artifact_id)
    payload = (
        artifact.payload_json
        if artifact is not None and artifact.payload_json is not None
        else (artifact.payload_text if artifact is not None else None)
    )
    expected_hash = _hash_payload(payload) if payload is not None else None
    if (
        artifact is None
        or artifact.etf_profile_id != profile.id
        or artifact.data_source_id != holdings_store.id
        or artifact.source_kind != snapshot.provenance
        or artifact.content_hash != expected_hash
        or artifact.source_url != snapshot.source_url
        or artifact.source_identifier != snapshot.source_identifier
        or artifact.composition_date != snapshot.composition_date
        or artifact.parser_version != snapshot.parser_version
        or not snapshot.source_url
        or not isinstance(payload, str | dict)
        or not payload
    ):
        raise ETFHoldingsRouteHeldError("native qualification raw artifact integrity check failed")
    evidence = (artifact.legal_metadata or {}).get("native_initial_qualification_evidence")
    completeness = evidence.get("composition_completeness") if isinstance(evidence, dict) else None
    snapshot_legal = (
        snapshot.extra_data.get("legal_metadata") if isinstance(snapshot.extra_data, dict) else None
    )
    snapshot_evidence = (
        snapshot_legal.get("native_initial_qualification_evidence")
        if isinstance(snapshot_legal, dict)
        else None
    )
    instrument = profile.instrument
    if (
        not isinstance(evidence, dict)
        or evidence != snapshot_evidence
        or evidence.get("instrument_id") != profile.instrument_id
        or evidence.get("symbol") != instrument.symbol.strip().upper()
        or evidence.get("composition_date") != snapshot.composition_date.isoformat()
        or evidence.get("schema_fingerprint")
        != (snapshot.extra_data or {}).get("schema_fingerprint")
        or evidence.get("parser_version") != snapshot.parser_version
        or evidence.get("raw_payload_hash") != expected_hash
        or snapshot.completeness_status != "complete"
        or not isinstance(completeness, dict)
        or completeness.get("status") != "complete"
        or completeness.get("verified") is not True
        or completeness.get("all_reported_rows_parsed") is not True
        or completeness.get("reported_rows") != snapshot.row_count
        or completeness.get("parsed_rows") != snapshot.row_count
        or completeness.get("source_payload_hash") != expected_hash
        or not isinstance(snapshot_legal, dict)
        or snapshot_legal.get("native_composition_completeness_evidence") != completeness
        or artifact.fetched_at < job.started_at
    ):
        raise ETFHoldingsRouteHeldError(
            "native qualification fund/date/schema evidence is incomplete"
        )
    adapter_state = (
        await db.execute(
            select(ETFHoldingsAdapterState)
            .where(
                ETFHoldingsAdapterState.etf_profile_id == profile.id,
                ETFHoldingsAdapterState.adapter_key == (profile.adapter_key or source.name),
            )
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    _verify_persisted_qualification_adapter_state(
        adapter_state,
        profile=profile,
        source=source,
        snapshot=snapshot,
        evidence=evidence,
    )
    if not snapshot.source_identifier:
        identity = evidence.get("fund_identity")
        spdr_route_evidence = (
            evidence.get("provider") == "spdr"
            and evidence.get("adapter_key") == "spdr"
            and evidence.get("source_identifier") is None
            and evidence.get("source_identifier_basis") == "fund_scoped_spdr_workbook_route"
            and isinstance(identity, dict)
            and identity.get("basis") == "spdr_fund_workbook_preamble"
            and identity.get("source_url") == snapshot.source_url
        )
        amplify_account_evidence = (
            evidence.get("provider") == "amplify"
            and evidence.get("adapter_key") == "amplify"
            and evidence.get("source_identifier") is None
            and evidence.get("source_identifier_basis") == "selected_account_rows"
            and isinstance(identity, dict)
            and identity.get("basis") == "amplify_selected_account_csv"
            and identity.get("account") == evidence.get("symbol")
            and isinstance(identity.get("row_count"), int)
            and not isinstance(identity.get("row_count"), bool)
            and identity.get("row_count", 0) > 0
            and identity.get("source_url") == snapshot.source_url
        )
        if not (spdr_route_evidence or amplify_account_evidence):
            raise ETFHoldingsRouteHeldError("native qualification source identifier is missing")
    if evidence.get("fund_identity", {}).get("basis") == "amplify_selected_account_csv":
        account_identity = evidence["fund_identity"]
        if (
            account_identity.get("account") != instrument.symbol.strip().upper()
            or account_identity.get("source_url") != snapshot.source_url
            or account_identity.get("source_date") != snapshot.composition_date.isoformat()
            or account_identity.get("row_count") != snapshot.row_count
        ):
            raise ETFHoldingsRouteHeldError(
                "native Amplify selected-account evidence does not match the persisted snapshot"
            )
    extra_data = dict(job.extra_data or {})
    request_ids = extra_data.get("provider_request_log_ids")
    if (
        not isinstance(request_ids, list)
        or not request_ids
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in request_ids
        )
        or len(request_ids) != len(set(request_ids))
    ):
        raise ETFHoldingsRouteHeldError("native qualification request log lineage is missing")
    request_urls = extra_data.get("request_urls")
    if (
        not isinstance(request_urls, list)
        or len(request_urls) != len(request_ids)
        or any(not isinstance(url, str) or not url.strip() for url in request_urls)
        or not any(
            _canonical_request_url(snapshot.source_url) == _canonical_request_url(url)
            for url in request_urls
        )
    ):
        raise ETFHoldingsRouteHeldError(
            "native qualification snapshot URL does not match its physical request lineage"
        )
    if not 1 <= len(request_ids) <= ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS:
        raise ETFHoldingsRouteHeldError("native qualification exceeded its physical request budget")
    logs = list(
        (
            await db.scalars(
                select(ProviderRequestLog).where(ProviderRequestLog.id.in_(request_ids))
            )
        ).all()
    )
    logs_by_id = {row.id: row for row in logs}
    if len(logs_by_id) != len(request_ids):
        raise ETFHoldingsRouteHeldError("native qualification request logs are incomplete")
    for request_id in request_ids:
        log = logs_by_id[request_id]
        if (
            log.data_source_id != source.id
            or log.capability != ProviderCapability.ETF_HOLDINGS
            or log.operation != NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION
            or log.instrument_id != profile.instrument_id
            or (log.provider_symbol or "").strip().upper() != instrument.symbol.strip().upper()
            or not log.success
            or log.completed_at is None
            or log.http_requests != 1
            or not isinstance(log.settled_usage_units, Decimal | int | float)
            or Decimal(str(log.settled_usage_units)) <= Decimal("0")
        ):
            raise ETFHoldingsRouteHeldError("native qualification request was not fully settled")
    if isinstance(evidence.get("retained_evidence_continuation"), dict):
        _verify_retained_evidence_body_log_link(
            evidence=evidence,
            profile=profile,
            source=source,
            snapshot=snapshot,
            job=job,
            artifact=artifact,
            request_ids=request_ids,
            request_urls=request_urls,
            logs_by_id=logs_by_id,
        )
    else:
        _verify_native_holdings_body_log_link(
            evidence=evidence,
            profile=profile,
            source=source,
            snapshot=snapshot,
            job=job,
            request_ids=request_ids,
            request_urls=request_urls,
            logs_by_id=logs_by_id,
        )
    if evidence.get("fund_identity", {}).get("basis") == "issuer_product_catalog":
        await _verify_issuer_catalog_identity_evidence(
            db,
            evidence=evidence["fund_identity"],
            profile=profile,
            source=source,
            job=job,
        )
    elif evidence.get("fund_identity", {}).get("basis") == "invesco_product_catalog":
        await _verify_invesco_catalog_identity_evidence(
            db,
            evidence=evidence["fund_identity"],
            profile=profile,
            source=source,
            job=job,
        )
    return snapshot, artifact, [logs_by_id[value] for value in request_ids]


def _retained_log_capture(log: ProviderRequestLog) -> dict[str, Any]:
    payloads = log.response_payloads
    captures = [
        item.get("witness")
        for item in payloads or []
        if isinstance(item, dict) and item.get("kind") == ETF_NATIVE_RESPONSE_BODY_WITNESS_KIND
    ]
    if len(captures) != 1 or not isinstance(captures[0], dict):
        raise ETFNativeSourceEvidenceError(
            "Retained native evidence requires one exact Provider response capture per request"
        )
    capture = captures[0]
    if (
        capture.get("request_log_id") != log.id
        or capture.get("response_body_sha256") is None
        or capture.get("response_body_bytes") != log.response_bytes
    ):
        raise ETFNativeSourceEvidenceError(
            "Retained native response capture does not match its settled request log"
        )
    return capture


def _reparse_retained_native_failure(
    *,
    profile: ETFProfile,
    adapter: Any,
    predecessor: ETFHoldingsBackfillJob,
    rejected_artifact: ETFHoldingsRawArtifact,
    source: DataSource,
    request_logs: list[ProviderRequestLog],
    request_urls: list[str],
    catalog_identity: dict[str, Any] | None = None,
) -> tuple[HoldingsFetchResult, dict[str, Any], dict[str, Any]]:
    """Reparse one supported failed response without opening a transport."""

    provider = str(getattr(adapter, "source_provider", "")).strip().lower()
    if provider not in {"spdr", "ishares"}:
        raise ETFHoldingsRouteHeldError(
            "retained-evidence continuation is limited to reviewed SPDR and iShares responses"
        )
    if (
        predecessor.status != "failed"
        or predecessor.job_type != NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE
        or predecessor.source_provider != provider
        or predecessor.etf_profile_id != profile.id
        or rejected_artifact.source_kind != "issuer_adapter_rejected_fetch"
        or rejected_artifact.etf_profile_id != profile.id
        or rejected_artifact.data_source_id != source.id
        or rejected_artifact.source_url not in request_urls
    ):
        raise ETFHoldingsRouteHeldError(
            "retained evidence does not belong to this failed native qualification"
        )
    failure = " ".join((predecessor.failure_reason or "").casefold().split())
    expected_failures = {
        "spdr": {
            "native qualification source body does not prove the selected fund identity",
        },
        "ishares": {
            "native holdings composition completeness is not proven "
            "(provider=ishares, status=incomplete, reason=all-container row vectors are "
            "incomplete or misaligned).",
        },
    }
    if failure not in expected_failures[provider]:
        raise ETFHoldingsRouteHeldError(
            "failed native qualification is not an eligible parser-evidence continuation"
        )

    payload = (
        rejected_artifact.payload_json
        if rejected_artifact.payload_json is not None
        else rejected_artifact.payload_text
    )
    if (
        not isinstance(payload, str | dict)
        or not payload
        or _hash_payload(payload) != rejected_artifact.content_hash
    ):
        raise ETFNativeSourceEvidenceError(
            "Retained rejected artifact is absent or its content hash does not match"
        )
    extra = predecessor.extra_data if isinstance(predecessor.extra_data, dict) else {}
    lineage_ids = extra.get("provider_request_log_ids")
    lineage_urls = extra.get("request_urls")
    artifact_metadata = (
        rejected_artifact.legal_metadata
        if isinstance(rejected_artifact.legal_metadata, dict)
        else {}
    )
    if (
        not isinstance(lineage_ids, list)
        or not lineage_ids
        or len(lineage_ids) != len(set(lineage_ids))
        or not 1 <= len(lineage_ids) <= ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS
        or lineage_urls != request_urls
        or len(request_urls) != len(lineage_ids)
        or artifact_metadata.get("provider_request_log_ids") != lineage_ids
        or artifact_metadata.get("request_urls") != request_urls
        or [log.id for log in request_logs] != lineage_ids
    ):
        raise ETFHoldingsRouteHeldError(
            "retained artifact and failed-job request lineage do not match exactly"
        )
    attempts = artifact_metadata.get("request_attempts")
    if not isinstance(attempts, list) or len(attempts) != len(request_logs):
        raise ETFHoldingsRouteHeldError("retained artifact has incomplete request attempt facts")
    attempts_by_id = {
        item.get("request_log_id"): item for item in attempts if isinstance(item, dict)
    }
    if len(attempts_by_id) != len(request_logs):
        raise ETFHoldingsRouteHeldError("retained artifact request attempt IDs are ambiguous")
    for log_id, url, log in zip(lineage_ids, request_urls, request_logs, strict=True):
        attempt = attempts_by_id.get(log_id)
        if (
            attempt is None
            or attempt.get("request_url") != url
            or attempt.get("success") is not log.success
            or attempt.get("response_payloads") != log.response_payloads
        ):
            raise ETFHoldingsRouteHeldError(
                "retained artifact request facts differ from the original Provider log"
            )
    scope = extra.get("qualification_scope")
    if not isinstance(scope, dict):
        raise ETFHoldingsRouteHeldError("failed native qualification has no committed scope")
    for request_id, url, log in zip(lineage_ids, request_urls, request_logs, strict=True):
        try:
            parsed_url = urlsplit(url)
            expiry = datetime.fromisoformat(str(scope.get("expires_at")))
            if expiry.tzinfo is None:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ETFHoldingsRouteHeldError(
                "failed native request scope or URL is invalid"
            ) from exc
        hosts = (
            (source.config or {}).get("etf_holdings_review", {}).get("https_hosts", [])
            if isinstance(source.config, dict)
            else []
        )
        requested = log.requested_at
        completed = log.completed_at
        requested = _utc_datetime(requested) if isinstance(requested, datetime) else None
        completed = _utc_datetime(completed) if isinstance(completed, datetime) else None
        if (
            scope.get("attempt_id") != predecessor.id
            or scope.get("provider") != provider
            or scope.get("data_source_id") != source.id
            or scope.get("capability") != ProviderCapability.ETF_HOLDINGS.value
            or scope.get("operation") != NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION
            or scope.get("profile_id") != profile.id
            or scope.get("instrument_id") != profile.instrument_id
            or scope.get("provider_symbol") != profile.instrument.symbol.strip().upper()
            or scope.get("max_physical_requests")
            != ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS
            or scope.get("review_revision") is None
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(scope.get("provider_review_fingerprint") or "")
            )
            or log.data_source_id != source.id
            or log.capability != ProviderCapability.ETF_HOLDINGS
            or log.operation != NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION
            or log.instrument_id != profile.instrument_id
            or (log.provider_symbol or "").strip().upper()
            != profile.instrument.symbol.strip().upper()
            or log.success is not True
            or completed is None
            or log.http_requests != 1
            or not isinstance(log.settled_usage_units, Decimal | int | float)
            or Decimal(str(log.settled_usage_units)) <= 0
            or requested is None
            or requested < _utc_datetime(predecessor.started_at)
            or requested > _utc_datetime(expiry)
            or completed > _utc_datetime(expiry)
            or parsed_url.scheme.lower() != "https"
            or not parsed_url.hostname
            or parsed_url.hostname.lower() not in {str(host).lower() for host in hosts}
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.port not in (None, 443)
        ):
            raise ETFHoldingsRouteHeldError(
                "settled native request no longer matches its original reviewed scope"
            )
        capture = _retained_log_capture(log)
        expected_url_hash = hashlib.sha256(_canonical_request_url(url).encode("utf-8")).hexdigest()
        if (
            capture.get("physical_request_url_sha256") != expected_url_hash
            or capture.get("attempt_id") != predecessor.id
            or capture.get("provider") != provider
            or capture.get("data_source_id") != source.id
            or capture.get("capability") != ProviderCapability.ETF_HOLDINGS.value
            or capture.get("operation") != NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION
            or capture.get("profile_id") != profile.id
            or capture.get("instrument_id") != profile.instrument_id
            or capture.get("provider_symbol") != profile.instrument.symbol.strip().upper()
            or capture.get("account_scope") != scope.get("account_scope")
            or capture.get("review_revision") != scope.get("review_revision")
            or capture.get("provider_review_fingerprint")
            != scope.get("provider_review_fingerprint")
            or isinstance(capture.get("status_code"), bool)
            or not isinstance(capture.get("status_code"), int)
            or capture.get("status_code") not in range(200, 400)
        ):
            raise ETFHoldingsRouteHeldError(
                "retained response capture does not match its original reviewed scope"
            )

    captures = [_retained_log_capture(log) for log in request_logs]
    matching = [
        (log, url, capture)
        for log, url, capture in zip(request_logs, request_urls, captures, strict=True)
        if _canonical_request_url(url) == _canonical_request_url(rejected_artifact.source_url or "")
    ]
    if len(matching) != 1:
        raise ETFHoldingsRouteHeldError(
            "retained holdings artifact URL does not identify exactly one settled response"
        )
    holdings_log, _holdings_url, holdings_capture = matching[0]
    if holdings_capture.get("status_code") not in range(200, 300):
        raise ETFNativeSourceEvidenceError(
            "retained holdings body did not come from a successful final response"
        )
    response_payloads = holdings_log.response_payloads
    if not isinstance(response_payloads, list):
        raise ETFNativeSourceEvidenceError("Retained holdings response payload is missing")

    recovery_input: dict[str, Any]
    if provider == "spdr":
        binary_payloads = [
            item
            for item in response_payloads
            if isinstance(item, dict) and item.get("kind") == "etf_native_response_body"
        ]
        if (
            holdings_capture.get("binary_body") is not True
            or len(binary_payloads) != 1
            or binary_payloads[0].get("encoding") != "base64"
            or binary_payloads[0].get("complete") is not True
        ):
            raise ETFNativeSourceEvidenceError(
                "SPDR retained workbook bytes are not complete and uniquely captured"
            )
        try:
            workbook_bytes = base64.b64decode(
                binary_payloads[0].get("body_base64", ""), validate=True
            )
        except (TypeError, ValueError) as exc:
            raise ETFNativeSourceEvidenceError(
                "SPDR retained workbook encoding is invalid"
            ) from exc
        if (
            len(workbook_bytes) != holdings_capture.get("response_body_bytes")
            or len(workbook_bytes) != binary_payloads[0].get("bytes_received")
            or hashlib.sha256(workbook_bytes).hexdigest()
            != holdings_capture.get("response_body_sha256")
            or binary_payloads[0].get("sha256") != holdings_capture.get("response_body_sha256")
        ):
            raise ETFNativeSourceEvidenceError(
                "SPDR retained workbook bytes do not match the settled physical response"
            )
        workbook_rows = parse_xlsx_table(workbook_bytes)
        rows, composition_date, fund_symbol = adapter._parse_workbook(
            workbook_bytes, symbol=profile.instrument.symbol.strip().upper()
        )
        completeness = adapter._workbook_completeness(
            workbook_rows,
            rows=rows,
            fund_symbol=fund_symbol,
            composition_date=composition_date,
        )
        normalized_payload = {"source_format": "xlsx", "workbook_rows": workbook_rows}
        raw_text = _table_to_text(workbook_rows)
        if (
            payload != normalized_payload
            or rejected_artifact.payload_text != raw_text
            or fund_symbol != profile.instrument.symbol.strip().upper()
            or composition_date is None
            or completeness.get("status") != "complete"
        ):
            raise ETFNativeSourceEvidenceError(
                "SPDR retained workbook no longer proves a complete exact-fund composition"
            )
        result = HoldingsFetchResult(
            rows=rows,
            raw_text=raw_text,
            raw_json=normalized_payload,
            source_url=rejected_artifact.source_url,
            source_identifier=rejected_artifact.source_identifier,
            legal_metadata={
                "source_access": "spdr_fund_scoped_daily_holdings_xlsx",
                "source_provider": provider,
                "adapter_key": adapter.adapter_key,
                "source_format": "xlsx",
                "snapshot_provenance": "spdr_native_daily_holdings_workbook",
                "composition_date": composition_date.isoformat(),
                "native_composition_completeness": completeness,
            },
        )
        recovery_input = {
            "representation": "provider_request_log_binary_body",
            "request_log_id": holdings_log.id,
            "input_sha256": holdings_capture["response_body_sha256"],
            "input_bytes": len(workbook_bytes),
            "normalized_payload_sha256": _hash_payload(normalized_payload),
        }
    else:
        if (
            holdings_capture.get("binary_body") is True
            or not isinstance(payload, dict)
            or not isinstance(rejected_artifact.payload_json, dict)
        ):
            raise ETFNativeSourceEvidenceError(
                "iShares retained response has no normalized JSON body"
            )
        json_payloads = [
            item
            for item in response_payloads
            if isinstance(item, dict)
            and item.get("kind") != ETF_NATIVE_RESPONSE_BODY_WITNESS_KIND
            and item.get("kind") != "etf_native_response_body"
        ]
        if len(json_payloads) != 1 or json_payloads[0] != rejected_artifact.payload_json:
            raise ETFNativeSourceEvidenceError(
                "iShares Provider log and rejected artifact do not retain the same JSON object"
            )
        raw_json = rejected_artifact.payload_json
        rows = adapter._parse_blackrock_holdings_payload(raw_json)
        completeness = adapter._holdings_all_completeness(raw_json, rows=rows)
        reported_date = adapter._composition_date_from_payload(raw_json)
        composition_date = (
            date.fromisoformat(reported_date) if isinstance(reported_date, str) else reported_date
        )
        if (
            composition_date is None
            or completeness.get("status") != "complete"
            or catalog_identity is None
        ):
            raise ETFNativeSourceEvidenceError(
                "iShares retained JSON lacks exact catalog, reported date, or complete rows"
            )
        result = HoldingsFetchResult(
            rows=rows,
            raw_text=rejected_artifact.payload_text,
            raw_json=raw_json,
            source_url=rejected_artifact.source_url,
            source_identifier=rejected_artifact.source_identifier,
            legal_metadata={
                "source_access": adapter.config.source_access,
                "source_provider": provider,
                "adapter_key": adapter.adapter_key,
                "route_resolution": "issuer_public_json_api",
                "source_format": "json",
                "composition_date": composition_date.isoformat(),
                "native_composition_completeness": completeness,
                "issuer_product_id": catalog_identity["product_id"],
                "issuer_product_catalog": {
                    "catalog_key": catalog_identity["catalog_key"],
                    "catalog_source_url": catalog_identity["source_url"],
                    "catalog_final_url": catalog_identity["final_url"],
                    "catalog_content_sha256": catalog_identity["content_sha256"],
                    "catalog_retrieved_at": catalog_identity["retrieved_at"],
                    "catalog_request_log_ids": catalog_identity["request_log_ids"],
                    "catalog_cache_id": catalog_identity["cache_id"],
                    "catalog_cache_hit": catalog_identity["cache_hit"],
                    "ticker": catalog_identity["ticker"],
                    "name": catalog_identity["name"],
                    "issuer_product_id": catalog_identity["product_id"],
                    "product_url": catalog_identity["product_url"],
                    "catalog_complete": catalog_identity["catalog_complete"],
                    "catalog_reported_total": catalog_identity["catalog_reported_total"],
                },
            },
        )
        normalized_bytes = json.dumps(
            raw_json, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        recovery_input = {
            "representation": "provider_request_log_normalized_json_object",
            "request_log_id": holdings_log.id,
            "normalized_payload_sha256": _hash_payload(raw_json),
            "normalized_payload_bytes": len(normalized_bytes),
            "physical_response_sha256": holdings_capture["response_body_sha256"],
            "physical_response_bytes": holdings_capture["response_body_bytes"],
        }

    request_binding = SimpleNamespace(
        native_initial_qualification_job_id=predecessor.id,
        native_initial_qualification_scope=scope,
        request_log_ids=list(lineage_ids),
        request_urls_by_log_id=dict(zip(lineage_ids, request_urls, strict=True)),
        response_body_witnesses=captures,
    )
    source_evidence = _native_adapter_fetch_evidence(
        profile,
        adapter,
        result,
        request_binding=request_binding,
        require_body_witness=False,
    )
    if provider == "ishares" and source_evidence.get("fund_identity") != catalog_identity:
        raise ETFNativeSourceEvidenceError(
            "iShares normalized response and verified product catalog identity disagree"
        )
    continuation = {
        "version": 1,
        "predecessor_job_id": predecessor.id,
        "predecessor_job_type": predecessor.job_type,
        "source_provider": provider,
        "account_scope": scope["account_scope"],
        "review_revision": scope["review_revision"],
        "provider_review_fingerprint": scope["provider_review_fingerprint"],
        "provider_request_log_ids": list(lineage_ids),
        "request_urls": list(request_urls),
        "physical_http_requests": 0,
        "quota_reservations": 0,
        "physical_body_capture": holdings_capture,
        "recovery_input": recovery_input,
        "raw_artifact_id": rejected_artifact.id,
        "raw_artifact_sha256": rejected_artifact.content_hash,
    }
    source_evidence["retained_evidence_continuation"] = continuation
    return result, source_evidence, continuation


def _verify_persisted_qualification_adapter_state(
    state: ETFHoldingsAdapterState | None,
    *,
    profile: ETFProfile,
    source: DataSource,
    snapshot: ETFHoldingsSnapshot,
    evidence: dict[str, Any],
) -> None:
    """Require the ordinary-refresh schema state written with the snapshot."""

    state_metadata = state.extra_data if state is not None else None
    if not isinstance(state_metadata, dict):
        state_metadata = {}
    snapshot_metadata = snapshot.extra_data if isinstance(snapshot.extra_data, dict) else {}
    schema_fingerprint = evidence.get("schema_fingerprint")
    if (
        state is None
        or state.etf_profile_id != profile.id
        or state.adapter_key != (profile.adapter_key or source.name)
        or state.status != "success"
        or state.data_source_id != snapshot.data_source_id
        or state.source_url != snapshot.source_url
        or state.source_identifier != snapshot.source_identifier
        or state.parser_version != snapshot.parser_version
        or state.composition_date != snapshot.composition_date
        or state.row_count != snapshot.row_count
        or state.last_success_at is None
        or state_metadata.get("schema_fingerprint") != schema_fingerprint
        or snapshot_metadata.get("schema_fingerprint") != schema_fingerprint
    ):
        raise ETFHoldingsRouteHeldError(
            "native qualification persisted adapter schema state is incomplete or mismatched"
        )


def _verify_native_holdings_body_log_link(
    *,
    evidence: dict[str, Any],
    profile: ETFProfile,
    source: DataSource,
    snapshot: ETFHoldingsSnapshot,
    job: ETFHoldingsBackfillJob,
    request_ids: list[int],
    request_urls: list[str],
    logs_by_id: dict[int, ProviderRequestLog],
) -> None:
    """Require the artifact's parsed body witness on its exact settled log."""

    witness = evidence.get("holdings_response_body_witness")
    capture = witness.get("provider_capture") if isinstance(witness, dict) else None
    request_id = capture.get("request_log_id") if isinstance(capture, dict) else None
    if (
        not isinstance(witness, dict)
        or not isinstance(capture, dict)
        or isinstance(request_id, bool)
        or not isinstance(request_id, int)
        or request_id not in request_ids
        or len(request_ids) != len(request_urls)
    ):
        raise ETFHoldingsRouteHeldError(
            "native qualification holdings body witness has no exact request log"
        )
    index = request_ids.index(request_id)
    request_url = request_urls[index]
    request_log = logs_by_id.get(request_id)
    scope = (job.extra_data or {}).get("qualification_scope")
    expected_scope = {
        "attempt_id": job.id,
        "provider": source.name,
        "data_source_id": source.id,
        "capability": ProviderCapability.ETF_HOLDINGS.value,
        "operation": NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION,
        "profile_id": profile.id,
        "instrument_id": profile.instrument_id,
        "provider_symbol": profile.instrument.symbol.strip().upper(),
        "account_scope": scope.get("account_scope") if isinstance(scope, dict) else None,
        "review_revision": scope.get("review_revision") if isinstance(scope, dict) else None,
        "provider_review_fingerprint": (
            scope.get("provider_review_fingerprint") if isinstance(scope, dict) else None
        ),
    }
    request_url_hash = hashlib.sha256(
        _canonical_request_url(request_url).encode("utf-8")
    ).hexdigest()
    snapshot_url_hash = hashlib.sha256(
        _canonical_request_url(snapshot.source_url or "").encode("utf-8")
    ).hexdigest()
    if (
        request_log is None
        or not isinstance(scope, dict)
        or witness.get("parser_input_sha256") != capture.get("response_body_sha256")
        or witness.get("normalized_payload_sha256") != evidence.get("raw_payload_hash")
        or any(capture.get(key) != value for key, value in expected_scope.items())
        or capture.get("physical_request_url_sha256") != request_url_hash
        or capture.get("physical_request_url_sha256") != snapshot_url_hash
        or capture.get("status_code") not in range(200, 300)
        or request_log.response_bytes != capture.get("response_body_bytes")
    ):
        raise ETFHoldingsRouteHeldError(
            "native qualification body witness is outside the settled request scope or URL"
        )

    payloads = request_log.response_payloads
    if not isinstance(payloads, list):
        raise ETFHoldingsRouteHeldError(
            "native qualification request log has no captured response body witness"
        )
    persisted_witnesses = [
        payload.get("witness")
        for payload in payloads
        if isinstance(payload, dict)
        and payload.get("kind") == ETF_NATIVE_RESPONSE_BODY_WITNESS_KIND
    ]
    if persisted_witnesses != [capture]:
        raise ETFHoldingsRouteHeldError(
            "native qualification request log body witness is missing or mismatched"
        )
    if capture.get("binary_body") is True:
        binary_payloads = [
            payload
            for payload in payloads
            if isinstance(payload, dict) and payload.get("kind") == "etf_native_response_body"
        ]
        if len(binary_payloads) != 1:
            raise ETFHoldingsRouteHeldError(
                "native qualification binary response bytes were not retained exactly once"
            )
        binary = binary_payloads[0]
        try:
            body = base64.b64decode(binary.get("body_base64", ""), validate=True)
        except (ValueError, TypeError) as exc:
            raise ETFHoldingsRouteHeldError(
                "native qualification binary response log is invalid"
            ) from exc
        if (
            binary.get("encoding") != "base64"
            or binary.get("complete") is not True
            or binary.get("bytes_received") != capture.get("response_body_bytes")
            or hashlib.sha256(body).hexdigest() != capture.get("response_body_sha256")
        ):
            raise ETFHoldingsRouteHeldError(
                "native qualification binary response bytes do not match the body witness"
            )


def _verify_retained_evidence_body_log_link(
    *,
    evidence: dict[str, Any],
    profile: ETFProfile,
    source: DataSource,
    snapshot: ETFHoldingsSnapshot,
    job: ETFHoldingsBackfillJob,
    artifact: ETFHoldingsRawArtifact,
    request_ids: list[int],
    request_urls: list[str],
    logs_by_id: dict[int, ProviderRequestLog],
) -> None:
    """Verify a no-transport continuation without conflating JSON and wire bytes."""

    proof = evidence.get("retained_evidence_continuation")
    artifact_metadata = artifact.legal_metadata if isinstance(artifact.legal_metadata, dict) else {}
    scope = (job.extra_data or {}).get("qualification_scope")
    capture = proof.get("physical_body_capture") if isinstance(proof, dict) else None
    recovery_input = proof.get("recovery_input") if isinstance(proof, dict) else None
    log_id = capture.get("request_log_id") if isinstance(capture, dict) else None
    if (
        not isinstance(proof, dict)
        or proof.get("version") != 1
        or proof.get("predecessor_job_id") != job.id
        or proof.get("predecessor_job_type") != NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE
        or proof.get("source_provider") != source.name
        or proof.get("provider_request_log_ids") != request_ids
        or proof.get("request_urls") != request_urls
        or proof.get("physical_http_requests") != 0
        or proof.get("quota_reservations") != 0
        or artifact_metadata.get("retained_evidence_continuation") != proof
        or artifact_metadata.get("provider_request_log_ids") != request_ids
        or isinstance(log_id, bool)
        or not isinstance(log_id, int)
        or log_id not in request_ids
        or not isinstance(recovery_input, dict)
        or not isinstance(scope, dict)
    ):
        raise ETFHoldingsRouteHeldError(
            "retained-evidence continuation receipt is incomplete or mismatched"
        )
    log = logs_by_id.get(log_id)
    index = request_ids.index(log_id)
    request_url = request_urls[index]
    if (
        log is None
        or _canonical_request_url(snapshot.source_url or "") != _canonical_request_url(request_url)
        or capture.get("physical_request_url_sha256")
        != hashlib.sha256(_canonical_request_url(request_url).encode("utf-8")).hexdigest()
        or capture.get("response_body_bytes") != log.response_bytes
        or capture.get("status_code") not in range(200, 300)
        or capture.get("attempt_id") != job.id
        or capture.get("provider") != source.name
        or capture.get("data_source_id") != source.id
        or capture.get("profile_id") != profile.id
        or capture.get("instrument_id") != profile.instrument_id
        or capture.get("provider_symbol") != profile.instrument.symbol.strip().upper()
        or capture.get("account_scope") != scope.get("account_scope")
        or capture.get("review_revision") != scope.get("review_revision")
        or capture.get("provider_review_fingerprint") != scope.get("provider_review_fingerprint")
    ):
        raise ETFHoldingsRouteHeldError(
            "retained response body is outside the original settled request lineage"
        )
    persisted_captures = [
        item.get("witness")
        for item in log.response_payloads or []
        if isinstance(item, dict) and item.get("kind") == ETF_NATIVE_RESPONSE_BODY_WITNESS_KIND
    ]
    if persisted_captures != [capture]:
        raise ETFHoldingsRouteHeldError(
            "retained response capture differs from its immutable Provider request log"
        )

    if source.name == "spdr":
        binary_payloads = [
            item
            for item in log.response_payloads or []
            if isinstance(item, dict) and item.get("kind") == "etf_native_response_body"
        ]
        if (
            capture.get("binary_body") is not True
            or recovery_input.get("representation") != "provider_request_log_binary_body"
            or len(binary_payloads) != 1
        ):
            raise ETFHoldingsRouteHeldError("SPDR continuation is not bound to retained XLSX bytes")
        try:
            body = base64.b64decode(binary_payloads[0].get("body_base64", ""), validate=True)
        except (TypeError, ValueError) as exc:
            raise ETFHoldingsRouteHeldError("SPDR retained XLSX bytes are invalid") from exc
        digest = hashlib.sha256(body).hexdigest()
        if (
            binary_payloads[0].get("complete") is not True
            or binary_payloads[0].get("bytes_received") != len(body)
            or binary_payloads[0].get("sha256") != digest
            or digest != capture.get("response_body_sha256")
            or recovery_input.get("input_sha256") != digest
            or recovery_input.get("input_bytes") != len(body)
        ):
            raise ETFHoldingsRouteHeldError("SPDR retained XLSX reparse hash is inconsistent")
    elif source.name == "ishares":
        json_payloads = [
            item
            for item in log.response_payloads or []
            if isinstance(item, dict)
            and item.get("kind") != ETF_NATIVE_RESPONSE_BODY_WITNESS_KIND
            and item.get("kind") != "etf_native_response_body"
        ]
        payload = artifact.payload_json
        if (
            capture.get("binary_body") is True
            or recovery_input.get("representation") != "provider_request_log_normalized_json_object"
            or not isinstance(payload, dict)
            or len(json_payloads) != 1
            or json_payloads[0] != payload
        ):
            raise ETFHoldingsRouteHeldError(
                "iShares continuation is not bound to the retained normalized JSON object"
            )
        normalized_bytes = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        normalized_hash = _hash_payload(payload)
        if (
            normalized_hash != evidence.get("raw_payload_hash")
            or recovery_input.get("normalized_payload_sha256") != normalized_hash
            or recovery_input.get("normalized_payload_bytes") != len(normalized_bytes)
            or recovery_input.get("physical_response_sha256") != capture.get("response_body_sha256")
            or recovery_input.get("physical_response_bytes") != capture.get("response_body_bytes")
        ):
            raise ETFHoldingsRouteHeldError(
                "iShares normalized JSON hash is not linked to its retained physical capture"
            )
    else:
        raise ETFHoldingsRouteHeldError("retained-evidence provider is not supported")


async def _finalize_native_qualification(
    bind,
    *,
    attempt_id: int,
    status: str,
    reason: str,
) -> None:
    session = AsyncSession(bind=bind, expire_on_commit=False)
    try:
        job = await session.get(ETFHoldingsBackfillJob, attempt_id)
        if job is not None and job.status == "running":
            await session.refresh(job, attribute_names=["extra_data"])
            job.status = status
            job.failure_reason = reason
            job.completed_at = datetime.now(UTC)
            extra = dict(job.extra_data or {})
            extra["qualification_outcome"] = {"status": "not_qualified", "reason": reason}
            job.extra_data = extra
        await session.commit()
    finally:
        await session.close()


async def _await_shielded_finalizer(coro) -> None:
    task = asyncio.create_task(coro)
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    task.result()


async def qualify_native_etf_fund(
    db: AsyncSession,
    *,
    profile_id: int,
    requested_by_user_id: int,
) -> ETFHoldingsBackfillJob:
    """Execute one admin-only native qualification, without enabling its policy."""

    require_unbound_etf_holdings_context("native ETF initial qualification")
    if not settings.PROVIDER_ROUTING_ENABLED:
        raise ETFHoldingsRouteHeldError("shared Provider routing is disabled")
    bind_native, fingerprint = _native_provider_contract()
    operation_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    lock_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    attempt: ETFHoldingsBackfillJob | None = None
    attempt_id: int | None = None
    try:
        (
            profile,
            source,
            policy,
            entitlement,
            adapter,
            provider_name,
            account_scope,
            review_fingerprint,
        ) = await _current_native_rows(operation_db, profile_id=profile_id)
        lock_instrument_id = profile.instrument_id
        lock_provider_name = provider_name
        if lock_db.get_bind().dialect.name != "postgresql":
            raise ETFHoldingsRouteHeldError(
                "cross-process native qualification serialization requires PostgreSQL"
            )
        await lock_db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _qualification_lock_key(provider_name, profile.instrument_id)},
        )
        await operation_db.rollback()
        (
            profile,
            source,
            policy,
            entitlement,
            adapter,
            provider_name,
            account_scope,
            review_fingerprint,
        ) = await _current_native_rows(operation_db, profile_id=profile_id)
        if profile.instrument_id != lock_instrument_id or provider_name != lock_provider_name:
            raise ETFHoldingsRouteHeldError(
                "native ETF route changed while waiting for its one-shot lock"
            )
        prior_jobs = list(
            (
                await operation_db.scalars(
                    select(ETFHoldingsBackfillJob)
                    .join(
                        ETFProfile,
                        ETFProfile.id == ETFHoldingsBackfillJob.etf_profile_id,
                    )
                    .where(
                        ETFProfile.instrument_id == profile.instrument_id,
                        ETFHoldingsBackfillJob.source_provider == provider_name,
                        ETFHoldingsBackfillJob.job_type
                        == NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE,
                    )
                )
            ).all()
        )
        _require_one_shot_available(prior_jobs)

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ETF_NATIVE_INITIAL_QUALIFICATION_DEADLINE_SECONDS)
        attempt = ETFHoldingsBackfillJob(
            etf_profile_id=profile.id,
            requested_by_user_id=requested_by_user_id,
            source_provider=provider_name,
            job_type=NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE,
            status="running",
            max_filings=None,
            started_at=now,
            discovered_count=0,
            ingested_count=0,
            skipped_count=0,
            failed_count=0,
            extra_data={"qualification_outcome": {"status": "in_progress"}},
        )
        operation_db.add(attempt)
        await operation_db.flush()
        # Keep the durable identifier independent of ORM expiration.  A later
        # rollback expires ``attempt`` even with expire_on_commit=False.
        attempt_id = int(attempt.id)
        scope = _attempt_scope(
            attempt_id=attempt_id,
            provider_name=provider_name,
            data_source_id=source.id,
            profile=profile,
            account_scope=account_scope,
            entitlement_revision=entitlement.revision,
            review_fingerprint=review_fingerprint,
            expires_at=expires_at,
        )
        attempt.extra_data = {
            "qualification_scope": scope,
            "qualification_outcome": {"status": "in_progress"},
            "provider_request_log_ids": [],
            "request_urls": [],
        }
        await operation_db.commit()

        with bind_native(
            attempt_id=attempt_id,
            provider_name=provider_name,
            data_source_id=source.id,
            fund_profile_id=profile.id,
            instrument_id=profile.instrument_id,
            provider_symbol=profile.instrument.symbol.strip().upper(),
            operation=NATIVE_ETF_INITIAL_QUALIFICATION_OPERATION,
            account_scope=account_scope,
            entitlement_revision=entitlement.revision,
            provider_review_fingerprint=review_fingerprint,
            expires_at=expires_at,
            max_physical_requests=ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS,
        ):
            snapshot = await _refresh_adapter_route(
                operation_db,
                profile,
                native_initial_qualification_job_id=attempt_id,
                native_initial_qualification_scope=scope,
            )

        snapshot, raw_artifact, request_logs = await _verify_qualification_snapshot(
            operation_db,
            snapshot_id=snapshot.id,
            profile=profile,
            source=source,
            job=attempt,
        )
        current_rows = await _current_native_rows(operation_db, profile_id=profile.id)
        (
            current_profile,
            current_source,
            current_policy,
            current_entitlement,
            current_adapter,
            current_provider,
            current_account_scope,
            current_fingerprint,
        ) = current_rows
        if (
            not _native_review_snapshot_still_matches(
                scope=scope,
                profile=current_profile,
                source=current_source,
                policy=current_policy,
                entitlement=current_entitlement,
                adapter=current_adapter,
                initial_adapter=adapter,
                provider_name=current_provider,
                account_scope=current_account_scope,
                review_fingerprint=current_fingerprint,
                now=datetime.now(UTC),
            )
            or not request_logs
            or raw_artifact.id != snapshot.source_artifact_id
        ):
            raise ETFHoldingsRouteHeldError(
                "native publisher review or evidence changed before qualification commit"
            )

        current_entitlement.live_probe_status = "passed"
        current_entitlement.revision = int(current_entitlement.revision) + 1
        extra = dict(attempt.extra_data or {})
        extra["qualification_snapshot_id"] = snapshot.id
        extra["qualification_raw_artifact_id"] = raw_artifact.id
        extra["qualification_request_log_ids"] = [row.id for row in request_logs]
        extra["qualification_outcome"] = {
            "status": "passed",
            "qualified_at": datetime.now(UTC).isoformat(),
            "snapshot_id": snapshot.id,
            "raw_artifact_id": raw_artifact.id,
            "request_log_ids": [row.id for row in request_logs],
        }
        attempt.extra_data = extra
        attempt.status = "completed"
        attempt.failure_reason = None
        attempt.completed_at = datetime.now(UTC)
        attempt.discovered_count = snapshot.row_count
        attempt.ingested_count = 1
        await operation_db.flush()
        await record_entitlement_revision(
            operation_db,
            current_entitlement,
            change_reason=f"native_etf_initial_qualification:{attempt_id}",
        )
        await operation_db.commit()
        return (
            await operation_db.execute(
                select(ETFHoldingsBackfillJob)
                .options(selectinload(ETFHoldingsBackfillJob.filings))
                .where(ETFHoldingsBackfillJob.id == attempt_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
    except asyncio.CancelledError:
        await operation_db.rollback()
        if attempt_id is not None:
            await _await_shielded_finalizer(
                _finalize_native_qualification(
                    db.bind,
                    attempt_id=attempt_id,
                    status="cancelled",
                    reason="native ETF initial qualification was cancelled; replay denied",
                )
            )
        raise
    except BaseException as exc:
        await operation_db.rollback()
        if attempt_id is not None:
            await _await_shielded_finalizer(
                _finalize_native_qualification(
                    db.bind,
                    attempt_id=attempt_id,
                    status="failed",
                    reason=bounded_redact_provider_message(exc, max_length=1000),
                )
            )
        raise
    finally:
        await lock_db.close()
        await operation_db.close()


async def _require_current_free_scope(
    db: AsyncSession, *, source: DataSource, account_scope: str
) -> None:
    digest = hashlib.sha256(account_scope.strip().encode("utf-8")).hexdigest()
    now = datetime.now(UTC)

    def admitted(sync_session) -> bool:
        decision = provider_recurring_cost_status(sync_session)
        budget = sync_session.get(ProviderRecurringCostBudget, 1)
        commitment = sync_session.scalar(
            select(ProviderRecurringCostCommitment).where(
                ProviderRecurringCostCommitment.data_source_id == source.id,
                ProviderRecurringCostCommitment.environment == settings.APP_ENV.strip().lower(),
                ProviderRecurringCostCommitment.billing_account_scope_digest == digest,
            )
        )
        if not decision.allowed or budget is None or commitment is None:
            return False
        effective_at = _utc_datetime(commitment.effective_at)
        ends_at = _utc_datetime(commitment.ends_at) if commitment.ends_at is not None else None
        return bool(
            budget.currency == "USD"
            and commitment.state == "active"
            and effective_at <= now
            and (ends_at is None or ends_at > now)
            and Decimal(str(commitment.amount)) == Decimal("0")
            and Decimal(str(commitment.monthly_equivalent)) == Decimal("0")
            and commitment.currency == "USD"
            and commitment.post_trial_amount is None
        )

    if not await db.run_sync(admitted):
        raise ETFHoldingsRouteHeldError(
            "retained-evidence continuation requires the current verified-free account commitment"
        )


async def _retained_ishares_catalog_claim(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    source: DataSource,
    predecessor: ETFHoldingsBackfillJob,
) -> dict[str, Any]:
    extra = predecessor.extra_data if isinstance(predecessor.extra_data, dict) else {}
    request_ids = extra.get("provider_request_log_ids")
    if not isinstance(request_ids, list):
        raise ETFHoldingsRouteHeldError("iShares failed job has no catalog request lineage")
    candidates = list(
        (
            await db.scalars(
                select(ETFIssuerCatalogCache).where(
                    ETFIssuerCatalogCache.provider_name == source.name,
                    ETFIssuerCatalogCache.catalog_key == ISHARES_US_CATALOG_KEY,
                    ETFIssuerCatalogCache.data_source_id == source.id,
                    ETFIssuerCatalogCache.requested_symbol
                    == profile.instrument.symbol.strip().upper(),
                )
            )
        ).all()
    )
    matches = [
        cache
        for cache in candidates
        if isinstance(cache.provider_request_log_ids, list)
        and cache.provider_request_log_ids
        and set(cache.provider_request_log_ids) <= set(request_ids)
    ]
    if len(matches) != 1:
        raise ETFHoldingsRouteHeldError(
            "iShares failed job does not identify exactly one retained catalog response"
        )
    cache = matches[0]
    try:
        body = base64.b64decode(cache.raw_body_base64, validate=True)
        if (
            len(body) != cache.response_bytes
            or hashlib.sha256(body).hexdigest() != cache.content_sha256
            or cache.source_url != ISHARES_US_CATALOG_URL
        ):
            raise ValueError("catalog bytes differ from retained cache metadata")
        catalog = parse_ishares_us_product_catalog(
            body.decode(cache.response_encoding, errors="strict"), page_url=cache.final_url
        )
    except (IssuerCatalogError, UnicodeDecodeError, TypeError, ValueError, LookupError) as exc:
        raise ETFHoldingsRouteHeldError("retained iShares catalog content is invalid") from exc
    product = catalog.product_for(profile.instrument.symbol.strip().upper())
    if (
        product is None
        or not catalog.complete
        or not cache.catalog_complete
        or catalog.reported_total != cache.reported_total
        or [entry.as_json() for entry in catalog.entries] != cache.parsed_entries
        or not catalog_product_matches_canonical_fund(
            product=product,
            ticker=profile.instrument.symbol.strip().upper(),
            canonical_name=str(profile.instrument.name or ""),
        )
    ):
        raise ETFHoldingsRouteHeldError(
            "retained iShares catalog does not prove the exact canonical fund"
        )
    metadata = {
        "catalog_key": cache.catalog_key,
        "catalog_source_url": cache.source_url,
        "catalog_final_url": cache.final_url,
        "catalog_content_sha256": cache.content_sha256,
        "catalog_retrieved_at": _utc_datetime(cache.fetched_at).isoformat(),
        "catalog_request_log_ids": cache.provider_request_log_ids,
        "catalog_cache_id": cache.id,
        "catalog_cache_hit": False,
        "ticker": product.ticker,
        "name": product.name,
        "issuer_product_id": product.product_id,
        "product_url": product.product_url,
        "catalog_complete": catalog.complete,
        "catalog_reported_total": catalog.reported_total,
    }
    claim = _issuer_catalog_identity_claim(profile, metadata)
    if claim is None:
        raise ETFHoldingsRouteHeldError("retained iShares catalog identity claim is invalid")
    await _verify_issuer_catalog_identity_evidence(
        db,
        evidence=claim,
        profile=profile,
        source=source,
        job=predecessor,
    )
    return claim


async def _finalize_retained_evidence_continuation(
    bind, *, attempt_id: int, status: str, outcome: dict[str, Any], reason: str | None = None
) -> None:
    session = AsyncSession(bind=bind, expire_on_commit=False)
    try:
        attempt = await session.get(ETFHoldingsBackfillJob, attempt_id)
        if attempt is not None and attempt.status == "running":
            extra = dict(attempt.extra_data or {})
            extra["retained_evidence_continuation"] = {
                **dict(extra.get("retained_evidence_continuation") or {}),
                "outcome": outcome,
            }
            attempt.extra_data = extra
            attempt.status = status
            attempt.failure_reason = reason
            attempt.completed_at = datetime.now(UTC)
            if status == "completed":
                attempt.ingested_count = 1
                attempt.discovered_count = int(outcome.get("row_count") or 0)
            else:
                attempt.failed_count = 1
        await session.commit()
    finally:
        await session.close()


async def continue_native_etf_fund_from_retained_evidence(
    db: AsyncSession,
    *,
    predecessor_job_id: int,
    expected_symbol: str,
    requested_by_user_id: int,
) -> ETFHoldingsBackfillJob:
    """Qualify one exact failed SPDR/iShares response without new transport."""

    require_unbound_etf_holdings_context("native ETF retained-evidence continuation")
    if not settings.PROVIDER_ROUTING_ENABLED:
        raise ETFHoldingsRouteHeldError("shared Provider routing is disabled")
    operation_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    lock_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    continuation_id: int | None = None
    try:
        predecessor = await operation_db.get(ETFHoldingsBackfillJob, predecessor_job_id)
        if predecessor is None or predecessor.status != "failed":
            raise ETFHoldingsRouteHeldError("only a retained failed native job can be continued")
        if predecessor.job_type != NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE:
            raise ETFHoldingsRouteHeldError("predecessor is not a native initial qualification")
        profile_id = predecessor.etf_profile_id
        current = await _current_native_rows(operation_db, profile_id=profile_id)
        profile, source, policy, entitlement, adapter, provider, account_scope, fingerprint = (
            current
        )
        if (
            provider not in {"spdr", "ishares"}
            or predecessor.source_provider != provider
            or profile.instrument.symbol.strip().upper() != expected_symbol.strip().upper()
        ):
            raise ETFHoldingsRouteHeldError(
                "failed job does not match this current SPDR/iShares canonical route"
            )
        if lock_db.get_bind().dialect.name != "postgresql":
            raise ETFHoldingsRouteHeldError(
                "retained native continuation serialization requires PostgreSQL"
            )
        await lock_db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _qualification_lock_key(provider, profile.instrument_id)},
        )
        await operation_db.rollback()
        predecessor = await operation_db.get(ETFHoldingsBackfillJob, predecessor_job_id)
        current = await _current_native_rows(operation_db, profile_id=profile_id)
        profile, source, policy, entitlement, adapter, provider, account_scope, fingerprint = (
            current
        )
        if predecessor is None or predecessor.status != "failed":
            raise ETFHoldingsRouteHeldError("failed predecessor changed during continuation lock")
        if (
            provider not in {"spdr", "ishares"}
            or predecessor.source_provider != provider
            or profile.instrument.symbol.strip().upper() != expected_symbol.strip().upper()
        ):
            raise ETFHoldingsRouteHeldError("native route changed during continuation lock")

        original_jobs = list(
            (
                await operation_db.scalars(
                    select(ETFHoldingsBackfillJob).where(
                        ETFHoldingsBackfillJob.etf_profile_id == profile.id,
                        ETFHoldingsBackfillJob.source_provider == provider,
                        ETFHoldingsBackfillJob.job_type
                        == NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE,
                    )
                )
            ).all()
        )
        if len(original_jobs) != 1 or original_jobs[0].id != predecessor.id:
            raise ETFHoldingsRouteHeldError(
                "retained continuation requires the sole original failed one-shot job"
            )
        prior_continuations = list(
            (
                await operation_db.scalars(
                    select(ETFHoldingsBackfillJob).where(
                        ETFHoldingsBackfillJob.etf_profile_id == profile.id,
                        ETFHoldingsBackfillJob.source_provider == provider,
                        ETFHoldingsBackfillJob.job_type
                        == NATIVE_ETF_RETAINED_EVIDENCE_CONTINUATION_JOB_TYPE,
                    )
                )
            ).all()
        )
        if any(
            isinstance(job.extra_data, dict)
            and (job.extra_data.get("retained_evidence_continuation") or {}).get(
                "predecessor_job_id"
            )
            == predecessor.id
            for job in prior_continuations
        ):
            raise ETFHoldingsRouteHeldError(
                "a retained-evidence continuation was already recorded for this failed job"
            )
        scope = (predecessor.extra_data or {}).get("qualification_scope")
        if (
            not isinstance(scope, dict)
            or scope.get("provider") != provider
            or scope.get("data_source_id") != source.id
            or scope.get("profile_id") != profile.id
            or scope.get("instrument_id") != profile.instrument_id
            or scope.get("provider_symbol") != profile.instrument.symbol.strip().upper()
            or scope.get("account_scope") != account_scope
            or scope.get("review_revision") != entitlement.revision
            or scope.get("provider_review_fingerprint") != fingerprint
        ):
            raise ETFHoldingsRouteHeldError(
                "failed request review/account scope no longer matches current disabled review"
            )
        await _require_current_free_scope(operation_db, source=source, account_scope=account_scope)

        now = datetime.now(UTC)
        continuation = ETFHoldingsBackfillJob(
            etf_profile_id=profile.id,
            requested_by_user_id=requested_by_user_id,
            source_provider=provider,
            job_type=NATIVE_ETF_RETAINED_EVIDENCE_CONTINUATION_JOB_TYPE,
            status="running",
            max_filings=None,
            started_at=now,
            discovered_count=0,
            ingested_count=0,
            skipped_count=0,
            failed_count=0,
            extra_data={
                "retained_evidence_continuation": {
                    "predecessor_job_id": predecessor.id,
                    "status": "in_progress",
                    "physical_http_requests": 0,
                    "quota_reservations": 0,
                }
            },
        )
        operation_db.add(continuation)
        await operation_db.flush()
        continuation_id = int(continuation.id)
        await operation_db.commit()

        try:
            predecessor = await operation_db.get(ETFHoldingsBackfillJob, predecessor_job_id)
            if predecessor is None:
                raise ETFHoldingsRouteHeldError("retained failed predecessor disappeared")
            original_extra = (
                predecessor.extra_data if isinstance(predecessor.extra_data, dict) else {}
            )
            request_ids = original_extra.get("provider_request_log_ids")
            request_urls = original_extra.get("request_urls")
            if (
                not isinstance(request_ids, list)
                or not isinstance(request_urls, list)
                or len(request_ids) != len(request_urls)
                or not request_ids
                or len(request_ids) > ETF_NATIVE_INITIAL_QUALIFICATION_MAX_PHYSICAL_REQUESTS
            ):
                raise ETFHoldingsRouteHeldError(
                    "failed job has no bounded physical request lineage"
                )
            request_logs = list(
                (
                    await operation_db.scalars(
                        select(ProviderRequestLog).where(ProviderRequestLog.id.in_(request_ids))
                    )
                ).all()
            )
            logs_by_id = {row.id: row for row in request_logs}
            if len(logs_by_id) != len(request_ids):
                raise ETFHoldingsRouteHeldError("failed job request logs are incomplete")
            request_logs = [logs_by_id[value] for value in request_ids]
            rejected_candidates = list(
                (
                    await operation_db.scalars(
                        select(ETFHoldingsRawArtifact).where(
                            ETFHoldingsRawArtifact.etf_profile_id == profile.id,
                            ETFHoldingsRawArtifact.data_source_id == source.id,
                            ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
                        )
                    )
                ).all()
            )
            rejected = [
                artifact
                for artifact in rejected_candidates
                if isinstance(artifact.legal_metadata, dict)
                and artifact.legal_metadata.get("provider_request_log_ids") == request_ids
                and artifact.legal_metadata.get("request_urls") == request_urls
            ]
            if len(rejected) != 1:
                raise ETFHoldingsRouteHeldError(
                    "failed job does not identify exactly one retained rejected response artifact"
                )
            catalog_identity = (
                await _retained_ishares_catalog_claim(
                    operation_db,
                    profile=profile,
                    source=source,
                    predecessor=predecessor,
                )
                if provider == "ishares"
                else None
            )
            fetch_result, evidence, continuation_proof = _reparse_retained_native_failure(
                profile=profile,
                adapter=adapter,
                predecessor=predecessor,
                rejected_artifact=rejected[0],
                source=source,
                request_logs=request_logs,
                request_urls=request_urls,
                catalog_identity=catalog_identity,
            )
            composition_date = date.fromisoformat(evidence["composition_date"])
            completeness = evidence["composition_completeness"]
            parser_version = evidence["parser_version"]
            result_metadata = {
                **(fetch_result.legal_metadata or {}),
                "native_initial_qualification_evidence": evidence,
                "native_composition_completeness_evidence": completeness,
                "composition_date": composition_date.isoformat(),
                "composition_date_source_field": evidence["composition_date_source_field"],
                "provider_request_log_ids": list(request_ids),
                "provider_request_attempts": (rejected[0].legal_metadata or {}).get(
                    "request_attempts", []
                ),
                "retained_evidence_continuation": continuation_proof,
                "source_quality": "self_snapshotted_holdings",
                "expected_cadence": fetch_result.legal_metadata.get("expected_cadence"),
            }
            from app.services.etf_holdings_refresh import (  # noqa: PLC0415
                _holdings_completeness_status,
                _native_artifact_identity_validation,
            )

            completeness_status = _holdings_completeness_status(result_metadata, {})
            if completeness_status != "complete":
                raise ETFNativeSourceEvidenceError(
                    "retained native response is not verified complete"
                )
            artifact_identity_validation = _native_artifact_identity_validation(
                profile,
                {"status": "unverified"},
                evidence,
            )
            if artifact_identity_validation.get("status") != "matched":
                raise ETFNativeSourceEvidenceError(
                    "retained native fund identity cannot be projected to the selected profile"
                )
            result_metadata["artifact_identity_validation"] = artifact_identity_validation
            if not isinstance(fetch_result.source_url, str) or not fetch_result.source_url.strip():
                raise ETFNativeSourceEvidenceError("retained holdings URL is absent")
            captured_at = request_logs[
                request_ids.index(continuation_proof["physical_body_capture"]["request_log_id"])
            ].completed_at
            if captured_at is None:
                raise ETFNativeSourceEvidenceError(
                    "retained holdings response has no completion time"
                )
            known_at = _utc_datetime(captured_at)
            snapshot = await ingest_holdings_snapshot(
                operation_db,
                etf_instrument=profile.instrument,
                rows=fetch_result.rows,
                composition_date=composition_date,
                known_at=known_at,
                provenance=str(
                    fetch_result.legal_metadata.get("snapshot_provenance")
                    or "issuer_self_snapshotted_holdings"
                ),
                source_provider=provider,
                source_url=fetch_result.source_url,
                source_identifier=fetch_result.source_identifier,
                source_quality="self_snapshotted_holdings",
                completeness_status=completeness_status,
                parser_version=parser_version,
                raw_payload_text=fetch_result.raw_text,
                raw_payload_json=fetch_result.raw_json,
                schema_fingerprint_override=evidence["schema_fingerprint"],
                legal_metadata={
                    **result_metadata,
                    "composition_date": composition_date.isoformat(),
                    "timing_provenance": {
                        "composition_date": f"provider_reported:{evidence['composition_date_source_field']}",
                        "known_at": "original_settled_provider_request_completed_at",
                        "published_at": "not_reported",
                    },
                },
                notes="Qualified from the exact retained settled native response; no new request was made.",
                allow_provider_enrichment=False,
                snapshot_extra_data={
                    "retained_evidence_continuation": continuation_proof,
                    "timing_provenance": {
                        "composition_date": f"provider_reported:{evidence['composition_date_source_field']}",
                        "known_at": "original_settled_provider_request_completed_at",
                    },
                },
            )
            snapshot, raw_artifact, verified_logs = await _verify_qualification_snapshot(
                operation_db,
                snapshot_id=snapshot.id,
                profile=profile,
                source=source,
                job=predecessor,
            )
            if (
                not verified_logs
                or raw_artifact.id != snapshot.source_artifact_id
                or raw_artifact.content_hash != evidence["raw_payload_hash"]
            ):
                raise ETFHoldingsRouteHeldError(
                    "retained evidence snapshot failed its persisted lineage check"
                )
            current = await _current_native_rows(operation_db, profile_id=profile.id)
            (
                current_profile,
                current_source,
                current_policy,
                current_entitlement,
                current_adapter,
                current_provider,
                current_account_scope,
                current_fingerprint,
            ) = current
            if (
                current_profile.instrument_id != profile.instrument_id
                or current_source.id != source.id
                or current_policy.is_enabled
                or current_entitlement.revision != scope["review_revision"]
                or current_provider != provider
                or current_account_scope != account_scope
                or current_fingerprint != fingerprint
                or current_adapter is not adapter
            ):
                raise ETFHoldingsRouteHeldError(
                    "current disabled publisher review changed before retained qualification"
                )
            current_entitlement.live_probe_status = "passed"
            current_entitlement.revision = int(current_entitlement.revision) + 1
            continuation_job = await operation_db.get(ETFHoldingsBackfillJob, continuation_id)
            if continuation_job is None:
                raise ETFHoldingsRouteHeldError("retained continuation receipt disappeared")
            continuation_job.extra_data = {
                **dict(continuation_job.extra_data or {}),
                "retained_evidence_continuation": {
                    "predecessor_job_id": predecessor.id,
                    "status": "passed_from_retained_evidence",
                    "physical_http_requests": 0,
                    "quota_reservations": 0,
                    "snapshot_id": snapshot.id,
                    "raw_artifact_id": raw_artifact.id,
                    "raw_payload_sha256": evidence["raw_payload_hash"],
                    "physical_body_sha256": continuation_proof["physical_body_capture"][
                        "response_body_sha256"
                    ],
                    "recovery_input": continuation_proof["recovery_input"],
                    "request_log_ids": list(request_ids),
                    "row_count": snapshot.row_count,
                    "composition_date": snapshot.composition_date.isoformat(),
                },
            }
            continuation_job.status = "completed"
            continuation_job.failure_reason = None
            continuation_job.completed_at = datetime.now(UTC)
            continuation_job.discovered_count = snapshot.row_count
            continuation_job.ingested_count = 1
            await operation_db.flush()
            await record_entitlement_revision(
                operation_db,
                current_entitlement,
                change_reason=f"native_etf_retained_evidence_continuation:{continuation_id}",
            )
            await operation_db.commit()
            return (
                await operation_db.execute(
                    select(ETFHoldingsBackfillJob)
                    .options(selectinload(ETFHoldingsBackfillJob.filings))
                    .where(ETFHoldingsBackfillJob.id == continuation_id)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
        except asyncio.CancelledError:
            await operation_db.rollback()
            await _await_shielded_finalizer(
                _finalize_retained_evidence_continuation(
                    db.bind,
                    attempt_id=continuation_id,
                    status="cancelled",
                    outcome={
                        "status": "cancelled",
                        "predecessor_job_id": predecessor_job_id,
                        "physical_http_requests": 0,
                        "quota_reservations": 0,
                    },
                    reason="retained evidence continuation was cancelled; replay denied",
                )
            )
            raise
        except (ETFHoldingsRouteHeldError, ETFNativeSourceEvidenceError, IssuerCatalogError) as exc:
            await operation_db.rollback()
            reason = bounded_redact_provider_message(exc, max_length=1000)
            await _await_shielded_finalizer(
                _finalize_retained_evidence_continuation(
                    db.bind,
                    attempt_id=continuation_id,
                    status="failed",
                    outcome={
                        "status": "not_qualified",
                        "predecessor_job_id": predecessor_job_id,
                        "physical_http_requests": 0,
                        "quota_reservations": 0,
                        "reason": reason,
                    },
                    reason=reason,
                )
            )
            return (
                await operation_db.execute(
                    select(ETFHoldingsBackfillJob)
                    .options(selectinload(ETFHoldingsBackfillJob.filings))
                    .where(ETFHoldingsBackfillJob.id == continuation_id)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
        except BaseException as exc:
            await operation_db.rollback()
            await _await_shielded_finalizer(
                _finalize_retained_evidence_continuation(
                    db.bind,
                    attempt_id=continuation_id,
                    status="failed",
                    outcome={
                        "status": "internal_error",
                        "predecessor_job_id": predecessor_job_id,
                        "physical_http_requests": 0,
                        "quota_reservations": 0,
                    },
                    reason=bounded_redact_provider_message(exc, max_length=1000),
                )
            )
            raise
    finally:
        await lock_db.close()
        await operation_db.close()
