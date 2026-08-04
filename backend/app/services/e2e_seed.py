import hashlib
import math
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import EquityDetail, Instrument
from app.models.ohlcv import OHLCVBar, Timeframe


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
    }
    symbols = tuple(names)
    existing = {
        instrument.symbol.upper(): instrument
        for instrument in (await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))).scalars()
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

    for symbol in symbols[1:]:
        profile = await db.scalar(select(ETFProfile).where(ETFProfile.instrument_id == existing[symbol].id))
        if profile is None:
            db.add(ETFProfile(
                instrument_id=existing[symbol].id,
                issuer="reference-only",
                fund_family="E2E reference identity",
                adapter_status="unresolved",
                extra_data={"seed": "e2e", "identity_only": True},
            ))


_E2E_MARKET_NAMES = {
    "NVDA": "NVIDIA Corporation",
    "MSFT": "Microsoft Corporation",
    "AMD": "Advanced Micro Devices",
    "AVGO": "Broadcom Inc.",
    "CRM": "Salesforce, Inc.",
    "ORCL": "Oracle Corporation",
    "SMH": "VanEck Semiconductor ETF",
    "SOXX": "iShares Semiconductor ETF",
}

_E2E_INDUSTRIES = {
    "NVDA": "Semiconductors",
    "AMD": "Semiconductors",
    "AVGO": "Semiconductors",
    "MSFT": "Systems Software",
    "CRM": "Systems Software",
    "ORCL": "Systems Software",
}

_E2E_HOLDINGS = {
    "XLK": ("NVDA", "MSFT", "AMD", "AVGO", "CRM", "ORCL"),
    "SMH": ("NVDA", "AMD", "AVGO"),
    "SOXX": ("NVDA", "AMD", "AVGO"),
}


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
        detail = await db.scalar(select(EquityDetail).where(EquityDetail.instrument_id == instrument.id))
        if detail is None:
            db.add(
                EquityDetail(
                    instrument_id=instrument.id,
                    sector="Technology",
                    industry=industry,
                    country="US",
                    exchange_mic="XNAS",
                    field_provenance={"seed": "e2e", "controlled_fixture": True},
                )
            )
        else:
            # The identity-only fixture may already have a detail row created by
            # another deterministic seed.  Complete the opt-in market fixture's
            # classifications without changing any production path.
            detail.sector = "Technology"
            detail.industry = industry
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
        "SPY", "RSP", "QQQ", "DIA", "IWM",
        "XLK", "XLY", "XLC", "XLF", "XLV", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB",
        *tuple(_E2E_MARKET_NAMES),
    ]
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(tuple(all_symbols))))
        ).scalars()
    }

    # Enough deterministic daily history for RSI, moving averages, 52-week position,
    # ratios, breadth, and the positive-close Study Lab factory study.
    start = date(2024, 1, 2)
    trading_days: list[date] = []
    cursor = start
    while len(trading_days) < 520:
        if cursor.weekday() < 5:
            trading_days.append(cursor)
        cursor += timedelta(days=1)

    base_prices = {
        "SPY": 420.0, "RSP": 150.0, "QQQ": 360.0, "DIA": 380.0, "IWM": 190.0,
        "XLK": 175.0, "XLY": 170.0, "XLC": 70.0, "XLF": 38.0, "XLV": 130.0,
        "XLI": 100.0, "XLP": 75.0, "XLE": 85.0, "XLU": 65.0, "XLRE": 40.0,
        "XLB": 80.0, "NVDA": 480.0, "MSFT": 330.0, "AMD": 120.0, "AVGO": 900.0,
        "CRM": 240.0, "ORCL": 105.0, "SMH": 180.0, "SOXX": 210.0,
    }
    for symbol, instrument in instruments.items():
        if await db.scalar(
            select(OHLCVBar.id)
            .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.timeframe == Timeframe.D1)
            .limit(1)
        ) is not None:
            continue
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
                    timeframe=Timeframe.D1,
                    ts=datetime.combine(day, time(21, 0), tzinfo=UTC),
                    session="regular",
                    open=Decimal(str(round(open_, 8))),
                    high=Decimal(str(round(high, 8))),
                    low=Decimal(str(round(low, 8))),
                    close=Decimal(str(round(close, 8))),
                    volume=Decimal(str(1_000_000 + (index % 31) * 10_000 + len(symbol) * 1_000)),
                    is_adjusted=True,
                )
            )
            previous = close
        db.add_all(bars)
    await db.flush()

    # Create controlled, point-in-time ETF-proxy holdings for sector and industry drilldown.
    etf_symbols = {"SPY", "RSP", "QQQ", "DIA", "IWM", "XLK", "XLY", "XLC", "XLF", "XLV", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB", "SMH", "SOXX"}
    profiles: dict[str, ETFProfile] = {}
    for symbol in etf_symbols:
        instrument = instruments.get(symbol)
        if instrument is None:
            continue
        profile = await db.scalar(select(ETFProfile).where(ETFProfile.instrument_id == instrument.id))
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
        if profile is None or await db.scalar(
            select(ETFHoldingsSnapshot.id).where(
                ETFHoldingsSnapshot.etf_profile_id == profile.id,
                ETFHoldingsSnapshot.composition_date == composition_date,
                ETFHoldingsSnapshot.source_provider == "e2e_reference",
            ).limit(1)
        ) is not None:
            continue
        digest = hashlib.sha256(f"{etf_symbol}:e2e:{composition_date.isoformat()}".encode()).hexdigest()
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
            extra_data={"seed": "e2e", "controlled_fixture": True},
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


async def _get_or_create_instrument_type(
    db: AsyncSession, asset_class_id: int
) -> InstrumentType:
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
