from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.providers.base import MarketDataProvider
from app.providers.yfinance import YFinanceProvider

_PROVIDERS: dict[str, MarketDataProvider] = {
    "yfinance": YFinanceProvider(),
}


def get_provider(name: str) -> MarketDataProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise KeyError(f"Unknown provider '{name}'")
    return provider


def get_default_market_data_provider() -> MarketDataProvider:
    return get_provider(settings.DEFAULT_MARKET_DATA_PROVIDER)


def get_default_metadata_provider() -> MarketDataProvider:
    return get_provider(settings.DEFAULT_METADATA_PROVIDER)


def get_default_event_provider() -> MarketDataProvider:
    return get_provider(settings.DEFAULT_EVENT_PROVIDER)


def get_default_discovery_provider() -> MarketDataProvider:
    return get_provider(settings.DEFAULT_DISCOVERY_PROVIDER)


def get_identifier_provider_chain() -> list[str]:
    return [name for name in settings.IDENTIFIER_PROVIDER_PRIORITY if name]


async def ensure_data_source(db: AsyncSession, provider_name: str) -> DataSource:
    result = await db.execute(select(DataSource).where(DataSource.name == provider_name))
    src = result.scalar_one_or_none()
    if src is None:
        provider = get_provider(provider_name)
        src = DataSource(
            name=provider_name,
            base_url=provider.base_url,
            description=provider.description,
            is_active=True,
        )
        db.add(src)
        await db.flush()
    return src


def provider_symbol_for_instrument(
    instrument: Instrument,
    provider_name: str | None = None,
) -> str:
    for provider_symbol in instrument.provider_symbols:
        data_source = getattr(provider_symbol, "data_source", None)
        if provider_name is not None and data_source is not None and data_source.name != provider_name:
            continue
        if provider_name is not None and data_source is None:
            continue
        if provider_symbol.is_active and provider_symbol.is_primary:
            return provider_symbol.provider_symbol

    for provider_symbol in instrument.provider_symbols:
        data_source = getattr(provider_symbol, "data_source", None)
        if provider_name is not None and data_source is not None and data_source.name != provider_name:
            continue
        if provider_name is not None and data_source is None:
            continue
        if provider_symbol.is_active:
            return provider_symbol.provider_symbol

    for listing in instrument.listings:
        if listing.is_primary and listing.is_active:
            return listing.ticker

    return instrument.symbol
