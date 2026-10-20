from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityCell, CapabilityRequirement, Degradation
from app.strategy_lab_v2.capability_preparation import CapabilityPreflightService
from app.strategy_lab_v2.capability_summary import CapabilitySummaryDecision
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    DataSeriesManifest,
    EventGranularity,
    ProductClass,
)
from app.strategy_lab_v2.execution_capabilities import ExecutionCapabilityBinding
from app.strategy_lab_v2.provider_series_contract import (
    ProviderSeriesCapabilityEvidence,
    provider_coverage_evidence_digest,
)

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 2, 1, tzinfo=UTC)
_NOW = datetime(2026, 10, 20, 20, tzinfo=UTC)


def _requirement(*, session: str = "regular") -> CapabilityRequirement:
    return CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=_START,
        end=_END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session=session,
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash-equity",
        corporate_action_semantics="split-v1",
    )


def _cell() -> CapabilityCell:
    return CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
        corporate_action_semantics=frozenset({"split-v1"}),
        history_start=_START,
        history_end=_END,
        evidence_digest=content_digest("trusted-coverage-evidence"),
    )


def _provider_evidence(
    *,
    identity_status: str = "resolved",
    coverage_status: str = "ready",
    dataset_status: str = "fresh",
    content_marker: str = "bars-v1",
) -> ProviderSeriesCapabilityEvidence:
    instrument = SimpleNamespace(
        id=7,
        domain_key="US.AAPL",
        identity_status=identity_status,
    )
    series = SimpleNamespace(
        id=31,
        instrument_id=7,
        data_source_id=4,
        source_series_key="AAPL:D1:consolidated:regular:split_adjusted:v1",
        timeframe="D1",
        session_code="regular",
        feed_scope="consolidated",
        adjustment_basis="split_adjusted",
        is_active=True,
        provenance={"provider": "local-provider", "corporate_action_semantics": "split-v1"},
    )
    assessment = SimpleNamespace(
        status=coverage_status,
        covered_start=datetime(2024, 1, 2, tzinfo=UTC),
        covered_end=datetime(2024, 1, 31, tzinfo=UTC),
        bar_count=22,
        missing_slices=()
        if coverage_status == "ready"
        else ((datetime(2024, 1, 10, tzinfo=UTC), datetime(2024, 1, 11, tzinfo=UTC)),),
    )
    calendar_digest = content_digest("XNYS-calendar-v1")
    manifest = DataSeriesManifest(
        instrument_id="US.AAPL",
        event_type="ohlcv",
        event_granularity=EventGranularity.BAR,
        timeframe="D1",
        session="regular",
        feed="consolidated",
        start=_START,
        end=_END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        corporate_action_semantics="split-v1",
        coverage_evidence_digest=content_digest("placeholder"),
        content_digest=content_digest(content_marker),
        row_count=22,
    )
    manifest = replace(
        manifest,
        coverage_evidence_digest=provider_coverage_evidence_digest(
            instrument,
            series,
            assessment,
            calendar_digest=calendar_digest,
        ),
    )
    state = SimpleNamespace(
        instrument_id=7,
        data_source_id=4,
        dataset_type="ohlcv",
        dataset_key="D1:adj",
        status=dataset_status,
        stale_after=datetime(2026, 10, 21, tzinfo=UTC),
        fetched_at=datetime(2026, 10, 20, 19, tzinfo=UTC),
        coverage_start=datetime(2024, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2024, 2, 1, tzinfo=UTC),
    )
    return ProviderSeriesCapabilityEvidence(
        instrument=instrument,
        series=series,
        manifest=manifest,
        coverage_assessment=assessment,
        dataset_state=state,
        calendar_digest=calendar_digest,
        evaluated_at=_NOW,
        product_class=ProductClass.EQUITY,
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
    )


def _binding() -> ExecutionCapabilityBinding:
    return ExecutionCapabilityBinding(
        engine_name="nautilus",
        engine_version="2.0.0rc6",
        engine_build_digest=content_digest("wheel-image-build"),
        conformance_fingerprint=content_digest("exact-conformance-report"),
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
        authoritative=True,
    )


