from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.schemas.instrument_acquisition import (
    InstrumentAcquireResponse,
    InstrumentAcquisitionSourceOutcome,
)
from app.tasks import data_tasks


def _held_response(*retry_ats: datetime) -> InstrumentAcquireResponse:
    return InstrumentAcquireResponse(
        request_id="identity-child",
        status="held",
        reason_code="exact_profile_not_admitted",
        source_outcomes=[
            InstrumentAcquisitionSourceOutcome(
                provider=f"provider-{index}",
                capability=ProviderCapability.INSTRUMENT_METADATA.value,
                operation="get_instrument_profile",
                status="held",
                reason_code="provider_quota_admission_denied",
                retry_at=retry_at,
            )
            for index, retry_at in enumerate(retry_ats)
        ],
    )


async def _run_identity_child(monkeypatch, response: InstrumentAcquireResponse):
    owner = SimpleNamespace(id=33, is_active=True)
    instrument = SimpleNamespace(
        id=17,
        symbol="CSX",
        identity_status="quarantined",
        domain_key=None,
        primary_identifier_type="internal",
        primary_identifier_value="instrument:17",
        is_synthetic=False,
        instrument_type_id=None,
    )
    parent = SimpleNamespace(
        metadata_payload={
            "data_preparation": {"role": "owner_request_tracking", "owner_user_id": owner.id}
        }
    )
    job = SimpleNamespace(
        id=93,
        capability=ProviderCapability.INSTRUMENT_METADATA.value,
        instrument_id=instrument.id,
        timeframe=None,
        status="leased",
        next_attempt_at=datetime.now(UTC),
        lease_token="identity-lease",
        priority=100,
        metadata_payload={
            "data_preparation_child": {
                "kind": "identity_profile",
                "symbol": "CSX",
                "instrument_id": instrument.id,
                "refresh_profile": False,
                "required_profile_fields": [],
                "parent_refs": [{"parent_job_id": 700, "owner_user_id": owner.id}],
            }
        },
    )

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, model, identifier):
            if model.__name__ == "MarketRefreshJob" and identifier == 700:
                return parent
            if model.__name__ == "User" and identifier == owner.id:
                return owner
            if model.__name__ == "Instrument" and identifier == instrument.id:
                return instrument
            return None

        async def refresh(self, _job):
            return None

        async def commit(self):
            return None

    acquire = AsyncMock(return_value=response)
    retry = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", Session)
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(side_effect=[[job], []]))
    monkeypatch.setattr(
        data_tasks,
        "_native_usage_prerequisite_for_operation",
        AsyncMock(return_value=(None, None, False, None)),
    )
    monkeypatch.setattr(
        "app.services.data_preparation.record_identity_preparation_outcome", AsyncMock()
    )
    monkeypatch.setattr(data_tasks, "retry_refresh_job", retry)
    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete)
    monkeypatch.setattr("app.routers.instruments.acquire_instrument", acquire)
    result = await data_tasks.process_refresh_jobs({})
    return result, acquire, retry, complete


@pytest.mark.asyncio
async def test_identity_child_resolves_its_exact_canonical_row(monkeypatch):
    soon = datetime.now(UTC) + timedelta(minutes=5)

    _result, acquire, _retry, _complete = await _run_identity_child(
        monkeypatch, _held_response(soon)
    )

    request = acquire.await_args.args[0]
    assert request.symbol == "CSX"
    # Duplicate tickers exist after discovery; the child names its exact row.
    assert request.instrument_id == 17


@pytest.mark.asyncio
async def test_near_provider_reset_defers_identity_child_to_earliest_reset(monkeypatch):
    monkeypatch.setattr(settings, "INSTRUMENT_IDENTITY_HELD_DEFER_MAX_SECONDS", 3600)
    soon = datetime.now(UTC) + timedelta(minutes=5)
    monthly = datetime.now(UTC) + timedelta(days=13)

    result, _acquire, retry, complete = await _run_identity_child(
        monkeypatch, _held_response(monthly, soon)
    )

    assert result["retried"] == 1
    retry.assert_awaited_once()
    assert retry.await_args.kwargs["retry_at"] == soon
    complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_far_provider_reset_completes_recoverable_hold_instead_of_parking(monkeypatch):
    monkeypatch.setattr(settings, "INSTRUMENT_IDENTITY_HELD_DEFER_MAX_SECONDS", 3600)
    monthly = datetime.now(UTC) + timedelta(days=13)

    result, _acquire, retry, complete = await _run_identity_child(
        monkeypatch, _held_response(monthly)
    )

    assert result["retried"] == 0
    assert result["completed"] == 1
    retry.assert_not_awaited()
    summary = complete.await_args.kwargs["result_summary"]
    # A terminal "held" child is re-evaluated by the next ordinary ensure pass
    # (see _identity_job_has_terminal_negative) and releases waiting history.
    assert summary["preparation_status"] == "held"
    assert summary["reason_code"] == "exact_profile_not_admitted"
