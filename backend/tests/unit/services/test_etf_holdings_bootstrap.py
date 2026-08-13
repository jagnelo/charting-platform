from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.services.etf_holdings import ensure_lightweight_etf_instrument
from app.services.etf_holdings_refresh import (
    ETFHoldingsBootstrapResult,
    _apply_known_route_metadata,
    _issuer_product_identifier,
    bootstrap_etf_holdings_profile,
)
from app.services.instrument_mastering import ensure_internal_identifier


class AsyncSessionAdapter:
    def __init__(self, session):
        self._session = session

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def flush(self, *args, **kwargs):
        self._session.flush(*args, **kwargs)

    async def refresh(self, *args, **kwargs):
        self._session.refresh(*args, **kwargs)

    def add(self, *args, **kwargs):
        return self._session.add(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._session, item)


class _AsyncNestedContext:
    def __init__(self, owner):
        self.owner = owner

    async def __aenter__(self):
        self.owner.nested_enters += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.owner.nested_exits += 1
        return False


class FakeBootstrapDB:
    def __init__(self):
        self.nested_enters = 0
        self.nested_exits = 0
        self.flush_calls = 0

    def begin_nested(self):
        return _AsyncNestedContext(self)

    async def flush(self, *args, **kwargs):
        self.flush_calls += 1


class _SyncNestedContext:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        self.owner.nested_enters += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.owner.nested_exits += 1
        return False


class FakeSyncBootstrapDB(FakeBootstrapDB):
    def begin_nested(self):
        return _SyncNestedContext(self)


def test_curated_route_metadata_repairs_stale_adapter_key():
    """A later issuer route must override an obsolete historical inference."""

    profile = SimpleNamespace(
        instrument=SimpleNamespace(symbol="SMH", name="VanEck Semiconductor ETF"),
        issuer="VanEck",
        fund_family=None,
        product_url=None,
        provider_aliases={"holdings_adapter": "vaneck"},
        sec_cik="0001137360",
        sec_series_id="S000034411",
        sec_class_id="C000105869",
        adapter_key="ark",
        adapter_status="success",
        adapter_confidence=0.78,
    )

    assert _apply_known_route_metadata(profile) is True
    assert profile.adapter_key == "vaneck"
    assert profile.provider_aliases["product_slug"] == "semiconductor-etf-smh"
    assert profile.adapter_status == "candidate"


def test_explicit_issuer_product_slug_precedes_sec_series_id():
    """SEC enrichment must not shadow an issuer-native route identifier."""

    assert _issuer_product_identifier(
        {
            "sec_series_id": "S000034411",
            "product_slug": "semiconductor-etf-smh",
        }
    ) == "semiconductor-etf-smh"


@pytest.mark.asyncio
async def test_ensure_lightweight_etf_instrument_only_creates_one_internal_identifier(db):
    async_db = AsyncSessionAdapter(db)

    instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="XLE",
        name="SPDR Select Sector Fund - Energy Select Sector",
    )
    db.flush()

    identifiers = (
        db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.instrument_id == instrument.id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.INTERNAL,
            )
        )
        .scalars()
        .all()
    )

    assert len(identifiers) == 1
    assert identifiers[0].identifier_value == f"instrument:{instrument.id}"
    assert identifiers[0].is_active is True
    assert instrument.primary_identifier_value is not None
    assert instrument.primary_identifier_type is not None


