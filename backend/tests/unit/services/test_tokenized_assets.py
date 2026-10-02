from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.market_data_foundation import (
    Issuer,
    MarketEvent,
    MarketSeries,
    MarketSeriesDefault,
    ProviderPaginationState,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import (
    InstrumentDatasetState,
    LatestPriceSnapshot,
    MarketBarObservation,
)
from app.models.provider_runtime import ProviderCapability
from app.models.tokenized_asset import TokenizedAssetDetail, TokenizedAssetObservation
from app.providers.base import TokenizedAssetRecord
from app.providers.errors import ProviderNotConfiguredError
from app.services import tokenized_assets
from app.services.tokenized_assets import (
    refresh_tokenized_assets,
    refresh_tokenized_events,
    refresh_tokenized_historical_prices,
    refresh_tokenized_prices,
    upsert_tokenized_asset,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_dinari_sandbox_asset_cannot_enter_canonical_persistence(db):
    record = TokenizedAssetRecord(
        provider="dinari",
        asset_id="sandbox-stock-uuid",
        symbol="dAAPL",
        name="Sandbox Apple dShare",
        raw_payload={"id": "sandbox-stock-uuid"},
    )

    with pytest.raises(ProviderNotConfiguredError, match="canary-only"):
        await upsert_tokenized_asset(AsyncSessionAdapter(db), record)

    assert db.query(TokenizedAssetDetail).count() == 0
    assert db.query(Instrument).filter(Instrument.domain_key.startswith("tokenized:dinari:")).count() == 0


@pytest.mark.asyncio
async def test_upsert_keeps_token_distinct_and_links_unambiguous_underlying(db, instrument):
    instrument.isin = "US0378331005"
    db.flush()
    record = TokenizedAssetRecord(
        provider="xstocks",
        asset_id="x:AAPL",
        symbol="xAAPL",
        name="Apple xStock",
        underlying_symbol=instrument.symbol,
        underlying_isin="US0378331005",
        network="solana",
        chain_id=101,
        contract_address="So111",
        price=Decimal("100.25"),
        multiplier=Decimal("0.98"),
        collateral={"deployments": [{"network": "solana", "address": "So111"}]},
        observed_at=datetime.now(UTC),
        raw_payload={"id": "x:AAPL"},
    )

    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    assert token.id != instrument.id
    assert token.domain_key == "tokenized:xstocks:" + token.domain_key.rsplit(":", 1)[1]
    await upsert_tokenized_asset(AsyncSessionAdapter(db), record)

    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()
    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_isin"
    assert detail.multiplier == Decimal("0.98")
    assert detail.deployments[0]["address"] == "So111"

    snapshot = db.execute(
        select(LatestPriceSnapshot)
        .where(LatestPriceSnapshot.instrument_id == token.id)
        .order_by(LatestPriceSnapshot.id)
    ).scalars().first()
    assert snapshot is not None
    assert snapshot.price == Decimal("100.25")
    observations = db.execute(
        select(TokenizedAssetObservation)
        .where(TokenizedAssetObservation.instrument_id == token.id)
        .order_by(TokenizedAssetObservation.id)
    ).scalars().all()
    assert len(observations) == 2
    assert observations[0].payload == {"id": "x:AAPL"}
    assert observations[1].payload == {"id": "x:AAPL"}


@pytest.mark.asyncio
async def test_upsert_retains_underlying_cik_and_links_existing_issuer_without_conflating_token(
    db, instrument
):
    issuer = Issuer(
        domain_key="cik:0000320193",
        legal_name="Apple Inc.",
        cik="0000320193",
        country_code="US",
    )
    db.add(issuer)
    db.flush()
    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="dinari-aapl-cik",
        symbol="dAAPL",
        name="Apple dShare",
        underlying_symbol=instrument.symbol,
        underlying_cik="320193",
        raw_payload={"cik": "320193"},
    )

    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)

    assert token.id != instrument.id
    assert token.issuer_id is None
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()
    assert detail.underlying_cik == "0000320193"
    assert detail.underlying_issuer_id == issuer.id
    assert detail.provenance["underlying_issuer_link_status"] == "linked_by_cik"


