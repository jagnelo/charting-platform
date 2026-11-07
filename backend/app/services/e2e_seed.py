import hashlib
import math
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.exchange import Exchange
from app.models.instrument import EquityDetail, Instrument
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import AdjustmentBasis
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.services.market_series import (
    SeriesScope,
    get_or_create_series,
    select_default_series_for_complete_range,
)
from app.services.top_down_taxonomy import benchmark_family_proxy_symbols

# The browser fixture intentionally mirrors the complete configured benchmark
# family proxy registry. These are controlled identities and holdings, not a
# claim about the live composition of any index or ETF.
_E2E_BENCHMARK_PROXY_NAMES = {
    symbol: f"Controlled {symbol} benchmark-family proxy"
    for symbol in benchmark_family_proxy_symbols()
}


async def seed_e2e_instruments(db: AsyncSession) -> None:
    """Seed deterministic workstation symbols for browser tests without provider I/O.

    These are canonical reference identities only: no bars, holdings, or provider
    entitlements are fabricated. Data-dependent tools therefore render explicit
    unavailable/coverage states instead of generating instrument-not-found errors.
    """

    asset_class = await _get_or_create_asset_class(db)
    instrument_type = await _get_or_create_instrument_type(db, asset_class.id)
    names = {
        "AAPL": "Apple Inc.",
        "SPY": "S&P 500 proxy ETF",
        "RSP": "S&P 500 equal-weight ETF",
        "QQQ": "Nasdaq-100 proxy ETF",
        "DIA": "Dow 30 proxy ETF",
        "IWM": "Russell 2000 proxy ETF",
        "XLK": "Technology Select Sector SPDR",
        "XLY": "Consumer Discretionary Select Sector SPDR",
        "XLC": "Communication Services Select Sector SPDR",
        "XLF": "Financial Select Sector SPDR",
        "XLV": "Health Care Select Sector SPDR",
        "XLI": "Industrial Select Sector SPDR",
        "XLP": "Consumer Staples Select Sector SPDR",
        "XLE": "Energy Select Sector SPDR",
        "XLU": "Utilities Select Sector SPDR",
        "XLRE": "Real Estate Select Sector SPDR",
        "XLB": "Materials Select Sector SPDR",
        **_E2E_BENCHMARK_PROXY_NAMES,
    }
    symbols = tuple(names)
    existing = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }
    for symbol, name in names.items():
        if symbol not in existing:
            instrument = Instrument(
                symbol=symbol,
                name=name,
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
                field_provenance={"seed": "e2e", "identity_only": True},
            )
            db.add(instrument)
            existing[symbol] = instrument
    await db.flush()

    # Keep one canonical venue row in the controlled identity fixture so the
    # authenticated workstation exercises the same exchange-aware listing
    # contract used by production instrument reports.  This is deliberately
    # labelled test data and never claims live venue coverage.
    arca = await db.scalar(select(Exchange).where(Exchange.mic == "ARCX"))
    if arca is None:
        arca = Exchange(
            mic="ARCX",
            name="NYSE Arca",
            country_code="US",
            timezone="America/New_York",
            market_open="09:30",
            market_close="16:00",
            currency="USD",
        )
        db.add(arca)
        await db.flush()
    spy_listing = await db.scalar(
        select(InstrumentListing).where(
            InstrumentListing.instrument_id == existing["SPY"].id,
            InstrumentListing.ticker == "SPY",
            InstrumentListing.exchange_id == arca.id,
        )
    )
    if spy_listing is None:
        db.add(
            InstrumentListing(
                instrument_id=existing["SPY"].id,
                exchange_id=arca.id,
                ticker="SPY",
                currency="USD",
                is_primary=True,
                is_active=True,
                source="e2e_reference",
                provenance={"seed": "e2e", "controlled_fixture": True},
            )
        )
        await db.flush()
    elif (
        spy_listing.source in (None, "e2e_reference")
        and existing["SPY"].field_provenance
        and existing["SPY"].field_provenance.get("seed") == "e2e"
    ):
        spy_listing.currency = "USD"
        spy_listing.is_active = True
        spy_listing.is_primary = True
        spy_listing.source = "e2e_reference"
        spy_listing.provenance = {
            **(spy_listing.provenance or {}),
            "seed": "e2e",
            "controlled_fixture": True,
        }

    for symbol in symbols[1:]:
        profile = await db.scalar(
            select(ETFProfile).where(ETFProfile.instrument_id == existing[symbol].id)
        )
        if profile is None:
            db.add(
                ETFProfile(
                    instrument_id=existing[symbol].id,
                    issuer="reference-only",
                    fund_family="E2E reference identity",
                    adapter_status="unresolved",
                    extra_data={"seed": "e2e", "identity_only": True},
                )
            )


