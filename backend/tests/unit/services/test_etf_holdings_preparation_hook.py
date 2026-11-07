from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.ohlcv import Timeframe
from app.schemas.data_preparation import PreparationDataset
from app.services import etf_holdings, etf_holdings_refresh
from app.services.data_preparation_contracts import (
    DatasetPreparationContext,
    DatasetPreparationResult,
)
from app.services.etf_holdings_preparation import prepare_etf_holdings
from app.services.etf_holdings_provider_bridge import ETFHoldingsRouteHeldError
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

_KNOWN_QUOTA_RETRY_AT = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)


def _context(*, deadline: datetime | None = None) -> DatasetPreparationContext:
    return DatasetPreparationContext(
        request_id="request-123",
        dependency_id="dependency-456",
        dataset=PreparationDataset.HOLDINGS,
        timeframe=Timeframe.D1,
        adjusted=True,
        requested_start=None,
        requested_end=None,
        priority="visible",
        deadline=deadline or datetime.now(UTC) + timedelta(minutes=2),
    )


def _instrument():
    return SimpleNamespace(
        id=41,
        symbol="IGV",
        name="iShares Expanded Tech-Software Sector ETF",
        is_active=True,
        is_synthetic=False,
        identity_status="resolved",
    )


def _profile():
    return SimpleNamespace(id=52, instrument_id=41)


def _snapshot(snapshot_id: int = 73):
    return SimpleNamespace(
        id=snapshot_id,
        etf_profile_id=52,
        composition_date=date(2026, 11, 5),
    )


def _current_capability():
    return {
        "availability": "current",
        "identity_verified": True,
        "usable_for_current_analysis": True,
    }


def _install_readers(monkeypatch, *, profiles, snapshots, capabilities):
    get_profile = AsyncMock(side_effect=profiles)
    get_snapshot = AsyncMock(side_effect=snapshots)
    get_capability = AsyncMock(side_effect=capabilities)
    monkeypatch.setattr(etf_holdings, "get_etf_profile_for_instrument", get_profile)
    monkeypatch.setattr(etf_holdings, "_latest_snapshot_record_for_profile", get_snapshot)
    monkeypatch.setattr(etf_holdings, "holdings_capability_for_profile", get_capability)
    return get_profile, get_snapshot, get_capability


def _install_existing_spdr_route(monkeypatch, profile):
    adapter = SimpleNamespace(
        source_provider="spdr",
        probe=MagicMock(return_value=SimpleNamespace(status="ready")),
    )
    monkeypatch.setattr(
        etf_holdings_refresh,
        "_resolve_canonical_fund_instrument",
        AsyncMock(return_value=profile.instrument),
    )
    monkeypatch.setattr(
        etf_holdings_refresh,
        "known_etf_route_metadata",
        MagicMock(
            return_value={
                "provider_aliases": {
                    "holdings_adapter": "spdr",
                    "holdings_source_provider": "spdr",
                }
            }
        ),
    )
    monkeypatch.setattr(
        etf_holdings_refresh,
        "get_etf_profile_for_instrument",
        AsyncMock(return_value=profile),
    )
    monkeypatch.setattr(etf_holdings_refresh, "get_latest_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(
        etf_holdings_refresh, "_apply_known_route_metadata", MagicMock(return_value=False)
    )
    monkeypatch.setattr(
        etf_holdings_refresh,
        "_aliases",
        MagicMock(
            return_value={
                "holdings_source_provider": "spdr",
            }
        ),
    )
    monkeypatch.setattr(etf_holdings_refresh, "_string_aliases", MagicMock(return_value={}))
    monkeypatch.setattr(
        etf_holdings_refresh, "get_holdings_adapter", MagicMock(return_value=adapter)
    )
    monkeypatch.setattr(
        etf_holdings_refresh,
        "_explicit_etf_acquisition_binder",
        MagicMock(return_value=MagicMock(return_value=nullcontext())),
    )
    return adapter


@pytest.mark.asyncio
async def test_current_verified_snapshot_returns_shared_result_without_acquiring(monkeypatch):
    profile = _profile()
    snapshot = _snapshot()
    _install_readers(
        monkeypatch,
        profiles=[profile],
        snapshots=[snapshot],
        capabilities=[_current_capability()],
    )
    acquire = AsyncMock()
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)

    result = await prepare_etf_holdings(object(), _instrument(), context=_context())

    assert isinstance(result, DatasetPreparationResult)
    assert result.status == "ready"
    assert result.covered_start == datetime(2026, 11, 5, tzinfo=UTC)
    assert result.covered_end == datetime(2026, 11, 6, tzinfo=UTC)
    assert result.acquired_version == snapshot.id
    acquire.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_snapshot_delegates_to_existing_acquire_but_never_fakes_ready(monkeypatch):
    profile = _profile()
    snapshot = _snapshot()
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    _install_readers(
        monkeypatch,
        profiles=[profile, profile],
        snapshots=[snapshot, snapshot],
        capabilities=[stale, stale],
    )
    acquire = AsyncMock(return_value=SimpleNamespace(outcome="acquired"))
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)
    context = _context()
    db = object()

    result = await prepare_etf_holdings(db, _instrument(), context=context)

    assert result.status == "waiting"
    assert result.reason_code == "issuer_snapshot_not_current"
    acquire.assert_awaited_once_with(
        db,
        symbol="IGV",
        request_id="request-123",
        refresh=True,
        instrument_id=41,
    )