@pytest.mark.asyncio
async def test_upsert_does_not_guess_ambiguous_underlying(db, instrument_type, instrument):
    duplicate = Instrument(
        symbol="AAPL",
        name="Apple duplicate listing",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(duplicate)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPL",
        name="Apple Stock Token",
        underlying_symbol="AAPL",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()
    assert detail.underlying_instrument_id is None
    assert detail.provenance["underlying_link_status"] == "unresolved_or_ambiguous"


@pytest.mark.asyncio
async def test_upsert_prefers_underlying_isin_over_duplicate_ticker(db, instrument_type, instrument):
    instrument.isin = "US0378331005"
    duplicate = Instrument(
        symbol="AAPL",
        name="Apple duplicate listing",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(duplicate)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="d-aapl",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_isin="US0378331005",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_isin"


@pytest.mark.asyncio
async def test_upsert_links_underlying_by_figi_before_ticker(db, instrument_type, instrument):
    instrument.domain_key = "figi:BBG000B9XRY4"
    duplicate = Instrument(
        symbol="AAPL",
        name="Apple duplicate listing",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(duplicate)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="d-aapl-figi",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_figi=" bbg000b9xry4 ",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_figi"
    assert detail.underlying_figi == "BBG000B9XRY4"


@pytest.mark.asyncio
async def test_upsert_links_underlying_by_composite_figi_identifier(db, instrument, instrument_type):
    identifier = InstrumentIdentifier(
        instrument_id=instrument.id,
        identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI,
        identifier_value="BBG000B9XRY4",
        is_active=True,
    )
    db.add(identifier)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="d-aapl-composite-figi",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_composite_figi="BBG000B9XRY4",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_composite_figi"
    assert detail.underlying_composite_figi == "BBG000B9XRY4"


@pytest.mark.asyncio
async def test_upsert_links_underlying_by_cusip_identifier(db, instrument, instrument_type):
    identifier = InstrumentIdentifier(
        instrument_id=instrument.id,
        identifier_type=InstrumentIdentifierType.CUSIP,
        identifier_value="037833100",
        is_active=True,
    )
    db.add(identifier)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="d-aapl-cusip",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_cusip="037833100",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_cusip"
    assert detail.underlying_cusip == "037833100"


@pytest.mark.asyncio
async def test_upsert_refuses_conflicting_stable_underlying_identifiers(
    db, instrument_type, instrument
):
    instrument.domain_key = "figi:BBG000B9XRY4"
    conflicting = Instrument(
        symbol="AAPL",
        name="Apple conflicting identity",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
        domain_key="isin:US0378331005",
    )
    db.add(conflicting)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="d-aapl-conflict",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_figi="BBG000B9XRY4",
        underlying_isin="US0378331005",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id is None
    assert detail.provenance["underlying_link_status"] == "unresolved_or_ambiguous_figi"


@pytest.mark.asyncio
async def test_upsert_resolves_underlying_isin_from_canonical_identifier(db, instrument, instrument_type):
    identifier = InstrumentIdentifier(
        instrument_id=instrument.id,
        identifier_type=InstrumentIdentifierType.ISIN,
        identifier_value="US0378331005",
        is_active=True,
    )
    db.add(identifier)
    db.flush()

    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="d-aapl-identifier",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_isin="US0378331005",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id == instrument.id
    assert detail.provenance["underlying_link_status"] == "linked_by_isin"


@pytest.mark.asyncio
async def test_upsert_does_not_fallback_to_ticker_when_underlying_isin_unresolved(db, instrument):
    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="d-aapl-unresolved",
        symbol="dAAPL",
        name="Apple Token",
        underlying_symbol="AAPL",
        underlying_isin="US0000000000",
        raw_payload={},
    )
    token = await upsert_tokenized_asset(AsyncSessionAdapter(db), record)
    detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == token.id)
    ).scalar_one()

    assert detail.underlying_instrument_id is None
    assert detail.provenance["underlying_link_status"] == "unresolved_or_ambiguous_isin"


@pytest.mark.asyncio
async def test_refresh_tokenized_prices_routes_by_provider_asset_id_and_persists_quote(
    db, instrument, monkeypatch
):
    initial = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPLx",
        name="Apple Stock Token",
        underlying_symbol=instrument.symbol,
        raw_payload={"id": "rh-aapl"},
    )
    await upsert_tokenized_asset(AsyncSessionAdapter(db), initial)
    calls = []

    async def fake_execute(_db, _capability, operation, **kwargs):
        calls.append((operation, kwargs["provider_name"], kwargs["provider_symbol"], kwargs["usage_identity"]))
        return SimpleNamespace(
            provider_name="robinhood_tokens",
            result=TokenizedAssetRecord(
                provider="robinhood_tokens",
                asset_id="rh-aapl",
                symbol="AAPLx",
                name="Apple Stock Token",
                price=Decimal("123.45"),
                bid=Decimal("123.40"),
                ask=Decimal("123.50"),
                underlying_symbol=instrument.symbol,
                observed_at=datetime.now(UTC),
                raw_payload={"quote": {"bid": "123.40", "ask": "123.50"}},
            ),
        )

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=10)

    assert result["status"] == "refreshed"
    assert result["requested"] == 1
    assert result["refreshed"] == 1
    assert result["failed"] == 0
    assert calls == [("get_tokenized_price", "robinhood_tokens", "rh-aapl", "rh-aapl")]
    token_detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.provider_asset_id == "rh-aapl")
    ).scalar_one()
    snapshot = db.execute(
        select(LatestPriceSnapshot).where(
            LatestPriceSnapshot.instrument_id == token_detail.instrument_id
        )
    ).scalar_one()
    # The token has a distinct instrument ID from the underlying; locate the
    # quote through the token's provider symbol rather than the economic ticker.
    assert snapshot.provider_symbol == "AAPLx"
    assert snapshot.price == Decimal("123.45")


