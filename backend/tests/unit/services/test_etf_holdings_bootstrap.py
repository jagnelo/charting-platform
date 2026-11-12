from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.services.etf_holdings import ensure_lightweight_etf_instrument
from app.services.etf_holdings_refresh import (
    ETFHoldingsBootstrapResult,
    ETFHoldingsRouteHeldError,
    _apply_known_route_metadata,
    _bootstrap_from_sec_filings,
    _issuer_product_identifier,
    _refresh_adapter_route,
    _resolve_canonical_fund_instrument,
    acquire_etf_holdings_profile,
    bootstrap_etf_holdings_profile,
    holdings_snapshot_is_bootstrap_ready,
    refresh_etf_holdings_for_date,
)
from app.services.instrument_mastering import ensure_internal_identifier

_EXPLICIT_ETF_ACQUISITION_BINDING = ContextVar(
    "test_explicit_etf_acquisition_binding", default=None
)


def _install_explicit_etf_acquisition_binder(monkeypatch):
    from app.services.provider_runtime import bind_explicit_etf_holdings_acquisition

    calls = []

    @contextmanager
    def bind(**kwargs):
        calls.append(kwargs)
        token = _EXPLICIT_ETF_ACQUISITION_BINDING.set(kwargs)
        try:
            with bind_explicit_etf_holdings_acquisition(**kwargs) as scope:
                yield scope
        finally:
            _EXPLICIT_ETF_ACQUISITION_BINDING.reset(token)

    monkeypatch.setattr(
        "app.services.provider_runtime.bind_explicit_etf_holdings_acquisition",
        bind,
        raising=False,
    )
    return calls


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
        self.commit_calls = 0
        self.is_active = True

    def begin_nested(self):
        return _AsyncNestedContext(self)

    async def flush(self, *args, **kwargs):
        self.flush_calls += 1

    async def commit(self):
        self.commit_calls += 1


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


def test_curated_qqqe_route_metadata_selects_direxion_adapter():
    """The Nasdaq-100 equal leg must bootstrap through its explicit issuer route."""

    profile = SimpleNamespace(
        instrument=SimpleNamespace(symbol="QQQE", name="Direxion NASDAQ-100 Equal Weighted ETF"),
        issuer=None,
        fund_family=None,
        product_url=None,
        provider_aliases={},
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
        adapter_key="unresolved",
        adapter_status="holdings_adapter_unresolved",
        adapter_confidence=0,
    )

    assert _apply_known_route_metadata(profile) is True
    assert profile.issuer == "Direxion"
    assert profile.adapter_key == "direxion"
    assert profile.adapter_status == "candidate"
    assert profile.provider_aliases["holdings_adapter"] == "direxion"
    assert profile.provider_aliases["issuer_product_url"].endswith(
        "/nasdaq-100-equal-weighted-index-etf"
    )


def test_explicit_issuer_product_slug_precedes_sec_series_id():
    """SEC enrichment must not shadow an issuer-native route identifier."""

    assert (
        _issuer_product_identifier(
            {
                "sec_series_id": "S000034411",
                "product_slug": "semiconductor-etf-smh",
            }
        )
        == "semiconductor-etf-smh"
    )


@pytest.mark.parametrize(
    ("status", "resolved_count", "expected"),
    [
        ("partial", 1, False),
        ("unknown", 10, False),
        ("complete", 0, False),
        ("complete", 10, True),
        ("filing_reconstructed", 10, True),
    ],
)
def test_holdings_snapshot_readiness_requires_resolved_complete_evidence(
    status, resolved_count, expected
):
    snapshot = SimpleNamespace(completeness_status=status, resolved_count=resolved_count)
    assert holdings_snapshot_is_bootstrap_ready(snapshot) is expected


def test_holdings_snapshot_readiness_uses_present_rows_instead_of_summary_count():
    snapshot = SimpleNamespace(
        completeness_status="complete",
        resolved_count=8,
        rows=[],
    )

    assert holdings_snapshot_is_bootstrap_ready(snapshot) is False


