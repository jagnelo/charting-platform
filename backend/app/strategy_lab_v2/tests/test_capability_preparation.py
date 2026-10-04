from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityCell, CapabilityRequirement, Degradation
from app.strategy_lab_v2.capability_preparation import CapabilityPreflightService
from app.strategy_lab_v2.capability_summary import CapabilitySummaryDecision
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.execution_capabilities import ExecutionCapabilityBinding

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 2, 1, tzinfo=UTC)


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


def _binding() -> ExecutionCapabilityBinding:
    return ExecutionCapabilityBinding(
        engine_name="nautilus",
        engine_version="2.0.0rc5",
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

    async def resolve_cells(**kwargs: Any) -> tuple[CapabilityCell, ...]:
        observed["cells_request"] = kwargs
        return (_cell(),)

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
    async def resolve_cells(**_kwargs: Any) -> tuple[CapabilityCell, ...]:
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
    async def resolve_cells(**_kwargs: Any) -> tuple[CapabilityCell, ...]:
        return (_cell(),)

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