@pytest.mark.asyncio
async def test_refresh_tokenized_prices_rotates_past_repeated_asset_failure(
    db, instrument, monkeypatch
):
    for asset_id in ("rh-failing", "rh-next"):
        await upsert_tokenized_asset(
            AsyncSessionAdapter(db),
            TokenizedAssetRecord(
                provider="robinhood_tokens",
                asset_id=asset_id,
                symbol=asset_id,
                name=asset_id,
                underlying_symbol=instrument.symbol,
                raw_payload={"id": asset_id},
            ),
        )
    calls: list[str] = []

    async def fake_execute(_db, _capability, _operation, **kwargs):
        identifier = kwargs["provider_symbol"]
        calls.append(identifier)
        if identifier == "rh-failing":
            raise RuntimeError("temporary provider failure")
        return SimpleNamespace(
            provider_name="robinhood_tokens",
            result=TokenizedAssetRecord(
                provider="robinhood_tokens",
                asset_id=identifier,
                symbol=identifier,
                name=identifier,
                price=Decimal("100.00"),
                underlying_symbol=instrument.symbol,
                observed_at=datetime.now(UTC),
                raw_payload={"id": identifier},
            ),
        )

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    first = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=1)
    second = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=1)

    assert first["status"] == "failed"
    assert first["requested"] == 1
    assert second["status"] == "refreshed"
    assert second["requested"] == 1
    assert calls == ["rh-failing", "rh-next"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timespan", "expected_timeframe"),
    [
        ("DAY", Timeframe.D1),
        ("WEEK", Timeframe.W1),
        ("MONTH", Timeframe.MN),
        ("YEAR", Timeframe.Y1),
    ],
)
async def test_refresh_tokenized_historical_prices_normalizes_raw_247_bars(
    db, instrument, monkeypatch, timespan, expected_timeframe
):
    await upsert_tokenized_asset(
        AsyncSessionAdapter(db),
        TokenizedAssetRecord(
            provider="robinhood_tokens",
            asset_id="dinari-aapl-history",
            symbol="dAAPL",
            name="Apple dShare",
            underlying_symbol=instrument.symbol,
            raw_payload={},
        ),
    )
    provider = SimpleNamespace(
        fetch_tokenized_historical_prices=lambda identifier, **kwargs: [
            {
                "timestamp": datetime(2026, 9, 1, tzinfo=UTC),
                "open": Decimal("100"),
                "high": Decimal("105"),
                "low": Decimal("99"),
                "close": Decimal("104"),
                "raw_payload": {"stock_id": identifier},
            }
        ]
    )
    source = SimpleNamespace(id=77)
    persisted: list[OHLCVBar] = []

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="robinhood_tokens", provider=provider)]

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.TOKENIZED_HISTORICAL_PRICES
        assert operation == "fetch_tokenized_historical_prices"
        assert kwargs["provider_name"] == "robinhood_tokens"
        assert kwargs["provider_symbol"] == "dinari-aapl-history"
        result = kwargs["invoke"](provider, kwargs["provider_symbol"])
        return SimpleNamespace(provider_name="robinhood_tokens", data_source=source, result=result)

    async def fake_attach(_db, _instrument, timeframe, adjusted, execution, *, bars):
        assert timeframe is expected_timeframe
        assert adjusted is False
        assert execution.data_source is source
        return bars

    async def fake_persist(_db, _instrument, **kwargs):
        assert kwargs["data_source_id"] == 77
        assert kwargs["provider_symbol"] == "dinari-aapl-history"
        assert kwargs["timeframe"] is expected_timeframe
        assert kwargs["adjusted"] is False
        persisted.extend(kwargs["bars"])

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    monkeypatch.setattr(tokenized_assets, "_attach_provider_series", fake_attach)
    monkeypatch.setattr(tokenized_assets, "persist_price_history_bars", fake_persist)

    result = await refresh_tokenized_historical_prices(
        AsyncSessionAdapter(db), max_assets=10, timespan=timespan
    )

    assert result["status"] == "refreshed", result
    assert result["requested"] == 1
    assert result["refreshed"] == 1
    assert result["failed"] == 0
    assert result["history"][0]["provider_asset_id"] == "dinari-aapl-history"
    assert len(persisted) == 1
    assert persisted[0].timeframe is expected_timeframe
    assert persisted[0].session == "24_7"
    assert persisted[0].is_adjusted is False
    assert persisted[0].volume is None
    assert persisted[0].vwap is None
    assert persisted[0].provenance["feed"] == "tokenized_aggregate_history"


