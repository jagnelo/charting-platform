"""Descriptors for optional, disabled-by-default provider integrations.

Keeping these providers in the registry makes the operational roster visible to
administrators without pretending an unconfigured credential or entitlement is
usable.  A provider becomes routable only when a concrete adapter and reviewed
capability entitlement are supplied.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class ConfiguredProvider:
    name: str
    base_url: str
    description: str


OPTIONAL_PROVIDER_DESCRIPTORS = {
    "tiingo": ConfiguredProvider(
        "tiingo",
        "https://api.tiingo.com",
        "Optional EOD/intraday provider; disabled until terms and credentials are reviewed.",
    ),
    "twelve_data": ConfiguredProvider(
        "twelve_data",
        "https://api.twelvedata.com",
        "Optional multi-asset provider; disabled until terms and credentials are reviewed.",
    ),
    "finnhub": ConfiguredProvider(
        "finnhub",
        "https://finnhub.io/api/v1",
        "Optional US profile/earnings/news provider; disabled until terms are reviewed.",
    ),
    "marketstack": ConfiguredProvider(
        "marketstack",
        "https://api.marketstack.com/v1",
        "Optional EOD/intraday provider; disabled until terms and credentials are reviewed.",
    ),
    "eodhd": ConfiguredProvider(
        "eodhd",
        "https://eodhd.com/api",
        "Optional long-history provider; disabled until cost and redistribution terms are reviewed.",
    ),
    "fmp": ConfiguredProvider(
        "fmp",
        "https://financialmodelingprep.com/stable",
        "Optional fundamentals/calendar provider; disabled until terms are reviewed.",
    ),
    "finra": ConfiguredProvider(
        "finra",
        "https://api.finra.org",
        "Public short-interest/reference datasets; adapter disabled until endpoint fixtures are validated.",
    ),
    "tradier": ConfiguredProvider(
        "tradier",
        "https://api.tradier.com/v1",
        "Optional US equities/options provider; account and personal-use terms apply.",
    ),
    "marketdata_app": ConfiguredProvider(
        "marketdata_app",
        "https://api.marketdata.app/v1",
        "Optional delayed US stocks/options provider; credit and personal-use limits apply.",
    ),
    "ibkr": ConfiguredProvider(
        "ibkr",
        "https://api.ibkr.com",
        "Optional account-bound market-data adapter; read-only boundary.",
    ),
    "coinbase": ConfiguredProvider(
        "coinbase", "https://api.exchange.coinbase.com", "Optional crypto market-data provider."
    ),
    "kraken": ConfiguredProvider(
        "kraken", "https://api.kraken.com", "Optional crypto/futures market-data provider."
    ),
    "xstocks": ConfiguredProvider(
        "xstocks",
        "https://api.xstocks.fi/api/v2",
        "Public xStocks tokenized-equity/ETF metadata, prices, multipliers and corporate actions; public quota is not documented.",
    ),
    "robinhood_tokens": ConfiguredProvider(
        "robinhood_tokens",
        "https://api.robinhood.com/rhj",
        "Robinhood Chain Stock Token public assets, prices and corporate actions.",
    ),
    "bybit_xstocks": ConfiguredProvider(
        "bybit_xstocks",
        "https://api.bybit.com",
        "Bybit public xStocks instrument metadata and market tickers.",
    ),
    "gate_tradfi": ConfiguredProvider(
        "gate_tradfi",
        "https://api.gateio.ws/api/v4",
        "Gate public TradFi/xStocks symbol and order-book data.",
    ),
    "kraken_xstocks": ConfiguredProvider(
        "kraken_xstocks",
        "https://api.kraken.com/0/public",
        "Kraken public xStocks pair metadata and ticker data.",
    ),
    "ondo_global_markets": ConfiguredProvider(
        "ondo_global_markets",
        "https://api.gm.ondo.finance",
        "Catalogue-only tokenized US stock/ETF API; onboarding is required.",
    ),
    "dinari": ConfiguredProvider(
        "dinari",
        "https://api-enterprise.sandbox.dinari.com/api/v2",
        "Catalogue-only tokenized-equity infrastructure; partner access is required.",
    ),
    "alpaca_itn": ConfiguredProvider(
        "alpaca_itn",
        "https://api.alpaca.markets",
        "Catalogue-only tokenization network; authorized-participant access is required.",
    ),
}