@pytest.mark.asyncio
async def test_sec_bootstrap_does_not_treat_non_equity_rows_as_ready(monkeypatch):
    """A materialized cash-only snapshot must still allow SEC fallback."""

    profile = SimpleNamespace(
        id=7,
        instrument_id=101,
        instrument=SimpleNamespace(symbol="QQQ", name="Invesco QQQ Trust"),
        sec_cik="0001067839",
    )
    non_equity_snapshot = SimpleNamespace(
        completeness_status="complete",
        resolved_count=1,
        rows=[
            SimpleNamespace(
                row_type="cash",
                holding_type="cash",
                is_resolved=True,
                constituent_instrument_id=None,
                constituent_instrument=None,
            )
        ],
    )
    ready_snapshot = SimpleNamespace(
        completeness_status="filing_reconstructed",
        resolved_count=1,
        rows=[
            SimpleNamespace(
                row_type="security",
                holding_type="equity",
                is_resolved=True,
                constituent_instrument_id=42,
                constituent_instrument=SimpleNamespace(symbol="AAPL"),
            )
        ],
    )
    latest_calls = 0
    nport_calls = 0
    legacy_calls = 0

    async def fake_get_latest_snapshot(
        db, instrument_id, *, include_holdings=True, include_controlled_fixture=True
    ):
        nonlocal latest_calls
        assert include_holdings is True
        assert include_controlled_fixture is False
        latest_calls += 1
        return non_equity_snapshot if latest_calls == 1 else ready_snapshot

    async def fake_nport(db, *, profile, max_filings, requested_by_user_id):
        nonlocal nport_calls
        nport_calls += 1
        assert max_filings == 3
        assert requested_by_user_id is None
        return {"discovered": 1, "ingested": 1, "skipped": 0, "failed": 0}

    async def fake_legacy(db, *, profile, max_filings, requested_by_user_id):
        nonlocal legacy_calls
        legacy_calls += 1
        return {"discovered": 0, "ingested": 0, "skipped": 0, "failed": 0}

    probe = SimpleNamespace(status="ready")

    async def fake_probe(db, profile):
        return probe

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_latest_snapshot", fake_get_latest_snapshot
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.probe_etf_holdings_adapter_route", fake_probe
    )
    monkeypatch.setattr("app.services.etf_holdings_edgar.backfill_sec_nport_holdings", fake_nport)
    monkeypatch.setattr("app.services.etf_holdings_edgar.backfill_sec_legacy_holdings", fake_legacy)

    result = await _bootstrap_from_sec_filings(object(), profile=profile)

    assert result is not None
    assert result.refresh_attempted is True
    assert result.refresh_succeeded is True
    assert "SEC N-PORT" in (result.message or "")
    assert nport_calls == 1
    assert legacy_calls == 0


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
    stale_two_value = "legacy:" + ("A" * 73)
    stale_two = InstrumentIdentifier(
        instrument_id=instrument.id,
        data_source_id=None,
        identifier_type=InstrumentIdentifierType.INTERNAL,
        identifier_value=stale_two_value,
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
    inactive = [row for row in identifiers if row.id != active[0].id]
    assert {row.identifier_value for row in inactive} == {stale_two_value}
    assert all(not row.is_active and not row.is_primary for row in inactive)

    # Re-running the repair must not grow/mutate historical values.
    await ensure_internal_identifier(async_db, instrument)
    db.flush()
    assert {row.identifier_value for row in inactive} == {stale_two_value}
    assert instrument.primary_identifier_type == InstrumentIdentifierType.INTERNAL.value
    assert instrument.primary_identifier_value == f"instrument:{instrument.id}"


@pytest.mark.asyncio
async def test_bootstrap_uses_async_nested_transaction_for_ready_routes(monkeypatch):
    db = FakeBootstrapDB()
    instrument = SimpleNamespace(id=101, symbol="NIKL", name="Sprott Nickel Miners ETF")
    profile = SimpleNamespace(
        id=301,
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
        lambda *args, **kwargs: None,
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

    result = await bootstrap_etf_holdings_profile(
        db, symbol="NIKL", name="Sprott Nickel Miners ETF"
    )

    assert isinstance(result, ETFHoldingsBootstrapResult)
    assert result.refresh_attempted is True
    assert result.refresh_succeeded is True
    assert db.nested_enters == 1
    assert db.nested_exits == 1


@pytest.mark.asyncio
async def test_dated_refresh_preserves_provider_snapshot_metadata(monkeypatch):
    """Dated routes must retain their completeness/provenance contract on persistence."""

    db = FakeBootstrapDB()
    instrument = SimpleNamespace(id=101, symbol="QQQ", name="Invesco QQQ Trust")
    profile = SimpleNamespace(
        id=302,
        instrument=instrument,
        adapter_key="invesco",
        provider_aliases={},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
    )
    snapshot = SimpleNamespace(id=501)
    captured: dict = {}

    class FakeAdapter:
        adapter_key = "invesco"

        async def fetch_for_date(self, **kwargs):
            assert kwargs["symbol"] == "QQQ"
            assert kwargs["requested_date"].isoformat() == "2026-06-30"
            return SimpleNamespace(
                rows=[SimpleNamespace(symbol="AAPL")],
                raw_text="AAPL",
                raw_json={"rows": ["AAPL"]},
                source_url="https://sec.example/qqq.xml",
                source_identifier="000001",
                legal_metadata={
                    "route_resolution": "sec_edgar_filing_fallback",
                    "source_provider": "sec",
                    "source_format": "xml",
                    "snapshot_provenance": "sec_nport_reconstructed_holdings",
                    "source_quality": "filing_reconstructed_holdings",
                    "completeness_status": "filing_reconstructed",
                    "parser_version": "invesco-sec-v2",
                    "known_at": "2026-06-01T13:45:30Z",
                    "published_at": "2026-06-01T13:45:30Z",
                },
            )

    async def fake_ingest(_db, **kwargs):
        captured.update(kwargs)
        return snapshot

    async def fake_record_success(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter",
        lambda key: FakeAdapter() if key == "invesco" else None,
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.ingest_holdings_snapshot", fake_ingest)
    monkeypatch.setattr("app.services.etf_holdings_refresh._record_success", fake_record_success)

    result = await refresh_etf_holdings_for_date(
        db,
        profile,
        requested_date=date(2026, 6, 30),
    )

    assert result is snapshot
    assert captured["provenance"] == "sec_nport_reconstructed_holdings"
    assert captured["source_provider"] == "sec"
    assert captured["source_quality"] == "filing_reconstructed_holdings"
    assert captured["completeness_status"] == "filing_reconstructed"
    assert captured["parser_version"] == "invesco-sec-v2"
    assert captured["known_at"] == datetime(2026, 6, 1, 13, 45, 30, tzinfo=UTC)
    assert captured["published_at"] == datetime(2026, 6, 1, 13, 45, 30, tzinfo=UTC)
    assert captured["legal_metadata"]["timing_provenance"] == {
        "composition_date": "requested_date_fallback",
        "as_of_date": "requested_date",
        "known_at": "provider_reported",
        "published_at": "provider_reported",
    }
    assert "SEC EDGAR holdings filings" in captured["notes"]


@pytest.mark.asyncio
async def test_latest_refresh_preserves_profile_declared_source_quality(monkeypatch):
    """Latest-route refreshes must retain curated profile source-quality evidence."""

    db = FakeBootstrapDB()
    instrument = SimpleNamespace(id=101, symbol="SPY", name="SPDR S&P 500 ETF Trust")
    profile = SimpleNamespace(
        id=303,
        instrument=instrument,
        adapter_key="spdr",
        provider_aliases={"holdings_source_quality": "issuer_reported_dated_complete_holdings"},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
    )
    captured: dict = {}

    class FakeAdapter:
        adapter_key = "spdr"
        source_provider = "spdr"

        def probe(self, **_kwargs):
            return SimpleNamespace(status="ready", reason=None, confidence=0.95)

        async def fetch_latest(self, **_kwargs):
            return SimpleNamespace(
                rows=[SimpleNamespace(symbol="AAPL")],
                raw_text="AAPL",
                raw_json={"rows": ["AAPL"]},
                source_url="https://spdr.example/spy.csv",
                source_identifier="SPY",
                legal_metadata={"completeness_status": "complete"},
            )

    async def fake_ingest(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(completeness_status=kwargs["completeness_status"])

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter",
        lambda key: FakeAdapter() if key == "spdr" else None,
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.ingest_holdings_snapshot", fake_ingest)

    result = await _refresh_adapter_route(db, profile)

    assert result.completeness_status == "complete"
    assert captured["source_quality"] == "issuer_reported_dated_complete_holdings"
    assert captured["completeness_status"] == "complete"


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
        return SimpleNamespace(
            id=501,
            etf_symbol="XLK",
            completeness_status="complete",
            resolved_count=10,
        )

    async def fake_probe_etf_holdings_adapter_route(db, profile):
        return probe

    def explicit_acquire_must_not_be_called(**_kwargs):
        raise AssertionError("legacy bootstrap must not enter explicit acquisition scope")

    monkeypatch.setattr(
        "app.services.provider_runtime.bind_explicit_etf_holdings_acquisition",
        explicit_acquire_must_not_be_called,
        raising=False,
    )

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_lightweight_etf_instrument",
        fake_ensure_lightweight_etf_instrument,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile", fake_ensure_etf_profile
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.known_etf_route_metadata",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_latest_snapshot", fake_get_latest_snapshot
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.probe_etf_holdings_adapter_route",
        fake_probe_etf_holdings_adapter_route,
    )

    result = await bootstrap_etf_holdings_profile(db, symbol="XLK", name=instrument.name)

    assert isinstance(result, ETFHoldingsBootstrapResult)
    assert result.refresh_attempted is False
    assert result.refresh_succeeded is True
    assert result.probe.status == "ready"


@pytest.mark.asyncio
async def test_bootstrap_retries_instead_of_short_circuiting_partial_snapshot(monkeypatch):
    """The inner holdings bootstrap must actually retry an incomplete latest snapshot."""

    db = FakeBootstrapDB()
    instrument = SimpleNamespace(id=101, symbol="SPY", name="S&P 500 ETF")
    profile = SimpleNamespace(
        instrument=instrument,
        issuer="State Street",
        fund_family=None,
        product_url=None,
        provider_aliases={},
        sec_cik="seeded",
        sec_series_id=None,
        sec_class_id=None,
        adapter_key="spdr",
        adapter_status="candidate",
        adapter_confidence=0.9,
    )
    partial_snapshot = SimpleNamespace(
        id=501,
        completeness_status="partial",
        resolved_count=2,
    )
    probe = SimpleNamespace(
        adapter_key="spdr",
        confidence=0.95,
        status="ready",
        reason="State Street's public workbook route is available.",
    )
    refreshed_snapshot = SimpleNamespace(id=502)
    refresh_calls = []

    async def fake_ensure_lightweight_etf_instrument(db, symbol, name=None):
        return instrument

    async def fake_ensure_etf_profile(db, instrument):
        return profile

    async def fake_get_latest_snapshot(
        db, instrument_id, include_holdings=True, include_controlled_fixture=True
    ):
        assert include_controlled_fixture is False
        return partial_snapshot

    async def fake_probe_etf_holdings_adapter_route(db, profile):
        return probe

    async def fake_refresh_adapter_route(db, profile):
        refresh_calls.append(profile.instrument.symbol)
        return refreshed_snapshot

    async def fake_record_success(db, profile, snapshot):
        return None

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_lightweight_etf_instrument",
        fake_ensure_lightweight_etf_instrument,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile", fake_ensure_etf_profile
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.known_etf_route_metadata",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_latest_snapshot", fake_get_latest_snapshot
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.probe_etf_holdings_adapter_route",
        fake_probe_etf_holdings_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route", fake_refresh_adapter_route
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh._record_success", fake_record_success)

    result = await bootstrap_etf_holdings_profile(db, symbol="SPY", name=instrument.name)

    assert result.refresh_attempted is True
    assert result.refresh_succeeded is True
    assert refresh_calls == ["SPY"]
    assert db.nested_enters == 1


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
        lambda *args, **kwargs: None,
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

    result = await bootstrap_etf_holdings_profile(
        db, symbol="NIKL", name="Sprott Nickel Miners ETF"
    )

    assert isinstance(result, ETFHoldingsBootstrapResult)
    assert result.refresh_attempted is True
    assert result.refresh_succeeded is True
    assert db.nested_enters == 1
    assert db.nested_exits == 1


class _FundResolutionResult:
    def __init__(self, matches):
        self.matches = matches

    def scalars(self):
        return self

    def all(self):
        return self.matches


class _FundResolutionDB:
    def __init__(self, matches):
        self.matches = matches

    async def execute(self, _statement):
        return _FundResolutionResult(self.matches)


def _canonical_fund_instrument(**overrides):
    values = {
        "id": 81,
        "symbol": "OIH",
        "name": "VanEck Oil Services ETF",
        "is_active": True,
        "is_synthetic": False,
        "identity_status": "resolved",
        "instrument_type": SimpleNamespace(name="ETF", asset_class=SimpleNamespace(name="Equity")),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("instrument", "matches", "expected"),
    [
        (_canonical_fund_instrument(), 1, True),
        (
            _canonical_fund_instrument(
                instrument_type=SimpleNamespace(
                    name="ETF", asset_class=SimpleNamespace(name="Commodity")
                )
            ),
            1,
            True,
        ),
        (
            _canonical_fund_instrument(
                instrument_type=SimpleNamespace(
                    name="Exchange Traded Vehicle",
                    asset_class=SimpleNamespace(name="Exchange Traded Product"),
                )
            ),
            1,
            True,
        ),
        (
            _canonical_fund_instrument(
                instrument_type=SimpleNamespace(
                    name="Exchange Traded Vehicle",
                    asset_class=SimpleNamespace(name="Equity"),
                )
            ),
            1,
            False,
        ),
        (
            _canonical_fund_instrument(
                instrument_type=SimpleNamespace(
                    name="ETN", asset_class=SimpleNamespace(name="Exchange Traded Product")
                )
            ),
            1,
            False,
        ),
        (_canonical_fund_instrument(identity_status="provisional"), 1, False),
        (
            _canonical_fund_instrument(
                instrument_type=SimpleNamespace(
                    name="Stock", asset_class=SimpleNamespace(name="Equity")
                )
            ),
            1,
            False,
        ),
        (_canonical_fund_instrument(is_active=False), 1, False),
        (_canonical_fund_instrument(is_synthetic=True), 1, False),
        (_canonical_fund_instrument(), 2, False),
    ],
)
async def test_acquire_resolves_only_one_active_canonical_fund(instrument, matches, expected):
    resolved = await _resolve_canonical_fund_instrument(
        _FundResolutionDB([instrument] * matches), "OIH"
    )

    assert (resolved is not None) is expected


@pytest.mark.asyncio
async def test_acquire_cache_only_is_read_only_and_never_probes(monkeypatch):
    db = FakeBootstrapDB()
    instrument = _canonical_fund_instrument()
    profile = SimpleNamespace(id=21, instrument_id=81, instrument=instrument)
    cached = SimpleNamespace(id=99, source_provider="vaneck")

    async def profile_for_instrument(_db, instrument_id):
        assert instrument_id == instrument.id
        return profile

    async def latest_snapshot(_db, instrument_id, **kwargs):
        assert instrument_id == instrument.id
        assert kwargs == {"include_holdings": True, "include_controlled_fixture": False}
        return cached

    async def must_not_be_called(*_args, **_kwargs):
        raise AssertionError("cache-only acquisition must not perform source work")

    def explicit_acquire_must_not_be_called(**_kwargs):
        raise AssertionError("cache-only acquisition must not bind Provider scope")

    monkeypatch.setattr(
        "app.services.provider_runtime.bind_explicit_etf_holdings_acquisition",
        explicit_acquire_must_not_be_called,
        raising=False,
    )

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        profile_for_instrument,
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.get_latest_snapshot", latest_snapshot)
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._apply_known_route_metadata", must_not_be_called
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter", must_not_be_called
    )

    result = await acquire_etf_holdings_profile(
        db, symbol="OIH", request_id="f30d76c2-f0da-4d90-b713-52c7d0e2f847", refresh=False
    )

    assert result is not None
    assert result.outcome == "cached"
    assert result.snapshot is cached
    assert result.refresh_attempted is False
    assert result.provider_request_log_ids == []
    assert db.flush_calls == 0
    assert db.commit_calls == 0


async def _async_value(value):
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("binder_available", [True, False], ids=["bound", "provider-not-staged"])
async def test_acquire_refresh_creates_only_profile_for_existing_canonical_fund(
    monkeypatch, binder_available
):
    db = FakeBootstrapDB()
    instrument = _canonical_fund_instrument()
    profile = SimpleNamespace(
        id=22,
        instrument_id=81,
        instrument=None,
        adapter_key=None,
        provider_aliases={},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
    )
    acquired_snapshot = SimpleNamespace(id=111)
    captured = {}
    profile_creations = []
    success_records = []
    binder_calls = _install_explicit_etf_acquisition_binder(monkeypatch) if binder_available else []
    if not binder_available:
        monkeypatch.delattr(
            "app.services.provider_runtime.bind_explicit_etf_holdings_acquisition",
            raising=False,
        )

    class FakeAdapter:
        source_provider = "vaneck"
        supports_issuer_only_acquire = True

        def probe(self, **kwargs):
            assert kwargs["symbol"] == "OIH"
            return SimpleNamespace(status="ready", reason=None, confidence=0.9)

    profile_reads = 0

    async def profile_for_instrument(_db, _instrument_id):
        nonlocal profile_reads
        profile_reads += 1
        return None if profile_reads == 1 else profile

    async def ensure_profile(_db, supplied_instrument):
        profile_creations.append(supplied_instrument)
        return profile

    async def latest_snapshot(_db, _instrument_id, **_kwargs):
        return None

    async def refresh_route(_db, supplied_profile, **kwargs):
        assert supplied_profile is profile
        assert db.commit_calls == 1
        if binder_available:
            assert _EXPLICIT_ETF_ACQUISITION_BINDING.get() == {
                "request_id": "7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
                "instrument_id": instrument.id,
                "symbol": instrument.symbol,
                "issuer_provider_name": "vaneck",
            }
        kwargs["request_log_ids_out"].append(481)
        captured.update(kwargs)
        return acquired_snapshot

    async def record_success(_db, supplied_profile, *, snapshot):
        success_records.append((supplied_profile, snapshot))

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        profile_for_instrument,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.known_etf_route_metadata",
        lambda symbol, **kwargs: {
            "provider_aliases": {
                "holdings_adapter": "vaneck",
                "product_slug": "oil-services-etf-oih",
            }
        }
        if symbol == "OIH"
        else None,
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.ensure_etf_profile", ensure_profile)

    def apply_curated_route(supplied_profile, **_kwargs):
        supplied_profile.adapter_key = "vaneck"
        supplied_profile.provider_aliases = {
            "holdings_adapter": "vaneck",
            "holdings_source_provider": "vaneck",
            "product_slug": "oil-services-etf-oih",
        }
        return True

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._apply_known_route_metadata", apply_curated_route
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.get_latest_snapshot", latest_snapshot)
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter",
        lambda key: FakeAdapter() if key == "vaneck" else None,
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh._refresh_adapter_route", refresh_route)
    monkeypatch.setattr("app.services.etf_holdings_refresh._record_success", record_success)

    result = await acquire_etf_holdings_profile(
        db,
        symbol="OIH",
        instrument_id=instrument.id,
        request_id="7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
        refresh=True,
    )

    assert result is not None
    assert db.commit_calls == 1
    if not binder_available:
        assert result.outcome == "held"
        assert result.refresh_attempted is False
        assert result.refresh_succeeded is False
        assert result.provider_request_log_ids == []
        assert captured == {}
        assert success_records == []
        return

    assert result.outcome == "acquired"
    assert result.snapshot_id == acquired_snapshot.id
    assert result.refresh_attempted is True
    assert profile.instrument is instrument
    assert profile_creations == [instrument]
    assert profile_reads == 2
    assert captured["acquisition_request_id"] == "7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d"
    assert captured["atomic_ingest_savepoint"] is True
    assert captured["request_log_ids_out"] == result.provider_request_log_ids
    assert result.provider_request_log_ids == [481]
    assert binder_calls == [
        {
            "request_id": "7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "issuer_provider_name": "vaneck",
        }
    ]
    assert _EXPLICIT_ETF_ACQUISITION_BINDING.get() is None
    from app.services import provider_runtime

    assert provider_runtime._EXPLICIT_ACQUISITION_CONTEXT.get() is None
    assert success_records == [(profile, acquired_snapshot)]
    assert db.flush_calls == 2


@pytest.mark.asyncio
async def test_acquire_rejects_unknown_fund_without_creating_profile(monkeypatch):
    async def no_profile_or_creation(*_args, **_kwargs):
        raise AssertionError("invalid identities must be rejected before profile access")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(None),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        no_profile_or_creation,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile", no_profile_or_creation
    )

    result = await acquire_etf_holdings_profile(
        FakeBootstrapDB(),
        symbol="NOTAETF",
        request_id="7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
        refresh=True,
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instrument_type",
    [
        SimpleNamespace(name="ETF", asset_class=SimpleNamespace(name="Equity")),
        SimpleNamespace(
            name="Exchange Traded Vehicle",
            asset_class=SimpleNamespace(name="Exchange Traded Product"),
        ),
    ],
    ids=["etf", "exchange-traded-vehicle"],
)
async def test_selected_acquire_returns_unavailable_without_exact_route(
    monkeypatch, instrument_type
):
    from app.schemas.etf_holdings import ETFProfileAcquireOut, ETFProfileAcquireRequest

    instrument = _canonical_fund_instrument()
    instrument.symbol = "IGV"
    instrument.instrument_type = instrument_type

    async def no_profile(_db, _instrument_id):
        return None

    async def profile_creation_must_not_run(*_args, **_kwargs):
        raise AssertionError("an unaudited ticker must not create a guessed adapter profile")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument", no_profile
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.known_etf_route_metadata",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile", profile_creation_must_not_run
    )

    result = await acquire_etf_holdings_profile(
        FakeBootstrapDB(),
        symbol="IGV",
        instrument_id=instrument.id,
        request_id="f30d76c2-f0da-4d90-b713-52c7d0e2f847",
        refresh=True,
    )

    assert result is not None
    assert result.outcome == "unavailable"
    assert result.profile is None
    assert result.instrument_id == instrument.id
    assert result.symbol == "IGV"
    assert result.refresh_attempted is False
    assert result.provider_request_log_ids == []
    assert "fund-specific product identifier" in result.message

    request = ETFProfileAcquireRequest(
        request_id="f30d76c2-f0da-4d90-b713-52c7d0e2f847",
        instrument_id=instrument.id,
        refresh=True,
    )
    response = ETFProfileAcquireOut(
        request_id=request.request_id,
        outcome=result.outcome,
        instrument_id=result.instrument_id,
        symbol=result.symbol,
        refresh=request.refresh,
        refresh_attempted=result.refresh_attempted,
        refresh_succeeded=result.refresh_succeeded,
        profile=None,
        snapshot=None,
        provider_request_log_ids=result.provider_request_log_ids,
        message=result.message,
    )
    assert response.instrument_id == instrument.id
    assert response.symbol == "IGV"
    assert response.profile is None
    assert response.outcome == "unavailable"