def _payload(*, session: str = "regular", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requirements": [
            {
                "instrument_id": "US.AAPL",
                "product_class": "equity",
                "event_granularity": "bar",
                "event_type": "ohlcv",
                "timeframe": "1d",
                "start": _START.isoformat(),
                "end": _END.isoformat(),
                "adjustment": "split_adjusted",
                "session": session,
                "feed": "consolidated",
                "execution_model": "bar-close",
                "account_model": "cash-equity",
                "corporate_action_semantics": "split-v1",
            }
        ]
    }
    if extra is not None:
        payload.update(extra)
    return payload


@pytest.mark.asyncio
async def test_capability_preflight_joins_typed_requirements_with_host_evidence() -> None:
    observed: dict[str, Any] = {}

    async def resolve_cells(**kwargs: Any) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        observed["cells_request"] = kwargs
        return (_provider_evidence(),)

    async def resolve_binding(**kwargs: Any) -> ExecutionCapabilityBinding:
        observed["binding_request"] = kwargs
        return _binding()

    payload = _payload()
    summary = await CapabilityPreflightService(
        capability_cells=resolve_cells,
        execution_binding=resolve_binding,
    )(
        principal="owner-1",
        request_id="request-1",
        idempotency_key="capability-key",
        payload=payload,
        payload_digest=content_digest(payload),
    )

    assert summary.decision is CapabilitySummaryDecision.RIGOROUS
    assert summary.executable
    assert summary.ranking_eligible
    assert summary.authoritative
    assert summary.can_publish_authoritative_results
    assert observed["cells_request"]["principal"] == "owner-1"
    assert observed["cells_request"]["idempotency_key"] == "capability-key"
    assert observed["cells_request"]["requirements"] == (_requirement(),)
    assert observed["binding_request"]["report"].fingerprint == summary.report_fingerprint


@pytest.mark.asyncio
async def test_missing_host_coverage_fails_closed_without_inventing_cells() -> None:
    async def resolve_cells(**_kwargs: Any) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        return ()

    async def resolve_binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        return _binding()

    payload = _payload()
    summary = await CapabilityPreflightService(
        capability_cells=resolve_cells,
        execution_binding=resolve_binding,
    )(
        principal="owner-1",
        request_id="request-1",
        idempotency_key="capability-key",
        payload=payload,
        payload_digest=content_digest(payload),
    )

    assert summary.decision is CapabilitySummaryDecision.UNSUPPORTED
    assert summary.data_gaps == ("US.AAPL:instrument_coverage",)
    assert not summary.executable
    assert not summary.ranking_eligible
    assert not summary.can_publish_authoritative_results


