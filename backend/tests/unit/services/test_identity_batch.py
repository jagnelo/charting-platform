from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import InstrumentIdentityQuarantine, MarketRefreshJob
from app.models.provider_observation import InstrumentIdentifierSnapshot
from app.models.provider_runtime import ProviderCapability
from app.providers.openfigi import OpenFigiTickerMapping
from app.services.identity_batch import (
    names_compatible,
    openfigi_us_ticker,
    release_long_held_identity_jobs,
    resolve_us_listed_equity_identities,
)
from app.services.instrument_mastering import ensure_internal_identifier
from app.services.market_data_identity import instrument_identity_is_qualified
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError
from tests.unit.conftest import AsyncSessionAdapter

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _now() -> datetime:
    return NOW


async def _no_hold(_db) -> None:
    return None


def _exchange(db, mic: str = "XNAS") -> Exchange:
    exchange = db.query(Exchange).filter(Exchange.mic == mic).one_or_none()
    if exchange is None:
        exchange = Exchange(mic=mic, name=mic, country_code="US")
        db.add(exchange)
        db.flush()
    return exchange


def _openfigi_source(db) -> DataSource:
    source = DataSource(name="openfigi", base_url="https://api.openfigi.com")
    db.add(source)
    db.flush()
    return source


async def _discovered(db, instrument_type, symbol: str, name: str, *, mic="XNAS") -> Instrument:
    instrument = Instrument(
        symbol=symbol,
        name=name,
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        identity_status="quarantined",
    )
    db.add(instrument)
    db.flush()
    db.add(
        InstrumentListing(
            instrument_id=instrument.id,
            ticker=symbol,
            exchange_id=_exchange(db, mic).id,
            is_primary=True,
            is_active=True,
        )
    )
    db.flush()
    await ensure_internal_identifier(AsyncSessionAdapter(db), instrument)
    db.flush()
    return instrument


def _install_openfigi(monkeypatch, mappings_by_ticker: dict[str, OpenFigiTickerMapping]):
    calls: list[list[str]] = []

    class FakeProvider:
        name = "openfigi"

        def map_us_tickers(self, tickers):
            calls.append(list(tickers))
            return [
                mappings_by_ticker.get(ticker)
                or OpenFigiTickerMapping(ticker=ticker, status="no_match")
                for ticker in tickers
            ]

    async def execute(_db, capability, operation, *, provider_name, invoke, **_kwargs):
        assert capability is ProviderCapability.INSTRUMENT_IDENTIFIERS
        assert operation == "fetch_stable_identifiers"
        assert provider_name == "openfigi"
        return SimpleNamespace(provider_name="openfigi", result=invoke(FakeProvider(), None))

    monkeypatch.setattr("app.services.provider_runtime.execute_provider_call", execute)
    return calls


def test_openfigi_us_ticker_only_maps_plain_and_single_class_tickers():
    assert openfigi_us_ticker("aapl") == "AAPL"
    assert openfigi_us_ticker("BRK.B") == "BRK/B"
    assert openfigi_us_ticker("BF-B") == "BF/B"
    assert openfigi_us_ticker("BAC.PRS") is None
    assert openfigi_us_ticker("HOLDING-3CE0534611") is None
    assert openfigi_us_ticker("ABCDEFG") is None


def test_names_compatible_tolerates_format_but_rejects_another_company():
    assert names_compatible("Apple Inc. - Common Stock", "APPLE INC", "AAPL")
    assert names_compatible("International Business Machines Corp", "INTL BUSINESS MACHINES", "IBM")
    assert names_compatible("AAPL", "APPLE INC", "AAPL")
    assert names_compatible("", "APPLE INC", "AAPL")
    assert not names_compatible("Zeta Mining Ltd", "ACME WIDGETS INC", "ZETA")