@pytest.mark.asyncio
async def test_selected_acquire_uses_null_issuer_canonical_name_only_as_catalog_hint(
    monkeypatch,
):
    instrument = _canonical_fund_instrument(
        symbol="IGV",
        name="iShares Expanded Tech-Software Sector ETF",
        issuer_id=None,
        issuer=None,
    )
    profile = SimpleNamespace(
        id=991,
        instrument_id=instrument.id,
        instrument=instrument,
        issuer=None,
        sponsor=None,
        fund_family=None,
        index_name=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
        provider_aliases={},
        legal_metadata={},
        adapter_key=None,
        adapter_status="unresolved",
        adapter_confidence=0,
    )
    profile_lookups = 0

    async def profile_lookup(_db, _instrument_id):
        nonlocal profile_lookups
        profile_lookups += 1
        return None if profile_lookups == 1 else profile

    async def ensure_profile(_db, _instrument):
        return profile

    async def no_snapshot(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument", profile_lookup
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.ensure_etf_profile", ensure_profile)
    monkeypatch.setattr("app.services.etf_holdings_refresh.get_latest_snapshot", no_snapshot)
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._explicit_etf_acquisition_binder", lambda: None
    )

    result = await acquire_etf_holdings_profile(
        FakeBootstrapDB(),
        symbol="IGV",
        instrument_id=instrument.id,
        request_id="537c16da-6d60-4e3c-b19d-2b0dbbe6f8a6",
        refresh=True,
    )

    assert result is not None
    assert result.outcome == "held"
    assert result.refresh_attempted is False
    assert result.provider_request_log_ids == []
    assert result.profile is profile
    assert profile.adapter_key == "ishares"
    assert profile.issuer is None
    assert profile.provider_aliases == {
        "holdings_adapter": "ishares",
        "holdings_source_provider": "ishares",
        "issuer_product_catalog_key": "ishares_us_etf_products_v1",
        "issuer_catalog_discovery_hint": "canonical_iShares_fund_name",
    }
    assert "Provider request scope is staged" in result.message