_E2E_MARKET_NAMES = {
    "NVDA": "NVIDIA Corporation",
    "MSFT": "Microsoft Corporation",
    "AMD": "Advanced Micro Devices",
    "AVGO": "Broadcom Inc.",
    "CRM": "Salesforce, Inc.",
    "ORCL": "Oracle Corporation",
    "AMZN": "Amazon.com, Inc.",
    "TSLA": "Tesla, Inc.",
    "META": "Meta Platforms, Inc.",
    "GOOGL": "Alphabet Inc.",
    "JPM": "JPMorgan Chase & Co.",
    "BAC": "Bank of America Corporation",
    "LLY": "Eli Lilly and Company",
    "UNH": "UnitedHealth Group Incorporated",
    "CAT": "Caterpillar Inc.",
    "GE": "GE Aerospace",
    "PG": "The Procter & Gamble Company",
    "COST": "Costco Wholesale Corporation",
    "XOM": "Exxon Mobil Corporation",
    "CVX": "Chevron Corporation",
    "NEE": "NextEra Energy, Inc.",
    "DUK": "Duke Energy Corporation",
    "PLD": "Prologis, Inc.",
    "AMT": "American Tower Corporation",
    "LIN": "Linde plc",
    "APD": "Air Products and Chemicals, Inc.",
    "SMH": "VanEck Semiconductor ETF",
    "SOXX": "iShares Semiconductor ETF",
}

_E2E_RECENT_HISTORY_START = date(2024, 1, 2)
_E2E_RECENT_HISTORY_BARS = 520
_E2E_LONG_RRG_START = date(2019, 1, 2)
_E2E_MONTHLY_RRG_SYMBOLS = (
    "SPY",
    "XLK",
    "XLY",
    "XLC",
    "XLF",
    "XLV",
    "XLI",
    "XLP",
    "XLE",
    "XLU",
    "XLRE",
    "XLB",
)

_E2E_INDUSTRIES = {
    "NVDA": "Semiconductors",
    "AMD": "Semiconductors",
    "AVGO": "Semiconductors",
    "MSFT": "Systems Software",
    "CRM": "Systems Software",
    "ORCL": "Systems Software",
    "AMZN": "Broadline Retail",
    "TSLA": "Automobiles",
    "META": "Interactive Media & Services",
    "GOOGL": "Interactive Media & Services",
    "JPM": "Diversified Banks",
    "BAC": "Diversified Banks",
    "LLY": "Pharmaceuticals",
    "UNH": "Health Care Services",
    "CAT": "Machinery",
    "GE": "Aerospace & Defense",
    "PG": "Household Products",
    "COST": "Consumer Staples Distribution & Retail",
    "XOM": "Integrated Oil & Gas",
    "CVX": "Integrated Oil & Gas",
    "NEE": "Electric Utilities",
    "DUK": "Electric Utilities",
    "PLD": "Industrial REITs",
    "AMT": "Telecom Tower REITs",
    "LIN": "Industrial Gases",
    "APD": "Industrial Gases",
}

