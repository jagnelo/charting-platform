from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.etf_holdings import ETFHolding
from app.models.instrument import EquityDetail, Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.providers.base import IdentifierRecord, InstrumentProfile, ListingRecord
from app.services.etf_holdings import (
    _capability_source_tier,
    _enrich_existing_constituent_classification,
    _holding_needs_reconcile,
    _resolve_or_create_constituent,
    ensure_etf_profile,
    ensure_lightweight_etf_instrument,
    ingest_holdings_snapshot,
    reconcile_snapshot_constituents,
)
from app.services.etf_holdings_adapters import CanonicalHoldingRow
from app.services.etf_holdings_refresh import reconcile_all_etf_holdings_classifications
from app.services.instrument_mastering import ensure_instrument_type, register_identifier


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


class FakeMetadataProvider:
    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        if symbol != "MSFT":
            return None
        return InstrumentProfile(
            provider="yfinance",
            symbol="MSFT",
            canonical_symbol="MSFT",
            name="Microsoft Corporation",
            currency="USD",
            quote_type="EQUITY",
            exchange="NASDAQ",
            identifiers=[
                IdentifierRecord(
                    identifier_type="ISIN",
                    identifier_value="US5949181045",
                    is_primary=True,
                    source="yfinance",
                ),
            ],
            listings=[
                ListingRecord(
                    provider_symbol="MSFT",
                    exchange_code="NASDAQ",
                    currency="USD",
                    provider_instrument_type="EQUITY",
                    is_primary=True,
                ),
            ],
            raw_payload={},
        )


class SectorOnlyMetadataProvider:
    calls: list[str]

    def __init__(self) -> None:
        self.calls = []

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile:
        self.calls.append(symbol)
        return InstrumentProfile(
            provider="provider-native",
            symbol=symbol,
            canonical_symbol=symbol,
            name="Microsoft Corporation",
            currency="USD",
            quote_type="EQUITY",
            exchange="NASDAQ",
            extra={"sector": "Information Technology", "classification_system": "provider_native"},
        )


def test_capability_source_tier_does_not_default_unclassified_ingest_to_issuer_native():
    assert (
        _capability_source_tier(
            provenance="controlled_fixture",
            source_provider="unclassified_provider",
        )
        == "none"
    )
    assert (
        _capability_source_tier(
            provenance="issuer_self_snapshotted_holdings",
            source_provider="example_issuer",
        )
        == "issuer_native"
    )
    assert (
        _capability_source_tier(
            provenance="unclassified_artifact",
            source_provider="unknown",
            legal_metadata={"source_tier": "licensed_vendor"},
        )
        == "licensed_vendor"
    )
    assert (
        _capability_source_tier(
            provenance="aggregator_snapshot",
            source_provider="market_vendor",
        )
        == "none"
    )
    assert (
        _capability_source_tier(
            provenance="vendor_snapshot",
            source_provider="market_data",
            legal_metadata={"entitlement_status": "licensed"},
        )
        == "licensed_vendor"
    )


@pytest.mark.asyncio
async def test_ingest_persists_none_for_unclassified_source_tier(db):
    async_db = AsyncSessionAdapter(db)
    etf_instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="UNCL",
        name="Unclassified ETF",
    )

    snapshot = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf_instrument,
        rows=[
            CanonicalHoldingRow(
                symbol="AAPL",
                name="Apple Inc.",
                weight=Decimal("1"),
                currency="USD",
                holding_type="equity",
                row_type="security",
            )
        ],
        composition_date=date(2026, 9, 5),
        provenance="controlled_fixture",
        source_provider="unclassified_provider",
        completeness_status="complete",
    )

    assert snapshot.extra_data["source_tier"] == "none"


@pytest.mark.asyncio
async def test_ingest_rejects_future_metadata_before_profile_hydration(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    etf_instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="FUTURE",
        name="Future Metadata ETF",
    )

    async def unexpected_profile_hydration(*_args, **_kwargs):
        raise AssertionError("future metadata must be rejected before profile hydration")

    monkeypatch.setattr(
        "app.services.etf_holdings.ensure_etf_profile",
        unexpected_profile_hydration,
    )

    with pytest.raises(ValueError, match="future composition date"):
        await ingest_holdings_snapshot(
            async_db,
            etf_instrument=etf_instrument,
            rows=[],
            composition_date=date.today() + timedelta(days=1),
            provenance="issuer_native",
            source_provider="issuer-test",
        )