@pytest.mark.asyncio
async def test_acquire_is_ready_only_after_new_current_snapshot_is_read_back(monkeypatch):
    profile = _profile()
    old_snapshot = _snapshot(73)
    persisted_snapshot = _snapshot(74)
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    _install_readers(
        monkeypatch,
        profiles=[profile, profile],
        snapshots=[old_snapshot, persisted_snapshot],
        capabilities=[stale, _current_capability()],
    )
    acquire = AsyncMock(return_value=SimpleNamespace(outcome="acquired"))
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)

    result = await prepare_etf_holdings(object(), _instrument(), context=_context())

    assert result.status == "ready"
    assert result.acquired_version == persisted_snapshot.id
    assert result.covered_start == datetime(2026, 11, 5, tzinfo=UTC)
    acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_deadline_does_not_start_issuer_acquisition(monkeypatch):
    profile = _profile()
    snapshot = _snapshot()
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    _install_readers(
        monkeypatch,
        profiles=[profile],
        snapshots=[snapshot],
        capabilities=[stale],
    )
    acquire = AsyncMock()
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)
    context = _context(deadline=datetime.now(UTC) - timedelta(seconds=1))

    result = await prepare_etf_holdings(object(), _instrument(), context=context)

    assert result.status == "waiting"
    assert result.reason_code == "preparation_deadline_elapsed"
    assert result.acquired_version == snapshot.id
    acquire.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_route_stays_unavailable_without_profile_or_snapshot(monkeypatch):
    _install_readers(monkeypatch, profiles=[None, None], snapshots=[], capabilities=[])
    acquire = AsyncMock(return_value=SimpleNamespace(outcome="unavailable"))
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)

    result = await prepare_etf_holdings(object(), _instrument(), context=_context())

    assert result.status == "unavailable"
    assert result.reason_code == "issuer_route_unavailable"
    assert result.acquired_version is None
    acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_held_acquisition_exposes_only_the_known_capability_retry_time(monkeypatch):
    profile = _profile()
    snapshot = _snapshot()
    retry_at = datetime.now(UTC) + timedelta(minutes=4)
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    held = stale | {"circuit_open_until": retry_at}
    _install_readers(
        monkeypatch,
        profiles=[profile, profile],
        snapshots=[snapshot, snapshot],
        capabilities=[stale, held],
    )
    acquire = AsyncMock(return_value=SimpleNamespace(outcome="held"))
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)

    result = await prepare_etf_holdings(object(), _instrument(), context=_context())

    assert result.status == "waiting"
    assert result.reason_code == "issuer_acquisition_held"
    assert result.retry_at == retry_at


@pytest.mark.asyncio
async def test_route_mismatch_is_reported_as_unavailable(monkeypatch):
    profile = _profile()
    snapshot = _snapshot()
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    _install_readers(
        monkeypatch,
        profiles=[profile, profile],
        snapshots=[snapshot, snapshot],
        capabilities=[stale, stale],
    )
    acquire = AsyncMock(
        return_value=SimpleNamespace(
            outcome="held",
            reason_code="issuer_route_mismatch",
        )
    )
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)

    result = await prepare_etf_holdings(object(), _instrument(), context=_context())

    assert result.status == "unavailable"
    assert result.reason_code == "issuer_route_mismatch"


@pytest.mark.asyncio
async def test_known_provider_quota_retry_is_preserved_in_dataset_result(monkeypatch):
    profile = _profile()
    snapshot = _snapshot()
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    _install_readers(
        monkeypatch,
        profiles=[profile, profile],
        snapshots=[snapshot, snapshot],
        capabilities=[stale, stale],
    )
    retry_at = datetime.now(UTC) + timedelta(minutes=7)
    acquire = AsyncMock(
        return_value=SimpleNamespace(
            outcome="held",
            reason_code="provider_quota_admission_held",
            retry_at=retry_at,
        )
    )
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)

    result = await prepare_etf_holdings(object(), _instrument(), context=_context())

    assert result.status == "waiting"
    assert result.reason_code == "provider_quota_admission_held"
    assert result.retry_at == retry_at