@pytest.mark.asyncio
async def test_catalog_route_uses_canonical_instrument_name_not_profile_alias(monkeypatch):
    instrument = _canonical_fund_instrument(
        id=82,
        symbol="IGV",
        name="iShares Expanded Tech-Software Sector ETF",
        issuer_id=None,
        issuer=None,
    )
    profile = SimpleNamespace(
        id=992,
        instrument_id=instrument.id,
        instrument=instrument,
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
        adapter_key="ishares",
        provider_aliases={
            "holdings_adapter": "ishares",
            "holdings_source_provider": "ishares",
            "issuer_product_catalog_key": "ishares_us_etf_products_v1",
            "canonical_fund_name": "iShares Expanded Tech ETF (untrusted alias)",
        },
    )
    observed = {}

    class Adapter:
        adapter_key = "ishares"
        source_provider = "ishares"

        def probe(self, **kwargs):
            assert kwargs["symbol"] == "IGV"
            return SimpleNamespace(status="ready", reason=None, confidence=0.9)

        async def fetch_latest(self, *, symbol, issuer_product_id=None, identifiers=None):
            observed.update(identifiers or {})
            raise ETFHoldingsRouteHeldError("controlled no-network stop")

    async def no_artifact(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter", lambda _key: Adapter()
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._retain_rejected_fetch_artifact", no_artifact
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="controlled no-network"):
        await _refresh_adapter_route(FakeBootstrapDB(), profile)

    assert observed["canonical_fund_name"] == instrument.name