class FakeIdentifierProvider:
    name = "openfigi"

    def __init__(self, mapping: dict[str, list[IdentifierRecord]]):
        self.mapping = mapping

    def fetch_stable_identifiers(self, symbol: str) -> list[IdentifierRecord]:
        return list(self.mapping.get(symbol, []))

    def resolve_instrument_profile(
        self,
        *,
        isin: str | None = None,
        cusip: str | None = None,
        sedol: str | None = None,
    ) -> InstrumentProfile | None:
        key = (isin or cusip or sedol or "").strip().upper()
        if key != "882508104":
            return None
        return InstrumentProfile(
            provider="openfigi",
            symbol="TXN",
            canonical_symbol="TXN",
            name="Texas Instruments Incorporated",
            currency="USD",
            quote_type="EQUITY",
            exchange="NASDAQ",
            identifiers=[
                IdentifierRecord(
                    identifier_type="CUSIP",
                    identifier_value="882508104",
                    source="openfigi",
                ),
                IdentifierRecord(
                    identifier_type="COMPOSITE_FIGI",
                    identifier_value="BBG000BLNQ16",
                    is_primary=True,
                    source="openfigi",
                ),
            ],
            listings=[
                ListingRecord(
                    provider_symbol="TXN",
                    exchange_code="NASDAQ",
                    currency="USD",
                    provider_instrument_type="EQUITY",
                    is_primary=True,
                )
            ],
            raw_payload={"ticker": "TXN", "name": "Texas Instruments Incorporated"},
        )


@pytest.mark.asyncio
async def test_resolver_enriches_security_rows_through_provider_metadata(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "development")
    monkeypatch.setattr(
        "app.services.etf_holdings.get_default_metadata_provider",
        lambda: FakeMetadataProvider(),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers",
        lambda: [
            FakeIdentifierProvider(
                {
                    "MSFT": [
                        IdentifierRecord(
                            identifier_type="COMPOSITE_FIGI",
                            identifier_value="BBG000BPH459",
                            is_primary=True,
                            source="openfigi",
                        ),
                        IdentifierRecord(
                            identifier_type="FIGI",
                            identifier_value="BBG000BPH45",
                            source="openfigi",
                        ),
                    ]
                }
            )
        ],
    )

    instrument, confidence, _ = await _resolve_or_create_constituent(
        async_db,
        CanonicalHoldingRow(
            symbol="MSFT",
            name="Microsoft Corp",
            currency="USD",
            holding_type="equity",
            row_type="security",
        ),
        source_provider="ishares",
    )
    db.flush()

    assert instrument is not None
    assert instrument.symbol == "MSFT"
    assert instrument.name == "Microsoft Corporation"
    assert confidence == Decimal("0.9000")

    identifiers = (
        db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.instrument_id == instrument.id,
                InstrumentIdentifier.identifier_type.in_(
                    [
                        InstrumentIdentifierType.ISIN,
                        InstrumentIdentifierType.COMPOSITE_FIGI,
                        InstrumentIdentifierType.FIGI,
                    ]
                ),
            )
        )
        .scalars()
        .all()
    )
    identifier_values = {row.identifier_value for row in identifiers}
    assert "US5949181045" in identifier_values
    assert "BBG000BPH459" in identifier_values
    assert "BBG000BPH45" in identifier_values


@pytest.mark.asyncio
async def test_sector_only_metadata_never_promotes_to_industry_during_enrichment(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")
    instrument = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="MSFT",
        name="Microsoft Corporation",
        currency="USD",
        is_active=True,
    )
    db.add(instrument)
    db.flush()
    detail = EquityDetail(
        instrument_id=instrument.id,
        sector="Information Technology",
        field_provenance={"sector": {"classification_system": "provider_native"}},
    )
    db.add(detail)
    db.flush()

    provider = SectorOnlyMetadataProvider()
    monkeypatch.setattr("app.services.etf_holdings.get_default_metadata_provider", lambda: provider)

    await _enrich_existing_constituent_classification(
        async_db,
        instrument,
        reported_name="Microsoft Corporation",
        source_provider="spdr",
    )
    db.refresh(detail)

    assert provider.calls == ["MSFT"]
    assert detail.industry is None
    assert detail.sector == "Information Technology"
    assert detail.field_provenance == {"sector": {"classification_system": "provider_native"}}

    row = ETFHolding(
        reported_symbol="MSFT",
        reported_name="Microsoft Corporation",
        row_type="security",
        holding_type="equity",
        constituent_instrument=instrument,
        is_resolved=True,
    )
    assert _holding_needs_reconcile(row) is True