@pytest.mark.asyncio
async def test_refresh_tokenized_historical_prices_persists_scoped_series_and_observations(
    db, instrument, monkeypatch
):
    """The tokenized path must exercise the canonical persistence boundary.

    This deliberately leaves ``_attach_provider_series`` and
    ``persist_price_history_bars`` intact.  The provider call is still a
    deterministic fixture, but the resulting bar, observation, dataset state,
    and compatibility default are written through the same path used in a
    credentialed refresh.
    """

    await upsert_tokenized_asset(
        AsyncSessionAdapter(db),
        TokenizedAssetRecord(
            provider="robinhood_tokens",
            asset_id="dinari-aapl-persisted",
            symbol="dAAPL",
            name="Apple dShare",
            underlying_symbol=instrument.symbol,
            raw_payload={},
        ),
    )
    source = DataSource(
        name="dinari-tokenized-history-test",
        base_url="https://sandbox.dinari.com",
        is_active=True,
    )
    db.add(source)
    db.flush()
    provider = SimpleNamespace(
        fetch_tokenized_historical_prices=lambda identifier, **kwargs: [
            {
                "timestamp": datetime(2026, 9, 2, tzinfo=UTC),
                "open": "100.00",
                "high": "105.00",
                "low": "99.00",
                "close": "104.00",
                "raw_payload": {"stock_id": identifier},
            }
        ]
    )

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="robinhood_tokens", provider=provider)]

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.TOKENIZED_HISTORICAL_PRICES
        assert operation == "fetch_tokenized_historical_prices"
        result = kwargs["invoke"](provider, kwargs["provider_symbol"])
        return SimpleNamespace(
            provider_name="robinhood_tokens", data_source=source, result=result
        )

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    result = await refresh_tokenized_historical_prices(
        AsyncSessionAdapter(db), max_assets=10, timespan="DAY"
    )

    assert result["status"] == "refreshed", result
    detail = db.execute(
        select(TokenizedAssetDetail).where(
            TokenizedAssetDetail.provider_asset_id == "dinari-aapl-persisted"
        )
    ).scalar_one()
    bar = db.execute(
        select(OHLCVBar).where(OHLCVBar.instrument_id == detail.instrument_id)
    ).scalar_one()
    assert bar.data_source_id == source.id
    assert bar.market_series_id is not None
    assert bar.session == "24_7"
    assert bar.is_adjusted is False
    assert bar.volume is None
    assert bar.vwap is None
    assert bar.provenance["feed"] == "tokenized_aggregate_history"

    series = db.get(MarketSeries, bar.market_series_id)
    assert series is not None
    assert series.feed_scope == "tokenized_aggregate_history"
    assert series.session_code == "24_7"
    assert series.timeframe == Timeframe.D1.value
    assert series.is_canonical is True

    default = db.execute(
        select(MarketSeriesDefault).where(
            MarketSeriesDefault.instrument_id == detail.instrument_id,
            MarketSeriesDefault.timeframe == Timeframe.D1.value,
            MarketSeriesDefault.is_adjusted.is_(False),
        )
    ).scalar_one()
    assert default.market_series_id == bar.market_series_id

    observation = db.execute(
        select(MarketBarObservation).where(
            MarketBarObservation.instrument_id == detail.instrument_id
        )
    ).scalar_one()
    assert observation.data_source_id == source.id
    assert observation.market_series_id == bar.market_series_id
    assert observation.provider_symbol == "dinari-aapl-persisted"
    assert observation.session == "24_7"
    assert observation.source_payload["feed"] == "tokenized_aggregate_history"

    dataset = db.execute(
        select(InstrumentDatasetState).where(
            InstrumentDatasetState.instrument_id == detail.instrument_id,
            InstrumentDatasetState.data_source_id == source.id,
            InstrumentDatasetState.dataset_type == "ohlcv",
            InstrumentDatasetState.dataset_key == "D1:raw",
        )
    ).scalar_one()
    assert dataset.status.value == "fresh"
    assert dataset.coverage_start == bar.ts
    assert dataset.coverage_end == bar.ts
    assert dataset.extra_data == {"bar_count": 1, "adjusted": False}


@pytest.mark.asyncio
async def test_refresh_tokenized_historical_prices_accepts_year_timespan(db):
    result = await refresh_tokenized_historical_prices(
        AsyncSessionAdapter(db), timespan="YEAR"
    )

    assert result["status"] == "no_assets"
    assert result["timespan"] == "YEAR"


@pytest.mark.asyncio
async def test_refresh_tokenized_assets_reports_full_page_as_partial(
    db, monkeypatch
):
    provider = SimpleNamespace(name="robinhood_tokens")
    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="dinari-aapl",
        symbol="dAAPL",
        name="Apple dShare",
        raw_payload={},
    )

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="robinhood_tokens", provider=provider)]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        return SimpleNamespace(provider_name="robinhood_tokens", result=[record])

    async def fake_upsert(_db, _record):
        return None

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    monkeypatch.setattr(tokenized_assets, "upsert_tokenized_asset", fake_upsert)

    result = await refresh_tokenized_assets(
        AsyncSessionAdapter(db), max_pages=1, page_size=1
    )

    assert result == {
        "status": "partial",
        "providers": [
            {
                "provider": "robinhood_tokens",
                "assets": 1,
                "pages_fetched": 1,
                "truncated": True,
                "complete": False,
            }
        ],
        "assets": 1,
        "truncated": True,
        "complete": False,
        "failed": 0,
        "failures": [],
    }