@pytest.mark.asyncio
async def test_batch_resolves_unambiguous_composite_and_wakes_waiting_identity_child(
    db, instrument_type, monkeypatch
):
    session = AsyncSessionAdapter(db)
    _openfigi_source(db)
    csx = await _discovered(db, instrument_type, "CSX", "CSX CORP")
    none = await _discovered(db, instrument_type, "NOFG", "No Figi Holdings")
    renamed = await _discovered(db, instrument_type, "ZETA", "Zeta Mining Ltd")
    held_child = MarketRefreshJob(
        request_key="prep-identity:csx",
        capability=ProviderCapability.INSTRUMENT_METADATA.value,
        instrument_id=csx.id,
        priority=100,
        status="deferred",
        attempts=1,
        next_attempt_at=NOW + timedelta(days=13),
        metadata_payload={"data_preparation_child": {"kind": "identity_profile"}},
        result_summary={"preparation_status": "held"},
    )
    db.add(held_child)
    db.flush()
    calls = _install_openfigi(
        monkeypatch,
        {
            "CSX": OpenFigiTickerMapping(
                ticker="CSX",
                status="matched",
                composite_figi="BBG000BGJRC8",
                name="CSX CORP",
                security_type="Common Stock",
            ),
            "ZETA": OpenFigiTickerMapping(
                ticker="ZETA",
                status="matched",
                composite_figi="BBG000ZETA01",
                name="ACME WIDGETS INC",
            ),
        },
    )

    result = await resolve_us_listed_equity_identities(
        session,
        ensure_native_baseline=_no_hold,
        max_requests=10,
        max_seconds=60,
        retry_after=timedelta(days=7),
        now=_now,
    )

    # Three instruments travel in one mapping request (one quota unit).
    assert calls == [["CSX", "NOFG", "ZETA"]]
    assert result["requests"] == 1
    assert result["status"] == "exhausted"
    assert result["outcomes"] == {"resolved": 1, "no_match": 1, "name_mismatch": 1}
    assert csx.identity_status == "resolved"
    assert csx.domain_key == "composite-figi:BBG000BGJRC8"
    assert csx.primary_identifier_type == "composite_figi"
    assert csx.primary_identifier_value == "BBG000BGJRC8"
    assert await instrument_identity_is_qualified(session, csx)
    primaries = (
        db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.instrument_id == csx.id,
                InstrumentIdentifier.is_primary.is_(True),
            )
        )
        .scalars()
        .all()
    )
    assert [row.identifier_type for row in primaries] == [InstrumentIdentifierType.COMPOSITE_FIGI]
    assert held_child.next_attempt_at.replace(tzinfo=UTC) == NOW
    assert result["identity_jobs_woken"] == 1
    for unresolved in (none, renamed):
        assert unresolved.domain_key is None
        assert unresolved.identity_status == "quarantined"
        assert not await instrument_identity_is_qualified(session, unresolved)
    snapshots = db.query(InstrumentIdentifierSnapshot).all()
    assert sorted(row.payload["outcome"]["status"] for row in snapshots) == [
        "name_mismatch",
        "no_match",
        "resolved",
    ]

    # Every attempted listing is recorded, so the next pass spends no quota
    # on them until the retry window passes.
    second = await resolve_us_listed_equity_identities(
        session,
        ensure_native_baseline=_no_hold,
        max_requests=10,
        max_seconds=60,
        retry_after=timedelta(days=7),
        now=_now,
    )
    assert second["requests"] == 0
    assert second["status"] == "exhausted"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_batch_quarantines_a_figi_already_owned_by_another_instrument(
    db, instrument_type, monkeypatch
):
    session = AsyncSessionAdapter(db)
    _openfigi_source(db)
    owner = await _discovered(db, instrument_type, "CSX", "CSX CORP")
    owner.identity_status = "resolved"
    owner.domain_key = "composite-figi:BBG000BGJRC8"
    owner.primary_identifier_type = "composite_figi"
    owner.primary_identifier_value = "BBG000BGJRC8"
    db.add(
        InstrumentIdentifier(
            instrument_id=owner.id,
            identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI,
            identifier_value="BBG000BGJRC8",
            is_primary=True,
        )
    )
    duplicate = await _discovered(db, instrument_type, "CSX", "CSX CORP")
    db.flush()
    _install_openfigi(
        monkeypatch,
        {
            "CSX": OpenFigiTickerMapping(
                ticker="CSX", status="matched", composite_figi="BBG000BGJRC8", name="CSX CORP"
            )
        },
    )

    result = await resolve_us_listed_equity_identities(
        session,
        ensure_native_baseline=_no_hold,
        max_requests=10,
        max_seconds=60,
        retry_after=timedelta(days=7),
        now=_now,
    )

    assert result["outcomes"] == {"identity_conflict": 1}
    assert duplicate.domain_key is None
    assert duplicate.identity_status == "quarantined"
    assert owner.domain_key == "composite-figi:BBG000BGJRC8"
    quarantine = (
        db.query(InstrumentIdentityQuarantine)
        .filter(InstrumentIdentityQuarantine.instrument_id == duplicate.id)
        .one()
    )
    assert quarantine.proposed_domain_key == "composite-figi:BBG000BGJRC8"
    assert f"instrument {owner.id}" in quarantine.reason
    assert (
        db.query(InstrumentIdentifier)
        .filter(
            InstrumentIdentifier.instrument_id == duplicate.id,
            InstrumentIdentifier.identifier_type == InstrumentIdentifierType.COMPOSITE_FIGI,
        )
        .count()
        == 0
    )


