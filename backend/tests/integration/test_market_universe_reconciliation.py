from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.instrument_reconciliation import (
    InstrumentReconciliationIssue,
    InstrumentReconciliationIssueObservation,
)
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    MarketUniverseLifecycleObservation,
    MarketUniverseReconciliationRun,
)
from app.models.provider_observation import UniverseDiscoverySnapshot
from app.services.market_universe import _quarantine_candidate, reconcile_us_universe
from app.services.provider_observations import store_universe_discovery_snapshot


class _AsyncSessionAdapter:
    """Expose the integration fixture's synchronous session to async services."""

    def __init__(self, session):
        self._session = session

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def flush(self, *args, **kwargs):
        return self._session.flush(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return self._session.get(*args, **kwargs)

    async def commit(self):
        return self._session.commit()

    async def rollback(self):
        return self._session.rollback()

    def add(self, value):
        self._session.add(value)

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.mark.asyncio
async def test_cta_source_page_and_raw_payload_are_durably_stored(db):
    """Persist the complete downloaded source before any row normalization."""

    source = DataSource(name="cta_plan", base_url="https://ftp.nyse.com/cta_symbol_files/")
    db.add(source)
    db.flush()
    page = {
        "total": 1,
        "quotes": [{"symbol": "PERSIST", "exchange_mic": "XNYS"}],
        "complete": False,
        "validation_errors": ["unknown participant retained for review"],
        "source_files": ["cta_symbol_file_index", "CTA.Symbol.File.20261012.csv"],
        "source_snapshot_date": "2026-10-12",
        "raw_source_payload": {
            "index_html": "<a href='CTA.Symbol.File.20261012.csv'>file</a>",
            "symbol_file_csv": "PERSIST,,?,,,,,,,,,,,,,0",
        },
    }

    await store_universe_discovery_snapshot(
        _AsyncSessionAdapter(db),
        data_source_id=source.id,
        quote_type="EQUITY",
        offset=0,
        page=page,
    )
    db.commit()
    stored = db.execute(select(UniverseDiscoverySnapshot)).scalar_one()

    assert stored.payload["page"] == page
    assert (
        stored.payload["page"]["raw_source_payload"]["symbol_file_csv"]
        == page["raw_source_payload"]["symbol_file_csv"]
    )
    assert stored.payload["page"]["validation_errors"] == page["validation_errors"]


@pytest.mark.asyncio
async def test_combined_nms_and_otc_reconciliation_persists_complete_source_evidence(
    db, monkeypatch
):
    """PostgreSQL stores both complete venue snapshots in one reconciliation cycle."""

    from app.services import market_universe

    sources = {
        "nasdaq": DataSource(name="nasdaq", base_url="https://nasdaq.example.test"),
        "finra_otc_directory": DataSource(
            name="finra_otc_directory", base_url="https://finra.example.test"
        ),
    }
    db.add_all(list(sources.values()))
    db.flush()
    resolved = [
        SimpleNamespace(provider_name=name, data_source=source) for name, source in sources.items()
    ]
    pages = {
        "nasdaq": {
            "total": 2,
            "quotes": [
                {"symbol": "PGNMS", "name": "Postgres NMS Example", "exchange": "XNAS"},
                {"symbol": "PGTXS", "name": "Postgres TXSE Example", "exchange": "TXSE"},
            ],
            "source_files": ["nasdaqlisted", "otherlisted"],
            "source_file_creation_times": {
                "nasdaqlisted": "2026-10-09T21:31:00",
                "otherlisted": "2026-10-09T21:31:00",
            },
        },
        "finra_otc_directory": {
            "total": 1,
            "quotes": [{"symbol": "PGOTC", "name": "Postgres OTC Example", "exchange": "OTC"}],
            "source_snapshot_date": "2026-10-09",
        },
    }
    providers = {
        name: SimpleNamespace(
            supported_discovery_types=lambda: ["EQUITY"],
            discover_universe_page=lambda _quote_type, _offset, page=page: page,
        )
        for name, page in pages.items()
    }

    async def resolve_fixture(*_args, **_kwargs):
        return resolved

    async def execute_fixture(_db, _capability, operation, *, provider_name, invoke, **_kwargs):
        assert operation.endswith(":0")
        return SimpleNamespace(
            result=invoke(providers[provider_name], None),
            data_source=sources[provider_name],
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda name: providers[name])
    monkeypatch.setattr(market_universe, "execute_provider_call", execute_fixture)

    result = await market_universe.reconcile_us_universe(
        _AsyncSessionAdapter(db), quote_types=["EQUITY"]
    )

    runs = (
        db.execute(
            select(MarketUniverseReconciliationRun).order_by(MarketUniverseReconciliationRun.id)
        )
        .scalars()
        .all()
    )
    snapshots = (
        db.execute(select(UniverseDiscoverySnapshot).order_by(UniverseDiscoverySnapshot.id))
        .scalars()
        .all()
    )

    assert result["status"] == "complete"
    assert result["providers"] == ["finra_otc_directory", "nasdaq"]
    assert [(run.provenance["provider"], run.status) for run in runs] == [
        ("nasdaq", "complete"),
        ("finra_otc_directory", "complete"),
    ]
    assert [snapshot.data_source.name for snapshot in snapshots] == [
        "nasdaq",
        "finra_otc_directory",
    ]
    assert [snapshot.payload["page"] for snapshot in snapshots] == [
        pages["nasdaq"],
        pages["finra_otc_directory"],
    ]
    assert [run.provenance["absence_scope"] for run in runs] == [None, "US_OTC"]
    nasdaq_run = runs[0]
    assert nasdaq_run.expected_count == 2
    assert nasdaq_run.observed_count == 2
    assert nasdaq_run.provenance["venue_coverage"]["row_counts"] == {"TXSE": 1, "XNAS": 1}
    assert nasdaq_run.provenance["source_snapshot_date"] == "2026-10-09"
    assert nasdaq_run.provenance["source_file_creation_times"] == {
        "nasdaqlisted": "2026-10-09T21:31:00",
        "otherlisted": "2026-10-09T21:31:00",
    }
    txse = db.execute(select(Exchange).where(Exchange.mic == "TXSE")).scalar_one()
    txse_listing = db.execute(
        select(InstrumentListing).where(InstrumentListing.exchange_id == txse.id)
    ).scalar_one()
    assert txse_listing.ticker == "PGTXS"


@pytest.mark.asyncio
async def test_failed_reconciliation_flush_keeps_raw_page_and_finishes_run(db_engine, monkeypatch):
    """A row-write constraint failure cannot strand a run or erase fetched data."""

    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument
    from app.services import market_universe

    async_engine = create_async_engine(
        db_engine.url.set(drivername="postgresql+asyncpg"), pool_pre_ping=True
    )
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            asset_class = AssetClass(name="Reconcile Test Equity", description="Test")
            db.add(asset_class)
            await db.flush()
            instrument_type = InstrumentType(
                name="Reconcile Test Stock", asset_class_id=asset_class.id
            )
            db.add(instrument_type)
            await db.flush()
            source = DataSource(
                name="fixture-duplicate-provider-symbol", base_url="https://example.test"
            )
            instrument = Instrument(
                symbol="DUPLICATE",
                name="Existing binding owner",
                instrument_type_id=instrument_type.id,
                currency="USD",
            )
            instrument_b = Instrument(
                symbol="OTHER",
                name="Conflicting binding owner",
                instrument_type_id=instrument_type.id,
                currency="USD",
            )
            db.add_all([source, instrument, instrument_b])
            await db.flush()
            db.add(
                InstrumentProviderSymbol(
                    instrument_id=instrument.id,
                    data_source_id=source.id,
                    provider_symbol="DUPLICATE",
                    provider_exchange_code="OTC",
                )
            )
            await db.commit()
            resolved = SimpleNamespace(provider_name=source.name, data_source=source)
            provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])

            async def resolve_fixture(*_args, **_kwargs):
                return [resolved]

            async def complete_page(*_args, **_kwargs):
                return SimpleNamespace(
                    result={
                        "total": 1,
                        "quotes": [{"symbol": "DUPLICATE", "exchange": "OTC"}],
                        "complete": True,
                    },
                    data_source=source,
                )

            async def fail_on_duplicate_binding(session, **_kwargs):
                session.add(
                    InstrumentProviderSymbol(
                        instrument_id=instrument_b.id,
                        data_source_id=source.id,
                        provider_symbol="DUPLICATE",
                        provider_exchange_code="OTC",
                    )
                )
                await session.flush()

            monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
            monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
            monkeypatch.setattr(market_universe, "execute_provider_call", complete_page)
            monkeypatch.setattr(market_universe, "_reconcile_rows", fail_on_duplicate_binding)

            source_id = source.id
            result = await reconcile_us_universe(db, provider_name=resolved.provider_name)

            run = (
                await db.execute(
                    select(MarketUniverseReconciliationRun).where(
                        MarketUniverseReconciliationRun.data_source_id == source_id
                    )
                )
            ).scalar_one()
            snapshots = (
                (
                    await db.execute(
                        select(UniverseDiscoverySnapshot).where(
                            UniverseDiscoverySnapshot.data_source_id == source_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            bindings = (
                (
                    await db.execute(
                        select(InstrumentProviderSymbol).where(
                            InstrumentProviderSymbol.data_source_id == source_id,
                            InstrumentProviderSymbol.provider_symbol == "DUPLICATE",
                        )
                    )
                )
                .scalars()
                .all()
            )

            assert result["status"] == "failed"
            assert run.status == "failed"
            assert "duplicate key" in (run.error or "").lower()
            assert len(snapshots) == 1
            assert snapshots[0].payload["page"]["quotes"] == [
                {"symbol": "DUPLICATE", "exchange": "OTC"}
            ]
            assert len(bindings) == 1
    finally:
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_nms_absence_requires_same_cycle_cta_and_nasdaq_equity_etf_scopes(db, monkeypatch):
    """Only the complete same-date Tape A/B + Tape C pair can count NMS absence."""

    from app.services import market_universe

    observed_at = datetime(2026, 10, 8, 21, 0, tzinfo=UTC)
    sources = {
        name: DataSource(name=name, base_url=f"https://{name}.example.test")
        for name in ("cta_plan", "nasdaq")
    }
    db.add_all(sources.values())
    db.flush()
    for name in ("cta_plan", "nasdaq"):
        prior = MarketUniverseReconciliationRun(
            data_source_id=sources[name].id,
            quote_type="EQUITY",
            observed_at=observed_at,
            finished_at=observed_at,
            status="complete",
            provenance={
                "provider": name,
                "quote_type": "EQUITY",
                "source_snapshot_date": "2026-10-08",
                "snapshot_complete": True,
            },
        )
        db.add(prior)
        db.flush()
        db.add(
            MarketUniverseLifecycleObservation(
                data_source_id=sources[name].id,
                run_id=prior.id,
                provider_symbol=f"MISSING_{name.upper()}",
                exchange_mic="XNAS",
                quote_type="EQUITY",
                observed_at=observed_at,
                present=True,
                lifecycle_status="active",
                first_seen_at=observed_at,
                last_seen_at=observed_at,
                consecutive_seen=1,
                consecutive_missing=0,
                payload={"source": name},
            )
        )
    db.flush()

    nasdaq_files = ["nasdaqlisted", "otherlisted"]
    creation_times = {
        "nasdaqlisted": "2026-10-09T21:31:00",
        "otherlisted": "2026-10-09T21:31:00",
    }
    pages = {
        ("cta_plan", "EQUITY"): {
            "total": 1,
            "quotes": [{"symbol": "ACTIVE", "name": "Active Equity", "exchange": "XNAS"}],
            "complete": True,
            "source_files": ["cta_symbol_file_index", "CTA.Symbol.File.20261009.csv"],
            "source_snapshot_date": "2026-10-09",
            "source_row_count": 1,
            "raw_source_payload": {"index_html": "index", "symbol_file_csv": "row"},
        },
        ("nasdaq", "EQUITY"): {
            "total": 1,
            "quotes": [
                {
                    "symbol": "ACTIVE",
                    "name": "Active Equity",
                    "exchange": "XNAS",
                    "source_file": "nasdaqlisted",
                }
            ],
            "source_files": nasdaq_files,
            "source_file_creation_times": creation_times,
        },
        ("nasdaq", "ETF"): {
            "total": 1,
            "quotes": [
                {
                    "symbol": "FUNDX",
                    "name": "Fund X",
                    "exchange": "XNAS",
                    "quoteType": "ETF",
                    "source_file": "nasdaqlisted",
                }
            ],
            "source_files": nasdaq_files,
            "source_file_creation_times": creation_times,
        },
    }
    providers = {
        "cta_plan": SimpleNamespace(
            supported_discovery_types=lambda: ["EQUITY"],
            discover_universe_page=lambda quote_type, _offset: pages[("cta_plan", quote_type)],
        ),
        "nasdaq": SimpleNamespace(
            supported_discovery_types=lambda: ["EQUITY", "ETF"],
            discover_universe_page=lambda quote_type, _offset: pages[("nasdaq", quote_type)],
        ),
    }
    resolved = [
        SimpleNamespace(provider_name=name, data_source=source) for name, source in sources.items()
    ]

    async def resolve_fixture(*_args, **_kwargs):
        return resolved

    async def execute_fixture(_db, _capability, _operation, *, provider_name, invoke, **_kwargs):
        return SimpleNamespace(
            result=invoke(providers[provider_name], None),
            data_source=sources[provider_name],
        )

    async def completed_session(*_args, **_kwargs):
        return datetime(2026, 10, 9).date(), "America/New_York"

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda name: providers[name])
    monkeypatch.setattr(market_universe, "execute_provider_call", execute_fixture)
    monkeypatch.setattr(market_universe, "_completed_nms_session", completed_session)

    partial = await reconcile_us_universe(
        _AsyncSessionAdapter(db), provider_name="nasdaq", missing_confirmations=1
    )
    assert partial["status"] == "complete"
    stale_after_partial = (
        db.execute(
            select(MarketUniverseLifecycleObservation).where(
                MarketUniverseLifecycleObservation.provider_symbol.like("MISSING_%")
            )
        )
        .scalars()
        .all()
    )
    assert all(
        observation.present and observation.consecutive_missing == 0
        for observation in stale_after_partial
    )

    result = await reconcile_us_universe(_AsyncSessionAdapter(db), missing_confirmations=1)

    runs = (
        db.execute(
            select(MarketUniverseReconciliationRun)
            .where(
                MarketUniverseReconciliationRun.data_source_id.in_([s.id for s in sources.values()])
            )
            .order_by(MarketUniverseReconciliationRun.id)
        )
        .scalars()
        .all()
    )
    observations = (
        db.execute(
            select(MarketUniverseLifecycleObservation).where(
                MarketUniverseLifecycleObservation.data_source_id.in_(
                    [s.id for s in sources.values()]
                )
            )
        )
        .scalars()
        .all()
    )
    assert result["status"] == "complete"
    assert len(runs) == 7  # two prior, two Nasdaq-only, then the complete three-scope cycle
    union_runs = [run for run in runs if run.provenance.get("nms_union_complete")]
    assert len(union_runs) == 3
    assert [run.provenance["absence_scope"] for run in union_runs] == [
        "US_NMS",
        "US_NMS",
        "US_NMS",
    ]
    partial_runs = [
        run
        for run in runs
        if run.provenance.get("reconciliation_cycle_id")
        and not run.provenance.get("nms_union_complete")
    ]
    assert len(partial_runs) == 2
    assert all(run.provenance["absence_scope"] is None for run in partial_runs)
    stale_observations = [
        observation
        for observation in observations
        if observation.provider_symbol.startswith("MISSING_")
    ]
    assert {observation.consecutive_missing for observation in stale_observations} == {1}
    assert all(not observation.present for observation in stale_observations)


@pytest.mark.asyncio
async def test_long_reconciliation_reason_uses_bounded_postgres_fingerprint(db):
    """Long human-readable quarantine reasons remain persistable in Postgres."""

    source = DataSource(name="nasdaq", base_url="https://nasdaq.example.test")
    db.add(source)
    db.flush()
    reason = "ticker/venue matches multiple instruments without a provider binding"
    arguments = {
        "data_source_id": source.id,
        "provider_name": "nasdaq",
        "symbol": "BSRT",
        "exchange_mic": "XNYS",
        "payload": {"symbol": "BSRT", "source_record": {"Security Name": "Example"}},
        "reason": reason,
    }

    await _quarantine_candidate(_AsyncSessionAdapter(db), **arguments)
    db.commit()

    issue = db.execute(select(InstrumentReconciliationIssue)).scalar_one()
    assert len(issue.fingerprint) == 64
    assert issue.payload["reason"] == reason
    assert db.query(InstrumentReconciliationIssueObservation).count() == 1

    await _quarantine_candidate(_AsyncSessionAdapter(db), **arguments)
    db.commit()
    assert db.query(InstrumentReconciliationIssue).count() == 1
    assert db.query(InstrumentReconciliationIssueObservation).count() == 2


@pytest.mark.asyncio
async def test_short_legacy_reconciliation_fingerprint_is_reused(db):
    """Existing readable fingerprints remain the same issue after upgrade."""

    source = DataSource(name="nasdaq", base_url="https://nasdaq.example.test")
    db.add(source)
    db.flush()
    reason = "ambiguous match"
    legacy_fingerprint = f"nasdaq:ABC:XNAS:{reason}"
    db.add(
        InstrumentReconciliationIssue(
            data_source_id=source.id,
            provider_symbol="ABC",
            issue_type="unresolved_universe_identity",
            fingerprint=legacy_fingerprint,
            status="open",
            payload={"reason": reason},
            observed_at=datetime.now(UTC),
        )
    )
    db.commit()

    await _quarantine_candidate(
        _AsyncSessionAdapter(db),
        data_source_id=source.id,
        provider_name="nasdaq",
        symbol="ABC",
        exchange_mic="XNAS",
        payload={"symbol": "ABC"},
        reason=reason,
    )
    db.commit()

    issues = db.query(InstrumentReconciliationIssue).all()
    assert len(issues) == 1
    assert issues[0].fingerprint == legacy_fingerprint
    observations = db.query(InstrumentReconciliationIssueObservation).all()
    assert len(observations) == 1
    assert observations[0].fingerprint == legacy_fingerprint