@pytest.mark.asyncio
async def test_refresh_tokenized_assets_resumes_page_after_fairness_budget(
    db, monkeypatch
):
    calls: list[int] = []
    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPLx",
        name="Apple Stock Token",
        raw_payload={"page": 0},
    )

    class Provider:
        name = "robinhood_tokens"

        def discover_tokenized_assets(self, *, page: int = 0, page_size: int = 100):
            calls.append(page)
            if page < 2:
                return [record]
            return []

    provider = Provider()

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name=provider.name, provider=provider)]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_upsert(_db, _record):
        return None

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    monkeypatch.setattr(tokenized_assets, "upsert_tokenized_asset", fake_upsert)

    first = await refresh_tokenized_assets(AsyncSessionAdapter(db), max_pages=1, page_size=1)
    second = await refresh_tokenized_assets(AsyncSessionAdapter(db), max_pages=1, page_size=1)
    third = await refresh_tokenized_assets(AsyncSessionAdapter(db), max_pages=1, page_size=1)

    assert calls == [0, 1, 2]
    assert first["status"] == "partial" and first["providers"][0]["pages_fetched"] == 1
    assert second["status"] == "partial" and second["providers"][0]["pages_fetched"] == 1
    assert third["status"] == "refreshed" and third["complete"] is True
    state = db.execute(
        select(ProviderPaginationState).where(
            ProviderPaginationState.state_key == "tokenized-assets:robinhood_tokens:1"
        )
    ).scalar_one()
    assert state.status == "complete"
    assert state.page_number == 0
    assert state.cursor is None


@pytest.mark.asyncio
async def test_refresh_tokenized_assets_resumes_opaque_cursor_page(
    db, monkeypatch
):
    calls: list[str | None] = []
    record = TokenizedAssetRecord(
        provider="bybit_xstocks",
        asset_id="AAPLx",
        symbol="AAPLx",
        name="Apple xStock",
        raw_payload={},
    )

    class Provider:
        name = "bybit_xstocks"

        def discover_tokenized_assets(self, **_kwargs):
            raise AssertionError("opaque-cursor provider must use its cursor method")

        def discover_tokenized_page(self, *, cursor=None, page_size=100):
            calls.append(cursor)
            return ([record], "cursor-2") if cursor is None else ([record], None)

    provider = Provider()

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name=provider.name, provider=provider)]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_upsert(_db, _record):
        return None

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    monkeypatch.setattr(tokenized_assets, "upsert_tokenized_asset", fake_upsert)

    first = await refresh_tokenized_assets(AsyncSessionAdapter(db), max_pages=1, page_size=1)
    second = await refresh_tokenized_assets(AsyncSessionAdapter(db), max_pages=1, page_size=1)

    assert calls == [None, "cursor-2"]
    assert first["truncated"] is True
    assert second["complete"] is True
    state = db.execute(
        select(ProviderPaginationState).where(
            ProviderPaginationState.state_key == "tokenized-assets:bybit_xstocks:1"
        )
    ).scalar_one()
    assert state.status == "complete"
    assert state.cursor is None
    assert len(state.cursor_history) == 1


@pytest.mark.asyncio
async def test_refresh_tokenized_assets_marks_short_page_complete(
    db, monkeypatch
):
    provider = SimpleNamespace(name="robinhood_tokens")
    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="dinari-aapl",
        symbol="dAAPL",
        name="Apple dShare",
        raw_payload={},
    )

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="robinhood_tokens", provider=provider)]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        return SimpleNamespace(provider_name="robinhood_tokens", result=[record])

    async def fake_upsert(_db, _record):
        return None

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    monkeypatch.setattr(tokenized_assets, "upsert_tokenized_asset", fake_upsert)

    result = await refresh_tokenized_assets(
        AsyncSessionAdapter(db), max_pages=3, page_size=2
    )

    assert result["status"] == "refreshed"
    assert result["truncated"] is False
    assert result["complete"] is True
    assert result["providers"] == [
        {
            "provider": "robinhood_tokens",
            "assets": 1,
            "pages_fetched": 1,
            "truncated": False,
            "complete": True,
        }
    ]
    assert result["failed"] == 0
    assert result["failures"] == []