@pytest.mark.asyncio
async def test_resolver_can_skip_optional_provider_enrichment_for_bounded_ingestion(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "development")

    def unexpected_provider_call():
        raise AssertionError("bounded holdings ingestion must not fan out to metadata providers")

    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers", unexpected_provider_call
    )
    monkeypatch.setattr(
        "app.services.etf_holdings.get_default_metadata_provider", unexpected_provider_call
    )

    instrument, confidence, note = await _resolve_or_create_constituent(
        async_db,
        CanonicalHoldingRow(
            symbol="BOUNDFAST",
            name="Bounded Ingestion Corp",
            currency="USD",
            holding_type="equity",
            row_type="security",
        ),
        source_provider="spdr",
        allow_provider_enrichment=False,
    )
    db.flush()

    assert instrument is not None
    assert instrument.symbol == "BOUNDFAST"
    assert confidence == Decimal("0.5000")
    assert note is None


@pytest.mark.asyncio
async def test_resolver_collapses_duplicate_symbol_variants_via_stable_identifiers(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "development")
    monkeypatch.setattr(
        "app.services.etf_holdings.get_default_metadata_provider",
        lambda: FakeMetadataProvider(),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers",
        lambda: [
            FakeIdentifierProvider(
                {
                    "AAPL": [
                        IdentifierRecord(
                            identifier_type="COMPOSITE_FIGI",
                            identifier_value="BBG000B9XRY4",
                            is_primary=True,
                            source="openfigi",
                        )
                    ]
                }
            )
        ],
    )

    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")
    existing = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="APPLE-US",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    db.add(existing)
    db.flush()
    await register_identifier(
        async_db,
        existing,
        "openfigi",
        IdentifierRecord(
            identifier_type="COMPOSITE_FIGI",
            identifier_value="BBG000B9XRY4",
            is_primary=True,
            source="openfigi",
        ),
    )
    db.flush()

    resolved, confidence, _ = await _resolve_or_create_constituent(
        async_db,
        CanonicalHoldingRow(
            symbol="AAPL",
            name="Apple Inc",
            currency="USD",
            holding_type="equity",
            row_type="security",
        ),
        source_provider="spdr",
    )
    db.flush()

    assert resolved is not None
    assert resolved.id == existing.id
    assert confidence == Decimal("0.9200")
    instruments = db.execute(select(Instrument)).scalars().all()
    assert len(instruments) == 1


@pytest.mark.asyncio
async def test_reconcile_snapshot_constituents_promotes_identifier_only_placeholders(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "test")

    etf_instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="QQQ",
        name="Invesco QQQ Trust",
    )
    await ensure_etf_profile(async_db, etf_instrument, issuer="Invesco")

    snapshot = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf_instrument,
        source_provider="sec",
        provenance="sec_nport",
        composition_date=date(2026, 3, 31),
        rows=[
            CanonicalHoldingRow(
                symbol=None,
                name="Texas Instruments Inc.",
                cusip="882508104",
                currency="USD",
                holding_type="equity",
                row_type="security",
            )
        ],
    )
    db.flush()
    db.refresh(snapshot)
    placeholder = snapshot.rows[0].constituent_instrument
    assert placeholder is not None
    assert placeholder.symbol.startswith("HOLDING-")

    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "development")
    monkeypatch.setattr(
        "app.services.etf_holdings.get_default_metadata_provider",
        lambda: FakeMetadataProvider(),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers",
        lambda: [FakeIdentifierProvider({})],
    )

    snapshot = await reconcile_snapshot_constituents(async_db, snapshot)
    db.flush()
    db.refresh(snapshot)
    promoted = snapshot.rows[0].constituent_instrument

    assert promoted is not None
    assert promoted.symbol == "TXN"
    assert promoted.name == "Texas Instruments Incorporated"
    assert snapshot.resolved_count == 1
    assert snapshot.unresolved_count == 0


@pytest.mark.asyncio
async def test_explicit_issuer_adapter_wins_over_stale_fund_family_inference(db):
    async_db = AsyncSessionAdapter(db)

    etf = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="SMH",
        name="VanEck Semiconductor ETF",
    )
    profile = await ensure_etf_profile(
        async_db,
        etf,
        issuer="VanEck",
        fund_family="ARK ETF Trust",
        provider_aliases={
            "holdings_adapter": "vaneck",
            "product_slug": "semiconductor-etf-smh",
        },
    )

    assert profile.adapter_key == "vaneck"
    assert profile.adapter_status == "candidate"