@pytest.mark.asyncio
async def test_ensure_internal_identifier_repairs_duplicate_internal_rows(db, instrument):
    async_db = AsyncSessionAdapter(db)

    stale_one = InstrumentIdentifier(
        instrument_id=instrument.id,
        data_source_id=None,
        identifier_type=InstrumentIdentifierType.INTERNAL,
        identifier_value="etf:AAPL",
        is_primary=True,
        is_active=True,
    )
    stale_two = InstrumentIdentifier(
        instrument_id=instrument.id,
        data_source_id=None,
        identifier_type=InstrumentIdentifierType.INTERNAL,
        identifier_value="legacy:AAPL",
        is_primary=False,
        is_active=True,
    )
    db.add_all([stale_one, stale_two])
    db.flush()

    instrument.primary_identifier_type = None
    instrument.primary_identifier_value = None

    await ensure_internal_identifier(async_db, instrument)
    db.flush()

    identifiers = (
        db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.instrument_id == instrument.id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.INTERNAL,
            )
        )
        .scalars()
        .all()
    )

    active = [row for row in identifiers if row.is_active]
    assert len(active) == 1
    assert active[0].identifier_value == f"instrument:{instrument.id}"
    assert active[0].is_primary is True
    assert any("__superseded__" in row.identifier_value for row in identifiers if row.id != active[0].id)
    assert instrument.primary_identifier_type == InstrumentIdentifierType.INTERNAL.value
    assert instrument.primary_identifier_value == f"instrument:{instrument.id}"


@pytest.mark.asyncio
async def test_bootstrap_uses_async_nested_transaction_for_ready_routes(monkeypatch):
    db = FakeBootstrapDB()
    instrument = SimpleNamespace(id=101, symbol="NIKL", name="Sprott Nickel Miners ETF")
    profile = SimpleNamespace(
        instrument=instrument,
        issuer=None,
        fund_family=None,
        product_url=None,
        provider_aliases=None,
        sec_cik="seeded",
        sec_series_id=None,
        sec_class_id=None,
        adapter_key="sprott",
        adapter_status="ready",
        adapter_confidence=0.75,
    )
    probe = SimpleNamespace(
        adapter_key="sprott",
        confidence=0.75,
        status="ready",
        reason="Sprott ETF product pages are discoverable from the public ETF sitemap.",
    )
    snapshot = SimpleNamespace(id=501)

    async def fake_ensure_lightweight_etf_instrument(db, symbol, name=None):
        return instrument

    async def fake_ensure_etf_profile(db, instrument):
        return profile

    async def fake_get_latest_snapshot(
        db, instrument_id, include_holdings=True, include_controlled_fixture=True
    ):
        assert include_controlled_fixture is False
        return None

    async def fake_probe_etf_holdings_adapter_route(db, profile):
        return probe

    async def fake_refresh_adapter_route(db, profile):
        return snapshot

    async def fake_record_success(db, profile, snapshot):
        return None

    async def fake_bootstrap_from_sec_filings(db, profile):
        return None

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_lightweight_etf_instrument",
        fake_ensure_lightweight_etf_instrument,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile",
        fake_ensure_etf_profile,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.known_etf_route_metadata",
        lambda symbol: None,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_latest_snapshot",
        fake_get_latest_snapshot,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.probe_etf_holdings_adapter_route",
        fake_probe_etf_holdings_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route",
        fake_refresh_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._record_success",
        fake_record_success,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._bootstrap_from_sec_filings",
        fake_bootstrap_from_sec_filings,
    )

    result = await bootstrap_etf_holdings_profile(db, symbol="NIKL", name="Sprott Nickel Miners ETF")

    assert isinstance(result, ETFHoldingsBootstrapResult)
    assert result.refresh_attempted is True
    assert result.refresh_succeeded is True
    assert db.nested_enters == 1
    assert db.nested_exits == 1