@pytest.mark.asyncio
async def test_batch_makes_no_request_while_the_native_baseline_is_held(
    db, instrument_type, monkeypatch
):
    session = AsyncSessionAdapter(db)
    _openfigi_source(db)
    await _discovered(db, instrument_type, "CSX", "CSX CORP")
    calls = _install_openfigi(monkeypatch, {})

    async def held(_db):
        return "native_usage_refresh_not_enabled_for_provider"

    result = await resolve_us_listed_equity_identities(
        session,
        ensure_native_baseline=held,
        max_requests=10,
        max_seconds=60,
        retry_after=timedelta(days=7),
        now=_now,
    )

    assert calls == []
    assert result["status"] == "held"
    assert result["reason_code"] == "native_usage_refresh_not_enabled_for_provider"
    # Not recorded as attempted: the listing stays eligible for the next pass.
    assert db.query(InstrumentIdentifierSnapshot).count() == 0


@pytest.mark.asyncio
async def test_batch_stops_on_quota_denial_without_marking_candidates_attempted(
    db, instrument_type, monkeypatch
):
    session = AsyncSessionAdapter(db)
    _openfigi_source(db)
    await _discovered(db, instrument_type, "CSX", "CSX CORP")
    attempts = []

    async def denied(*_args, **_kwargs):
        attempts.append(1)
        raise ProviderQuotaAdmissionError("window", retry_at=NOW + timedelta(hours=2))

    monkeypatch.setattr("app.services.provider_runtime.execute_provider_call", denied)

    result = await resolve_us_listed_equity_identities(
        session,
        ensure_native_baseline=_no_hold,
        max_requests=10,
        max_seconds=60,
        retry_after=timedelta(days=7),
        now=_now,
    )

    assert attempts == [1]
    assert result["status"] == "deferred"
    assert result["reason_code"] == "provider_quota_admission_denied"
    assert db.query(InstrumentIdentifierSnapshot).count() == 0


@pytest.mark.asyncio
async def test_batch_ignores_resolved_non_us_and_non_equity_rows(db, instrument_type, monkeypatch):
    from app.models.asset_class import AssetClass, InstrumentType

    session = AsyncSessionAdapter(db)
    _openfigi_source(db)
    foreign = await _discovered(db, instrument_type, "VOD", "Vodafone", mic="XLON")
    db.query(Exchange).filter(Exchange.mic == "XLON").one().country_code = "GB"
    crypto_class = AssetClass(name="Cryptocurrency", description="crypto")
    db.add(crypto_class)
    db.flush()
    crypto_type = InstrumentType(name="Crypto Spot", asset_class_id=crypto_class.id)
    db.add(crypto_type)
    db.flush()
    await _discovered(db, crypto_type, "BTC", "Bitcoin")
    db.flush()
    calls = _install_openfigi(monkeypatch, {})

    result = await resolve_us_listed_equity_identities(
        session,
        ensure_native_baseline=_no_hold,
        max_requests=10,
        max_seconds=60,
        retry_after=timedelta(days=7),
        now=_now,
    )

    assert calls == []
    assert result["status"] == "exhausted"
    assert foreign.domain_key is None


@pytest.mark.asyncio
async def test_release_long_held_identity_jobs_is_bounded_and_identity_only(db):
    session = AsyncSessionAdapter(db)
    far = NOW + timedelta(days=13)
    jobs = [
        MarketRefreshJob(
            request_key=f"prep-identity:{index}",
            capability=ProviderCapability.INSTRUMENT_METADATA.value,
            priority=100,
            status="deferred",
            attempts=1,
            next_attempt_at=far,
            metadata_payload={"data_preparation_child": {"kind": "identity_profile"}},
            result_summary={"preparation_status": "held"},
        )
        for index in range(3)
    ]
    near = MarketRefreshJob(
        request_key="prep-identity:near",
        capability=ProviderCapability.INSTRUMENT_METADATA.value,
        priority=100,
        status="deferred",
        attempts=1,
        next_attempt_at=NOW + timedelta(minutes=10),
        metadata_payload={"data_preparation_child": {"kind": "identity_profile"}},
        result_summary={"preparation_status": "held"},
    )
    db.add_all([*jobs, near])
    db.flush()

    released = await release_long_held_identity_jobs(
        session, now=NOW, defer_limit=timedelta(hours=1), max_jobs=2
    )

    assert released == 2
    assert sorted(job.next_attempt_at.replace(tzinfo=UTC) == NOW for job in jobs) == [
        False,
        True,
        True,
    ]
    assert near.next_attempt_at.replace(tzinfo=UTC) == NOW + timedelta(minutes=10)
