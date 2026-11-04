"""One-shot admin qualification for a reviewed native ETF holdings adapter."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

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
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers.errors import bounded_redact_provider_message
from app.services.etf_holdings import ETF_HOLDINGS_INTERNAL_PROVIDER, _hash_payload
from app.services.etf_holdings_adapters import get_holdings_adapter
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
from app.services.provider_runtime import (
    provider_entitlement_admission,
    record_entitlement_revision,
)

NATIVE_ETF_INITIAL_QUALIFICATION_JOB_TYPE = "native_etf_initial_qualification"
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