@pytest.mark.asyncio
async def test_ingest_holdings_snapshot_normalizes_long_currency_names_in_rows(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "test")

    etf_instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="QQQJ",
        name="Invesco NASDAQ Next Gen 100 ETF",
    )

    snapshot = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf_instrument,
        source_provider="sec",
        provenance="sec_nport",
        composition_date=date(2026, 3, 31),
        rows=[
            CanonicalHoldingRow(
                symbol=None,
                name="Shopify Inc.",
                cusip="82509L107",
                isin="CA82509L1076",
                currency="Canada Dollar",
                holding_type="equity",
                row_type="security",
            )
        ],
    )
    db.flush()
    db.refresh(snapshot)

    assert snapshot.rows[0].currency == "CAD"


@pytest.mark.asyncio
async def test_reconcile_snapshot_constituents_ignores_placeholder_na_identifiers(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "test")

    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")
    wrong_match = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="SUGI",
        name="SUGIH ENERGY TBK PT",
        currency="IDR",
        is_active=True,
    )
    db.add(wrong_match)
    db.flush()
    await register_identifier(
        async_db,
        wrong_match,
        "etf_holdings_internal",
        IdentifierRecord(
            identifier_type="CUSIP",
            identifier_value="N/A",
            source="broken_legacy_snapshot",
        ),
    )
    db.flush()

    etf_instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="EEM",
        name="iShares MSCI Emerging Markets ETF",
    )

    snapshot = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf_instrument,
        source_provider="sec",
        provenance="sec_nport",
        composition_date=date(2026, 3, 31),
        rows=[
            CanonicalHoldingRow(
                symbol=None,
                name="Hong Kong Dollar",
                cusip="N/A",
                currency="HKD",
                market_value=Decimal("107.13"),
                shares=Decimal("840"),
                holding_type="equity",
                row_type="security",
            )
        ],
    )
    db.flush()
    db.refresh(snapshot)

    row = snapshot.rows[0]
    assert row.cusip is None
    assert row.constituent_instrument is not None
    assert row.constituent_instrument.symbol != "SUGI"
    assert row.constituent_instrument.name == "Hong Kong Dollar"


@pytest.mark.asyncio
async def test_reconcile_snapshot_constituents_repairs_existing_wrong_match_from_na_identifier(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "test")

    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")
    wrong_match = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="SUGI",
        name="SUGIH ENERGY TBK PT",
        currency="IDR",
        is_active=True,
    )
    db.add(wrong_match)
    db.flush()

    etf_instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="EEM",
        name="iShares MSCI Emerging Markets ETF",
    )
    snapshot = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf_instrument,
        source_provider="sec",
        provenance="sec_nport",
        composition_date=date(2026, 3, 31),
        rows=[
            CanonicalHoldingRow(
                symbol=None,
                name="Hong Kong Dollar",
                cusip=None,
                currency="HKD",
                market_value=Decimal("107.13"),
                shares=Decimal("840"),
                holding_type="equity",
                row_type="security",
            )
        ],
    )
    db.flush()
    db.refresh(snapshot)

    row = snapshot.rows[0]
    row.cusip = "N/A"
    row.constituent_instrument_id = wrong_match.id
    row.is_resolved = True
    row.resolution_confidence = Decimal("0.9500")
    row.resolution_note = "Matched by CUSIP."
    db.flush()

    snapshot = await reconcile_snapshot_constituents(async_db, snapshot)
    db.flush()
    db.refresh(snapshot)

    repaired = snapshot.rows[0]
    assert repaired.cusip is None
    assert repaired.constituent_instrument is not None
    assert repaired.constituent_instrument.symbol != "SUGI"
    assert repaired.constituent_instrument.name == "Hong Kong Dollar"