@pytest.mark.asyncio
async def test_selected_acquire_rejects_instrument_id_that_does_not_match_path_symbol(
    monkeypatch,
):
    instrument = _canonical_fund_instrument()

    async def profile_lookup_must_not_run(*_args, **_kwargs):
        raise AssertionError("mismatched selected identity must stop before profile lookup")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        profile_lookup_must_not_run,
    )

    result = await acquire_etf_holdings_profile(
        FakeBootstrapDB(),
        symbol=instrument.symbol,
        instrument_id=instrument.id + 1,
        request_id="f30d76c2-f0da-4d90-b713-52c7d0e2f847",
        refresh=True,
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["BWET", "BDRY"])
async def test_new_amplify_audit_profile_binds_native_route_then_holds_without_provider_source(
    monkeypatch, symbol
):
    db = FakeBootstrapDB()
    instrument = _canonical_fund_instrument()
    instrument.symbol = symbol
    instrument.name = f"{symbol} audited Amplify ETF"
    profile = SimpleNamespace(
        id=99,
        instrument_id=instrument.id,
        instrument=None,
        adapter_key=None,
        adapter_status="unresolved",
        adapter_confidence=None,
        provider_aliases={},
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
    )
    profile_reads = 0

    async def profile_for_instrument(_db, _instrument_id):
        nonlocal profile_reads
        profile_reads += 1
        return None if profile_reads == 1 else profile

    async def ensure_profile(_db, supplied_instrument):
        assert supplied_instrument is instrument
        return profile

    async def latest_snapshot(_db, _instrument_id, **_kwargs):
        return None

    class FakeAmplifyAdapter:
        adapter_key = "amplify"
        source_provider = "amplify"
        supports_issuer_only_acquire = True

        def probe(self, **kwargs):
            assert kwargs["symbol"] == symbol
            return SimpleNamespace(status="ready", reason=None, confidence=0.9)

    binder_calls = _install_explicit_etf_acquisition_binder(monkeypatch)

    async def provider_bridge_held(_db, _profile, **_kwargs):
        raise ETFHoldingsRouteHeldError("ETF publisher has no shared Provider source record")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        profile_for_instrument,
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.ensure_etf_profile", ensure_profile)
    monkeypatch.setattr("app.services.etf_holdings_refresh.get_latest_snapshot", latest_snapshot)
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter",
        lambda key: FakeAmplifyAdapter() if key == "amplify" else None,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route", provider_bridge_held
    )

    result = await acquire_etf_holdings_profile(
        db,
        symbol=symbol,
        instrument_id=instrument.id,
        request_id="f30d76c2-f0da-4d90-b713-52c7d0e2f847",
        refresh=True,
    )

    assert result is not None
    assert result.outcome == "held"
    assert result.profile is profile
    assert profile.instrument is instrument
    assert profile.adapter_key == "amplify"
    assert profile.provider_aliases["holdings_source_provider"] == "amplify"
    assert result.refresh_attempted is True
    assert result.refresh_succeeded is False
    assert result.snapshot is None
    assert result.provider_request_log_ids == []
    assert "no shared Provider source record" in result.message
    assert binder_calls == [
        {
            "request_id": "f30d76c2-f0da-4d90-b713-52c7d0e2f847",
            "instrument_id": instrument.id,
            "symbol": symbol,
            "issuer_provider_name": "amplify",
        }
    ]