@pytest.mark.asyncio
async def test_refresh_tokenized_assets_keeps_provider_failure_and_continues(
    db, monkeypatch
):
    first_provider = SimpleNamespace(name="test-unavailable-provider")
    second_provider = SimpleNamespace(name="robinhood_tokens")
    record = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPLx",
        name="Apple Stock Token",
        raw_payload={},
    )

    async def fake_chain(*_args, **_kwargs):
        return [
            SimpleNamespace(provider_name="test-unavailable-provider", provider=first_provider),
            SimpleNamespace(provider_name="robinhood_tokens", provider=second_provider),
        ]

    async def fake_execute(_db, _capability, operation, **_kwargs):
        if operation.endswith(":0") and _kwargs.get("provider_name") == "test-unavailable-provider":
            raise RuntimeError("provider unavailable https://api.example.test/?api_key=super-secret")
        return SimpleNamespace(provider_name="robinhood_tokens", result=[record])

    async def fake_upsert(_db, _record):
        return None

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    monkeypatch.setattr(tokenized_assets, "upsert_tokenized_asset", fake_upsert)

    result = await refresh_tokenized_assets(
        AsyncSessionAdapter(db), max_pages=1, page_size=2
    )

    assert result["status"] == "partial"
    assert result["assets"] == 1
    assert result["failed"] == 1
    assert result["failures"][0]["provider"] == "test-unavailable-provider"
    assert result["failures"][0]["page"] == 0
    assert "super-secret" not in result["failures"][0]["error"]
    assert result["providers"][-1]["provider"] == "robinhood_tokens"


@pytest.mark.asyncio
async def test_refresh_tokenized_assets_reports_all_provider_failures(db, monkeypatch):
    provider = SimpleNamespace(name="robinhood_tokens")

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="robinhood_tokens", provider=provider)]

    async def fake_execute(*_args, **_kwargs):
        raise RuntimeError("tokenized provider unavailable")

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    result = await refresh_tokenized_assets(AsyncSessionAdapter(db), max_pages=1, page_size=2)

    assert result["status"] == "failed"
    assert result["assets"] == 0
    assert result["failed"] == 1
    assert result["complete"] is False


@pytest.mark.asyncio
async def test_refresh_tokenized_assets_clamps_catalog_request_bounds(db, monkeypatch):
    provider = SimpleNamespace(name="robinhood_tokens")
    requested: list[tuple[int, int]] = []

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="robinhood_tokens", provider=provider)]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        result = kwargs["invoke"](provider, None)
        if hasattr(result, "__await__"):
            result = await result
        return SimpleNamespace(provider_name="robinhood_tokens", result=[])

    def discover(*, page: int, page_size: int):
        requested.append((page, page_size))
        return []

    provider.discover_tokenized_assets = discover
    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    result = await refresh_tokenized_assets(
        AsyncSessionAdapter(db), max_pages=5000, page_size=5000
    )

    assert result["status"] == "refreshed"
    assert requested == [(0, 1000)]


@pytest.mark.asyncio
async def test_refresh_tokenized_prices_keeps_per_asset_failure_evidence(db, instrument, monkeypatch):
    initial = TokenizedAssetRecord(
        provider="robinhood_tokens",
        asset_id="rh-aapl",
        symbol="AAPLx",
        name="Apple Stock Token",
        raw_payload={},
    )
    await upsert_tokenized_asset(AsyncSessionAdapter(db), initial)

    async def fake_execute(*_args, **_kwargs):
        raise RuntimeError("provider unavailable https://api.example.test/?api_key=super-secret")

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=10)

    assert result["status"] == "failed"
    assert result["requested"] == 1
    assert result["refreshed"] == 0
    assert result["failed"] == 1
    assert result["failures"][0]["provider_asset_id"] == "rh-aapl"
    assert "super-secret" not in result["failures"][0]["error"]
    assert len(result["failures"][0]["error"]) <= 500


@pytest.mark.asyncio
async def test_refresh_tokenized_events_redacts_provider_failure_evidence(db, monkeypatch):
    provider = SimpleNamespace(
        name="xstocks", fetch_tokenized_corporate_actions=lambda **_kwargs: []
    )

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="xstocks", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    async def fake_execute(*_args, **_kwargs):
        raise RuntimeError("provider unavailable Authorization: Bearer event-secret")

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_events(AsyncSessionAdapter(db))

    assert result["status"] == "failed"
    assert result["failed"] == 2  # xStocks history and upcoming phases
    assert result["failures"]
    assert all("event-secret" not in item["error"] for item in result["failures"])
    assert all(len(item["error"]) <= 500 for item in result["failures"])