_E2E_HOLDINGS = {
    "SPY": ("NVDA", "MSFT", "AMD", "AVGO", "CRM", "ORCL"),
    "RSP": ("NVDA", "MSFT", "AMD", "AVGO", "CRM", "ORCL"),
    "QQQ": ("NVDA", "MSFT", "AMD", "AVGO", "CRM", "ORCL"),
    "DIA": ("NVDA", "MSFT", "CAT", "GE", "JPM", "PG"),
    "IWM": ("AMD", "CRM", "CAT", "GE", "BAC", "COST"),
    "XLK": ("NVDA", "MSFT", "AMD", "AVGO", "CRM", "ORCL"),
    "XLY": ("AMZN", "TSLA"),
    "XLC": ("META", "GOOGL"),
    "XLF": ("JPM", "BAC"),
    "XLV": ("LLY", "UNH"),
    "XLI": ("CAT", "GE"),
    "XLP": ("PG", "COST"),
    "XLE": ("XOM", "CVX"),
    "XLU": ("NEE", "DUK"),
    "XLRE": ("PLD", "AMT"),
    "XLB": ("LIN", "APD"),
    "SMH": ("NVDA", "AMD", "AVGO"),
    "SOXX": ("NVDA", "AMD", "AVGO"),
}

# Every configured family leg receives a deterministic, labelled constituent
# snapshot in the opt-in browser environment. The varied real-world sizes of
# the S&P/Russell/Nasdaq families are deliberately not fabricated here; the
# acceptance contract needs coverage for every source role, while production
# membership still comes only from entitled/provider-evidenced snapshots.
_E2E_FAMILY_CONSTITUENTS = ("NVDA", "MSFT", "AMD", "AVGO", "CRM", "ORCL")
for _proxy_symbol in benchmark_family_proxy_symbols():
    _E2E_HOLDINGS.setdefault(_proxy_symbol, _E2E_FAMILY_CONSTITUENTS)


