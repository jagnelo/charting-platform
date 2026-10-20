from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.data_source import DataSource
from app.models.instrument import Instrument, OptionDetail, OptionRight, OptionStyle
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.providers.base import OptionContractRecord
from app.providers.errors import ProviderRateLimitError, ProviderResponseError
from app.services.options_data import (
    _estimate_missing_option_greeks,
    _marketdata_option_quote_credit_bound,
    _option_quote_payload,
    list_option_expirations,
    sync_option_chain_snapshot,
    sync_option_quote_history,
)
from tests.unit.conftest import AsyncSessionAdapter


def test_marketdata_option_quote_credit_bound_uses_inclusive_calendar_range():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    assert _marketdata_option_quote_credit_bound(start, start) == 1
    assert _marketdata_option_quote_credit_bound(start, start + timedelta(days=999)) == 1
    assert _marketdata_option_quote_credit_bound(start, start + timedelta(days=1000)) == 2


def test_option_quote_payload_preserves_explicit_empty_provider_object():
    class _Point:
        raw_payload = {}

    assert _option_quote_payload(_Point()) == {}


def test_missing_option_greeks_use_american_model_with_complete_input_provenance():
    contract = OptionContractRecord(
        provider_symbol="AAPL260116C00100000",
        underlying_symbol="AAPL",
        expiry_date=date(2027, 1, 16),
        strike=Decimal("100"),
        right="call",
        implied_vol=Decimal("0.25"),
    )

    greeks, extra = _estimate_missing_option_greeks(
        contract,
        spot=100.0,
        risk_free_rate=0.05,
        valuation_date=date(2026, 10, 6),
    )

    provenance = extra["local_greek_estimation"]
    assert greeks["delta"] is not None and Decimal("0") < greeks["delta"] < Decimal("1")
    assert greeks["gamma"] is not None and greeks["gamma"] > Decimal("0")
    assert greeks["theta"] is not None
    assert greeks["vega"] is not None
    assert greeks["rho"] is not None
    assert provenance["source"] == "local_model"
    assert provenance["model"] == "quantlib_american_binomial_crr"
    assert provenance["model_version"] == "quantlib-1.36-crr"
    assert provenance["valuation_date"] == "2026-10-06"
    assert provenance["spot"] == 100.0
    assert provenance["strike"] == 100.0
    assert provenance["implied_vol"] == 0.25
    assert provenance["risk_free_rate"] == 0.05
    assert provenance["dividend_yield"] == 0.0


def test_option_greek_estimation_preserves_provider_values_and_skips_expired_contracts():
    contract = OptionContractRecord(
        provider_symbol="AAPL260101C00100000",
        underlying_symbol="AAPL",
        expiry_date=date(2026, 1, 1),
        strike=Decimal("100"),
        right="call",
        implied_vol=Decimal("0.25"),
        delta=Decimal("0.4"),
        extra_greeks={"vendor_flag": "provider-value"},
    )

    greeks, extra = _estimate_missing_option_greeks(
        contract,
        spot=100.0,
        risk_free_rate=0.05,
        valuation_date=date(2026, 10, 6),
    )

    assert greeks["delta"] == Decimal("0.4")
    assert greeks["gamma"] is None
    assert extra == {"vendor_flag": "provider-value"}


@pytest.mark.asyncio
async def test_list_option_expirations_prefers_fresh_dataset_state(db, instrument, instrument_type):
    async_db = AsyncSessionAdapter(db)

    option_instrument = Instrument(
        symbol="AAPL 2026-06-19 C 100",
        name="AAPL Option",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(option_instrument)
    db.flush()

    db.add(
        OptionDetail(
            instrument_id=option_instrument.id,
            underlying_instrument_id=instrument.id,
            right=OptionRight.CALL,
            style=OptionStyle.AMERICAN,
            contract_key="aapl|2026-06-19|100|call",
            strike=Decimal("100"),
            expiry_date=datetime(2026, 6, 19, tzinfo=UTC).date(),
            contract_size=Decimal("100"),
        )
    )

    source = DataSource(name="yfinance", is_active=True)
    db.add(source)
    db.flush()

    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=source.id,
            dataset_type="option_expirations",
            dataset_key="all",
            status=DatasetStatus.FRESH,
            observed_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            stale_after=datetime.now(UTC) + timedelta(hours=1),
            extra_data={"expirations": ["2026-06-19", "2026-09-18", "2027-01-15"]},
        )
    )
    db.commit()

    expirations = await list_option_expirations(async_db, instrument)

    assert [item.isoformat() for item in expirations] == ["2026-06-19", "2026-09-18", "2027-01-15"]


@pytest.mark.asyncio
async def test_option_expirations_propagate_provider_capacity_failures(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)

    async def _fail(*_args, **_kwargs):
        raise ProviderRateLimitError("marketdata_app", "daily credits exhausted")

    monkeypatch.setattr("app.services.options_data.execute_provider_call", _fail)

    with pytest.raises(ProviderRateLimitError):
        await list_option_expirations(async_db, instrument, refresh=True)


@pytest.mark.asyncio
async def test_option_chain_propagates_provider_response_failures(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)

    async def _fail(*_args, **_kwargs):
        raise ProviderResponseError("marketdata_app", "malformed option-chain payload")

    monkeypatch.setattr("app.services.options_data.execute_provider_call", _fail)

    with pytest.raises(ProviderResponseError):
        await sync_option_chain_snapshot(
            async_db,
            instrument,
            expiration=datetime(2026, 6, 19, tzinfo=UTC).date(),
            refresh=True,
        )


@pytest.mark.asyncio
async def test_option_quote_history_propagates_provider_capacity_failures(
    db, instrument, monkeypatch
):
    async_db = AsyncSessionAdapter(db)

    async def _fail(*_args, **_kwargs):
        raise ProviderRateLimitError("marketdata_app", "daily credits exhausted")

    monkeypatch.setattr("app.services.options_data.execute_provider_call", _fail)

    with pytest.raises(ProviderRateLimitError):
        await sync_option_quote_history(
            async_db,
            instrument,
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 2, tzinfo=UTC),
            refresh=True,
        )