@pytest.mark.asyncio
async def test_client_cannot_inject_trusted_cells_or_engine_binding() -> None:
    calls: list[str] = []

    def resolve_cells(**_kwargs: Any) -> tuple[CapabilityCell, ...]:
        calls.append("cells")
        return (_cell(),)

    def resolve_binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        calls.append("binding")
        return _binding()

    payload = _payload(extra={"cells": [], "engine_binding": {}})
    service = CapabilityPreflightService(
        capability_cells=resolve_cells,
        execution_binding=resolve_binding,
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        await service(
            principal="owner-1",
            request_id="request-1",
            idempotency_key="capability-key",
            payload=payload,
            payload_digest=content_digest(payload),
        )
    assert calls == []


@pytest.mark.asyncio
async def test_capability_preflight_requires_a_digest_bound_to_the_request() -> None:
    async def resolve_cells(**_kwargs: Any) -> tuple[CapabilityCell, ...]:
        return (_cell(),)

    async def resolve_binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        return _binding()

    payload = _payload()
    service = CapabilityPreflightService(
        capability_cells=resolve_cells,
        execution_binding=resolve_binding,
    )
    with pytest.raises(ValueError, match="payload_digest"):
        await service(
            principal="owner-1",
            request_id="request-1",
            idempotency_key="capability-key",
            payload=payload,
            payload_digest=content_digest({"different": True}),
        )


@pytest.mark.asyncio
async def test_explicit_degradation_is_preserved_but_never_ranking_eligible() -> None:
    async def resolve_cells(**_kwargs: Any) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        return (_provider_evidence(),)

    async def resolve_binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        return _binding()

    payload = _payload(
        session="extended",
        extra={
            "allow_degraded": True,
            "degradations": [
                {
                    "instrument_id": "US.AAPL",
                    "field": "session",
                    "substituted_value": "regular",
                    "reason": "only regular-session evidence is available",
                }
            ],
        },
    )
    summary = await CapabilityPreflightService(
        capability_cells=resolve_cells,
        execution_binding=resolve_binding,
    )(
        principal="owner-1",
        request_id="request-1",
        idempotency_key="capability-key",
        payload=payload,
        payload_digest=content_digest(payload),
    )

    assert summary.decision is CapabilitySummaryDecision.DEGRADED
    assert summary.executable
    assert not summary.ranking_eligible
    assert not summary.can_publish_authoritative_results
    assert summary.degradations == (
        Degradation(
            "US.AAPL",
            "session",
            "regular",
            "only regular-session evidence is available",
        ),
    )


@pytest.mark.asyncio
async def test_revoked_host_coverage_cannot_reuse_a_previous_rigorous_preflight() -> None:
    evidence_available = True
    observed_owners: list[str] = []

    async def resolve_cells(**kwargs: Any) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        observed_owners.append(kwargs["principal"])
        return (_provider_evidence(),) if evidence_available else ()

    async def resolve_binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        return _binding()

    service = CapabilityPreflightService(
        capability_cells=resolve_cells, execution_binding=resolve_binding
    )
    payload = _payload()
    call: dict[str, Any] = dict(
        principal="owner-1",
        request_id="coverage-request",
        idempotency_key="coverage-key",
        payload=payload,
        payload_digest=content_digest(payload),
    )
    accepted = await service(**call)
    assert accepted.executable and accepted.can_publish_authoritative_results

    evidence_available = False
    rejected = await service(**call)

    assert observed_owners == ["owner-1", "owner-1"]
    assert rejected.decision is CapabilitySummaryDecision.UNSUPPORTED
    assert rejected.data_gaps == ("US.AAPL:instrument_coverage",)
    assert not rejected.executable
    assert not rejected.ranking_eligible
    assert not rejected.can_publish_authoritative_results
    assert rejected.report_fingerprint != accepted.report_fingerprint
    # The earlier immutable receipt stays intact rather than being overwritten.
    assert accepted.executable and accepted.can_publish_authoritative_results


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_resolver", ["coverage", "engine"])
async def test_host_resolver_outage_cannot_fall_back_to_previous_success(
    failed_resolver: str,
) -> None:
    outage = False
    calls: list[str] = []

    async def resolve_cells(**_kwargs: Any) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        calls.append("coverage")
        if outage and failed_resolver == "coverage":
            raise LookupError("coverage evidence unavailable")
        return (_provider_evidence(),)

    async def resolve_binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        calls.append("engine")
        if outage and failed_resolver == "engine":
            raise LookupError("engine evidence unavailable")
        return _binding()

    service = CapabilityPreflightService(
        capability_cells=resolve_cells, execution_binding=resolve_binding
    )
    payload = _payload()
    call: dict[str, Any] = dict(
        principal="owner-1",
        request_id="outage-request",
        idempotency_key="outage-key",
        payload=payload,
        payload_digest=content_digest(payload),
    )
    assert (await service(**call)).can_publish_authoritative_results
    calls.clear()
    outage = True

    with pytest.raises(LookupError, match="evidence unavailable"):
        await service(**call)
    assert calls == (["coverage"] if failed_resolver == "coverage" else ["coverage", "engine"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,unsupported",
    [
        ("product_classes", frozenset({ProductClass.CRYPTO})),
        ("execution_models", frozenset({"other-execution-model"})),
        ("account_models", frozenset({"other-account-model"})),
    ],
)
async def test_rigorous_data_cannot_authorize_an_unsupported_engine_scope(
    field: str, unsupported: frozenset[Any]
) -> None:
    async def resolve_cells(**_kwargs: Any) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        return (_provider_evidence(),)

    async def resolve_binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        changes: dict[str, Any] = {field: unsupported}
        return replace(_binding(), **changes)

    payload = _payload()
    summary = await CapabilityPreflightService(
        capability_cells=resolve_cells, execution_binding=resolve_binding
    )(
        principal="owner-1",
        request_id="scope-request",
        idempotency_key="scope-key",
        payload=payload,
        payload_digest=content_digest(payload),
    )

    assert not summary.data_gaps
    assert summary.decision is CapabilitySummaryDecision.UNSUPPORTED
    assert not summary.executable
    assert not summary.ranking_eligible
    assert not summary.can_publish_authoritative_results