@pytest.mark.asyncio
async def test_unknown_hold_does_not_receive_a_guessed_retry_deadline(monkeypatch):
    profile = _profile()
    snapshot = _snapshot()
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    _install_readers(
        monkeypatch,
        profiles=[profile, profile],
        snapshots=[snapshot, snapshot],
        capabilities=[stale, stale],
    )
    acquire = AsyncMock(
        return_value=SimpleNamespace(outcome="held", reason_code="issuer_request_held")
    )
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)

    result = await prepare_etf_holdings(object(), _instrument(), context=_context())

    assert result.status == "waiting"
    assert result.reason_code == "issuer_request_held"
    assert result.retry_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_reason", "expected_retry_at"),
    [
        (
            ProviderQuotaAdmissionError("quota hold", retry_at=_KNOWN_QUOTA_RETRY_AT),
            "provider_quota_admission_held",
            _KNOWN_QUOTA_RETRY_AT,
        ),
        (
            ETFHoldingsRouteHeldError("publisher route held without a known retry"),
            "issuer_request_held",
            None,
        ),
    ],
)
async def test_prepare_preserves_acquisition_hold_reason_and_only_known_retry(
    monkeypatch, failure, expected_reason, expected_retry_at
):
    instrument = _instrument()
    profile = SimpleNamespace(
        id=52,
        instrument_id=instrument.id,
        instrument=instrument,
        adapter_key="spdr",
    )
    snapshot = _snapshot()
    stale = {
        "availability": "stale",
        "identity_verified": True,
        "usable_for_current_analysis": False,
    }
    _install_readers(
        monkeypatch,
        profiles=[profile, profile],
        snapshots=[snapshot, snapshot],
        capabilities=[stale, stale],
    )
    _install_existing_spdr_route(monkeypatch, profile)
    refresh_route = AsyncMock(side_effect=failure)
    monkeypatch.setattr(etf_holdings_refresh, "_refresh_adapter_route", refresh_route)

    result = await prepare_etf_holdings(object(), instrument, context=_context())

    assert result.status == "waiting"
    assert result.reason_code == expected_reason
    assert result.retry_at == expected_retry_at
    refresh_route.assert_awaited_once()


@pytest.mark.asyncio
async def test_acquire_result_preserves_typed_quota_retry_deadline(monkeypatch):
    instrument = _instrument()
    profile = SimpleNamespace(id=52, instrument_id=41, instrument=instrument, adapter_key="spdr")
    _install_existing_spdr_route(monkeypatch, profile)
    retry_at = datetime.now(UTC) + timedelta(minutes=9)
    monkeypatch.setattr(
        etf_holdings_refresh,
        "_refresh_adapter_route",
        AsyncMock(side_effect=ProviderQuotaAdmissionError("quota hold", retry_at=retry_at)),
    )

    result = await etf_holdings_refresh.acquire_etf_holdings_profile(
        object(),
        symbol="IGV",
        request_id="request-123",
        refresh=True,
        instrument_id=41,
    )

    assert result is not None
    assert result.outcome == "held"
    assert result.reason_code == "provider_quota_admission_held"
    assert result.retry_at == retry_at


@pytest.mark.asyncio
async def test_acquire_result_keeps_unknown_route_hold_without_retry_time(monkeypatch):
    instrument = _instrument()
    profile = SimpleNamespace(id=52, instrument_id=41, instrument=instrument, adapter_key="spdr")
    _install_existing_spdr_route(monkeypatch, profile)
    monkeypatch.setattr(
        etf_holdings_refresh,
        "_refresh_adapter_route",
        AsyncMock(side_effect=ETFHoldingsRouteHeldError("publisher route held")),
    )

    result = await etf_holdings_refresh.acquire_etf_holdings_profile(
        object(),
        symbol="IGV",
        request_id="request-123",
        refresh=True,
        instrument_id=41,
    )

    assert result is not None
    assert result.outcome == "held"
    assert result.reason_code == "issuer_request_held"
    assert result.retry_at is None


@pytest.mark.asyncio
async def test_identity_or_dataset_mismatch_never_reaches_issuer_acquisition(monkeypatch):
    acquire = AsyncMock()
    monkeypatch.setattr(etf_holdings_refresh, "acquire_etf_holdings_profile", acquire)
    context = _context()

    provisional = _instrument()
    provisional.identity_status = "provisional"
    result = await prepare_etf_holdings(object(), provisional, context=context)
    assert result.status == "unavailable"
    assert result.reason_code == "canonical_etf_instrument_required"

    wrong_dataset = replace(context, dataset=PreparationDataset.HISTORY)
    result = await prepare_etf_holdings(object(), _instrument(), context=wrong_dataset)
    assert result.status == "unavailable"
    assert result.reason_code == "holdings_dataset_required"
    acquire.assert_not_awaited()