async def seed_e2e_market_data(db: AsyncSession) -> None:
    """Add deterministic local bars and holdings for deep browser acceptance.

    This is opt-in test infrastructure only.  It is never enabled by production
    configuration and every row carries controlled-fixture provenance so the browser
    can exercise the complete top-down workflow without contacting a provider.
    """

    asset_class = await _get_or_create_asset_class(db)
    instrument_type = await _get_or_create_instrument_type(db, asset_class.id)
    existing = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(
                select(Instrument).where(Instrument.symbol.in_(tuple(_E2E_MARKET_NAMES)))
            )
        ).scalars()
    }
    for symbol, name in _E2E_MARKET_NAMES.items():
        if symbol in existing:
            continue
        instrument = Instrument(
            symbol=symbol,
            name=name,
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            field_provenance={"seed": "e2e", "controlled_fixture": True},
        )
        db.add(instrument)
        existing[symbol] = instrument
    await db.flush()

    for symbol, industry in _E2E_INDUSTRIES.items():
        instrument = existing[symbol]
        detail = await db.scalar(
            select(EquityDetail).where(EquityDetail.instrument_id == instrument.id)
        )
        if detail is None:
            db.add(
                EquityDetail(
                    instrument_id=instrument.id,
                    sector="Technology",
                    industry=industry,
                    country="US",
                    exchange_mic="XNAS",
                    field_provenance={
                        "seed": "e2e",
                        "controlled_fixture": True,
                        "sector": {"classification_system": "controlled_fixture"},
                        "industry": {"classification_system": "controlled_fixture"},
                    },
                )
            )
        else:
            # The identity-only fixture may already have a detail row created by
            # another deterministic seed.  Complete the opt-in market fixture's
            # classifications without changing any production path.
            detail.sector = "Technology"
            detail.industry = industry
            detail.field_provenance = {
                **(detail.field_provenance or {}),
                "seed": "e2e",
                "controlled_fixture": True,
                "sector": {"classification_system": "controlled_fixture"},
                "industry": {"classification_system": "controlled_fixture"},
            }
            detail.country = "US"
            detail.exchange_mic = "XNAS"
            detail.field_provenance = {
                **(detail.field_provenance or {}),
                "seed": "e2e",
                "controlled_fixture": True,
            }

    source = await db.scalar(select(DataSource).where(DataSource.name == "e2e_reference"))
    if source is None:
        source = DataSource(
            name="e2e_reference",
            base_url="controlled://e2e",
            description="Deterministic local market fixture for browser acceptance only",
            is_active=True,
            config={"controlled_fixture": True},
            supported_capabilities=["ohlcv", "etf_holdings"],
        )
        db.add(source)
        await db.flush()

    all_symbols = [
        "SPY",
        "RSP",
        "QQQ",
        "DIA",
        "IWM",
        "XLK",
        "XLY",
        "XLC",
        "XLF",
        "XLV",
        "XLI",
        "XLP",
        "XLE",
        "XLU",
        "XLRE",
        "XLB",
        *benchmark_family_proxy_symbols(),
        *tuple(_E2E_MARKET_NAMES),
    ]
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(tuple(all_symbols))))
        ).scalars()
    }

    # The controlled SPY bars are canonical fixture evidence for deterministic
    # Study preparation.  Give that fixture identity an explicit E2E namespace;
    # this is not a FIGI/issuer assertion and cannot qualify a production row.
    spy = instruments["SPY"]
    spy_provenance = dict(spy.field_provenance or {})
    if spy_provenance.get("seed") == "e2e" and spy.domain_key in (None, "e2e:instrument:SPY"):
        spy.domain_key = "e2e:instrument:SPY"
        spy.identity_status = "resolved"
        spy.field_provenance = {
            **spy_provenance,
            "controlled_fixture": True,
            "identity": {
                "source": "e2e_reference",
                "basis": "explicit_fixture_identity",
            },
        }
    elif (
        spy.domain_key == "e2e:instrument:SPY" and spy_provenance.get("controlled_fixture") is True
    ):
        # Repeated startup should retain, rather than recreate, the same fixture
        # identity once it has been established.
        spy.identity_status = "resolved"

    # Enough deterministic daily history for RSI, moving averages, 52-week position,
    # ratios, breadth, and the positive-close Study Lab factory study.
    start = _E2E_RECENT_HISTORY_START
    trading_days: list[date] = []
    cursor = start
    while len(trading_days) < _E2E_RECENT_HISTORY_BARS:
        if cursor.weekday() < 5:
            trading_days.append(cursor)
        cursor += timedelta(days=1)

    long_rrg_days: list[date] = []
    cursor = _E2E_LONG_RRG_START
    while cursor < start:
        if cursor.weekday() < 5:
            long_rrg_days.append(cursor)
        cursor += timedelta(days=1)

    base_prices = {
        "SPY": 420.0,
        "RSP": 150.0,
        "QQQ": 360.0,
        "DIA": 380.0,
        "IWM": 190.0,
        "XLK": 175.0,
        "XLY": 170.0,
        "XLC": 70.0,
        "XLF": 38.0,
        "XLV": 130.0,
        "XLI": 100.0,
        "XLP": 75.0,
        "XLE": 85.0,
        "XLU": 65.0,
        "XLRE": 40.0,
        "XLB": 80.0,
        "NVDA": 480.0,
        "MSFT": 330.0,
        "AMD": 120.0,
        "AVGO": 900.0,
        "CRM": 240.0,
        "ORCL": 105.0,
        "SMH": 180.0,
        "SOXX": 210.0,
    }
    # Give every taxonomy proxy a stable but distinct baseline so ratio and
    # relative-return views remain useful in the controlled workstation.
    for position, symbol in enumerate(benchmark_family_proxy_symbols(), start=1):
        base_prices.setdefault(symbol, 100.0 + position * 7.5)
    # These explicit E2E source series make the same controlled daily fixture
    # visible to ordinary canonical reads. Existing rows are retained and
    # compatible rows from earlier fixture versions are attached in place.
    daily_series = {}
    for symbol, instrument in instruments.items():
        daily_series[symbol] = await get_or_create_series(
            db,
            SeriesScope(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1.value,
                data_source_id=source.id,
                feed_scope="e2e-reference",
                session_code="regular",
                adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                adjustment_version="e2e-split-adjusted-v1",
            ),
            canonical=True,
            source_series_key=f"e2e_reference:{symbol}:D1:split-adjusted",
            provenance={"seed": "e2e", "controlled_fixture": True},
        )

    for symbol, instrument in instruments.items():
        series = daily_series[symbol]
        scope_key = f"series:{series.id}:regular"
        # Adopt only rows whose source and adjustment lineage exactly match this
        # fixture. Incompatible legacy/provider rows remain untouched.
        compatible_rows = (
            await db.execute(
                select(OHLCVBar).where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.data_source_id == source.id,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(True),
                    OHLCVBar.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED,
                    OHLCVBar.adjustment_version == "e2e-split-adjusted-v1",
                    OHLCVBar.is_derived.is_(False),
                    (
                        OHLCVBar.market_series_id.is_(None)
                        | (OHLCVBar.market_series_id == series.id)
                    ),
                )
            )
        ).scalars()
        for existing_bar in compatible_rows:
            existing_bar.market_series_id = series.id
            existing_bar.scope_key = scope_key

        await db.flush()
    for symbol, instrument in instruments.items():
        series = daily_series[symbol]
        scope_key = f"series:{series.id}:regular"
        existing_timestamps = {
            timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp.astimezone(UTC)
            for timestamp in (
                await db.execute(
                    select(OHLCVBar.ts).where(
                        OHLCVBar.market_series_id == series.id,
                        OHLCVBar.timeframe == Timeframe.D1,
                        OHLCVBar.is_adjusted.is_(True),
                        OHLCVBar.is_derived.is_(False),
                    )
                )
            ).scalars()
        }
        base = base_prices.get(symbol, 100.0)
        slope = 0.00035 + (sum(ord(char) for char in symbol) % 7) * 0.00003
        bars: list[OHLCVBar] = []
        previous = base
        for index, day in enumerate(trading_days):
            cycle = math.sin(index / 17.0 + len(symbol)) * 0.008
            close = base * (1 + slope * index + cycle)
            # Keep a deterministic positive streak at the end for Study Lab.
            if index >= len(trading_days) - 8:
                close = previous * (1.0 + 0.004 + (index % 3) * 0.001)
            open_ = previous
            high = max(open_, close) * 1.004
            low = min(open_, close) * 0.996
            bars.append(
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=source.id,
                    market_series_id=series.id,
                    scope_key=scope_key,
                    timeframe=Timeframe.D1,
                    ts=datetime.combine(day, time(21, 0), tzinfo=UTC),
                    session="regular",
                    open=Decimal(str(round(open_, 8))),
                    high=Decimal(str(round(high, 8))),
                    low=Decimal(str(round(low, 8))),
                    close=Decimal(str(round(close, 8))),
                    volume=Decimal(str(1_000_000 + (index % 31) * 10_000 + len(symbol) * 1_000)),
                    is_adjusted=True,
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="e2e-split-adjusted-v1",
                )
            )
            previous = close

        # Extend only the controlled SPY/sector RRG fixture. Keep the existing
        # recent 520-row generator above unchanged; older history ends exactly
        # at its opening baseline and has explicit E2E provenance through the
        # shared controlled-fixture data source.
        if symbol in _E2E_MONTHLY_RRG_SYMBOLS:
            historical_previous = base * 0.72
            for index, day in enumerate(long_rrg_days):
                progress = (index + 1) / len(long_rrg_days)
                close = base * (0.72 + 0.28 * progress)
                if index == len(long_rrg_days) - 1:
                    close = base
                open_ = historical_previous
                high = max(open_, close) * 1.004
                low = min(open_, close) * 0.996
                bars.append(
                    OHLCVBar(
                        instrument_id=instrument.id,
                        data_source_id=source.id,
                        market_series_id=series.id,
                        scope_key=scope_key,
                        timeframe=Timeframe.D1,
                        ts=datetime.combine(day, time(21, 0), tzinfo=UTC),
                        session="regular",
                        open=Decimal(str(round(open_, 8))),
                        high=Decimal(str(round(high, 8))),
                        low=Decimal(str(round(low, 8))),
                        close=Decimal(str(round(close, 8))),
                        volume=Decimal(str(800_000 + (index % 31) * 9_000 + len(symbol) * 1_000)),
                        is_adjusted=True,
                        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                        adjustment_version="e2e-split-adjusted-v1",
                    )
                )
                historical_previous = close
        db.add_all(bar for bar in bars if bar.ts.astimezone(UTC) not in existing_timestamps)
    await db.flush()

    # The adjusted default is selected only after this controlled source has
    # complete fixture-range coverage; an older incompatible mapping is not
    # silently treated as a canonical adjusted series.
    recent_start = datetime.combine(trading_days[0], time(21, 0), tzinfo=UTC)
    long_start = datetime.combine(long_rrg_days[0], time(21, 0), tzinfo=UTC)
    daily_end = datetime.combine(trading_days[-1], time(21, 0), tzinfo=UTC)
    for symbol, instrument in instruments.items():
        await select_default_series_for_complete_range(
            db,
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            adjusted=True,
            market_series_id=daily_series[symbol].id,
            start=long_start if symbol in _E2E_MONTHLY_RRG_SYMBOLS else recent_start,
            end=daily_end,
        )
    await db.flush()

    # Keep the fixture's dataset-state contract in sync with the bars it writes.
    # Analysis endpoints use this state for freshness; omitting it would make a
    # fully populated controlled fixture report ``unavailable``.
    fetched_at = datetime.now(UTC)
    recent_coverage_start = datetime.combine(trading_days[0], time(21, 0), tzinfo=UTC)
    long_coverage_start = datetime.combine(long_rrg_days[0], time(21, 0), tzinfo=UTC)
    coverage_end = datetime.combine(trading_days[-1], time(21, 0), tzinfo=UTC)
    for symbol, instrument in instruments.items():
        state = await db.scalar(
            select(InstrumentDatasetState).where(
                InstrumentDatasetState.instrument_id == instrument.id,
                InstrumentDatasetState.data_source_id == source.id,
                InstrumentDatasetState.dataset_type == "ohlcv",
                InstrumentDatasetState.dataset_key == "D1:adj",
            )
        )
        if state is None:
            state = InstrumentDatasetState(
                instrument_id=instrument.id,
                data_source_id=source.id,
                dataset_type="ohlcv",
                dataset_key="D1:adj",
            )
            db.add(state)
        state.status = DatasetStatus.FRESH
        state.observed_at = fetched_at
        state.fetched_at = fetched_at
        state.stale_after = fetched_at + timedelta(days=1)
        has_long_rrg_history = symbol in _E2E_MONTHLY_RRG_SYMBOLS
        coverage_start = long_coverage_start if has_long_rrg_history else recent_coverage_start
        state.coverage_start = coverage_start
        state.coverage_end = coverage_end
        state.version = max(state.version or 1, 1)
        state.snapshot_hash = hashlib.sha256(
            f"{symbol}:e2e:D1:adj:{coverage_start.isoformat()}:{coverage_end.isoformat()}".encode()
        ).hexdigest()
        state.extra_data = {
            "seed": "e2e",
            "controlled_fixture": True,
            "bar_count": len(trading_days) + (len(long_rrg_days) if has_long_rrg_history else 0),
            "adjusted": True,
            "extended_monthly_rrg_history": has_long_rrg_history,
        }

    from app.services.derived_timeframes import materialize_derived_timeframes

    for symbol in _E2E_MONTHLY_RRG_SYMBOLS:
        instrument = instruments.get(symbol)
        if instrument is not None:
            await materialize_derived_timeframes(db, instrument.id, adjusted=True)

    # Create controlled, point-in-time ETF-proxy holdings for sector and industry drilldown.
    etf_symbols = {
        "SPY",
        "RSP",
        "QQQ",
        "DIA",
        "IWM",
        "XLK",
        "XLY",
        "XLC",
        "XLF",
        "XLV",
        "XLI",
        "XLP",
        "XLE",
        "XLU",
        "XLRE",
        "XLB",
        "SMH",
        "SOXX",
        *benchmark_family_proxy_symbols(),
    }
    profiles: dict[str, ETFProfile] = {}
    for symbol in etf_symbols:
        instrument = instruments.get(symbol)
        if instrument is None:
            continue
        profile = await db.scalar(
            select(ETFProfile).where(ETFProfile.instrument_id == instrument.id)
        )
        if profile is None:
            profile = ETFProfile(
                instrument_id=instrument.id,
                issuer="controlled-fixture",
                fund_family="E2E market data",
                adapter_status="ready",
                extra_data={"seed": "e2e", "controlled_fixture": True},
            )
            db.add(profile)
            await db.flush()
        profiles[symbol] = profile

    composition_date = date(2026, 1, 2)
    known_at = datetime(2026, 1, 3, tzinfo=UTC)
    for etf_symbol, holding_symbols in _E2E_HOLDINGS.items():
        profile = profiles.get(etf_symbol)
        if (
            profile is None
            or await db.scalar(
                select(ETFHoldingsSnapshot.id)
                .where(
                    ETFHoldingsSnapshot.etf_profile_id == profile.id,
                    ETFHoldingsSnapshot.composition_date == composition_date,
                    ETFHoldingsSnapshot.source_provider == "e2e_reference",
                )
                .limit(1)
            )
            is not None
        ):
            continue
        digest = hashlib.sha256(
            f"{etf_symbol}:e2e:{composition_date.isoformat()}".encode()
        ).hexdigest()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=composition_date,
            as_of_date=composition_date,
            known_at=known_at,
            published_at=known_at,
            provenance="controlled_fixture",
            source_provider="e2e_reference",
            source_url="controlled://e2e",
            source_identifier=f"e2e:{etf_symbol}:{composition_date.isoformat()}",
            source_quality="deterministic",
            completeness_status="complete",
            row_count=len(holding_symbols),
            resolved_count=len(holding_symbols),
            unresolved_count=0,
            total_weight=Decimal("1.0"),
            parser_version="e2e-v1",
            snapshot_hash=digest,
            notes="Controlled browser-acceptance fixture; not market data.",
            extra_data={
                "seed": "e2e",
                "controlled_fixture": True,
                "source_tier": "controlled_fixture",
                "transport_kind": "controlled_fixture",
            },
        )
        db.add(snapshot)
        await db.flush()
        weight = Decimal("1") / Decimal(len(holding_symbols))
        for position, holding_symbol in enumerate(holding_symbols):
            constituent = instruments.get(holding_symbol)
            if constituent is None:
                continue
            row_hash = hashlib.sha256(f"{etf_symbol}:{holding_symbol}:e2e".encode()).hexdigest()
            db.add(
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=constituent.id,
                    position=position,
                    reported_symbol=holding_symbol,
                    reported_name=constituent.name,
                    weight=weight,
                    shares=Decimal("1000"),
                    market_value=Decimal("1000000") * weight,
                    currency="USD",
                    country="US",
                    exchange="XNAS",
                    holding_type="equity",
                    row_type="security",
                    source_row_id=f"{etf_symbol}-{position}",
                    source_row_hash=row_hash,
                    is_resolved=True,
                    resolution_confidence=Decimal("1.0"),
                    resolution_note="Controlled E2E fixture.",
                    extra_data={"seed": "e2e", "controlled_fixture": True},
                )
            )
    await db.flush()


async def _get_or_create_asset_class(db: AsyncSession) -> AssetClass:
    existing = await db.scalar(select(AssetClass).where(AssetClass.name == "Equity"))
    if existing is not None:
        return existing
    asset_class = AssetClass(name="Equity", description="Equity instruments")
    db.add(asset_class)
    await db.flush()
    return asset_class


async def _get_or_create_instrument_type(db: AsyncSession, asset_class_id: int) -> InstrumentType:
    existing = await db.scalar(
        select(InstrumentType).where(
            InstrumentType.name == "Stock",
            InstrumentType.asset_class_id == asset_class_id,
        )
    )
    if existing is not None:
        return existing
    instrument_type = InstrumentType(name="Stock", asset_class_id=asset_class_id)
    db.add(instrument_type)
    await db.flush()
    return instrument_type