@pytest.mark.asyncio
async def test_refresh_tokenized_events_persists_and_links_explicit_action_identity(
    db, instrument, monkeypatch
):
    initial = TokenizedAssetRecord(
        provider="xstocks",
        asset_id="x:AAPL",
        symbol="xAAPL",
        name="Apple xStock",
        underlying_symbol=instrument.symbol,
        raw_payload={},
    )
    await upsert_tokenized_asset(AsyncSessionAdapter(db), initial)
    provider = SimpleNamespace(
        name="xstocks", fetch_tokenized_corporate_actions=lambda **_kwargs: []
    )
    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="xstocks", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.TOKENIZED_CORPORATE_ACTIONS
        assert operation == "fetch_tokenized_corporate_actions"
        assert kwargs["provider_name"] == "xstocks"
        return SimpleNamespace(
            provider_name="xstocks",
            result=[
                {
                    "id": "ca-1",
                    "assetId": "x:AAPL",
                    "actionType": "dividend",
                    "effectiveDate": "2026-09-11",
                    "announcedAt": "2026-09-10T10:15:00Z",
                    "amount": "0.25",
                },
                {"id": "malformed-but-valid", "symbol": "unlisted"},
            ],
        )

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_providers=2, page_size=25, include_upcoming=False
    )

    assert result["status"] == "refreshed"
    assert result["events"] == 2
    assert result["linked"] == 1
    assert result["unlinked"] == 1
    assert result["failed"] == 0
    events = db.execute(select(MarketEvent).order_by(MarketEvent.id)).scalars().all()
    assert len(events) == 2
    token_detail = db.execute(
        select(TokenizedAssetDetail).where(TokenizedAssetDetail.provider_asset_id == "x:AAPL")
    ).scalar_one()
    assert events[0].instrument_id == token_detail.instrument_id
    assert events[0].effective_date.isoformat() == "2026-09-11"
    assert events[0].announced_at.isoformat().startswith("2026-09-10T10:15:00")
    assert events[0].payload["raw"]["actionType"] == "dividend"
    assert events[1].instrument_id is None


@pytest.mark.asyncio
async def test_refresh_tokenized_events_fails_closed_on_non_object_page_row(
    db, instrument, monkeypatch
):
    provider = SimpleNamespace(
        name="xstocks", fetch_tokenized_corporate_actions=lambda **_kwargs: []
    )

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="xstocks", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    async def fake_execute(_db, _capability, _operation, **_kwargs):
        return SimpleNamespace(
            provider_name="xstocks",
            result=[
                {
                    "id": "valid-but-uncommitted",
                    "effectiveDate": "2026-09-11",
                },
                "malformed-provider-row",
            ],
        )

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_providers=1, page_size=25, include_upcoming=False
    )

    assert result["status"] == "failed"
    assert result["events"] == 0
    assert result["failed"] == 1
    assert "non-object row" in result["failures"][0]["error"]
    assert db.execute(select(MarketEvent)).scalars().all() == []
    state = db.execute(
        select(ProviderPaginationState).where(
            ProviderPaginationState.state_key == "tokenized-events:xstocks:history:25"
        )
    ).scalar_one()
    assert state.status == "failed"
    assert state.page_number == 1
    assert state.cursor is None


@pytest.mark.asyncio
async def test_refresh_tokenized_events_runs_bounded_global_split_feed(
    db, instrument, monkeypatch
):
    await upsert_tokenized_asset(
        AsyncSessionAdapter(db),
        TokenizedAssetRecord(
            provider="robinhood_tokens",
            asset_id="dinari-stock",
            symbol="dAAPL",
            name="Apple dShare",
            underlying_symbol=instrument.symbol,
            raw_payload={},
        ),
    )
    calls = []
    action_kwargs = []

    def fetch_actions(**kwargs):
        action_kwargs.append(kwargs)
        return [
            {
                "stock_id": "dinari-stock",
                "action_type": "split",
                "effective_date": "2026-09-11",
            }
        ]

    provider = SimpleNamespace(name="robinhood_tokens", fetch_tokenized_corporate_actions=fetch_actions)

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="robinhood_tokens", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    async def fake_execute(_db, capability, operation, **kwargs):
        calls.append((capability, operation, kwargs["provider_name"]))
        result = kwargs["invoke"](provider, None)
        return SimpleNamespace(provider_name="robinhood_tokens", result=result)

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)
    result = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_providers=1, page_size=25, include_upcoming=True
    )

    assert result["status"] == "refreshed"
    assert result["events"] == 1
    assert result["linked"] == 1
    assert result["unlinked"] == 0
    assert result["failed"] == 0
    assert calls == [
        (
            ProviderCapability.TOKENIZED_CORPORATE_ACTIONS,
            "fetch_tokenized_corporate_actions",
            "robinhood_tokens",
        )
    ]
    # The scheduler uses the selected provider's bounded global split feed and
    # never guesses an unsupported upcoming filter.
    assert action_kwargs == [{}]


@pytest.mark.asyncio
async def test_refresh_tokenized_events_rotates_providers_across_fairness_budget(
    db, monkeypatch
):
    calls: list[str] = []
    providers = {
        name: SimpleNamespace(
            name=name,
            fetch_tokenized_corporate_actions=lambda _name=name: [
                {"id": f"{_name}-event", "effectiveDate": "2026-09-11"}
            ],
        )
        for name in ("alpha_tokens", "beta_tokens")
    }
    chain = [
        SimpleNamespace(provider_name=name, provider=provider)
        for name, provider in providers.items()
    ]

    async def fake_chain(*_args, **_kwargs):
        return chain

    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider_name = kwargs["provider_name"]
        calls.append(provider_name)
        return SimpleNamespace(
            provider_name=provider_name,
            result=kwargs["invoke"](providers[provider_name], None),
        )

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    first = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_providers=1, include_upcoming=False
    )
    second = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_providers=1, include_upcoming=False
    )

    assert first["status"] == "refreshed"
    assert second["status"] == "refreshed"
    assert calls == ["alpha_tokens", "beta_tokens"]