@pytest.mark.asyncio
async def test_resolver_ignores_incompatible_internal_identifier_aliases(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "test")

    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")
    wrong_match = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="SUGI",
        name="SUGIH ENERGY TBK PT",
        currency="IDR",
        is_active=True,
    )
    db.add(wrong_match)
    db.flush()
    await register_identifier(
        async_db,
        wrong_match,
        "etf_holdings_internal",
        IdentifierRecord(
            identifier_type="ISIN",
            identifier_value="CA82509L1076",
            source="broken_legacy_snapshot",
        ),
    )
    db.flush()

    instrument, confidence, _ = await _resolve_or_create_constituent(
        async_db,
        CanonicalHoldingRow(
            symbol=None,
            name="Shopify Inc.",
            isin="CA82509L1076",
            currency="CAD",
            holding_type="equity",
            row_type="security",
        ),
        source_provider="sec",
    )
    db.flush()

    assert instrument is not None
    assert instrument.symbol != "SUGI"
    assert instrument.name == "Shopify Inc."
    assert confidence == Decimal("0.5000")

    poisoned_identifier = db.execute(
        select(InstrumentIdentifier).where(
            InstrumentIdentifier.instrument_id == wrong_match.id,
            InstrumentIdentifier.identifier_type == InstrumentIdentifierType.ISIN,
            InstrumentIdentifier.identifier_value == "CA82509L1076",
        )
    ).scalar_one_or_none()
    assert poisoned_identifier is None or poisoned_identifier.is_active is False


@pytest.mark.asyncio
async def test_register_identifier_reassigns_internal_alias_conflicts(db):
    async_db = AsyncSessionAdapter(db)
    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")

    wrong_match = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="SUGI",
        name="SUGIH ENERGY TBK PT",
        currency="IDR",
        is_active=True,
    )
    corrected = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="SHOP",
        name="Shopify Inc.",
        currency="CAD",
        is_active=True,
    )
    db.add(wrong_match)
    db.add(corrected)
    db.flush()

    await register_identifier(
        async_db,
        wrong_match,
        "etf_holdings_internal",
        IdentifierRecord(
            identifier_type="ISIN",
            identifier_value="CA82509L1076",
            source="broken_legacy_snapshot",
        ),
    )
    db.flush()

    await register_identifier(
        async_db,
        corrected,
        "etf_holdings_internal",
        IdentifierRecord(
            identifier_type="ISIN",
            identifier_value="CA82509L1076",
            source="reconciled_snapshot",
        ),
    )
    db.flush()

    moved_identifier = db.execute(
        select(InstrumentIdentifier).where(
            InstrumentIdentifier.identifier_type == InstrumentIdentifierType.ISIN,
            InstrumentIdentifier.identifier_value == "CA82509L1076",
        )
    ).scalar_one()
    assert moved_identifier.instrument_id == corrected.id


@pytest.mark.asyncio
async def test_name_compatibility_does_not_treat_generic_indonesian_suffixes_as_a_match(db):
    async_db = AsyncSessionAdapter(db)
    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")

    wrong_match = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="SUGI",
        name="SUGIH ENERGY TBK PT",
        currency="IDR",
        is_active=True,
    )
    db.add(wrong_match)
    db.flush()

    row = ETFHolding(
        snapshot_id=1,
        constituent_instrument_id=wrong_match.id,
        position=1,
        reported_name="PT Bank Rakyat Indonesia (Persero) Tbk",
        isin="ID1000118201",
        source_row_hash="test-row",
        row_type="security",
        holding_type="equity",
        is_resolved=True,
    )
    row.constituent_instrument = wrong_match

    assert _holding_needs_reconcile(row) is True


@pytest.mark.asyncio
async def test_resolver_materializes_real_symbol_from_cusip_only_rows(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "development")
    monkeypatch.setattr(
        "app.services.etf_holdings.get_default_metadata_provider",
        lambda: FakeMetadataProvider(),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers",
        lambda: [FakeIdentifierProvider({})],
    )

    instrument, confidence, note = await _resolve_or_create_constituent(
        async_db,
        CanonicalHoldingRow(
            symbol=None,
            name="Texas Instruments Inc.",
            cusip="882508104",
            currency="USD",
            holding_type="equity",
            row_type="security",
        ),
        source_provider="invesco",
    )
    db.flush()

    assert instrument is not None
    assert instrument.symbol == "TXN"
    assert instrument.name == "Texas Instruments Incorporated"
    assert confidence == Decimal("0.9400")
    assert note == "Matched through stable identifier profile enrichment."