@pytest.mark.asyncio
async def test_acquire_cache_only_does_not_create_missing_profile(monkeypatch):
    instrument = _canonical_fund_instrument()

    async def no_profile_or_creation(*_args, **_kwargs):
        raise AssertionError("cache-only must not create an ETF profile")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        lambda *_args: _async_value(None),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile", no_profile_or_creation
    )

    result = await acquire_etf_holdings_profile(
        FakeBootstrapDB(),
        symbol="OIH",
        request_id="7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
        refresh=False,
    )

    assert result is None


@pytest.mark.asyncio
async def test_acquire_holds_unproven_adapter_without_transport(monkeypatch):
    instrument = _canonical_fund_instrument()
    snapshot = SimpleNamespace(id=98)
    profile = SimpleNamespace(
        id=25,
        instrument_id=81,
        instrument=instrument,
        adapter_key="vaneck",
        provider_aliases={"holdings_adapter": "vaneck", "product_slug": "oil-services-etf-oih"},
    )

    class UnreviewedAdapter:
        source_provider = "vaneck"

        def probe(self, **_kwargs):
            raise AssertionError("issuer-only eligibility must be checked before probing")

    async def refresh_must_not_run(*_args, **_kwargs):
        raise AssertionError("unreviewed adapter must not reach shared transport")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        lambda *_args: _async_value(profile),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._apply_known_route_metadata",
        lambda _profile, **_kwargs: False,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_latest_snapshot",
        lambda *_args, **_kwargs: _async_value(snapshot),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter",
        lambda _key: UnreviewedAdapter(),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route", refresh_must_not_run
    )

    result = await acquire_etf_holdings_profile(
        FakeBootstrapDB(),
        symbol="OIH",
        request_id="7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
        refresh=True,
    )

    assert result is not None
    assert result.outcome == "held"
    assert result.refresh_attempted is False
    assert result.snapshot is snapshot
    assert result.provider_request_log_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_reason", "cancelled"),
    [
        (RuntimeError("bounded test failure"), None, False),
        (
            ValueError("Issuer holdings route returned a future composition date."),
            "future_dated_source",
            False,
        ),
        (asyncio.CancelledError(), None, True),
    ],
    ids=["failure", "future-date", "cancellation"],
)
async def test_acquire_failure_or_cancellation_restores_provider_scope(
    monkeypatch, failure, expected_reason, cancelled
):
    db = FakeBootstrapDB()
    instrument = _canonical_fund_instrument()
    prior_snapshot = SimpleNamespace(id=98, source_provider="vaneck")
    profile = SimpleNamespace(
        id=24,
        instrument_id=81,
        instrument=instrument,
        adapter_key="vaneck",
        provider_aliases={
            "holdings_adapter": "vaneck",
            "holdings_source_provider": "vaneck",
            "product_slug": "oil-services-etf-oih",
        },
        issuer="VanEck",
        sponsor="VanEck",
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
    )
    failure_records = []
    binder_calls = _install_explicit_etf_acquisition_binder(monkeypatch)

    class FakeAdapter:
        source_provider = "vaneck"
        supports_issuer_only_acquire = True

        def probe(self, **_kwargs):
            return SimpleNamespace(status="ready", reason=None, confidence=0.9)

    async def profile_for_instrument(_db, _instrument_id):
        return profile

    async def latest_snapshot(_db, _instrument_id, **_kwargs):
        return prior_snapshot

    async def refresh_route(*_args, **_kwargs):
        assert _EXPLICIT_ETF_ACQUISITION_BINDING.get() == {
            "request_id": "7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "issuer_provider_name": "vaneck",
        }
        _kwargs["request_log_ids_out"].append(582)
        raise failure

    async def record_failure(_db, supplied_profile, observed_failure):
        failure_records.append((supplied_profile, observed_failure))

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument",
        profile_for_instrument,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._apply_known_route_metadata",
        lambda _profile, **_kwargs: False,
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.get_latest_snapshot", latest_snapshot)
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_holdings_adapter",
        lambda _key: FakeAdapter(),
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh._refresh_adapter_route", refresh_route)
    monkeypatch.setattr("app.services.etf_holdings_refresh._record_failure", record_failure)

    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await acquire_etf_holdings_profile(
                db,
                symbol="OIH",
                request_id="7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d",
                refresh=True,
            )
        assert failure_records == []
    else:
        result = await acquire_etf_holdings_profile(
            db, symbol="OIH", request_id="7f8e2a8d-a1a1-44a3-a900-b08c7d297a3d", refresh=True
        )
        assert result is not None
        assert result.outcome == "failed"
        assert result.snapshot is prior_snapshot
        assert result.snapshot_id == prior_snapshot.id
        assert result.refresh_attempted is True
        assert result.refresh_succeeded is False
        assert result.provider_request_log_ids == [582]
        assert result.reason_code == expected_reason
        assert failure_records == [(profile, failure)]

    assert len(binder_calls) == 1
    assert _EXPLICIT_ETF_ACQUISITION_BINDING.get() is None
    from app.services import provider_runtime

    assert provider_runtime._EXPLICIT_ACQUISITION_CONTEXT.get() is None