@pytest.mark.asyncio
async def test_refresh_tokenized_events_resumes_numeric_pages_after_fairness_budget(
    db, monkeypatch
):
    calls = []
    pages = {
        1: [{"id": "page-1", "effectiveDate": "2026-09-11"}],
        2: [{"id": "page-2", "effectiveDate": "2026-09-12"}],
        3: [],
    }
    provider = SimpleNamespace(
        name="xstocks",
        fetch_tokenized_corporate_actions=lambda **kwargs: (
            calls.append(dict(kwargs)) or pages[kwargs["page"]]
        ),
    )

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="xstocks", provider=provider)]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        result = kwargs["invoke"](provider, None)
        return SimpleNamespace(provider_name="xstocks", result=result)

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    first = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_pages=1, page_size=1, include_upcoming=False
    )
    second = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_pages=1, page_size=1, include_upcoming=False
    )
    third = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_pages=1, page_size=1, include_upcoming=False
    )

    assert first["status"] == "partial"
    assert second["status"] == "partial"
    assert third["status"] == "no_events"
    assert calls == [
        {"upcoming": False, "page": 1, "page_size": 1},
        {"upcoming": False, "page": 2, "page_size": 1},
        {"upcoming": False, "page": 3, "page_size": 1},
    ]
    state = db.execute(
        select(ProviderPaginationState).where(
            ProviderPaginationState.state_key == "tokenized-events:xstocks:history:1"
        )
    ).scalar_one()
    assert state.status == "complete"
    assert state.page_number == 1
    assert state.cursor is None


@pytest.mark.asyncio
async def test_refresh_tokenized_events_resumes_opaque_cursor_across_provider_instances(
    db, monkeypatch
):
    calls = []
    provider_rows = {
        None: ([{"id": "dinari-page-1", "effectiveDate": "2026-09-11"}], "cursor-1"),
        "cursor-1": ([{"id": "dinari-page-2", "effectiveDate": "2026-09-12"}], None),
    }

    def make_provider():
        def fetch_page(**kwargs):
            calls.append((kwargs["page"], kwargs["cursor"]))
            return provider_rows[kwargs["cursor"]]

        return SimpleNamespace(
            name="dinari", fetch_tokenized_corporate_actions_page=fetch_page
        )

    provider = make_provider()

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="xstocks", provider=provider)]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        result = kwargs["invoke"](provider, None)
        return SimpleNamespace(provider_name="xstocks", result=result)

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    first = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_pages=1, page_size=1, include_upcoming=False
    )
    provider = make_provider()
    second = await refresh_tokenized_events(
        AsyncSessionAdapter(db), max_pages=1, page_size=1, include_upcoming=False
    )

    assert first["status"] == "partial"
    assert second["status"] == "refreshed"
    assert calls == [(1, None), (2, "cursor-1")]
    state = db.execute(
        select(ProviderPaginationState).where(
            ProviderPaginationState.state_key == "tokenized-events:xstocks:history:1"
        )
    ).scalar_one()
    assert state.status == "complete"
    assert state.cursor is None
    assert len(state.cursor_history) == 0


@pytest.mark.asyncio
async def test_dinari_sandbox_is_excluded_from_catalogue_and_event_persistence_paths(
    db, monkeypatch
):
    provider = SimpleNamespace(name="dinari", fetch_tokenized_corporate_actions=lambda: [])
    calls = []

    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="dinari", provider=provider)]

    async def fake_execute(*_args, **_kwargs):
        calls.append("executed")
        raise AssertionError("Sandbox canary must not enter persistence refreshes")

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    catalogue = await refresh_tokenized_assets(
        AsyncSessionAdapter(db), provider_name="dinari", max_pages=1, page_size=1
    )
    events = await refresh_tokenized_events(
        AsyncSessionAdapter(db), provider_name="dinari", max_providers=1
    )

    assert catalogue["status"] == "no_qualified_provider"
    assert events["status"] == "no_corporate_action_provider"
    assert calls == []
    assert db.query(TokenizedAssetDetail).count() == 0


@pytest.mark.asyncio
async def test_refresh_tokenized_events_reports_adapters_without_action_surface(db, monkeypatch):
    provider = SimpleNamespace(name="bybit_xstocks")
    async def fake_chain(*_args, **_kwargs):
        return [SimpleNamespace(provider_name="bybit_xstocks", provider=provider)]

    monkeypatch.setattr(tokenized_assets, "resolve_provider_chain", fake_chain)

    result = await refresh_tokenized_events(AsyncSessionAdapter(db))

    assert result == {
        "status": "no_corporate_action_provider",
        "providers": [],
        "unsupported": ["bybit_xstocks"],
        "events": 0,
        "linked": 0,
        "unlinked": 0,
        "failed": 0,
    }