@pytest.mark.asyncio
async def test_resolver_promotes_existing_placeholder_when_identifier_profile_resolves(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "development")
    monkeypatch.setattr(
        "app.services.etf_holdings.get_default_metadata_provider",
        lambda: FakeMetadataProvider(),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers",
        lambda: [FakeIdentifierProvider({})],
    )

    instrument_type_id = await ensure_instrument_type(async_db, "Equity", "Stock")
    placeholder = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="HOLDING-ABC123",
        name="Texas Instruments Inc.",
        currency="USD",
        is_active=True,
    )
    db.add(placeholder)
    db.flush()
    await register_identifier(
        async_db,
        placeholder,
        "etf_holdings_internal",
        IdentifierRecord(
            identifier_type="CUSIP",
            identifier_value="882508104",
            source="invesco",
        ),
    )
    db.flush()

    resolved, confidence, note = await _resolve_or_create_constituent(
        async_db,
        CanonicalHoldingRow(
            symbol=None,
            name="Texas Instruments Inc.",
            cusip="882508104",
            currency="USD",
            holding_type="equity",
            row_type="security",
        ),
        source_provider="invesco",
    )
    db.flush()

    assert resolved is not None
    assert resolved.id == placeholder.id
    assert resolved.symbol == "TXN"
    assert resolved.name == "Texas Instruments Incorporated"
    assert confidence == Decimal("0.9400")
    assert note == "Matched through stable identifier profile enrichment."


@pytest.mark.asyncio
async def test_reingesting_same_snapshot_reconciles_existing_placeholder_rows(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "development")
    monkeypatch.setattr(
        "app.services.etf_holdings.get_default_metadata_provider",
        lambda: FakeMetadataProvider(),
    )

    instrument_type_id = await ensure_instrument_type(async_db, "ETF", "ETF")
    etf = Instrument(
        instrument_type_id=instrument_type_id,
        symbol="QQQ",
        name="Invesco QQQ Trust",
        currency="USD",
        is_active=True,
    )
    db.add(etf)
    db.flush()
    await ensure_etf_profile(async_db, etf, issuer="Invesco")

    rows = [
        CanonicalHoldingRow(
            symbol=None,
            name="Texas Instruments Inc.",
            cusip="882508104",
            currency="USD",
            weight=Decimal("0.10"),
            holding_type="equity",
            row_type="security",
        )
    ]

    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers",
        lambda: [],
    )
    first = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf,
        rows=rows,
        composition_date=date(2026, 6, 7),
        provenance="issuer_current_holdings",
        source_provider="invesco",
        source_url="https://example.test/qqq.json",
        parser_version="test-v1",
    )
    db.flush()
    original_holding = first.rows[0]
    assert original_holding.constituent_instrument is not None
    assert original_holding.constituent_instrument.symbol.startswith("HOLDING-")
    assert first.resolved_count == 1

    monkeypatch.setattr(
        "app.services.etf_holdings.get_identifier_providers",
        lambda: [FakeIdentifierProvider({})],
    )
    second = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf,
        rows=rows,
        composition_date=date(2026, 6, 7),
        provenance="issuer_current_holdings",
        source_provider="invesco",
        source_url="https://example.test/qqq.json",
        parser_version="test-v1",
    )
    db.flush()

    assert second.id == first.id
    refreshed = db.execute(
        select(Instrument).where(Instrument.id == original_holding.constituent_instrument_id)
    ).scalar_one()
    assert refreshed.symbol == "TXN"
    assert refreshed.name == "Texas Instruments Incorporated"


@pytest.mark.asyncio
async def test_classification_maintenance_is_bounded_per_profile(db, monkeypatch):
    """The worker-facing maintenance contract processes a latest snapshot with a hard cap."""

    async_db = AsyncSessionAdapter(db)
    etf = await ensure_lightweight_etf_instrument(
        async_db, symbol="XLK", name="Technology Select Sector SPDR"
    )
    await ensure_etf_profile(async_db, etf, issuer="State Street")
    snapshot = await ingest_holdings_snapshot(
        async_db,
        etf_instrument=etf,
        rows=[
            CanonicalHoldingRow(
                symbol="MAINTTEST",
                name="Maintenance Test Security",
                weight=Decimal("0.10"),
                holding_type="equity",
                row_type="security",
            )
        ],
        composition_date=date(2026, 8, 12),
        provenance="issuer_current_holdings",
        source_provider="spdr",
    )
    db.flush()

    calls = []

    async def fake_reconcile(db_arg, snapshot_arg, *, max_classification_enrichment):
        calls.append((db_arg, snapshot_arg.id, max_classification_enrichment))
        return snapshot_arg

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.reconcile_snapshot_constituents",
        fake_reconcile,
    )

    summary = await reconcile_all_etf_holdings_classifications(
        async_db,
        max_profiles=1,
        max_enrichments_per_profile=7,
    )

    assert summary["profiles"] == 1
    assert summary["processed"] == 1
    assert summary["max_enrichments_per_profile"] == 7
    assert calls == [(async_db, snapshot.id, 7)]