@pytest.mark.asyncio
async def test_bootstrap_accepts_existing_public_snapshot_schema(monkeypatch):
    """A stored snapshot is already converted to the public schema by its loader."""
    db = FakeBootstrapDB()
    instrument = SimpleNamespace(id=101, symbol="XLK", name="Technology Select Sector SPDR Fund")
    profile = SimpleNamespace(
        instrument=instrument,
        issuer=None,
        fund_family=None,
        product_url=None,
        provider_aliases=None,
        sec_cik="seeded",
        sec_series_id=None,
        sec_class_id=None,
        adapter_key="spdr",
        adapter_status="success",
        adapter_confidence=0.95,
    )
    probe = SimpleNamespace(
        adapter_key="spdr",
        confidence=0.95,
        status="ready",
        reason="State Street's public workbook route is available.",
    )

    async def fake_ensure_lightweight_etf_instrument(db, symbol, name=None):
        return instrument

    async def fake_ensure_etf_profile(db, instrument):
        return profile

    async def fake_get_latest_snapshot(
        db, instrument_id, include_holdings=True, include_controlled_fixture=True
    ):
        assert include_controlled_fixture is False
        # This mirrors get_latest_snapshot's ETFHoldingsSnapshotOut contract;
        # it intentionally has no ORM ``rows`` collection.
        return SimpleNamespace(id=501, etf_symbol="XLK")

    async def fake_probe_etf_holdings_adapter_route(db, profile):
        return probe

    monkeypatch.setattr("app.services.etf_holdings_refresh.ensure_lightweight_etf_instrument", fake_ensure_lightweight_etf_instrument)
    monkeypatch.setattr("app.services.etf_holdings_refresh.ensure_etf_profile", fake_ensure_etf_profile)
    monkeypatch.setattr("app.services.etf_holdings_refresh.known_etf_route_metadata", lambda symbol: None)
    monkeypatch.setattr("app.services.etf_holdings_refresh.get_latest_snapshot", fake_get_latest_snapshot)
    monkeypatch.setattr("app.services.etf_holdings_refresh.probe_etf_holdings_adapter_route", fake_probe_etf_holdings_adapter_route)

    result = await bootstrap_etf_holdings_profile(db, symbol="XLK", name=instrument.name)

    assert isinstance(result, ETFHoldingsBootstrapResult)
    assert result.refresh_attempted is False
    assert result.refresh_succeeded is True
    assert result.probe.status == "ready"


@pytest.mark.asyncio
async def test_bootstrap_accepts_sync_nested_transaction_wrappers(monkeypatch):
    db = FakeSyncBootstrapDB()
    instrument = SimpleNamespace(id=101, symbol="NIKL", name="Sprott Nickel Miners ETF")
    profile = SimpleNamespace(
        instrument=instrument,
        issuer=None,
        fund_family=None,
        product_url=None,
        provider_aliases=None,
        sec_cik="seeded",
        sec_series_id=None,
        sec_class_id=None,
        adapter_key="sprott",
        adapter_status="ready",
        adapter_confidence=0.75,
    )
    probe = SimpleNamespace(
        adapter_key="sprott",
        confidence=0.75,
        status="ready",
        reason="Sprott ETF product pages are discoverable from the public ETF sitemap.",
    )
    snapshot = SimpleNamespace(id=501)

    async def fake_ensure_lightweight_etf_instrument(db, symbol, name=None):
        return instrument

    async def fake_ensure_etf_profile(db, instrument):
        return profile

    async def fake_get_latest_snapshot(
        db, instrument_id, include_holdings=True, include_controlled_fixture=True
    ):
        assert include_controlled_fixture is False
        return None

    async def fake_probe_etf_holdings_adapter_route(db, profile):
        return probe

    async def fake_refresh_adapter_route(db, profile):
        return snapshot

    async def fake_record_success(db, profile, snapshot):
        return None

    async def fake_bootstrap_from_sec_filings(db, profile):
        return None

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_lightweight_etf_instrument",
        fake_ensure_lightweight_etf_instrument,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile",
        fake_ensure_etf_profile,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.known_etf_route_metadata",
        lambda symbol: None,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_latest_snapshot",
        fake_get_latest_snapshot,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.probe_etf_holdings_adapter_route",
        fake_probe_etf_holdings_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route",
        fake_refresh_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._record_success",
        fake_record_success,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._bootstrap_from_sec_filings",
        fake_bootstrap_from_sec_filings,
    )

    result = await bootstrap_etf_holdings_profile(db, symbol="NIKL", name="Sprott Nickel Miners ETF")

    assert isinstance(result, ETFHoldingsBootstrapResult)
    assert result.refresh_attempted is True
    assert result.refresh_succeeded is True
    assert db.nested_enters == 1
    assert db.nested_exits == 1
