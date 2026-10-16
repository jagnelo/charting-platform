#!/usr/bin/env python3
"""Run the explicit, bounded provider live matrix.

Normal CI does not call external services. With ``RUN_LIVE_PROVIDER_TESTS=1``
this command reports every required credential, runs keyless probes, and runs
credentialed probes only when their exact environment is present. Missing
credentials return exit code 2; they are never represented as passing skips.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from xml.etree import ElementTree

import yaml
from dotenv import load_dotenv

_LOCK_SPEC = importlib.util.spec_from_file_location(
    "provider_live_lock", Path(__file__).with_name("provider_live_lock.py")
)
if (
    _LOCK_SPEC is None or _LOCK_SPEC.loader is None
):  # pragma: no cover - packaging failure
    raise ImportError("provider_live_lock.py is unavailable")
_LOCK_MODULE = importlib.util.module_from_spec(_LOCK_SPEC)
_LOCK_SPEC.loader.exec_module(_LOCK_MODULE)
ProviderLiveRunAlreadyActive = _LOCK_MODULE.ProviderLiveRunAlreadyActive
provider_live_run_lock = _LOCK_MODULE.provider_live_run_lock

ROOT = Path(__file__).resolve().parents[1]
SHARED_ENV_OVERRIDE = "CHARTING_PLATFORM_SHARED_ENV_FILE"
DEFAULT_SHARED_ENV = Path.home() / ".config" / "charting-platform" / "app.env"

KEYLESS = ("EDGAR_USER_AGENT",)
CREDENTIALS = {
    "alpaca": ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
    "massive": ("MASSIVE_API_KEY",),
    "alpha_vantage": ("ALPHA_VANTAGE_API_KEY",),
    "coingecko": ("COINGECKO_API_KEY",),
    "fred": ("FRED_API_KEY",),
    "finra": ("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET"),
    "finra_otc_directory": (),
    "tiingo": ("TIINGO_API_KEY",),
    "twelve_data": ("TWELVE_DATA_API_KEY",),
    "finnhub": ("FINNHUB_API_KEY",),
    "marketstack": ("MARKETSTACK_API_KEY",),
    "eodhd": ("EODHD_API_KEY",),
    "fmp": ("FMP_API_KEY",),
    "tradier": ("TRADIER_API_KEY",),
    "marketdata_app": ("MARKETDATA_APP_API_KEY",),
    "ibkr": ("IBKR_READ_ONLY_URL", "IBKR_READ_ONLY_SESSION_COOKIE"),
    "dinari": ("DINARI_API_KEY_ID", "DINARI_API_SECRET_KEY"),
    "ondo_global_markets": ("ONDO_GLOBAL_MARKETS_API_KEY",),
}


def provider_required_credentials(provider: str) -> tuple[str, ...]:
    """Return credentials required by the selected provider/source variant."""

    if provider == "finra_otc_directory":
        source_kind = str(os.getenv("FINRA_OTC_SOURCE_KIND", "") or "").strip().lower()
        if source_kind == "finra_otc_query_api":
            return (
                "FINRA_CLIENT_ID",
                "FINRA_CLIENT_SECRET",
                "FINRA_OTC_SOURCE_KIND",
                "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            )
        orf_configuration = (
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
            "FINRA_ORF_USERNAME",
            "FINRA_ORF_REFRESH_TOKEN",
            "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
        )
        # There is no supported live fallback source. Report the entire
        # documented ORF setup even when the source selector is still blank,
        # so the operator sees all required inputs in one preflight instead
        # of discovering them piecemeal across multiple blocked runs.
        if source_kind != "finra_orf_security_master":
            return ("FINRA_OTC_SOURCE_KIND", *orf_configuration)
        return orf_configuration
    names = list(CREDENTIALS.get(provider, ()))
    return tuple(dict.fromkeys(names))


# Keep the live acceptance surface explicit.  This is intentionally a
# provider-to-test-function manifest rather than a broad "module was imported"
# check: adding a provider to the registry must also add at least one bounded
# external read, or record a concrete reason why a live read is not applicable
# to that descriptor.  The unit wiring suite validates that every referenced
# function still exists in the checked-in live test files.
LIVE_PROVIDER_CASES = {
    "openfigi": (
        ("test_market_data_providers_live.py", "test_openfigi_keyless_mapping"),
        (
            "test_market_data_providers_live.py",
            "test_openfigi_keyless_profile_resolution",
        ),
        (
            "test_market_data_providers_live.py",
            "test_openfigi_keyless_account_usage_snapshot",
        ),
    ),
    "edgar": (
        ("test_market_data_providers_live.py", "test_sec_edgar_keyless_profile"),
        ("test_market_data_providers_live.py", "test_sec_edgar_keyless_search"),
        (
            "test_market_data_providers_live.py",
            "test_sec_edgar_credentialed_filings_and_company_facts",
        ),
        (
            "test_market_data_providers_live.py",
            "test_sec_edgar_full_ticker_exchange_directory_pagination_is_complete",
        ),
        (
            "test_market_data_providers_live.py",
            "test_sec_edgar_complete_unique_issuer_cik_directory_pagination_is_complete",
        ),
    ),
    "nasdaq": (
        # Both official Nasdaq files are one two-request source snapshot. The
        # full pagination case below is the sole manifest case so the local
        # two-requests/day cap cannot be consumed twice by duplicate cold
        # reads in the same acceptance run.
        (
            "test_market_data_providers_live.py",
            "test_nasdaq_trader_full_directory_pagination_is_complete",
        ),
    ),
    "cta_plan": (
        # The full raw Tape A/B source is exactly one live case: directory
        # index plus the newest published daily file (two admitted requests).
        (
            "test_market_data_providers_live.py",
            "test_cta_plan_latest_tape_ab_symbol_file_is_complete",
        ),
    ),
    "binance": (
        ("test_market_data_providers_live.py", "test_binance_keyless_crypto_history"),
        (
            "test_market_data_providers_live.py",
            "test_binance_keyless_bounded_daily_history",
        ),
        (
            "test_market_data_providers_live.py",
            "test_binance_keyless_account_usage_snapshot",
        ),
    ),
    "coinbase": (
        ("test_market_data_providers_live.py", "test_coinbase_keyless_crypto_history"),
        (
            "test_market_data_providers_live.py",
            "test_coinbase_keyless_history_quote_and_usd_products",
        ),
    ),
    "kraken": (
        ("test_market_data_providers_live.py", "test_kraken_keyless_crypto_history"),
    ),
    "alpaca": (
        ("test_market_data_providers_live.py", "test_alpaca_credentialed_history"),
        (
            "test_market_data_providers_live.py",
            "test_alpaca_credentialed_intraday_history",
        ),
        ("test_market_data_providers_live.py", "test_alpaca_credentialed_latest_price"),
        (
            "test_market_data_providers_live.py",
            "test_alpaca_credentialed_account_usage_snapshot",
        ),
        ("test_market_data_providers_live.py", "test_alpaca_credentialed_profile"),
        (
            "test_market_data_providers_live.py",
            "test_alpaca_credentialed_crypto_profile",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpaca_credentialed_assets_and_corporate_actions_page",
        ),
    ),
    "massive": (
        ("test_market_data_providers_live.py", "test_massive_credentialed_reference"),
        (
            "test_market_data_providers_live.py",
            "test_massive_credentialed_corporate_actions_complete",
        ),
        (
            "test_market_data_providers_live.py",
            "test_massive_credentialed_ipo_cursor_continuation",
        ),
        (
            "test_market_data_providers_live.py",
            "test_massive_credentialed_otc_ticker_universe_pagination_is_complete",
        ),
    ),
    "alpha_vantage": (
        ("test_market_data_providers_live.py", "test_alpha_vantage_credentialed_daily"),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_complete_listing_status",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_weekly",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_monthly",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_current_price",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_search",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_ipo_calendar",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_earnings_calendar",
        ),
        (
            "test_market_data_providers_live.py",
            "test_alpha_vantage_credentialed_earnings_history",
        ),
    ),
    "coingecko": (
        ("test_market_data_providers_live.py", "test_coingecko_credentialed_search"),
        (
            "test_market_data_providers_live.py",
            "test_coingecko_credentialed_profile_observes_id_resolution_request",
        ),
        (
            "test_market_data_providers_live.py",
            "test_coingecko_credentialed_universe_page",
        ),
    ),
    "fred": (
        (
            "test_market_data_providers_live.py",
            "test_fred_series_requires_persisted_data_rights_before_network_access",
        ),
        (
            "test_market_data_providers_live.py",
            "test_fred_credentialed_current_value",
        ),
    ),
    "finra": (
        (
            "test_market_data_providers_live.py",
            "test_finra_credentialed_short_interest",
        ),
        (
            "test_market_data_providers_live.py",
            "test_finra_credentialed_otc_daily_list",
        ),
    ),
    "finra_otc_directory": (
        (
            "test_market_data_providers_live.py",
            "test_finra_otc_directory_credentialed_source",
        ),
    ),
    "tiingo": (
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
    ),
    "twelve_data": (
        # Refresh both native counters before any market-data read. The
        # endpoint is quota-charged, but its exact post-call snapshot safely
        # establishes the matching fixed-minute credit and UTC-day request
        # windows for the rest of this bounded suite.
        (
            "test_market_data_providers_live.py",
            "test_twelve_data_credentialed_account_usage_snapshot",
        ),
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
    ),
    "finnhub": (
        (
            "test_market_data_providers_live.py",
            "test_finnhub_credentialed_account_usage_snapshot",
        ),
        (
            "test_market_data_providers_live.py",
            "test_finnhub_credentialed_company_profile",
        ),
    ),
    "marketstack": (
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
        (
            "test_market_data_providers_live.py",
            "test_marketstack_credentialed_exchange_ticker_pages",
        ),
    ),
    "eodhd": (
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
        (
            "test_market_data_providers_live.py",
            "test_eodhd_credentialed_delayed_quote",
        ),
        (
            "test_market_data_providers_live.py",
            "test_eodhd_credentialed_account_usage_snapshot",
        ),
        (
            "test_market_data_providers_live.py",
            "test_eodhd_free_plan_profile_entitlement_is_explicit",
        ),
    ),
    "fmp": (
        (
            "test_market_data_providers_live.py",
            "test_fmp_credentialed_account_usage_snapshot",
        ),
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
        (
            "test_market_data_providers_live.py",
            "test_fmp_long_history_is_paginated_without_gaps",
        ),
    ),
    "tradier": (
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
    ),
    "marketdata_app": (
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
        (
            "test_market_data_providers_live.py",
            "test_marketdata_app_credentialed_option_surface",
        ),
        (
            "test_market_data_providers_live.py",
            "test_marketdata_app_credentialed_option_quote_history",
        ),
        (
            "test_market_data_providers_live.py",
            "test_marketdata_app_response_priced_option_history_is_blocked_without_bound",
        ),
        (
            "test_market_data_providers_live.py",
            "test_marketdata_app_credentialed_account_usage_snapshot",
        ),
        (
            "test_market_data_providers_live.py",
            "test_marketdata_app_credentialed_latest_price",
        ),
        (
            "test_market_data_providers_live.py",
            "test_marketdata_app_credentialed_intraday_history",
        ),
    ),
    "ibkr": (
        (
            "test_market_data_providers_live.py",
            "test_ibkr_read_only_gateway_profile_history_and_snapshot",
        ),
    ),
    "xstocks": (
        ("test_tokenized_providers_live.py", "test_xstocks_account_usage_snapshot"),
        ("test_tokenized_providers_live.py", "test_xstocks_public_asset_and_price"),
        ("test_tokenized_providers_live.py", "test_xstocks_public_corporate_actions"),
    ),
    "robinhood_tokens": (
        ("test_tokenized_providers_live.py", "test_robinhood_public_asset_and_price"),
        ("test_tokenized_providers_live.py", "test_robinhood_public_corporate_actions"),
    ),
    "bybit_xstocks": (
        (
            "test_tokenized_providers_live.py",
            "test_bybit_public_xstocks_asset_and_price",
        ),
        (
            "test_tokenized_providers_live.py",
            "test_bybit_public_xstocks_cursor_page",
        ),
    ),
    "gate_tradfi": (
        (
            "test_tokenized_providers_live.py",
            "test_gate_public_tradfi_asset_and_orderbook",
        ),
    ),
    "kraken_xstocks": (
        (
            "test_tokenized_providers_live.py",
            "test_kraken_public_xstocks_asset_and_ticker",
        ),
    ),
    "dinari": (
        (
            "test_tokenized_providers_live.py",
            "test_dinari_credentialed_stock_metadata_price_quote_history_and_news",
        ),
    ),
    "ondo_global_markets": (
        (
            "test_tokenized_providers_live.py",
            "test_ondo_credentialed_metadata_price_market_summary_and_ohlc",
        ),
    ),
}

# Dinari Sandbox has an explicitly approved one-read-per-UTC-day canary policy.
# Its normal multi-operation manifest is intentionally not executable until
# Dinari publishes an account-specific quota/reset and operation-cost contract.
DINARI_CANARY_CASE = (
    "test_tokenized_providers_live.py",
    "test_dinari_credentialed_stock_metadata_price_quote_history_and_news",
)
DINARI_CANARY_OPERATION = "discover_tokenized_assets"
DINARI_CANARY_SAFETY_REASON = "intentional_no_request_policy: Sandbox numeric quota and operation-cost map remain unverified"

# Case-scoped live runs are supported only where the exact request family is
# pinned here. This makes narrow runs quota-safe while preserving the mapping
# from a test to the provider operation it is intended to prove.
LIVE_CASE_OPERATIONS = {
    "openfigi": {
        "test_openfigi_keyless_mapping": {"fetch_stable_identifiers"},
        "test_openfigi_keyless_profile_resolution": {"resolve_instrument_profile"},
        "test_openfigi_keyless_account_usage_snapshot": {"fetch_account_usage"},
    },
    "edgar": {
        "test_sec_edgar_keyless_profile": {"get_instrument_profile"},
        "test_sec_edgar_keyless_search": {"search_instruments"},
        "test_sec_edgar_credentialed_filings_and_company_facts": {
            "fetch_instrument_events",
            "fetch_fundamental_facts",
            "fetch_ipo_pipeline_events",
        },
        "test_sec_edgar_full_ticker_exchange_directory_pagination_is_complete": {
            "discover_universe_page"
        },
        "test_sec_edgar_complete_unique_issuer_cik_directory_pagination_is_complete": {
            "discover_issuer_ciks_page"
        },
    },
    "nasdaq": {
        "test_nasdaq_trader_full_directory_pagination_is_complete": {
            "discover_universe_page"
        },
    },
    "cta_plan": {
        "test_cta_plan_latest_tape_ab_symbol_file_is_complete": {
            "discover_universe_page"
        },
    },
    "binance": {
        "test_binance_keyless_crypto_history": {
            "fetch_latest_ohlcv",
            "get_current_price",
            "discover_universe_page",
        },
        "test_binance_keyless_bounded_daily_history": {"fetch_ohlcv"},
        "test_binance_keyless_account_usage_snapshot": {"fetch_account_usage"},
    },
    "alpha_vantage": {
        "test_alpha_vantage_credentialed_daily": {"fetch_ohlcv"},
        "test_alpha_vantage_credentialed_complete_listing_status": {
            "discover_universe_page"
        },
        "test_alpha_vantage_credentialed_weekly": {"fetch_ohlcv"},
        "test_alpha_vantage_credentialed_monthly": {"fetch_ohlcv"},
        "test_alpha_vantage_credentialed_current_price": {"get_current_price"},
        "test_alpha_vantage_credentialed_search": {"search_instruments"},
        "test_alpha_vantage_credentialed_ipo_calendar": {"fetch_market_events"},
        "test_alpha_vantage_credentialed_earnings_calendar": {
            "fetch_earnings_calendar"
        },
        "test_alpha_vantage_credentialed_earnings_history": {"fetch_instrument_events"},
    },
    "marketdata_app": {
        "test_optional_credentialed_provider_small_read": {"fetch_ohlcv"},
        "test_marketdata_app_credentialed_option_surface": {
            "list_option_expirations",
            "fetch_option_chain",
        },
        "test_marketdata_app_credentialed_option_quote_history": {
            "list_option_expirations",
            "fetch_option_chain",
            "fetch_option_quote_history",
        },
        "test_marketdata_app_credentialed_account_usage_snapshot": {
            "fetch_account_usage"
        },
        "test_marketdata_app_credentialed_latest_price": {"get_current_price"},
        "test_marketdata_app_credentialed_intraday_history": {"fetch_ohlcv"},
    },
    "coinbase": {
        "test_coinbase_keyless_crypto_history": {"fetch_ohlcv"},
        "test_coinbase_keyless_history_quote_and_usd_products": {
            "fetch_ohlcv",
            "get_current_price",
            "discover_universe_page",
        },
    },
    "kraken": {
        "test_kraken_keyless_crypto_history": {
            "fetch_ohlcv",
            "fetch_latest_ohlcv",
            "get_current_price",
            "discover_universe_page",
        },
    },
    "alpaca": {
        "test_alpaca_credentialed_history": {"fetch_ohlcv"},
        "test_alpaca_credentialed_intraday_history": {"fetch_ohlcv"},
        "test_alpaca_credentialed_latest_price": {"get_current_price"},
        "test_alpaca_credentialed_account_usage_snapshot": {"fetch_account_usage"},
        "test_alpaca_credentialed_profile": {"get_instrument_profile"},
        "test_alpaca_credentialed_crypto_profile": {"get_instrument_profile"},
        "test_alpaca_credentialed_assets_and_corporate_actions_page": {
            "discover_universe_page",
            "fetch_instrument_events",
        },
    },
    "massive": {
        "test_massive_credentialed_reference": {
            "get_instrument_profile",
            "fetch_market_events",
            "search_instruments",
            "fetch_market_holidays",
            "fetch_ohlcv",
        },
        "test_massive_credentialed_corporate_actions_complete": {
            "fetch_instrument_events",
        },
        "test_massive_credentialed_ipo_cursor_continuation": {
            "fetch_market_events",
        },
        "test_massive_credentialed_otc_ticker_universe_pagination_is_complete": {
            "discover_universe_page",
        },
    },
    "coingecko": {
        "test_coingecko_credentialed_search": {"search_instruments"},
        "test_coingecko_credentialed_profile_observes_id_resolution_request": {
            "get_instrument_profile"
        },
        "test_coingecko_credentialed_universe_page": {"discover_universe_page"},
    },
    "fred": {
        "test_fred_series_requires_persisted_data_rights_before_network_access": {
            "fetch_ohlcv"
        },
        "test_fred_credentialed_current_value": {"get_current_price"},
    },
    "marketstack": {
        "test_marketstack_credentialed_exchange_ticker_pages": {
            "discover_universe_page"
        },
        "test_optional_credentialed_provider_small_read": {
            "fetch_ohlcv",
            "get_current_price",
        },
    },
    "eodhd": {
        "test_eodhd_credentialed_delayed_quote": {"get_current_price"},
        # This parameterized case makes three EOD-history requests (daily,
        # weekly, monthly), then one latest-price and one universe-page read.
        # Name every operation so case preflight accounts for the whole test.
        "test_optional_credentialed_provider_small_read": {
            "fetch_ohlcv",
            "get_current_price",
            "discover_universe_page",
        },
        "test_eodhd_credentialed_account_usage_snapshot": {"fetch_account_usage"},
        "test_eodhd_free_plan_profile_entitlement_is_explicit": {
            "get_instrument_profile"
        },
    },
    "finra_otc_directory": {
        "test_finra_otc_directory_credentialed_source": {"discover_universe_page"},
    },
    "finra": {
        "test_finra_credentialed_short_interest": {"fetch_short_interest"},
        "test_finra_credentialed_otc_daily_list": {"fetch_market_events"},
    },
    "tiingo": {
        "test_optional_credentialed_provider_small_read": {
            "fetch_ohlcv",
            "get_instrument_profile",
            "get_current_price",
            "search_instruments",
        },
    },
    "twelve_data": {
        "test_optional_credentialed_provider_small_read": {
            "fetch_ohlcv",
            "get_current_price",
            "search_instruments",
            "discover_universe_page",
        },
        "test_twelve_data_credentialed_account_usage_snapshot": {"fetch_account_usage"},
    },
    "finnhub": {
        "test_finnhub_credentialed_account_usage_snapshot": {"fetch_account_usage"},
        "test_finnhub_credentialed_company_profile": {
            "get_instrument_profile",
            "fetch_instrument_events",
            "search_instruments",
            "discover_universe_page",
            "fetch_market_events",
            "get_current_price",
        },
    },
    "fmp": {
        "test_fmp_credentialed_account_usage_snapshot": {"fetch_account_usage"},
        "test_optional_credentialed_provider_small_read": {
            "fetch_ohlcv",
            "get_instrument_profile",
            "fetch_market_events",
            "get_current_price",
        },
        "test_fmp_long_history_is_paginated_without_gaps": {"fetch_ohlcv"},
    },
    "tradier": {
        "test_optional_credentialed_provider_small_read": {
            "fetch_ohlcv",
            "list_option_expirations",
            "fetch_option_chain",
        },
    },
    "ibkr": {
        "test_ibkr_read_only_gateway_profile_history_and_snapshot": {
            "get_instrument_profile",
            "fetch_ohlcv",
            "get_current_price",
        },
    },
    "xstocks": {
        "test_xstocks_account_usage_snapshot": {"fetch_account_usage"},
        "test_xstocks_public_asset_and_price": {
            "discover_tokenized_assets",
            "get_tokenized_asset",
            "get_tokenized_price",
        },
        "test_xstocks_public_corporate_actions": {"fetch_tokenized_corporate_actions"},
    },
    "robinhood_tokens": {
        "test_robinhood_public_asset_and_price": {
            "discover_tokenized_assets",
            "get_tokenized_asset",
            "get_tokenized_price",
        },
        "test_robinhood_public_corporate_actions": {
            "fetch_tokenized_corporate_actions"
        },
    },
    "bybit_xstocks": {
        "test_bybit_public_xstocks_asset_and_price": {
            "discover_tokenized_assets",
            "get_tokenized_asset",
            "get_tokenized_price",
        },
        "test_bybit_public_xstocks_cursor_page": {"discover_tokenized_page"},
    },
    "gate_tradfi": {
        "test_gate_public_tradfi_asset_and_orderbook": {
            "discover_tokenized_assets",
            "get_tokenized_asset",
            "get_tokenized_price",
        },
    },
    "kraken_xstocks": {
        "test_kraken_public_xstocks_asset_and_ticker": {
            "discover_tokenized_assets",
            "get_tokenized_asset",
            "get_tokenized_price",
        },
    },
    "dinari": {
        "test_dinari_credentialed_stock_metadata_price_quote_history_and_news": {
            "discover_tokenized_assets",
            "get_tokenized_asset",
            "get_tokenized_price",
            "get_tokenized_quote",
            "fetch_tokenized_historical_prices",
            "fetch_tokenized_news",
            "fetch_tokenized_dividends",
            "fetch_tokenized_splits",
            "fetch_tokenized_corporate_actions",
        },
    },
    "ondo_global_markets": {
        "test_ondo_credentialed_metadata_price_market_summary_and_ohlc": {
            "discover_tokenized_assets",
            "get_tokenized_price",
            "fetch_tokenized_market_data",
            "fetch_tokenized_ohlc",
            "fetch_tokenized_historical_prices",
        },
    },
}

# These registry entries are deliberately visible to administrators but do
# not represent an external market-data read that this provider-platform live
# runner can safely execute.  Each exclusion is explicit so it cannot become
# an accidental "forgot to add a test" escape hatch.
LIVE_PROVIDER_EXCLUSIONS = {
    "etf_holdings_internal": "internal issuer/SEC holdings ingestion; live adapter coverage is owned by the ETF workstream",
    "yfinance": "legacy unofficial compatibility provider; disabled by default and excluded from API-first acceptance",
    "alpaca_itn": "descriptor-only authorized-participant tokenization network; no concrete adapter or public read entitlement",
}

# Each provider in this map must produce measured, successful HTTP usage for
# every listed operation in the current runner invocation. These names are
# the stable capability-level labels emitted by the adapter probes and live
# usage ledger; a green pytest count alone is never external evidence.
LIVE_REQUIRED_OPERATIONS = {
    "openfigi": {
        "fetch_stable_identifiers",
        "resolve_instrument_profile",
        "fetch_account_usage",
    },
    "edgar": {
        "search_instruments",
        "get_instrument_profile",
        "fetch_instrument_events",
        "fetch_fundamental_facts",
        "fetch_ipo_pipeline_events",
        "discover_universe_page",
        "discover_issuer_ciks_page",
    },
    "nasdaq": {"discover_universe_page"},
    "cta_plan": {"discover_universe_page"},
    "binance": {
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "discover_universe_page",
        "fetch_account_usage",
    },
    "coinbase": {"fetch_ohlcv", "get_current_price", "discover_universe_page"},
    "kraken": {
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "discover_universe_page",
    },
    "alpaca": {
        "fetch_ohlcv",
        "get_current_price",
        "fetch_account_usage",
        "get_instrument_profile",
        "discover_universe_page",
        "fetch_instrument_events",
    },
    "massive": {
        "get_instrument_profile",
        "search_instruments",
        "fetch_market_events",
        "fetch_instrument_events",
        "fetch_ohlcv",
        "fetch_market_holidays",
        "discover_universe_page",
    },
    "alpha_vantage": {
        "fetch_ohlcv",
        "get_current_price",
        "search_instruments",
        "fetch_market_events",
        "fetch_earnings_calendar",
        "fetch_instrument_events",
        "discover_universe_page",
    },
    "coingecko": {
        "search_instruments",
        "get_instrument_profile",
        "discover_universe_page",
    },
    "fred": {"fetch_ohlcv", "get_current_price"},
    "finra": {"fetch_short_interest", "fetch_market_events"},
    "finra_otc_directory": {"discover_universe_page"},
    "tiingo": {
        "fetch_ohlcv",
        "get_instrument_profile",
        "get_current_price",
        "search_instruments",
    },
    "twelve_data": {
        "fetch_ohlcv",
        "search_instruments",
        "get_current_price",
        "discover_universe_page",
        "fetch_account_usage",
    },
    # The credentialed Finnhub probe exercises both the profile and the
    # instrument/market-event surfaces. Keep every metered operation in the
    # required set so a green run cannot silently omit either request.
    "finnhub": {
        "fetch_account_usage",
        "search_instruments",
        "get_instrument_profile",
        "fetch_instrument_events",
        "fetch_market_events",
        "discover_universe_page",
        "get_current_price",
    },
    "marketstack": {
        "fetch_ohlcv",
        "get_current_price",
        "discover_universe_page",
    },
    "eodhd": {
        "fetch_ohlcv",
        "get_instrument_profile",
        "get_current_price",
        "discover_universe_page",
        "fetch_account_usage",
    },
    "fmp": {
        "fetch_ohlcv",
        "get_instrument_profile",
        "fetch_market_events",
        "get_current_price",
        "fetch_account_usage",
    },
    "tradier": {"fetch_ohlcv", "list_option_expirations", "fetch_option_chain"},
    "marketdata_app": {
        "fetch_ohlcv",
        "get_current_price",
        "list_option_expirations",
        "fetch_option_chain",
        "fetch_option_quote_history",
        "fetch_account_usage",
    },
    "ibkr": {"get_instrument_profile", "fetch_ohlcv", "get_current_price"},
    "xstocks": {
        "fetch_account_usage",
        "discover_tokenized_assets",
        "get_tokenized_asset",
        "get_tokenized_price",
        "fetch_tokenized_corporate_actions",
    },
    "robinhood_tokens": {
        "discover_tokenized_assets",
        "get_tokenized_asset",
        "get_tokenized_price",
        "fetch_tokenized_corporate_actions",
    },
    "bybit_xstocks": {
        "discover_tokenized_assets",
        "discover_tokenized_page",
        "get_tokenized_asset",
        "get_tokenized_price",
    },
    "gate_tradfi": {
        "discover_tokenized_assets",
        "get_tokenized_asset",
        "get_tokenized_price",
    },
    "kraken_xstocks": {
        "discover_tokenized_assets",
        "get_tokenized_asset",
        "get_tokenized_price",
    },
    "dinari": {
        "discover_tokenized_assets",
        "get_tokenized_asset",
        "get_tokenized_price",
        "get_tokenized_quote",
        "fetch_tokenized_historical_prices",
        "fetch_tokenized_news",
        "fetch_tokenized_dividends",
        "fetch_tokenized_splits",
        "fetch_tokenized_corporate_actions",
    },
    "ondo_global_markets": {
        "discover_tokenized_assets",
        "get_tokenized_price",
        "fetch_tokenized_market_data",
        "fetch_tokenized_ohlc",
        "fetch_tokenized_historical_prices",
    },
}

# Public adapter methods are not automatically equivalent merely because they
# return a similar model.  These aliases are explicit reviewed classifications
# for methods whose implementation delegates to another metered operation or
# whose job is local contract math.  The inventory checker below fails closed
# when a new public provider method is added without one of these entries, a
# required live operation, or an explicit disposition.
LIVE_OPERATION_METHOD_ALIASES = {
    # All concrete fetch_latest_ohlcv implementations are bounded wrappers
    # around fetch_ohlcv.  The direct latest-window contract is therefore
    # covered by the underlying history case without pretending it is a second
    # provider request.  Providers may promote this to a distinct operation
    # later if their endpoint is changed to a dedicated latest-bars API.
    "fetch_latest_ohlcv": "fetch_ohlcv",
    # FINRA's page-aware Daily List method is the resumable implementation of
    # the same metered market-event capability. The bounded live case invokes
    # the compatibility method, which delegates its complete-page request to
    # this adapter; cursor progression is covered by the provider/service
    # fixture suite without inventing a larger live query budget.
    "fetch_market_events_page": "fetch_market_events",
    # FINRA short-interest reads are resumable pages of the same synchronous
    # dataset operation; the runtime meters every page under the existing
    # provider-specific request and byte dimensions.
    "fetch_short_interest_page": "fetch_short_interest",
    # The one-page event adapter is the bounded live evidence surface; the
    # service-level ingestion loop persists its cursor and resumes until the
    # direct full-history compatibility method reaches completion.
    "fetch_instrument_events_page": "fetch_instrument_events",
    # Dinari's page-aware corporate-action adapter is the resumable form of
    # the same provider operation; its tuple carries the opaque continuation
    # cursor but does not create a second upstream capability.
    "fetch_tokenized_corporate_actions_page": "fetch_tokenized_corporate_actions",
}
LIVE_LOCAL_PROVIDER_METHODS = frozenset(
    {
        "latest_window_start",
        "supported_discovery_types",
    }
)

# Service-level operations do not belong to a provider class, but their
# provider-facing request path must remain explicit in the usage contract.
# They are aliases until a bounded service integration case is added.
LIVE_SERVICE_OPERATION_ALIASES = {
    "fetch_rfr_ohlcv": "fetch_ohlcv",
    "bulk_fetch": "fetch_ohlcv",
    "reconcile_universe_page": "discover_universe_page",
}

# Bounded live cases may supply a response-dependent reservation override to
# the test helper. The preflight uses the same reviewed upper bound instead of
# rejecting the operation merely because the generic provider profile cannot
# safely assign a fixed cost. These are test-case bounds, not provider defaults
# or runtime routing entitlements.
LIVE_OPERATION_COST_OVERRIDES = {
    "binance": {
        # The manifest calls the documented latest-candle wrapper with one
        # daily bar.  The provider-specific estimator reserves the actual
        # request weight (including the wrapper's lookback padding); this is
        # a test-case bound, not a runtime default for arbitrary ranges.
        "fetch_latest_ohlcv": 2,
        # This exact 30-day daily range fits in one 1,000-candle page, and
        # Binance charges two request-weight units per /klines request. The
        # adapter stops on a short page; wider ranges use a caller estimate.
        "fetch_ohlcv": 2,
    },
    "coinbase": {
        # The bounded manifest requests one daily candle.  Coinbase's
        # estimator is one 300-candle page for that exact case.
        "fetch_latest_ohlcv": 1,
        "fetch_ohlcv": 1,
    },
    "kraken": {
        # Bounded recent daily-history test windows fit Kraken's single
        # recent-720 OHLC response. This is not a claim that REST paginates
        # older history.
        "fetch_ohlcv": 1,
        "fetch_latest_ohlcv": 1,
    },
    "coingecko": {
        # One /coins/markets page; the Demo monthly allowance is credit-based.
        "discover_universe_page": 1,
    },
    "fred": {"get_current_price": 1},
    "alpaca": {
        # The manifest exercises a five-day daily range and a five-day
        # five-minute range. The latter can span at most two 1,000-bar pages
        # under the bounded test window; both cases pass this same conservative
        # upper bound to the live reservation helper. The event live case uses
        # exactly one page; the ingestion service persists and resumes later
        # pages. These are test-case bounds, not a claim about Alpaca's
        # provider-wide allowance.
        "fetch_ohlcv": 2,
        "fetch_instrument_events": 1,
    },
    "massive": {
        # Each dedicated pagination case makes two provider requests: the
        # split and dividend feeds, or two one-row IPO cursor pages.
        "fetch_instrument_events": 2,
        "fetch_market_events": 2,
        # The manifest's 30-day daily history is one page under Massive's
        # 50,000-aggregate response cap.  Wider/different ranges must use the
        # provider estimator supplied by the caller instead of this bound.
        "fetch_ohlcv": 1,
    },
    "marketstack": {
        # The generic credentialed case is a five-day daily EOD range and fits
        # one 100-row response page.  This does not authorize arbitrary
        # history windows.
        "fetch_ohlcv": 1,
    },
    "marketdata_app": {
        # The bounded five-day date-granular probes can span six inclusive
        # calendar dates at a UTC boundary.  Reserve two credits so the
        # runner's preflight cannot under-account the test's own estimator.
        "fetch_ohlcv": 2,
        "fetch_option_chain": 20,
        # The positive live case uses a two-day single-contract range; the
        # reviewed inclusive date-span estimator reserves one credit. Runtime
        # callers must still calculate their own bound for arbitrary ranges.
        "fetch_option_quote_history": 1,
    },
}

# Additional operations exercised by a single compound manifest case. The
# operation-cost override is the conservative cost for each invocation; this
# map records how many times that case invokes the same operation.
LIVE_CASE_OPERATION_MULTIPLIERS = {
    "eodhd": {
        "test_optional_credentialed_provider_small_read": {"fetch_ohlcv": 3},
    },
    "twelve_data": {
        "test_optional_credentialed_provider_small_read": {"fetch_ohlcv": 2},
    },
    "coingecko": {
        "test_coingecko_credentialed_profile_observes_id_resolution_request": {
            "get_instrument_profile": 2,
        },
    },
    "xstocks": {
        "test_xstocks_public_asset_and_price": {"get_tokenized_price": 2},
    },
    "robinhood_tokens": {
        "test_robinhood_public_asset_and_price": {"get_tokenized_price": 2},
    },
    "bybit_xstocks": {
        "test_bybit_public_xstocks_asset_and_price": {"get_tokenized_price": 2},
        "test_bybit_public_xstocks_cursor_page": {"discover_tokenized_page": 2},
    },
    "gate_tradfi": {
        "test_gate_public_tradfi_asset_and_orderbook": {
            "get_tokenized_asset": 5,
            "get_tokenized_price": 10,
        },
    },
    "kraken_xstocks": {
        "test_kraken_public_xstocks_asset_and_ticker": {"get_tokenized_price": 2},
    },
    "dinari": {
        "test_dinari_credentialed_stock_metadata_price_quote_history_and_news": {
            "fetch_tokenized_historical_prices": 4,
            "fetch_tokenized_splits": 2,
            "fetch_tokenized_corporate_actions": 3,
        },
    },
    "ondo_global_markets": {
        "test_ondo_credentialed_metadata_price_market_summary_and_ohlc": {
            "get_tokenized_price": 2,
            "fetch_tokenized_market_data": 2,
            "fetch_tokenized_ohlc": 2,
            "fetch_tokenized_historical_prices": 2,
        },
    },
}


def _full_matrix_operation_multipliers() -> dict[str, dict[str, int]]:
    """Derive aggregate operation counts from the complete live-case manifest."""

    totals: dict[str, dict[str, int]] = {}
    for provider, cases in LIVE_PROVIDER_CASES.items():
        provider_totals = totals.setdefault(provider, {})
        for _path, case_name in cases:
            operations = LIVE_CASE_OPERATIONS.get(provider, {}).get(case_name, set())
            case_multipliers = LIVE_CASE_OPERATION_MULTIPLIERS.get(provider, {}).get(
                case_name, {}
            )
            for operation in operations:
                provider_totals[operation] = provider_totals.get(operation, 0) + int(
                    case_multipliers.get(operation, 1)
                )
    return totals


# Full-matrix quota admission reserves the sum of every operation represented
# by every selected case, including repeated reads. Individual HTTP sends still
# make their own atomic reservations immediately before transport.
LIVE_MATRIX_OPERATION_MULTIPLIERS = _full_matrix_operation_multipliers()

# Capability-level operations not executed by the bounded matrix are recorded
# explicitly instead of being mistaken for coverage.  These are current
# acceptance gaps (or deliberate policy blocks), not successful live evidence;
# each entry must be promoted to LIVE_REQUIRED_OPERATIONS or separately
# approved before the branch can be accepted as capability-exhaustive.
LIVE_OPERATION_DISPOSITIONS = {
    "edgar": {},
    "fred": {},
    "coingecko": {
        "fetch_account_usage": "expected_entitlement_denial: CoinGecko /key is Pro-only; the configured Demo plan tracks usage in the durable application ledger",
    },
    "finra": {
        # These are transport legs of one optional generic helper, not
        # independent market-data capabilities. The admitted FINRA surfaces
        # are the required synchronous short-interest and Daily List
        # operations, which split on provider partitions/date windows and
        # preserve every fetched page. Keep the helper fail-closed until a
        # concrete service owns durable streaming and tranche recovery.
        "submit_async_dataset": "transport_not_applicable: optional generic async transport leg; no admitted dataset service invokes it",
        "poll_async_dataset": "transport_not_applicable: optional generic async transport leg; no admitted dataset service invokes it",
        "download_async_result": "transport_not_applicable: optional generic async transport leg; no admitted dataset service invokes it",
    },
    "massive": {},
    "tiingo": {},
    "twelve_data": {},
    "finnhub": {
        "fetch_ohlcv": "expected_entitlement_denial: the observed free-plan key returned HTTP 403 for the stock-candle endpoint",
    },
    "eodhd": {},
    "fmp": {
        "discover_universe_page": (
            "expected_entitlement_denial: the configured Basic key returned HTTP 402 from "
            "stable/stock-list during the bounded live suite; keep this capability disabled "
            "until account entitlement is confirmed"
        ),
    },
    "tradier": {
        "search_instruments": "deferred by user: Tradier account/API integration is not admitted",
        "get_current_price": "deferred by user: Tradier account/API integration is not admitted",
    },
    "marketdata_app": {
        # Current price and historical option quotes have dedicated bounded
        # cases. The latter is reserved with the inclusive date-span estimator
        # rather than an invented fixed request cost.
    },
    "ibkr": {
        "search_instruments": "deferred by user: IBKR account/session integration is not admitted",
        "futures_history": "deferred by user: IBKR account/session integration is not admitted",
    },
    "binance": {},
    "ondo_global_markets": {
        "get_tokenized_asset": "deferred by user: Ondo onboarding/legal review is not admitted",
    },
}

# These are not missing capability implementations. They are explicit
# provider/source safety outcomes whose live case is intentionally prevented
# from reaching transport or is unnecessary for the selected source path.
# They remain separate from LIVE_OPERATION_DISPOSITIONS because the operation
# can become a normal required live read once the control is admitted.
LIVE_PROVIDER_SAFETY_DISPOSITIONS = {
    "fred": "intentional_no_request_policy: FRED quota limits and reset remain unverified",
    "coinbase": "intentional_no_request_policy: Coinbase keyless live acceptance cases are incomplete",
    "dinari": "intentional_no_request_policy: Sandbox numeric quota and operation-cost map remain unverified",
    "xstocks": "intentional_no_request_policy: deployment jurisdiction evidence is unresolved",
    "bybit_xstocks": "intentional_no_request_policy: provider-restricted deployment egress evidence is unresolved",
}


def owner_accepts_provider_terms_risk() -> bool:
    """Read the final owner decision with the same default as application config."""

    raw = os.getenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes"}
    backend_root = ROOT / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from app.config import settings

    return bool(settings.PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK)


def active_live_provider_safety_dispositions() -> dict[str, str]:
    """Apply the owner's recorded private-use decision without hiding access limits."""

    dispositions = dict(LIVE_PROVIDER_SAFETY_DISPOSITIONS)
    if owner_accepts_provider_terms_risk():
        dispositions.pop("fred", None)
        dispositions.pop("coinbase", None)
        dispositions.pop("xstocks", None)
    return dispositions


def active_live_no_request_cases() -> dict[tuple[str, str, str], str]:
    """Apply owner terms-risk approval to live-case request classifications."""

    cases = dict(LIVE_NO_REQUEST_CASES)
    if owner_accepts_provider_terms_risk():
        cases.pop(
            (
                "fred",
                "test_market_data_providers_live.py",
                "test_fred_series_requires_persisted_data_rights_before_network_access",
            ),
            None,
        )
        cases.pop(
            (
                "fred",
                "test_market_data_providers_live.py",
                "test_fred_credentialed_current_value",
            ),
            None,
        )
        cases.pop(
            (
                "coinbase",
                "test_market_data_providers_live.py",
                "test_coinbase_keyless_crypto_history",
            ),
            None,
        )
        cases.pop(
            (
                "coinbase",
                "test_market_data_providers_live.py",
                "test_coinbase_keyless_history_quote_and_usd_products",
            ),
            None,
        )
    return cases


# Dispositions are deliberately split into two classes:
#
# * ``live_required`` (and the unresolved ``deferred``/``blocked`` forms)
#   require a measured, successful live operation before evidence is complete.
# * ``expected_entitlement_denial``, ``intentional_no_request_policy``, and
#   ``human_deferred`` are explicit, reviewable non-data outcomes.  They stay
#   visible in receipts but do not get misreported as unresolved capability
#   coverage.  The provider-level deferral still has to be present in the
#   active workstream plan before it is excluded from a full run.
#
# Keep this list intentionally small and canonical.  ``live_operation_*``
# normalizes the legacy ``policy_block`` prefix so old hand-written reasons
# cannot create a fourth, ambiguous no-request category.
LIVE_COVERED_DISPOSITION_KINDS = frozenset(
    {
        "expected_entitlement_denial",
        "human_deferred",
        "intentional_no_request_policy",
        "transport_not_applicable",
    }
)

LIVE_DISPOSITION_KINDS = frozenset(
    {
        "blocked",
        "deferred",
        "expected_entitlement_denial",
        "human_deferred",
        "intentional_no_request_policy",
        "live_required",
        "transport_not_applicable",
    }
)


def live_operation_disposition_kind(disposition: str) -> str:
    """Normalize the explicit status prefix used in live coverage records."""

    prefix = str(disposition or "").split(":", 1)[0].strip().lower()
    if prefix == "deferred by user":
        return "human_deferred"
    if prefix in {"policy_block", "no_request_policy"}:
        # ``policy_block`` appeared in early receipts.  Treat it as the same
        # canonical class as the current explicit no-request policy status.
        return "intentional_no_request_policy"
    if prefix in LIVE_COVERED_DISPOSITION_KINDS:
        return prefix
    if prefix in {"deferred", "blocked"}:
        return prefix
    if prefix in {"live_required", "required_live"}:
        return "live_required"
    return "unclassified"


def _provider_public_method_names(provider: object) -> set[str]:
    """Return concrete provider methods that can cause external reads.

    Protocol methods in ``providers.base`` are intentionally ignored.  The
    concrete implementation classes (including the shared REST base used by
    the optional adapters) are inspected through their MRO so an inherited
    public method cannot silently escape the live-operation inventory.
    """

    names: set[str] = set()
    for implementation in type(provider).__mro__:
        if implementation.__module__ == "app.providers.base":
            continue
        for name, member in vars(implementation).items():
            if name.startswith("_") or name in LIVE_LOCAL_PROVIDER_METHODS:
                continue
            if inspect.isfunction(member) or inspect.ismethod(member):
                names.add(name)
    return names


def provider_method_inventory_errors() -> list[str]:
    """Ensure every concrete external provider method has a live disposition.

    This is deliberately a structural check.  It does not import credentials
    or call a provider.  The method aliases are explicit and are emitted in
    the live receipt so an alias cannot be confused with direct endpoint
    evidence.
    """

    backend_root = ROOT / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    try:
        from app.providers.registry import _PROVIDERS
    except Exception as exc:  # pragma: no cover - packaging/import failure
        return [f"provider method inventory unavailable: {type(exc).__name__}"]

    errors: list[str] = []
    for provider_name, provider in sorted(_PROVIDERS.items()):
        if provider_name in LIVE_PROVIDER_EXCLUSIONS:
            continue
        required = LIVE_REQUIRED_OPERATIONS.get(provider_name, set())
        dispositions = LIVE_OPERATION_DISPOSITIONS.get(provider_name, {})
        for method in sorted(_provider_public_method_names(provider)):
            if method in required or method in dispositions:
                continue
            alias = LIVE_OPERATION_METHOD_ALIASES.get(method)
            if alias is not None:
                if alias not in required and alias not in dispositions:
                    errors.append(
                        f"{provider_name}/{method} aliases untracked operation {alias}"
                    )
                continue
            errors.append(
                f"{provider_name}/{method} has no required live operation, alias, or disposition"
            )
    for operation, alias in sorted(LIVE_SERVICE_OPERATION_ALIASES.items()):
        if not operation.strip() or not alias.strip():
            errors.append(
                f"service operation alias is empty: {operation!r} -> {alias!r}"
            )
    return sorted(set(errors))


def live_matrix_inventory_errors() -> list[str]:
    """Return structural errors in the manifest/disposition inventory.

    This is intentionally pure and operates on the runner's declarative maps;
    it is safe to run before credentials, quota stores, or provider transports
    are touched.  A typo in a live-case or disposition map must fail closed,
    rather than silently weakening the full-run acceptance surface.
    """

    manifest_providers = set(LIVE_PROVIDER_CASES)
    required_providers = set(LIVE_REQUIRED_OPERATIONS)
    exclusion_providers = set(LIVE_PROVIDER_EXCLUSIONS)
    errors: list[str] = []

    if manifest_providers != required_providers:
        missing_required = sorted(manifest_providers - required_providers)
        orphan_required = sorted(required_providers - manifest_providers)
        if missing_required:
            errors.append(
                "providers missing LIVE_REQUIRED_OPERATIONS: "
                + ", ".join(missing_required)
            )
        if orphan_required:
            errors.append(
                "LIVE_REQUIRED_OPERATIONS has no manifest provider: "
                + ", ".join(orphan_required)
            )

    overlap = sorted(manifest_providers & exclusion_providers)
    if overlap:
        errors.append(
            "providers have both live cases and exclusions: " + ", ".join(overlap)
        )

    if DINARI_CANARY_CASE not in LIVE_PROVIDER_CASES.get("dinari", ()):
        errors.append("Dinari canary case is not present in the provider manifest")
    elif DINARI_CANARY_OPERATION not in LIVE_CASE_OPERATIONS.get("dinari", {}).get(
        DINARI_CANARY_CASE[1], set()
    ):
        errors.append("Dinari canary operation is not mapped to its manifest case")

    for provider, cases in sorted(LIVE_PROVIDER_CASES.items()):
        if not cases:
            errors.append(f"{provider} has no live manifest cases")
        elif len(set(cases)) != len(cases):
            errors.append(f"{provider} has duplicate live manifest cases")
    for provider, case_operations in sorted(LIVE_CASE_OPERATIONS.items()):
        manifest_names = {
            function_name
            for _relative_path, function_name in LIVE_PROVIDER_CASES.get(provider, ())
        }
        for function_name, operations in sorted(case_operations.items()):
            if function_name not in manifest_names:
                errors.append(
                    f"{provider} case-operation map references an unmanifested case: "
                    f"{function_name}"
                )
            if not operations or not operations <= LIVE_REQUIRED_OPERATIONS.get(
                provider, set()
            ):
                errors.append(
                    f"{provider}/{function_name} case-operation map is empty or "
                    "outside LIVE_REQUIRED_OPERATIONS"
                )
    no_request_keys = set(LIVE_NO_REQUEST_CASES)
    entitlement_denial_keys = set(LIVE_EXPECTED_ENTITLEMENT_DENIALS)
    for provider, cases in sorted(LIVE_PROVIDER_CASES.items()):
        mapped = LIVE_CASE_OPERATIONS.get(provider, {})
        for relative_path, function_name in cases:
            case_key = (provider, relative_path, function_name)
            if (
                function_name not in mapped
                and case_key not in no_request_keys
                and case_key not in entitlement_denial_keys
            ):
                errors.append(
                    f"{provider}/{function_name} has no reviewed case-operation or no-request mapping"
                )
    for provider, multipliers in sorted(LIVE_MATRIX_OPERATION_MULTIPLIERS.items()):
        for operation, count in sorted(multipliers.items()):
            if (
                operation not in LIVE_REQUIRED_OPERATIONS.get(provider, set())
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count < 1
            ):
                errors.append(
                    f"{provider}/{operation} has an invalid full-matrix operation multiplier"
                )
    for provider, cases in sorted(LIVE_CASE_OPERATION_MULTIPLIERS.items()):
        for function_name, multipliers in sorted(cases.items()):
            operations = LIVE_CASE_OPERATIONS.get(provider, {}).get(function_name)
            if operations is None:
                errors.append(
                    f"{provider}/{function_name} has multipliers without a case-operation map"
                )
                continue
            for operation, count in sorted(multipliers.items()):
                if (
                    operation not in operations
                    or isinstance(count, bool)
                    or not isinstance(count, int)
                    or count < 1
                ):
                    errors.append(
                        f"{provider}/{function_name}/{operation} has an invalid case operation multiplier"
                    )
    for provider, operations in sorted(LIVE_REQUIRED_OPERATIONS.items()):
        if not operations:
            errors.append(f"{provider} has no required live operations")
        mapped_operations = (
            set().union(*LIVE_CASE_OPERATIONS.get(provider, {}).values())
            if LIVE_CASE_OPERATIONS.get(provider)
            else set()
        )
        unassigned = (
            operations
            - mapped_operations
            - set(LIVE_OPERATION_DISPOSITIONS.get(provider, {}))
        )
        if unassigned:
            errors.append(
                f"{provider} required operations lack case cost maps or explicit dispositions: "
                + ", ".join(sorted(unassigned))
            )

    for provider, reason in sorted(LIVE_PROVIDER_EXCLUSIONS.items()):
        if not str(reason).strip():
            errors.append(f"{provider} has an empty live-manifest exclusion reason")

    for provider, dispositions in sorted(LIVE_OPERATION_DISPOSITIONS.items()):
        if provider not in manifest_providers:
            errors.append(f"{provider} has dispositions but no live manifest")
            continue
        overlap = sorted(
            set(dispositions) & set(LIVE_REQUIRED_OPERATIONS.get(provider, set()))
        )
        if overlap:
            errors.append(
                f"{provider} dispositions overlap required operations: "
                + ", ".join(overlap)
            )
        for operation, disposition in sorted(dispositions.items()):
            kind = live_operation_disposition_kind(disposition)
            if kind not in LIVE_DISPOSITION_KINDS:
                errors.append(
                    f"{provider}/{operation} has unknown disposition kind: {disposition}"
                )

    for provider, reason in sorted(active_live_provider_safety_dispositions().items()):
        if provider not in manifest_providers:
            errors.append(f"{provider} has safety disposition but no live manifest")
        if live_operation_disposition_kind(reason) != "intentional_no_request_policy":
            errors.append(
                f"{provider} safety disposition is not an intentional no-request policy"
            )

    manifest_cases = {
        (provider, relative_path, function_name)
        for provider, cases in LIVE_PROVIDER_CASES.items()
        for relative_path, function_name in cases
    }
    for mapping_name, mapping in (
        ("LIVE_NO_REQUEST_CASES", LIVE_NO_REQUEST_CASES),
        ("LIVE_EXPECTED_ENTITLEMENT_DENIALS", LIVE_EXPECTED_ENTITLEMENT_DENIALS),
    ):
        for case_key in mapping:
            if case_key not in manifest_cases:
                errors.append(
                    f"{mapping_name} references an unmanifested case: {case_key}"
                )
    for case_key, reason in LIVE_NO_REQUEST_CASES.items():
        if live_operation_disposition_kind(reason) != "intentional_no_request_policy":
            errors.append(
                "LIVE_NO_REQUEST_CASES must use intentional_no_request_policy: "
                + str(case_key)
            )
    for case_key, expected_denials in LIVE_EXPECTED_ENTITLEMENT_DENIALS.items():
        if not isinstance(expected_denials, dict) or not expected_denials:
            errors.append(
                "LIVE_EXPECTED_ENTITLEMENT_DENIALS must declare an HTTP status: "
                + str(case_key)
            )
        elif any(
            not isinstance(status, int)
            or isinstance(status, bool)
            or status < 100
            or status > 599
            for status in expected_denials.values()
        ):
            errors.append(
                "LIVE_EXPECTED_ENTITLEMENT_DENIALS contains an invalid HTTP status: "
                + str(case_key)
            )
    overlap_cases = sorted(
        set(LIVE_NO_REQUEST_CASES) & set(LIVE_EXPECTED_ENTITLEMENT_DENIALS)
    )
    if overlap_cases:
        errors.append(
            "a live case cannot be both no-request and entitlement-denial: "
            + ", ".join(str(item) for item in overlap_cases)
        )

    errors.extend(provider_method_inventory_errors())
    return sorted(set(errors))


# These manifest entries are deliberately not provider-live evidence. They
# prove only that the code refuses an unsafe request; they must remain visible
# in receipts and cannot satisfy LIVE_REQUIRED_OPERATIONS.
LIVE_NO_REQUEST_CASES = {
    (
        "fred",
        "test_market_data_providers_live.py",
        "test_fred_series_requires_persisted_data_rights_before_network_access",
    ): "intentional_no_request_policy: FRED persisted/automated-use rights and quota scope are not admitted",
    (
        "fred",
        "test_market_data_providers_live.py",
        "test_fred_credentialed_current_value",
    ): "intentional_no_request_policy: FRED persisted/automated-use rights and quota scope are not admitted",
    (
        "coinbase",
        "test_market_data_providers_live.py",
        "test_coinbase_keyless_crypto_history",
    ): "intentional_no_request_policy: Coinbase automated/persistent use authority is not admitted",
    (
        "coinbase",
        "test_market_data_providers_live.py",
        "test_coinbase_keyless_history_quote_and_usd_products",
    ): "intentional_no_request_policy: Coinbase automated/persistent use authority is not admitted",
    (
        "marketdata_app",
        "test_market_data_providers_live.py",
        "test_marketdata_app_response_priced_option_history_is_blocked_without_bound",
    ): "intentional_no_request_policy: response-priced historical option data has no reviewed hard ceiling",
}
LIVE_EXPECTED_ENTITLEMENT_DENIALS = {
    (
        "finnhub",
        "test_market_data_providers_live.py",
        "test_finnhub_credentialed_company_profile",
    ): {"fetch_ohlcv": 403},
    (
        "eodhd",
        "test_market_data_providers_live.py",
        "test_eodhd_free_plan_profile_entitlement_is_explicit",
    ): {"get_instrument_profile": 403},
}

# These provider suites currently contain a no-network branch that can return
# normally, or a direct cache miss path that bypasses quota admission. Block
# the entire selected/full invocation before any external calls until the
# provider contract is reviewed and both paths are safely metered.
LIVE_PREFLIGHT_ROUTING_CONTROLS = {
    "fred": ("fred",),
    "coinbase": ("coinbase market-data use",),
    "kraken": ("kraken market-data use",),
    "kraken_xstocks": ("kraken market-data use",),
    "coingecko": ("coingecko market-data use",),
    "massive": ("massive market-data use",),
    "edgar": ("edgar quota",),
    "nasdaq": ("nasdaq",),
    "cta_plan": ("cta_plan",),
    "finra": ("finra short-interest and Daily List data use",),
    "finra_otc_directory": ("finra otc directory",),
    "eodhd": ("eodhd",),
    "marketdata_app": ("marketdata.app persistent archive",),
    "marketstack": ("marketstack quota", "marketstack discovery"),
    "twelve_data": ("twelve_data persistent archive",),
    "dinari": ("dinari sandbox canary quota",),
    "xstocks": ("xstocks",),
    "bybit_xstocks": ("bybit_xstocks",),
    "fmp": ("fmp",),
    "tiingo": ("tiingo",),
}

BYTE_BOUND_OPERATIONS = {
    "tiingo": (
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "bulk_fetch",
        "search_instruments",
        "get_instrument_profile",
    ),
    "fmp": (
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "bulk_fetch",
        "get_instrument_profile",
        "fetch_market_events",
        "discover_universe_page",
        "fetch_account_usage",
    ),
}

FINRA_OTC_OPERATION_COSTS = ("discover_universe_page", "reconcile_universe_page")


def setting_is_configured(name: str) -> bool:
    """Return whether a live-probe setting is usable, not merely non-empty.

    The checked-in examples use a placeholder SEC contact value. Treating it
    as configured would start live calls and only fail inside the adapter,
    obscuring the exact deployment input that is missing.
    """

    value = os.getenv(name, "").strip()
    if name == "MASSIVE_API_KEY":
        return bool(value or os.getenv("MARKETDATA_API_KEY", "").strip())
    if not value:
        return False
    if name == "EDGAR_USER_AGENT" and any(
        marker in value.lower()
        for marker in ("example.com", "myemail@", "your.email", "<", ">")
    ):
        return False
    return True


def dinari_sandbox_canary_controls_missing() -> list[str]:
    """Return missing owner controls for the explicit Dinari Sandbox canary.

    These controls are intentionally separate from provider quota policy. They
    authorize one bounded, non-persisting validation run; they never make
    Dinari routable and never infer an unpublished Sandbox entitlement.
    """

    missing: list[str] = []
    if os.getenv("DINARI_SANDBOX_CANARY_AUTHORIZED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        missing.append("DINARI_SANDBOX_CANARY_AUTHORIZED")
    authority_reference = os.getenv(
        "DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE", ""
    ).strip()
    if (
        not authority_reference
        or len(authority_reference) > 256
        or not authority_reference.isprintable()
    ):
        missing.append("DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE")
    raw_limit = os.getenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "").strip()
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 0
    if limit != 1:
        missing.append("DINARI_SANDBOX_CANARY_MAX_REQUESTS (must be exactly 1)")
    return missing


def with_dinari_sandbox_canary_policy(function, *args, **kwargs):
    """Run preflight code with the test-only local Dinari policy enabled."""

    previous = os.environ.get("DINARI_SANDBOX_CANARY_RUN")
    os.environ["DINARI_SANDBOX_CANARY_RUN"] = "1"
    try:
        return function(*args, **kwargs)
    finally:
        if previous is None:
            os.environ.pop("DINARI_SANDBOX_CANARY_RUN", None)
        else:
            os.environ["DINARI_SANDBOX_CANARY_RUN"] = previous


def workflow_secret_environment_names() -> set[str]:
    """Find every secret-backed variable in the credentialed live workflow."""

    workflow_path = ROOT / ".github" / "workflows" / "provider-live.yml"
    try:
        source = workflow_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", source))


def durable_quota_preflight() -> tuple[bool, str | None]:
    """Check shared account admission storage before entering pytest/network."""

    if os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true":
        coordinator_url = os.getenv("PROVIDER_QUOTA_LEDGER_DATABASE_URL", "").strip()
        if not coordinator_url:
            return (
                False,
                "PROVIDER_QUOTA_LEDGER_DATABASE_URL (persistent environment coordinator)",
            )
        try:
            coordinator_scheme = urlsplit(coordinator_url).scheme.lower()
        except ValueError:
            coordinator_scheme = ""
        if coordinator_scheme not in {"postgresql", "postgresql+psycopg2"}:
            return (
                False,
                "PROVIDER_QUOTA_LEDGER_DATABASE_URL (persistent PostgreSQL coordinator required)",
            )
    backend_root = ROOT / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    try:
        from app.services.provider_quota_coordinator import (
            ProviderQuotaCoordinatorError,
            ensure_provider_quota_coordinator,
            reconcile_pending_live_receipts,
        )

        ensure_provider_quota_coordinator(
            require_persistent_coordinator=(
                os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"
            )
        )
        # Reconcile only reservation-linked registry rows. Legacy aggregate
        # JSONL artifacts have no reservation identity and remain observational
        # audit data; they are never converted into quota debits here.
        reconcile_pending_live_receipts()
    except ProviderQuotaCoordinatorError as exc:
        # Coordinator exceptions are deliberately redacted by the service and
        # contain only safe configuration/permission diagnostics. Preserve
        # that reason so an operator can fix the exact store problem without
        # guessing whether the ledger is absent, non-private, or inaccessible.
        return False, str(exc)
    except Exception:
        return (
            False,
            "PROVIDER_QUOTA_LEDGER_DATABASE_URL or private PROVIDER_QUOTA_LEDGER_PATH",
        )
    return True, None


def live_operation_quota_preflight(
    providers: set[str],
    *,
    operations_override: dict[str, set[str]] | None = None,
    operation_multipliers: dict[str, dict[str, int]] | None = None,
    bootstrap_providers: set[str] | None = None,
    local_operation_cost_overrides: dict[str, dict[str, int]] | None = None,
) -> dict[str, list[str]]:
    """Check every selected manifest operation before the first provider call.

    This is a read-only check of reviewed quota plans and current account
    baselines. Individual live tests still reserve atomically immediately
    before transport; the preflight prevents spending one provider's quota
    before discovering that another selected provider cannot be accounted for.

    Providers with an explicit manifest ``fetch_account_usage`` case may be
    admitted with an unknown baseline only for quota dimensions explicitly
    reconciled by that response. The usage operation's own cost against every
    other metered dimension must be reservable before transport; an
    unreported pool cannot be waived by a partial native snapshot. The
    manifest runner orders eligible snapshots before other metered cases.
    """

    backend_root = ROOT / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    try:
        from app.config import provider_rate_limit_seed
        from app.services.provider_quota_coordinator import (
            ProviderQuotaAdmissionError,
            ProviderQuotaCoordinatorError,
            _reservation_plan_for_live_probe,
            provider_quota_baseline_status,
        )
        from app.services.provider_runtime import (
            ProviderQuotaUnknownError,
            account_usage_reconciled_dimensions,
        )
    except Exception:
        return {"provider quota accounting": ["quota admission code is unavailable"]}

    blockers: dict[str, list[str]] = {}
    bootstrap_providers = set(bootstrap_providers or ())
    now = datetime.now(UTC)
    for provider in sorted(providers):
        operations = (
            operations_override.get(provider, set())
            if operations_override is not None
            else LIVE_REQUIRED_OPERATIONS.get(provider, set())
        )
        multipliers = (
            operation_multipliers.get(provider, {})
            if operation_multipliers is not None
            else LIVE_MATRIX_OPERATION_MULTIPLIERS.get(provider, {})
        )
        planned_specs: list[tuple[str, dict[str, object]]] = []
        planned_totals: dict[tuple[object, ...], int] = {}
        planned_identities: dict[tuple[object, ...], set[str]] = {}
        for operation in sorted(operations):
            label = f"{provider}/{operation}"
            try:
                _reset, _dimension_units, specs = _reservation_plan_for_live_probe(
                    provider,
                    operation,
                    usage_identity="LIVE-PREFLIGHT",
                    now=now,
                    operation_cost_override=(
                        (local_operation_cost_overrides or {})
                        .get(provider, {})
                        .get(operation)
                        or LIVE_OPERATION_COST_OVERRIDES.get(provider, {}).get(
                            operation
                        )
                    ),
                )
            except (
                ProviderQuotaAdmissionError,
                ProviderQuotaCoordinatorError,
                ProviderQuotaUnknownError,
            ) as exc:
                blockers.setdefault(provider, []).append(str(exc))
                continue
            multiplier = multipliers.get(operation, 1)
            if (
                isinstance(multiplier, bool)
                or not isinstance(multiplier, int)
                or multiplier < 1
            ):
                blockers.setdefault(provider, []).append(
                    f"{label}: reviewed live-matrix request multiplier is invalid"
                )
                continue
            for raw_spec in specs:
                spec = dict(raw_spec)
                if spec.get("release_only"):
                    planned_specs.append((label, spec))
                    continue
                dimension_name = str(spec.get("dimension") or "")
                key = (
                    str(spec.get("account_scope") or ""),
                    str(spec.get("quota_group") or ""),
                    dimension_name,
                    str(spec.get("window_started_at") or ""),
                    int(spec.get("window_seconds") or 0),
                    str(spec.get("reset") or ""),
                    str(spec.get("unit") or ""),
                )
                unit = str(spec.get("unit") or "").lower()
                if unit in {"symbol", "symbols", "unique_symbol", "unique_symbols"}:
                    identity = str(spec.get("identity_digest") or "")
                    if identity:
                        planned_identities.setdefault(key, set()).add(identity)
                        planned_totals[key] = len(planned_identities[key])
                    else:
                        planned_totals[key] = (
                            planned_totals.get(key, 0)
                            + int(spec.get("units") or 0) * multiplier
                        )
                else:
                    planned_totals[key] = (
                        planned_totals.get(key, 0)
                        + int(spec.get("units") or 0) * multiplier
                    )
                planned_specs.append((label, spec))

        reported_shortfalls: set[tuple[object, ...]] = set()
        for label, spec in planned_specs:
            if spec.get("release_only"):
                continue
            seed = provider_rate_limit_seed(provider)
            contract = seed.get("quota_contract") or {}
            policy = SimpleNamespace(
                quota_contract=contract,
                quota_scope=seed.get("quota_scope", ""),
            )
            dimensions = {
                str(item.get("name") or ""): item
                for item in contract.get("dimensions", [])
                if isinstance(item, dict)
            }
            dimension_name = str(spec.get("dimension") or "")
            dimension = dimensions.get(dimension_name)
            if dimension is None:
                blockers.setdefault(provider, []).append(
                    f"{label}: reviewed dimension {dimension_name or '<missing>'} is absent"
                )
                continue
            key = (
                str(spec.get("account_scope") or ""),
                str(spec.get("quota_group") or ""),
                dimension_name,
                str(spec.get("window_started_at") or ""),
                int(spec.get("window_seconds") or 0),
                str(spec.get("reset") or ""),
                str(spec.get("unit") or ""),
            )
            try:
                state = provider_quota_baseline_status(
                    provider_name=provider,
                    capability=str(spec.get("quota_group") or provider),
                    policy=policy,
                    dimension_name=dimension_name,
                    now=now,
                )
            except (
                ProviderQuotaAdmissionError,
                ProviderQuotaCoordinatorError,
                ProviderQuotaUnknownError,
            ) as exc:
                blockers.setdefault(provider, []).append(f"{label}: {exc}")
                continue
            if state.get("status") != "verified":
                if state.get("status") == "initializable" and (
                    (
                        str(dimension.get("baseline_mode") or "").strip()
                        == "local_zero"
                        and (
                            str(dimension.get("scope") or "").strip() == "deployment"
                            or dimension.get("application_usage_only") is True
                        )
                    )
                    or state.get("initial_baseline") == "exclusive_account_reset"
                ):
                    # These baselines are initialized atomically at reservation
                    # time. The individual test sends remain independently
                    # guarded by the durable coordinator.
                    continue
                if state.get("status") == "unknown" and provider in bootstrap_providers:
                    reconciled = account_usage_reconciled_dimensions(
                        policy, "fetch_account_usage"
                    )
                    if dimension_name in reconciled:
                        continue
                blockers.setdefault(provider, []).append(
                    f"{label}: active {dimension_name} usage baseline is {state.get('status', 'unknown')}"
                )
            elif key not in reported_shortfalls:
                required_units = planned_totals.get(key, 0)
                if int(state.get("remaining_units") or 0) < required_units:
                    blockers.setdefault(provider, []).append(
                        f"{label}: active {dimension_name} headroom is below the combined live-matrix reservation ({required_units} units)"
                    )
                    reported_shortfalls.add(key)
    return blockers


def usage_scope_is_configured() -> bool:
    """Require an attributable, bounded label for quota-consuming live runs."""

    value = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip()
    return bool(value) and len(value) <= 128 and value.isprintable()


def manifest_account_usage_providers(providers: set[str]) -> set[str]:
    """Return selected providers whose manifest includes native usage bootstrap."""

    return {
        provider
        for provider in providers
        if any(
            "account_usage" in function_name
            for _relative_path, function_name in LIVE_PROVIDER_CASES.get(provider, ())
        )
    }


def account_usage_only_provider_set() -> set[str]:
    """Return the manifest-derived providers accepted by usage-only runs."""

    return manifest_account_usage_providers(set(LIVE_PROVIDER_CASES))


def normalized_reviewed_https_source(value: str) -> str | None:
    """Return a credential-free HTTPS source URL suitable for exact review binding."""

    raw = value.strip()
    if not raw or any(character.isspace() for character in raw):
        return None
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return None
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")
    )


def finra_otc_source_review_missing() -> list[str]:
    missing: list[str] = []
    source_kind = os.getenv("FINRA_OTC_SOURCE_KIND", "").strip().lower()
    configured = normalized_reviewed_https_source(
        os.getenv("FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
    )
    if source_kind == "finra_otc_query_api":
        expected = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
        if configured != expected:
            missing.append("FINRA_OTC_SYMBOL_DIRECTORY_URL")
        return missing
    if source_kind != "finra_orf_security_master":
        missing.append(
            "FINRA_OTC_SOURCE_KIND (must be finra_otc_query_api or finra_orf_security_master)"
        )
    if os.getenv("FINRA_OTC_SOURCE_REVIEWED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        missing.append("FINRA_OTC_SOURCE_REVIEWED")
    if not os.getenv("FINRA_OTC_SOURCE_EVIDENCE", "").strip():
        missing.append("FINRA_OTC_SOURCE_EVIDENCE")
    reviewed = normalized_reviewed_https_source(
        os.getenv("FINRA_OTC_REVIEWED_SOURCE_URL", "")
    )
    if configured is None or reviewed != configured:
        missing.append("FINRA_OTC_REVIEWED_SOURCE_URL")
    if source_kind == "finra_orf_security_master":
        configured_inactive = normalized_reviewed_https_source(
            os.getenv("FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", "")
        )
        reviewed_inactive = normalized_reviewed_https_source(
            os.getenv("FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL", "")
        )
        if configured_inactive is None or reviewed_inactive != configured_inactive:
            missing.append("FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL")
    return missing


def routing_safety_preflight() -> dict[str, str]:
    """Describe safety controls that can block routing after a live read.

    Direct adapter probes intentionally remain useful even when a provider is
    non-routable. This report prevents a green adapter read from being
    mistaken for safe quota admission when a provider publishes a bandwidth
    pool without universal response-size ceilings.
    """

    backend_root = ROOT / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from app.config import (
        FMP_PUBLIC_QUOTA_EVIDENCE,
        FRED_MAPPED_SERIES_IDS,
        bybit_xstocks_market_data_use_authority_missing,
        coinbase_market_data_use_authority_missing,
        coingecko_market_data_use_authority_missing,
        eodhd_provider_display_terms_missing,
        kraken_market_data_use_authority_missing,
        massive_market_data_use_authority_missing,
        provider_contract_exception_missing,
        provider_operation_byte_bounds,
        provider_quota_admission_reset,
        provider_quota_reset_is_admission_safe,
        provider_rate_limit_seed,
        provider_terms_exception_missing,
        xstocks_market_data_use_authority_missing,
    )
    from app.config import settings as app_settings
    from app.providers.registry import provider_missing_routing_controls

    def _env_datetime(name: str) -> datetime | None:
        raw = os.getenv(name, "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _env_bool(name: str) -> bool:
        raw = os.getenv(name)
        if raw is None and hasattr(app_settings, name):
            return bool(getattr(app_settings, name))
        return str(raw or "").strip().lower() in {"1", "true", "yes"}

    live_settings = SimpleNamespace(
        FINRA_ORF_CUSIP_LICENSED=os.getenv("FINRA_ORF_CUSIP_LICENSED", "")
        .strip()
        .lower()
        in {"1", "true", "yes"},
        FINRA_ORF_CUSIP_LICENSE_EVIDENCE=os.getenv(
            "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", ""
        ),
        MASSIVE_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE=os.getenv(
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE", ""
        ),
        MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE=os.getenv(
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE", ""
        ),
        MASSIVE_MARKET_DATA_USE_REVIEWED_AT=_env_datetime(
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT"
        ),
        MASSIVE_MARKET_DATA_USE_EXPIRES_AT=_env_datetime(
            "MASSIVE_MARKET_DATA_USE_EXPIRES_AT"
        ),
        FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=_env_bool(
            "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED"
        ),
        FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE=os.getenv(
            "FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE", ""
        ),
        TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=_env_bool(
            "TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED"
        ),
        TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE=os.getenv(
            "TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE", ""
        ),
        MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=_env_bool(
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED"
        ),
        MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE=os.getenv(
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE", ""
        ),
        PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=_env_bool(
            "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK"
        ),
        MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED=_env_bool(
            "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED"
        ),
        MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE=os.getenv(
            "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE", ""
        ),
        TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=_env_bool(
            "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED"
        ),
        TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE=os.getenv(
            "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE", ""
        ),
        EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED=_env_bool(
            "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED"
        ),
        EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE=os.getenv(
            "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE", ""
        ),
        COINBASE_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "COINBASE_MARKET_DATA_USE_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE=os.getenv(
            "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE", ""
        ),
        COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE=os.getenv(
            "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE", ""
        ),
        COINBASE_MARKET_DATA_USE_REVIEWED_AT=_env_datetime(
            "COINBASE_MARKET_DATA_USE_REVIEWED_AT"
        ),
        COINBASE_MARKET_DATA_USE_EXPIRES_AT=_env_datetime(
            "COINBASE_MARKET_DATA_USE_EXPIRES_AT"
        ),
        KRAKEN_MARKET_DATA_USE_AUTHORIZED=_env_bool(
            "KRAKEN_MARKET_DATA_USE_AUTHORIZED"
        ),
        KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE=os.getenv(
            "KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE", ""
        ),
        KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE=os.getenv(
            "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE", ""
        ),
        KRAKEN_MARKET_DATA_USE_REVIEWED_AT=_env_datetime(
            "KRAKEN_MARKET_DATA_USE_REVIEWED_AT"
        ),
        KRAKEN_MARKET_DATA_USE_EXPIRES_AT=_env_datetime(
            "KRAKEN_MARKET_DATA_USE_EXPIRES_AT"
        ),
        COINGECKO_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "COINGECKO_MARKET_DATA_USE_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE=os.getenv(
            "COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE", ""
        ),
        COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE=os.getenv(
            "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE", ""
        ),
        COINGECKO_MARKET_DATA_USE_REVIEWED_AT=_env_datetime(
            "COINGECKO_MARKET_DATA_USE_REVIEWED_AT"
        ),
        COINGECKO_MARKET_DATA_USE_EXPIRES_AT=_env_datetime(
            "COINGECKO_MARKET_DATA_USE_EXPIRES_AT"
        ),
        XSTOCKS_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "XSTOCKS_MARKET_DATA_USE_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE=os.getenv(
            "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", ""
        ),
        XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE=os.getenv(
            "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", ""
        ),
        XSTOCKS_MARKET_DATA_USE_REVIEWED_AT=_env_datetime(
            "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT"
        ),
        XSTOCKS_MARKET_DATA_USE_EXPIRES_AT=_env_datetime(
            "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT"
        ),
        XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED=os.getenv(
            "XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE=os.getenv(
            "XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE", ""
        ),
        BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", ""
        ),
        BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", ""
        ),
        BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT=_env_datetime(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT"
        ),
        BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT=_env_datetime(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT"
        ),
        BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_AUTHORIZED=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_EVIDENCE=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_EVIDENCE", ""
        ),
        BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", ""
        )
        .strip()
        .lower()
        in {"1", "true", "yes"},
        BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE", ""
        ),
    )

    def _seed_safety_reset(provider_name: str, operation: str) -> str | None:
        """Return an explicit provider-scoped safety envelope, if declared."""

        contract = provider_rate_limit_seed(provider_name).get("quota_contract")
        if not isinstance(contract, dict):
            return None
        for dimension in contract.get("dimensions") or []:
            if not isinstance(dimension, dict):
                continue
            if str(dimension.get("name") or "") != operation:
                continue
            provider_reset = dimension.get("reset", contract.get("reset"))
            safety_reset = dimension.get("safety_reset")
            effective = provider_quota_admission_reset(provider_reset, safety_reset)
            if provider_quota_reset_is_admission_safe(provider_reset):
                return str(provider_reset).strip()
            if (
                safety_reset
                and effective != str(provider_reset or "").strip()
                and provider_quota_reset_is_admission_safe(effective)
            ):
                return effective
        return None

    result: dict[str, str] = {}
    result["alpaca corporate actions"] = (
        "routable: durable page cursor resumes until every page is stored"
    )
    result["alpaca market-data quota"] = (
        "routable: documented 200-requests/minute account pool with native reset headers"
    )
    result["massive corporate actions"] = (
        "routable: validated split/dividend cursors are followed until completion"
    )
    massive_use_missing = massive_market_data_use_authority_missing(
        source=live_settings
    )
    result["massive market-data use"] = (
        "routable"
        if not massive_use_missing
        else (
            "non-routable: Massive's Individual plan is limited to personal display "
            "and does not clearly cover this app's automated processing/archive. "
            "This is a provider-license restriction, not missing owner permission. "
            "Missing provider-terms evidence: " + ", ".join(massive_use_missing)
        )
    )
    massive_reset = os.getenv("MASSIVE_REVIEWED_RESET", "").strip()
    massive_quota_evidence = os.getenv("MASSIVE_QUOTA_EVIDENCE", "").strip()
    massive_quota_missing: list[str] = []
    if not provider_quota_reset_is_admission_safe(massive_reset):
        massive_quota_missing.append("MASSIVE_REVIEWED_RESET")
    if not massive_quota_evidence:
        massive_quota_missing.append("MASSIVE_QUOTA_EVIDENCE")
    massive_safety_reset = _seed_safety_reset("massive", "requests_per_minute")
    result["massive market-data quota"] = (
        "routable: documented 5-requests/minute pool enforced by an explicit rolling safety envelope"
        if massive_safety_reset and not massive_reset and not massive_quota_evidence
        else "routable"
        if not massive_quota_missing
        else "non-routable: documented 5-requests/minute Stocks Basic pool has no provider-published reset boundary; missing/invalid "
        + ", ".join(massive_quota_missing)
    )
    edgar_reset = os.getenv("EDGAR_REVIEWED_RESET", "").strip()
    edgar_quota_evidence = os.getenv("EDGAR_QUOTA_EVIDENCE", "").strip()
    edgar_quota_missing: list[str] = []
    if not provider_quota_reset_is_admission_safe(edgar_reset):
        edgar_quota_missing.append("EDGAR_REVIEWED_RESET")
    if not edgar_quota_evidence:
        edgar_quota_missing.append("EDGAR_QUOTA_EVIDENCE")
    edgar_safety_reset = _seed_safety_reset("edgar", "requests_per_second")
    result["edgar quota"] = (
        "routable: contract verified; SEC documents a 10-requests/second ceiling; the app uses a rolling one-second envelope and a provider-specific 10-minute throttle recovery hold; active shared-scope usage baseline is checked separately"
        if edgar_safety_reset and not edgar_reset and not edgar_quota_evidence
        else "routable: contract configured with reviewed reset evidence; active shared-scope usage baseline is checked separately"
        if not edgar_quota_missing
        else "non-routable: documented 10-requests/second SEC fair-access ceiling has no provider-published reset boundary; missing/invalid "
        + ", ".join(edgar_quota_missing)
    )
    async_bound = os.getenv("FINRA_ASYNC_MAX_RESULT_BYTES", "0").strip() or "0"
    try:
        result["finra async result bytes"] = (
            "routable"
            if int(async_bound) > 0
            else "non-routable: positive reviewed bound required"
        )
    except ValueError:
        result["finra async result bytes"] = "non-routable: bound is not an integer"

    result["finra short-interest and Daily List data use"] = (
        "no owner storage approval needed; FINRA credentials, quota, and source checks still apply"
    )

    finra_otc_missing: list[str] = []
    finra_otc_source_kind = os.getenv("FINRA_OTC_SOURCE_KIND", "").strip().lower()
    raw_finra_otc_costs = os.getenv("FINRA_OTC_OPERATION_COSTS", "").strip()
    try:
        finra_otc_costs = json.loads(raw_finra_otc_costs) if raw_finra_otc_costs else {}
    except json.JSONDecodeError:
        finra_otc_costs = None
    if finra_otc_source_kind != "finra_otc_query_api":
        if not isinstance(finra_otc_costs, dict):
            finra_otc_missing.append("FINRA_OTC_OPERATION_COSTS")
        elif not all(
            isinstance(finra_otc_costs.get(operation), int)
            and not isinstance(finra_otc_costs.get(operation), bool)
            and finra_otc_costs[operation] > 0
            for operation in FINRA_OTC_OPERATION_COSTS
        ):
            finra_otc_missing.append("FINRA_OTC_OPERATION_COSTS")
        for variable in (
            "FINRA_OTC_TERMS_REVIEWED",
            "FINRA_OTC_COMPLETENESS_REVIEWED",
            "FINRA_OTC_REDISTRIBUTION_REVIEWED",
        ):
            if os.getenv(variable, "").strip().lower() not in {"1", "true", "yes"}:
                finra_otc_missing.append(variable)
    if (
        finra_otc_source_kind == "finra_orf_security_master"
        and live_settings.FINRA_ORF_CUSIP_LICENSED
        and not str(live_settings.FINRA_ORF_CUSIP_LICENSE_EVIDENCE or "").strip()
    ):
        finra_otc_missing.append("FINRA_ORF_CUSIP_LICENSE_EVIDENCE")
    finra_otc_missing.extend(finra_otc_source_review_missing())
    try:
        finra_otc_poll = int(
            os.getenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "0").strip() or "0"
        )
    except ValueError:
        finra_otc_poll = 0
    if finra_otc_poll <= 0:
        finra_otc_missing.append("FINRA_OTC_POLL_INTERVAL_SECONDS")
    result["finra otc directory"] = (
        (
            "routable: official OTC Symbol Directory Query API with lossless "
            "record-total pagination"
            if finra_otc_source_kind == "finra_otc_query_api"
            else "routable"
        )
        if not finra_otc_missing
        else (
            "non-routable: FINRA OTC source or quota controls are incomplete. "
            "Missing/invalid controls: " + ", ".join(dict.fromkeys(finra_otc_missing))
        )
    )

    alpha_reset = os.getenv("ALPHA_VANTAGE_REVIEWED_RESET", "").strip()
    alpha_quota_evidence = os.getenv("ALPHA_VANTAGE_QUOTA_EVIDENCE", "").strip()
    alpha_missing: list[str] = []
    if not provider_quota_reset_is_admission_safe(alpha_reset):
        alpha_missing.append("ALPHA_VANTAGE_REVIEWED_RESET")
    if not alpha_quota_evidence:
        alpha_missing.append("ALPHA_VANTAGE_QUOTA_EVIDENCE")
    alpha_second_safety_reset = _seed_safety_reset(
        "alpha_vantage", "requests_per_second"
    )
    alpha_minute_safety_reset = _seed_safety_reset(
        "alpha_vantage", "requests_per_minute"
    )
    alpha_daily_safety_reset = _seed_safety_reset("alpha_vantage", "requests_per_day")
    result["alpha_vantage"] = (
        "routable: current-key response recommends 1 request/second and indicates a 5-requests/minute ceiling; official support confirms 25 requests/day; each is enforced in its own safety window"
        if alpha_second_safety_reset
        and alpha_minute_safety_reset
        and alpha_daily_safety_reset
        and not alpha_reset
        and not alpha_quota_evidence
        else "routable"
        if not alpha_missing
        else "non-routable: documented 25-requests/day allowance has no provider-published reset boundary; missing/invalid "
        + ", ".join(alpha_missing)
    )

    finnhub_minute_reset = os.getenv("FINNHUB_REVIEWED_MINUTE_RESET", "").strip()
    finnhub_second_reset = os.getenv("FINNHUB_REVIEWED_SECOND_RESET", "").strip()
    finnhub_minute_evidence = os.getenv("FINNHUB_MINUTE_QUOTA_EVIDENCE", "").strip()
    finnhub_second_evidence = os.getenv("FINNHUB_SECOND_QUOTA_EVIDENCE", "").strip()
    finnhub_missing: list[str] = []
    if not provider_quota_reset_is_admission_safe(finnhub_minute_reset):
        finnhub_missing.append("FINNHUB_REVIEWED_MINUTE_RESET")
    if not provider_quota_reset_is_admission_safe(finnhub_second_reset):
        finnhub_missing.append("FINNHUB_REVIEWED_SECOND_RESET")
    if not finnhub_minute_evidence:
        finnhub_missing.append("FINNHUB_MINUTE_QUOTA_EVIDENCE")
    if not finnhub_second_evidence:
        finnhub_missing.append("FINNHUB_SECOND_QUOTA_EVIDENCE")
    finnhub_minute_safety = _seed_safety_reset("finnhub", "calls_per_minute")
    finnhub_second_safety = _seed_safety_reset("finnhub", "hard_calls_per_second")
    result["finnhub"] = (
        "routable: documented minute/second ceilings enforced by explicit rolling safety envelopes"
        if (
            finnhub_minute_safety
            and finnhub_second_safety
            and not any(
                (
                    finnhub_minute_reset,
                    finnhub_second_reset,
                    finnhub_minute_evidence,
                    finnhub_second_evidence,
                )
            )
        )
        else "routable"
        if not finnhub_missing
        else "non-routable: independent minute and second reset boundaries require current review evidence; missing/invalid "
        + ", ".join(finnhub_missing)
    )

    eodhd_minute_limit_raw = os.getenv("EODHD_REVIEWED_MINUTE_LIMIT", "0").strip()
    try:
        eodhd_minute_limit = int(eodhd_minute_limit_raw or "0")
    except ValueError:
        eodhd_minute_limit = None
    eodhd_minute_reset = os.getenv("EODHD_REVIEWED_MINUTE_RESET", "").strip()
    eodhd_minute_evidence = os.getenv("EODHD_MINUTE_QUOTA_EVIDENCE", "").strip()
    eodhd_missing: list[str] = []
    eodhd_missing.extend(eodhd_provider_display_terms_missing(source=live_settings))
    if eodhd_minute_limit is None or eodhd_minute_limit < 0:
        eodhd_missing.append("EODHD_REVIEWED_MINUTE_LIMIT")
    elif eodhd_minute_limit > 0:
        # EODHD's Free-plan pricing row (20/minute) conflicts with its
        # API-limits page (1,000/minute on all plans). The code seed enforces
        # 20/minute. A reviewed account-specific override must carry its own
        # reset/evidence; zero means retain that conservative Free-plan cap.
        if not provider_quota_reset_is_admission_safe(eodhd_minute_reset):
            eodhd_missing.append("EODHD_REVIEWED_MINUTE_RESET")
        if not eodhd_minute_evidence:
            eodhd_missing.append("EODHD_MINUTE_QUOTA_EVIDENCE")
    eodhd_safety_reset = _seed_safety_reset("eodhd", "requests_per_minute")
    if not eodhd_safety_reset:
        eodhd_missing.append("documented requests_per_minute reset")
    result["eodhd"] = (
        (
            "routable: conservative Free-plan 20-requests/minute ceiling enforced by a rolling 60-second envelope"
            if eodhd_minute_limit == 0
            else "routable: account-specific minute override has reviewed reset/evidence"
        )
        if not eodhd_missing
        else "non-routable: invalid account-specific override or missing documented reset; "
        + ", ".join(eodhd_missing)
    )

    # These providers have a useful live read but still lack one or more
    # provider-specific admission dimensions. Keep the gap visible next to
    # the byte-bound controls rather than letting a passing probe imply safe
    # routing.
    owner_accepts_terms_risk = owner_accepts_provider_terms_risk()
    fred_scope = os.getenv("FRED_REVIEWED_LIMIT_SCOPE", "").strip()
    try:
        fred_limit = int(
            os.getenv("FRED_REVIEWED_REQUESTS_PER_MINUTE", "0").strip() or "0"
        )
    except ValueError:
        fred_limit = 0
    fred_quota_evidence = os.getenv("FRED_REVIEWED_QUOTA_EVIDENCE", "").strip()
    fred_reset = os.getenv("FRED_REVIEWED_RESET", "").strip()
    fred_reset_evidence = os.getenv("FRED_RESET_EVIDENCE", "").strip()
    fred_missing: list[str] = []
    if not owner_accepts_terms_risk:
        if fred_scope not in {"api_key", "account", "ip", "deployment"}:
            fred_missing.append("FRED_REVIEWED_LIMIT_SCOPE")
        if not 0 < fred_limit <= 120:
            fred_missing.append("FRED_REVIEWED_REQUESTS_PER_MINUTE")
        if not fred_quota_evidence:
            fred_missing.append("FRED_REVIEWED_QUOTA_EVIDENCE")
        if not provider_quota_reset_is_admission_safe(fred_reset):
            fred_missing.append("FRED_REVIEWED_RESET")
        if not fred_reset_evidence:
            fred_missing.append("FRED_RESET_EVIDENCE")
    if not owner_accepts_terms_risk:
        if (
            os.getenv("FRED_APPLICATION_USER_SCOPE", "").strip().lower()
            != "owner_personal_only"
        ):
            fred_missing.append("FRED_APPLICATION_USER_SCOPE")
        if not os.getenv("FRED_APPLICATION_USER_SCOPE_EVIDENCE", "").strip():
            fred_missing.append("FRED_APPLICATION_USER_SCOPE_EVIDENCE")
        if os.getenv("FRED_AUTOMATED_USE_AUTHORIZED", "").strip().lower() not in {
            "1",
            "true",
            "yes",
        }:
            fred_missing.append("FRED_AUTOMATED_USE_AUTHORIZED")
        if not os.getenv("FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "").strip():
            fred_missing.append("FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE")
        try:
            fred_series_rights = json.loads(
                os.getenv("FRED_SERIES_RIGHTS_EVIDENCE", "{}") or "{}"
            )
        except json.JSONDecodeError:
            fred_series_rights = None
        if not isinstance(fred_series_rights, dict) or any(
            not isinstance(fred_series_rights.get(series_id), str)
            or not fred_series_rights[series_id].strip()
            for series_id in FRED_MAPPED_SERIES_IDS
        ):
            fred_missing.append("FRED_SERIES_RIGHTS_EVIDENCE")
    result["fred"] = (
        (
            "routable: published 120-requests/minute ceiling enforced by a shared API-key rolling 60-second cap; provider scope/reset are unpublished and 429 stops routing"
            if owner_accepts_terms_risk
            else "routable"
        )
        if not fred_missing
        else "non-routable: provider-specific quota or terms controls are incomplete; missing/invalid "
        + ", ".join(fred_missing)
    )
    coinbase_missing = coinbase_market_data_use_authority_missing(source=live_settings)
    result["coinbase market-data use"] = (
        "routable"
        if not coinbase_missing
        else "non-routable: Coinbase terms require scoped prior written authority for this automated/persisted use; missing/invalid "
        + ", ".join(coinbase_missing)
    )
    kraken_missing = kraken_market_data_use_authority_missing(source=live_settings)
    result["kraken market-data use"] = (
        "routable"
        if not kraken_missing
        else "non-routable: Kraken's current API terms require prior written permission for third-party applications; the required single-user automated/private-archive scope is missing or invalid: "
        + ", ".join(kraken_missing)
    )
    coingecko_missing = coingecko_market_data_use_authority_missing(
        source=live_settings
    )
    result["coingecko market-data use"] = (
        "routable"
        if not coingecko_missing
        else "non-routable: CoinGecko Demo persistence requires scoped written authority; missing/invalid "
        + ", ".join(coingecko_missing)
    )
    result["nasdaq"] = (
        "routable: client-imposed 2 official-file requests per calendar day; vendor quota unpublished"
    )
    result["cta_plan"] = (
        "routable: client-imposed 2 public index/file requests per market day; CTA quota unpublished"
    )
    dinari_missing = provider_missing_routing_controls("dinari")
    result["dinari sandbox canary quota"] = (
        "routable for one read-only Sandbox connectivity canary per UTC day under the shared local test ledger; this is not a Dinari quota and does not enable recurring tests or application routing"
        if os.getenv("DINARI_SANDBOX_CANARY_RUN", "").strip() == "1"
        and not dinari_sandbox_canary_controls_missing()
        else (
            "non-routable: Dinari Sandbox requires a complete account-reviewed quota contract and worst-case operation-cost map; missing/invalid "
            + ", ".join(dinari_missing)
            if dinari_missing
            else "routable for the explicitly capped, non-persisting Sandbox canary only; durable account-window baselines are checked separately"
        )
    )
    xstocks_missing = xstocks_market_data_use_authority_missing(source=live_settings)
    result["xstocks"] = (
        "routable"
        if not xstocks_missing
        else "non-routable: the live-verified 1000/minute shared public header contract "
        "is accounted for, but deployment jurisdiction evidence is missing/invalid: "
        + ", ".join(xstocks_missing)
    )
    result["bybit_xstocks"] = (
        "routable: anonymous public calls are bounded by the documented 600/5-second/IP ceiling"
        if not bybit_xstocks_market_data_use_authority_missing(source=live_settings)
        else "non-routable: Bybit xStocks requires permitted request egress; "
        "egress jurisdiction evidence is missing/invalid: "
        + ", ".join(
            bybit_xstocks_market_data_use_authority_missing(source=live_settings)
        )
    )
    try:
        marketstack_limit = int(
            os.getenv("MARKETSTACK_REVIEWED_MONTHLY_LIMIT", "100").strip() or "0"
        )
    except ValueError:
        marketstack_limit = 0
    marketstack_missing: list[str] = []
    if marketstack_limit <= 0:
        marketstack_missing.append("MARKETSTACK_REVIEWED_MONTHLY_LIMIT")
    marketstack_reset = os.getenv("MARKETSTACK_REVIEWED_MONTHLY_RESET", "").strip()
    if marketstack_reset and not provider_quota_reset_is_admission_safe(
        marketstack_reset
    ):
        marketstack_missing.append("MARKETSTACK_REVIEWED_MONTHLY_RESET")
    if (marketstack_limit != 100 or marketstack_reset) and not os.getenv(
        "MARKETSTACK_QUOTA_EVIDENCE", ""
    ).strip():
        marketstack_missing.append("MARKETSTACK_QUOTA_EVIDENCE")
    result["marketstack quota"] = (
        "routable"
        if not marketstack_missing
        else "non-routable: invalid plan-specific limit/reset configuration; missing/invalid "
        + ", ".join(marketstack_missing)
    )
    marketstack_discovery_missing: list[str] = []
    if not os.getenv("MARKETSTACK_DISCOVERY_EXCHANGE", "").strip():
        marketstack_discovery_missing.append("MARKETSTACK_DISCOVERY_EXCHANGE")
    try:
        marketstack_page_cost = int(
            os.getenv("MARKETSTACK_DISCOVERY_MAX_PAGE_COST", "0").strip() or "0"
        )
    except ValueError:
        marketstack_page_cost = 0
    if marketstack_page_cost <= 0:
        marketstack_discovery_missing.append("MARKETSTACK_DISCOVERY_MAX_PAGE_COST")
    if not os.getenv(
        "MARKETSTACK_DISCOVERY_COST_EVIDENCE",
        "Marketstack first-party billing FAQ and exchange-ticker pagination docs",
    ).strip():
        marketstack_discovery_missing.append("MARKETSTACK_DISCOVERY_COST_EVIDENCE")
    marketstack_discovery_missing.extend(marketstack_missing)
    marketstack_discovery_missing.extend(
        provider_contract_exception_missing("MARKETSTACK", source=live_settings)
    )
    result["marketstack discovery"] = (
        "routable"
        if not marketstack_discovery_missing
        else "non-routable: venue-wide page cost, monthly allowance/reset, or MIC is unresolved: "
        + ", ".join(dict.fromkeys(marketstack_discovery_missing))
    )
    marketdata_plan = os.getenv("MARKETDATA_APP_REVIEWED_PLAN", "").strip().lower()
    marketdata_limits = {
        "free_forever": 100,
        "starter_trial": 10000,
        "trader_trial": 100000,
        "starter": 10000,
        "trader": 100000,
    }
    try:
        marketdata_limit = int(
            os.getenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "0").strip() or "0"
        )
    except ValueError:
        marketdata_limit = 0
    expected_marketdata_limit = marketdata_limits.get(marketdata_plan)
    marketdata_expiry_issue = False
    trial_expired = False
    if marketdata_plan.endswith("_trial"):
        raw_expiry = os.getenv("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", "").strip()
        try:
            parsed_expiry = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
        except ValueError:
            parsed_expiry = None
        marketdata_expiry_issue = parsed_expiry is None or parsed_expiry.tzinfo is None
        trial_expired = bool(
            parsed_expiry is not None
            and parsed_expiry.tzinfo is not None
            and parsed_expiry.astimezone(UTC) <= datetime.now(UTC)
        )
    marketdata_pair_valid = (
        expected_marketdata_limit is not None
        and marketdata_limit == expected_marketdata_limit
    )
    if marketdata_pair_valid and marketdata_expiry_issue:
        result["marketdata.app account plan"] = (
            "non-routable: trial requires a timezone-aware "
            "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT"
        )
    elif marketdata_pair_valid and trial_expired:
        result["marketdata.app account plan"] = (
            "routable: configured trial expired; effective quota automatically falls back to "
            "Free Forever at 100 credits/day"
        )
    elif marketdata_pair_valid and marketdata_plan.endswith("_trial"):
        result["marketdata.app account plan"] = (
            "non-routable: temporary trial plans are not admitted; use a separately "
            "reviewed non-trial entitlement"
        )
    elif marketdata_pair_valid and marketdata_plan in {"starter", "trader"}:
        if _env_bool("PROVIDER_FREE_ONLY_CHECKPOINT"):
            result["marketdata.app account plan"] = (
                "non-routable: shared free-only checkpoint blocks paid plans"
            )
        elif _env_bool("ALLOW_PAID_PROVIDER_ROUTING"):
            result["marketdata.app account plan"] = "routable: paid plan reviewed"
        else:
            result["marketdata.app account plan"] = (
                "non-routable: paid plan requires ALLOW_PAID_PROVIDER_ROUTING=true"
            )
    elif marketdata_pair_valid:
        result["marketdata.app account plan"] = "routable"
    else:
        result["marketdata.app account plan"] = (
            "non-routable: explicit reviewed plan/limit pair required"
        )
    raw_option_chain_bound = (
        os.getenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "0").strip() or "0"
    )
    try:
        option_chain_bound = int(raw_option_chain_bound)
    except ValueError:
        option_chain_bound = 0
    result["marketdata.app option chain"] = (
        "routable"
        if option_chain_bound >= 2
        else "non-routable: reviewed MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS must be >= 2"
    )
    result["marketdata.app option quote history"] = (
        "routable for bounded calls: the service derives and reserves a conservative "
        "inclusive-calendar-date credit estimate before transport; no unbounded "
        "request or fixed-cost fallback is admitted"
    )
    # Live probes also archive each observed response body to the owner-only
    # response archive. Therefore a provider terms exception for retained data
    # is required before MarketData.app probes may run; a live test must not
    # bypass the same source-rights gate applied to application ingestion.
    marketdata_archive_missing = provider_terms_exception_missing(
        "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED",
        "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE",
        source=live_settings,
    )
    result["marketdata.app persistent archive"] = (
        "routable: current provider terms allow the configured use"
        if not marketdata_archive_missing
        else "non-routable: MarketData.app terms require deletion when a subscription ends; "
        "provider-terms exception evidence is missing/invalid: "
        + ", ".join(marketdata_archive_missing)
    )
    twelve_data_archive_missing = provider_contract_exception_missing(
        "TWELVE_DATA", source=live_settings
    )
    result["twelve_data persistent archive"] = (
        "routable: current provider terms allow the configured use"
        if not twelve_data_archive_missing
        else "non-routable: current plan terms do not establish the required archive use; "
        "provider-terms exception evidence is missing/invalid: "
        + ", ".join(twelve_data_archive_missing)
    )

    for provider, operations in BYTE_BOUND_OPERATIONS.items():
        variable = f"{provider.upper()}_OPERATION_BYTE_BOUNDS"
        # Use the exact Settings value that application routing uses when no
        # explicit override is supplied. Reading only os.environ made the
        # live gate reject valid code-owned defaults. Still honor a runtime
        # override (including a deliberate empty object) exactly as Settings
        # does, so safety checks react to the environment under test.
        raw = os.getenv(variable)
        configured_bounds = provider_operation_byte_bounds(provider)
        missing: list[str] = []
        if raw is not None and raw.strip() != "__CODE_DEFAULT__":
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
                missing.append(f"{variable} is not valid JSON")
            if raw.strip() and parsed is not None and not isinstance(parsed, dict):
                missing.append(f"{variable} must be a JSON object")
            elif isinstance(parsed, dict):
                configured_bounds = {
                    str(operation): value
                    for operation, value in parsed.items()
                    if isinstance(value, int)
                    and not isinstance(value, bool)
                    and value > 0
                }
        if not configured_bounds:
            missing.append(f"{variable} is unset")
        missing.extend(
            operation for operation in operations if operation not in configured_bounds
        )
        if provider == "tiingo":
            missing.extend(
                provider_contract_exception_missing("TIINGO", source=live_settings)
            )
            unique_reset = os.getenv("TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "").strip()
            hourly_reset = os.getenv("TIINGO_REVIEWED_HOURLY_RESET", "").strip()
            unique_evidence = os.getenv(
                "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", ""
            ).strip()
            hourly_evidence = os.getenv("TIINGO_HOURLY_QUOTA_EVIDENCE", "").strip()
            unique_safety = _seed_safety_reset("tiingo", "unique_symbols_per_month")
            hourly_safety = _seed_safety_reset("tiingo", "requests_per_hour")
            if not (
                unique_safety
                and hourly_safety
                and not unique_reset
                and not hourly_reset
                and not unique_evidence
                and not hourly_evidence
            ):
                if not provider_quota_reset_is_admission_safe(unique_reset):
                    missing.append("TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET")
                if not provider_quota_reset_is_admission_safe(hourly_reset):
                    missing.append("TIINGO_REVIEWED_HOURLY_RESET")
                if not unique_evidence:
                    missing.append("TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE")
                if not hourly_evidence:
                    missing.append("TIINGO_HOURLY_QUOTA_EVIDENCE")
        if provider == "fmp":
            missing.extend(
                provider_contract_exception_missing("FMP", source=live_settings)
            )
            daily_reset = os.getenv("FMP_REVIEWED_DAILY_RESET", "").strip()
            daily_evidence = (
                os.getenv("FMP_CALL_QUOTA_EVIDENCE", "").strip()
                or os.getenv("FMP_DAILY_QUOTA_EVIDENCE", "").strip()
                or FMP_PUBLIC_QUOTA_EVIDENCE
            )
            # The provider-native reset stays unresolved when blank; the
            # registered quota contract then enforces a strict rolling 24h
            # application safety window instead. A supplied native boundary
            # must be calculable and backed by current account evidence.
            if daily_reset and not provider_quota_reset_is_admission_safe(daily_reset):
                missing.append("FMP_REVIEWED_DAILY_RESET")
            if not daily_evidence:
                missing.append("FMP_DAILY_QUOTA_EVIDENCE")
            bandwidth_reset = os.getenv("FMP_REVIEWED_BANDWIDTH_RESET", "").strip()
            if bandwidth_reset and not provider_quota_reset_is_admission_safe(
                bandwidth_reset
            ):
                missing.append("FMP_REVIEWED_BANDWIDTH_RESET")
            bandwidth_evidence = (
                os.getenv("FMP_BANDWIDTH_QUOTA_EVIDENCE", "").strip()
                or FMP_PUBLIC_QUOTA_EVIDENCE
            )
            if not bandwidth_evidence:
                missing.append("FMP_BANDWIDTH_QUOTA_EVIDENCE")
        result[provider] = (
            "routable"
            if not missing
            else (
                f"non-routable: missing reviewed controls for {', '.join(missing)}"
                if provider in {"tiingo", "fmp"}
                else f"non-routable: missing positive bounds for {', '.join(missing)}"
            )
        )
    return result


def live_required_safety_blockers(
    providers: set[str],
    safety_statuses: dict[str, str],
    *,
    account_usage_only: bool = False,
    operations_by_provider: dict[str, set[str]] | None = None,
) -> dict[str, list[str]]:
    """Apply live safety gates to the exact provider operation being tested.

    Account-usage-only probes do not fetch or retain market data. Resolve their
    controls through the registry's operation-scoped contract so a data-use
    or display restriction cannot prevent an otherwise admitted native quota
    snapshot. FINRA's synchronous equity-data operations also use that
    operation-scoped registry check: the owner-approved private-storage
    disposition is not a provider-wide routability status. Durable request
    quota, active-window baseline, credentials, and operation costs remain
    checked separately by the runner.
    """

    blocked: dict[str, list[str]] = {}
    if account_usage_only:
        from app.providers.registry import provider_missing_routing_controls

        for provider in sorted(providers):
            missing_controls = provider_missing_routing_controls(
                provider, "fetch_account_usage"
            )
            if missing_controls:
                blocked[provider] = [
                    "non-routable for account usage: missing/invalid "
                    + ", ".join(missing_controls)
                ]
        return blocked

    # FINRA's synchronous short-interest and Daily List adapters have exact
    # operation-scoped use controls in the provider registry. Its summary
    # status is deliberately explanatory (the owner's storage approval is not
    # a FINRA approval); treating that prose as a failed routability status
    # caused otherwise eligible live cases to be rejected before the actual
    # quota and source checks could run.
    if "finra" in providers:
        from app.providers.registry import provider_missing_routing_controls

        finra_operations = LIVE_REQUIRED_OPERATIONS.get("finra", set())
        missing_by_operation = {
            operation: provider_missing_routing_controls("finra", operation)
            for operation in sorted(finra_operations)
        }
        missing_controls = sorted(
            {
                control
                for controls in missing_by_operation.values()
                for control in controls
            }
        )
        if missing_controls:
            blocked["finra"] = [
                "non-routable: missing/invalid FINRA operation controls: "
                + ", ".join(missing_controls)
            ]

    # Massive's documented 5/minute allowance is per asset class and its Basic
    # tier includes stock reference data and corporate actions. Check the
    # normal provider-specific terms controls for all selected stock
    # operations; there is no separate unpublished reference bucket.
    if "massive" in providers:
        from app.providers.registry import provider_missing_routing_controls

        massive_operations = (
            operations_by_provider.get("massive")
            if operations_by_provider is not None
            else None
        ) or LIVE_REQUIRED_OPERATIONS.get("massive", set())
        missing_by_operation = {
            operation: provider_missing_routing_controls("massive", operation)
            for operation in sorted(massive_operations)
        }
        missing_controls = sorted(
            {
                control
                for controls in missing_by_operation.values()
                for control in controls
            }
        )
        if missing_controls:
            blocked["massive"] = [
                "non-routable: missing/invalid Massive operation controls: "
                + ", ".join(missing_controls)
            ]

    # Marketstack's monthly quota applies to all data reads, but the unresolved
    # per-page billing and MIC are specific to venue-wide ticker discovery.
    # Keep bounded history/profile cases testable without implying discovery is
    # admitted; a complete provider manifest still includes discovery below.
    if "marketstack" in providers:
        marketstack_operations = (
            operations_by_provider.get("marketstack")
            if operations_by_provider is not None
            else None
        ) or LIVE_REQUIRED_OPERATIONS.get("marketstack", set())
        required_controls = ["marketstack quota"]
        if (
            operations_by_provider is None
            or "discover_universe_page" in marketstack_operations
        ):
            required_controls.append("marketstack discovery")
        missing_controls = [
            safety_statuses.get(name, "non-routable: control status is missing")
            for name in required_controls
            if not safety_statuses.get(
                name, "non-routable: control status is missing"
            ).startswith("routable")
        ]
        if missing_controls:
            blocked["marketstack"] = missing_controls

    for provider in sorted(providers):
        if provider in {"finra", "massive", "marketstack"}:
            continue
        for safety_name in LIVE_PREFLIGHT_ROUTING_CONTROLS.get(provider, ()):
            status = safety_statuses.get(
                safety_name, "non-routable: control status is missing"
            )
            if not status.startswith("routable"):
                blocked.setdefault(provider, []).append(status)
    return blocked


def partition_live_provider_admission(
    selected: set[str],
    *,
    missing: dict[str, list[str]],
    quota_blockers: dict[str, list[str]],
    safety_blockers: dict[str, list[str]],
    unresolved_operations: list[str],
) -> tuple[set[str], dict[str, list[str]], list[str]]:
    """Separate eligible providers from provider-local blockers.

    Quota pools are provider/account scoped. A provider with an unknown quota,
    missing credential, or unresolved live operation must remain uncalled, but
    it must not prevent independently admitted providers from being tested.
    Global coordinator/inventory failures still stop every provider.
    """

    blocked: dict[str, list[str]] = {}
    global_blockers: list[str] = []

    def add(provider: str, reason: str) -> None:
        if provider in selected:
            blocked.setdefault(provider, []).append(reason)

    for provider, reasons in quota_blockers.items():
        for reason in reasons:
            add(provider, reason)
    for provider, reasons in safety_blockers.items():
        for reason in reasons:
            add(provider, reason)

    for item in unresolved_operations:
        provider, separator, detail = item.partition("/")
        if separator:
            add(provider, detail)
        else:
            global_blockers.append(f"unscoped live coverage blocker: {item}")

    global_groups = {
        "durable quota admission",
        "usage accounting",
        "live matrix inventory",
        "FINRA OTC source admission",
    }
    for group, reasons in missing.items():
        if group in {
            "provider-specific quota/cost/baseline admission",
            "required live capability safety",
            "unresolved capability live coverage",
        }:
            continue
        if group in global_groups:
            global_blockers.extend(f"{group}: {reason}" for reason in reasons)
        elif group == "keyless/config":
            for reason in reasons:
                add("edgar", reason)
        elif group in selected:
            for reason in reasons:
                add(group, reason)
        elif group == "explicitly deferred providers":
            for provider in reasons:
                if provider in selected:
                    add(provider, "provider is explicitly deferred")
        else:
            # Unknown preflight groups are fail-closed and global until their
            # provider ownership is made explicit.
            global_blockers.extend(
                f"unclassified preflight blocker {group}: {reason}"
                for reason in reasons
            )

    return selected - set(blocked), blocked, sorted(set(global_blockers))


def changed_provider_code() -> bool:
    if os.getenv("FORCE_LIVE_PROVIDER_PROBES") == "1":
        return True
    status = subprocess.run(
        ["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True
    )
    provider_paths = (
        "backend/app/config.py",
        "backend/app/providers/",
        "backend/app/services/provider",
        "backend/app/services/market_data.py",
        "backend/app/services/instrument_events.py",
        "backend/app/services/options_data.py",
        "backend/app/services/tokenized_assets.py",
        "backend/app/models/provider",
        "backend/app/routers/providers.py",
        "backend/app/schemas/provider",
        "backend/app/tasks/",
        "backend/app/workers/",
        "backend/tests/live/",
        "backend/tests/integration/provider",
        "backend/alembic/versions/",
        "scripts/run-live-provider-probes.py",
        "scripts/merge-provider-live-usage.py",
        "docs/data-providers.md",
        "docs/provider-live-validation.md",
        ".github/workflows/provider-live.yml",
        ".github/workflows/ci.yml",
        ".env.example",
        "backend/.env.example",
        "docker-compose.yml",
        "deploy/rpi/compose.yml",
    )
    if any(
        path.startswith(provider_paths)
        for path in (line[3:] for line in status.stdout.splitlines() if len(line) > 3)
    ):
        return True
    base = os.getenv("INTEGRATION_BASE_SHA")
    if not base:
        # Workstream metadata and documentation commits commonly follow the
        # provider source commit. Comparing only HEAD^1 would then make a
        # fresh checkout incorrectly skip the required live matrix. Prefer
        # the feature branch's staging merge-base, which remains stable across
        # those follow-up commits, and retain the narrow parent fallback for
        # detached/minimal repositories that do not have a staging ref.
        for candidate in ("staging", "origin/staging"):
            result = subprocess.run(
                ["git", "merge-base", "HEAD", candidate],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                base = result.stdout.strip()
                break
    if not base:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD^1"], cwd=ROOT, text=True, capture_output=True
        )
        base = result.stdout.strip() if result.returncode == 0 else ""
    if not base:
        return True
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    relevant = (
        "backend/app/config.py",
        "backend/app/providers/",
        "backend/app/services/provider",
        "backend/app/services/market_data.py",
        "backend/app/services/instrument_events.py",
        "backend/app/services/options_data.py",
        "backend/app/services/tokenized_assets.py",
        "backend/app/models/provider",
        "backend/app/routers/providers.py",
        "backend/app/schemas/provider",
        "backend/app/tasks/",
        "backend/app/workers/",
        "backend/tests/live/",
        "backend/tests/integration/provider",
        "backend/alembic/versions/",
        "scripts/run-live-provider-probes.py",
        "scripts/merge-provider-live-usage.py",
        "docs/data-providers.md",
        "docs/provider-live-validation.md",
        ".github/workflows/provider-live.yml",
        ".github/workflows/ci.yml",
        ".env.example",
        "backend/.env.example",
        "docker-compose.yml",
        "deploy/rpi/compose.yml",
    )
    return any(path.startswith(relevant) for path in result.stdout.splitlines())


def approved_live_deferrals(plan_path: Path | None = None) -> dict[str, str]:
    """Read human-approved provider deferrals from the branch-owned plan."""

    if plan_path is None:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
        slug = re.sub(r"[^A-Za-z0-9]+", "-", branch).strip("-").lower()
        plan_path = ROOT / "ops" / "workstreams" / slug / "plan.yaml"
    if not plan_path.is_file():
        return {}
    try:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    decisions = (
        plan.get("approved_execution_decisions") if isinstance(plan, dict) else None
    )
    providers = decisions.get("providers") if isinstance(decisions, dict) else None
    if not isinstance(providers, dict):
        return {}
    deferred: dict[str, str] = {}
    for provider, decision in providers.items():
        reason = str(decision or "").strip()
        if reason.lower().startswith("deferred by user"):
            name = str(provider).strip()
            if name not in LIVE_PROVIDER_CASES:
                raise ValueError(
                    f"workstream defers {name}, which has no live manifest disposition"
                )
            deferred[name] = reason
    return deferred


def selected_live_test_arguments(
    providers: list[str] | None,
    *,
    deferred_providers: set[str] | None = None,
    account_usage_only: bool = False,
    selected_cases: dict[str, set[str]] | None = None,
    dinari_sandbox_canary: bool = False,
) -> list[str]:
    """Return exact manifest nodes for a provider subset, or the full matrix."""
    if dinari_sandbox_canary:
        return [f"tests/live/{DINARI_CANARY_CASE[0]}::{DINARI_CANARY_CASE[1]}"]
    deferred = deferred_providers or set()
    if providers is None:
        selected = set(LIVE_PROVIDER_CASES) - deferred
    else:
        selected = set(providers)
    unknown = sorted(selected - set(LIVE_PROVIDER_CASES))
    if unknown:
        raise ValueError(f"providers have no live manifest cases: {', '.join(unknown)}")
    # Preserve manifest order. Pytest honors explicit node order, which lets a
    # provider put small/cost-sensitive probes before exhaustive pagination
    # cases. Sorting these names changes the schedule (e.g. Massive's full OTC
    # catalogue ran before its reference probe and consumed the remaining
    # rolling-window capacity).
    cases = dict.fromkeys(
        (relative_path, function_name)
        for provider in sorted(selected)
        for relative_path, function_name in LIVE_PROVIDER_CASES[provider]
        if selected_cases is None
        or function_name in selected_cases.get(provider, set())
        if not account_usage_only or "account_usage" in function_name
    )
    nodes = [
        f"tests/live/{relative_path}::{function_name}"
        for relative_path, function_name in cases
    ]
    # Several optional adapters intentionally share a parameterized live test.
    # Pytest's -k expression selects just the requested provider case while
    # keeping all cases for providers with dedicated functions.
    filter_terms = set() if account_usage_only else set(selected)
    shared_parameterized_cases = {"test_optional_credentialed_provider_small_read"}
    filter_terms.update(
        function_name.removeprefix("test_")
        for provider in selected
        for _relative_path, function_name in LIVE_PROVIDER_CASES[provider]
        if not account_usage_only or "account_usage" in function_name
        if function_name not in shared_parameterized_cases
    )
    if not nodes:
        return []
    return [*nodes, "-k", " or ".join(sorted(filter_terms))]


def live_test_provider_batches(
    providers: list[str] | None,
    *,
    isolate_provider_quota_windows: bool,
) -> list[list[str] | None]:
    """Keep each provider's native usage snapshot adjacent to its data tests."""

    if not isolate_provider_quota_windows:
        return [providers]
    if providers is None:
        raise ValueError(
            "provider-isolated live batches require an explicit provider list"
        )
    return [[provider] for provider in providers]


def parse_live_case_selectors(
    selectors: list[str] | None, providers: set[str]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Validate exact PROVIDER:case-function selectors and derive operations."""

    selected_cases: dict[str, set[str]] = {}
    selected_operations: dict[str, set[str]] = {}
    for selector in selectors or []:
        provider, separator, function_name = selector.partition(":")
        provider = provider.strip()
        function_name = function_name.strip()
        if not separator or not provider or not function_name:
            raise ValueError("--case must use PROVIDER:test_case_function")
        if provider not in providers:
            raise ValueError(
                f"--case provider {provider!r} must also be selected with --provider"
            )
        manifest_names = {name for _path, name in LIVE_PROVIDER_CASES.get(provider, ())}
        if function_name not in manifest_names:
            raise ValueError(
                f"--case {selector!r} is not in the live provider manifest"
            )
        operations = LIVE_CASE_OPERATIONS.get(provider, {}).get(function_name)
        if not operations:
            raise ValueError(
                f"--case {selector!r} has no explicit provider-operation mapping"
            )
        selected_cases.setdefault(provider, set()).add(function_name)
        selected_operations.setdefault(provider, set()).update(operations)
    return selected_cases, selected_operations


def selected_case_operation_multipliers(
    selected_cases: dict[str, set[str]],
) -> dict[str, dict[str, int]]:
    """Count same-operation calls represented by explicitly selected cases."""

    totals: dict[str, dict[str, int]] = {}
    for provider, case_names in selected_cases.items():
        provider_totals = totals.setdefault(provider, {})
        for case_name in case_names:
            operations = LIVE_CASE_OPERATIONS.get(provider, {}).get(case_name, set())
            case_multipliers = LIVE_CASE_OPERATION_MULTIPLIERS.get(provider, {}).get(
                case_name, {}
            )
            for operation in operations:
                count = case_multipliers.get(operation, 1)
                if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                    raise ValueError(
                        f"invalid operation multiplier for {provider}/{case_name}/{operation}"
                    )
                provider_totals[operation] = provider_totals.get(operation, 0) + count
    return totals


def _git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, text=True, capture_output=True, check=False
    )
    # Keep leading porcelain status columns intact. ``strip()`` corrupts the
    # first status line and can turn an ops/workstream path into a false source
    # modification during exact-SHA validation.
    return result.stdout.rstrip("\r\n") if result.returncode == 0 else ""


def _source_sha() -> str:
    return _git_output("rev-parse", "HEAD")


def _workstream_validation_path() -> Path | None:
    # Unit tests call runner helpers (and, in a few cases, ``main``) in the
    # same process as pytest.  Those calls intentionally use synthetic
    # providers and must never append acceptance-looking receipts to the
    # branch workstream ledger.  Real live runs execute this script as a
    # standalone process; an operator/CI can explicitly opt into persistence
    # while testing the runner itself with ``PROVIDER_LIVE_VALIDATION_WRITE``.
    if (
        os.getenv("PYTEST_CURRENT_TEST", "").strip()
        and os.getenv("PROVIDER_LIVE_VALIDATION_WRITE", "").strip() != "1"
    ):
        return None
    branch = _git_output("branch", "--show-current")
    if not branch:
        return None
    slug = re.sub(r"[^A-Za-z0-9]+", "-", branch).strip("-").lower()
    path = ROOT / "ops" / "workstreams" / slug / "validation.jsonl"
    return path if path.is_file() else None


def _dirty_source_paths() -> list[str]:
    status = _git_output("status", "--porcelain", "--untracked-files=all")
    paths: list[str] = []
    for line in status.splitlines():
        candidate = line[3:].split(" -> ")[-1] if len(line) >= 3 else line
        if candidate and not candidate.startswith("ops/workstreams/"):
            paths.append(candidate)
    return sorted(set(paths))


def _staged_candidate_from_git_state(
    *,
    status_output: str,
    unstaged_diff_exit_code: int,
    workstream_prefix: str = "",
    untracked_output: str,
    staged_paths: tuple[str, ...],
    staged_diff_output: str,
    tree_sha: str,
    parent_sha: str,
    staged_content: bytes = b"",
) -> tuple[dict[str, str] | None, str | None]:
    """Validate the staged source snapshot and reject unstaged source edits.

    Current-branch workstream records are excluded from the provider source
    candidate. Their unstaged notes may advance while a live matrix is running,
    provided the corresponding record is already represented in the staged
    candidate. All application, test, workflow, and other tracked changes must
    still be fully staged.
    """

    if not status_output.strip():
        return None, "no staged candidate changes"
    if unstaged_diff_exit_code not in {0, 1}:
        return None, "unable to inspect tracked working-tree changes"
    if untracked_output.strip():
        return (
            None,
            "untracked files must be staged or excluded before candidate validation",
        )

    for line in status_output.splitlines():
        if len(line) < 4:
            return None, "Git status contained an invalid porcelain record"
        index_status, worktree_status = line[0], line[1]
        if index_status == "?" or worktree_status == "?":
            return None, "untracked files are not part of the staged candidate tree"
        if index_status == " ":
            return None, "Git status contained a path with no staged change"
        if worktree_status != " ":
            path = line[3:].split(" -> ")[-1]
            if not workstream_prefix or not path.startswith(workstream_prefix):
                return None, "working-tree changes are not fully staged"

    changed_paths = list(staged_paths)
    if not changed_paths:
        return None, "the candidate index has no staged paths"
    for path in changed_paths:
        candidate_path = Path(path)
        basename = candidate_path.name.lower()
        path_parts = {part.lower() for part in candidate_path.parts}
        dotenv_file = basename == ".env" or (
            basename.startswith(".env.")
            and not basename.endswith((".example", ".sample", ".template"))
        )
        credential_name = basename in {
            "app.env",
            "credentials",
            "credentials.json",
            "credentials.yaml",
            "credentials.yml",
            "secrets",
            "secrets.json",
            "secrets.yaml",
            "secrets.yml",
            "id_rsa",
            "id_ed25519",
        }
        basename = Path(path).name.lower()
        if (
            dotenv_file
            or credential_name
            or bool(path_parts & {".ssh", "credentials", "secrets", "private_keys"})
            or candidate_path.suffix.lower()
            in {".pem", ".p12", ".pfx", ".key", ".p8", ".jks", ".keystore"}
        ):
            return None, f"credential-bearing path is prohibited in a candidate: {path}"

    secret_findings = staged_secret_findings(
        staged_diff_output, staged_content=staged_content
    )
    if secret_findings:
        return None, (
            "staged content resembles credential material: "
            + ", ".join(secret_findings)
        )

    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tree_sha):
        return None, "git write-tree did not return a valid tree identifier"
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", parent_sha):
        return None, "the staged candidate has no valid parent commit"
    return {"tree_sha": tree_sha, "parent_sha": parent_sha}, None


def _staged_changed_blob_content(
    paths: tuple[str, ...],
) -> tuple[bytes | None, str | None]:
    """Read changed index blobs, including binary blobs, for exact secret scans."""

    index = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if index.returncode:
        return None, "unable to inspect staged blob identities"
    requested = {os.fsencode(path) for path in paths}
    blobs: list[bytes] = []
    total_size = 0
    for entry in index.stdout.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, path = entry.split(b"\t", 1)
            _mode, object_id, stage = metadata.split()
        except ValueError:
            return None, "staged index contains an unrecognized entry"
        if path not in requested:
            continue
        if stage != b"0":
            return None, "staged merge-conflict entries cannot be scanned safely"
        size_result = subprocess.run(
            ["git", "cat-file", "-s", object_id.decode("ascii")],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if size_result.returncode:
            return None, "unable to inspect staged blob size"
        try:
            size = int(size_result.stdout.strip())
        except ValueError:
            return None, "staged blob reported an invalid size"
        if size > 20_000_000 or total_size + size > 100_000_000:
            return None, "staged secret scan exceeds its bounded blob-size budget"
        blob = subprocess.run(
            ["git", "cat-file", "blob", object_id.decode("ascii")],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if blob.returncode or len(blob.stdout) != size:
            return None, "unable to read exact staged blob content"
        blobs.append(blob.stdout)
        total_size += size
    return b"\n".join(blobs), None


def _staged_candidate_snapshot() -> tuple[dict[str, str] | None, str | None]:
    """Return the staged provider source candidate, excluding workstream notes."""

    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode:
        return None, "unable to inspect Git status"
    diff = subprocess.run(
        ["git", "diff", "--quiet", "--exit-code"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if untracked.returncode:
        return None, "unable to inspect untracked paths"
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=ROOT,
        text=False,
        capture_output=True,
        check=False,
    )
    if staged.returncode:
        return None, "unable to inspect staged paths"
    staged_diff = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-ext-diff", "--no-color"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if staged_diff.returncode:
        return None, "unable to scan staged content for credential material"
    staged_paths = tuple(
        os.fsdecode(path) for path in staged.stdout.split(b"\0") if path
    )
    staged_content, content_error = _staged_changed_blob_content(staged_paths)
    if content_error or staged_content is None:
        return None, content_error or "unable to scan staged blob content"
    branch = _git_output("branch", "--show-current")
    branch_slug = re.sub(r"[^A-Za-z0-9]+", "-", branch).strip("-").lower()
    workstream_prefix = f"ops/workstreams/{branch_slug}/" if branch_slug else ""
    candidate = _staged_candidate_from_git_state(
        status_output=status.stdout,
        unstaged_diff_exit_code=diff.returncode,
        workstream_prefix=workstream_prefix,
        untracked_output=untracked.stdout,
        staged_paths=staged_paths,
        staged_diff_output=staged_diff.stdout,
        tree_sha=_git_output("write-tree"),
        parent_sha=_source_sha(),
        staged_content=staged_content,
    )
    return candidate


def _candidate_source_unchanged(
    expected: dict[str, str], actual: dict[str, str] | None, error: str | None
) -> bool:
    """Compare Git identity fields, excluding provider-slice metadata."""

    return (
        error is None
        and actual is not None
        and expected.get("tree_sha") == actual.get("tree_sha")
        and expected.get("parent_sha") == actual.get("parent_sha")
    )


def _candidate_can_reuse_backend_environment(test_root: Path) -> bool:
    """Reuse the validated backend venv only when candidate dependencies match."""

    backend_root = ROOT / "backend"
    candidate_backend = test_root / "backend"
    environment_python = backend_root / ".venv" / "bin" / "python"
    if not environment_python.exists():
        return False
    for manifest in ("pyproject.toml", "uv.lock"):
        try:
            if (candidate_backend / manifest).read_bytes() != (
                backend_root / manifest
            ).read_bytes():
                return False
        except OSError:
            return False
    return True


def staged_secret_findings(
    staged_diff: str, *, staged_content: bytes = b""
) -> list[str]:
    """Return redacted names of configured or credential-shaped additions."""

    findings: list[str] = []
    added_diff = "\n".join(
        line
        for line in staged_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    secret_names = {name for names in CREDENTIALS.values() for name in names}
    secret_names.update(workflow_secret_environment_names())
    # These settings are live-test configuration/endpoint selectors, not
    # credentials.  Their URLs may legitimately appear in checked-in fixtures
    # and documentation, so scanning their configured values as secrets would
    # reject an otherwise safe staged candidate whenever an operator has a
    # matching local endpoint configured.
    secret_names.difference_update(
        {
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
            "IBKR_READ_ONLY_URL",
        }
    )
    for name in secret_names:
        value = os.getenv(name, "")
        if len(value) >= 6 and (
            value in staged_diff or value.encode("utf-8") in staged_content
        ):
            findings.append(name)

    private_key_marker = re.compile(
        r"(?m)^\s*\+?\s*-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*$"
    )
    if private_key_marker.search(added_diff) or private_key_marker.search(
        staged_content.decode("latin-1")
    ):
        findings.append("private-key material")

    secret_assignment_name = (
        r"([A-Z0-9_]*(?:API[_-]?KEY|CLIENT[_-]?(?:ID|SECRET)|"
        r"ACCESS[_-]?KEY|PRIVATE[_-]?KEY|SECRET|TOKEN|PASSWORD))"
    )
    # A source assignment is credential-shaped only when its value is a string
    # literal.  The previous optional-quote expression treated ordinary code
    # such as ``current_refresh_token = source.get(...)`` as though
    # ``source.get`` were a secret.  Exact configured credential values are
    # still scanned across the complete staged blobs above.
    quoted_assignment = re.compile(
        rf"(?im)^\+[^+\r\n]*?\b{secret_assignment_name}\b[\"']?\s*[:=]\s*"
        r"([\"'])([A-Za-z0-9_+/=.-]{20,})\2"
    )
    # Dotenv/shell-style uppercase assignments commonly omit quotes.  Keep a
    # separate, line-anchored detector for those without admitting arbitrary
    # Python expressions as values.
    unquoted_env_assignment = re.compile(
        rf"(?im)^\+\s*{secret_assignment_name}\s*=\s*"
        r"([A-Za-z0-9_+/=.-]{20,})\s*(?:#.*)?$"
    )
    placeholders = ("your_", "replace_", "example", "placeholder", "changeme", "<")
    safe_values = {"ci-contract-secret"}
    for match in quoted_assignment.finditer(added_diff):
        variable = match.group(1)
        value = match.group(3)
        normalized = value.lower()
        if normalized in safe_values or normalized.startswith(placeholders):
            continue
        findings.append(variable)
    for match in unquoted_env_assignment.finditer(added_diff):
        variable = match.group(1)
        value = match.group(2)
        normalized = value.lower()
        if normalized in safe_values or normalized.startswith(placeholders):
            continue
        findings.append(variable)

    dsn_assignment = re.compile(
        r"(?im)^\+[^+\r\n]*?\b([A-Z0-9_]*(?:DATABASE[_-]?URL|DB[_-]?URL|DSN|"
        r"CONNECTION[_-]?STRING|POSTGRES[_-]?URL))\b[\"']?\s*[:=]\s*"
        r"[\"']?([^\s\"'#]{12,})"
    )

    def is_local_example_dsn(value: str) -> bool:
        return bool(
            # Ignore the scanner's own regex literals; they contain URL-like
            # syntax and regex groups, but are not executable DSN values.
            "(?:" in value
            or "\\s" in value
            or "[" in value
            or '"' in value
            or "'" in value
            or re.fullmatch(
                r"(?i)(?:postgres(?:ql)?(?:\+[a-z0-9_]+)?)://postgres:postgres@(?:postgres|localhost|127\.0\.0\.1)(?::\d+)?/[^\s\"'<>]+",
                value,
            )
            or (
                "${POSTGRES_USER" in value
                and "${POSTGRES_PASSWORD" in value
                and "@postgres" in value
            )
        )

    for match in dsn_assignment.finditer(added_diff):
        variable, value = match.groups()
        if re.search(r"(?i)://[^/@:\s]+:[^/@\s]+@", value):
            if is_local_example_dsn(value):
                continue
            findings.append(variable)

    # Also catch an accidentally committed DSN in a binary/serialized blob or
    # an unlabelled line. Only report a finding label; never retain the URL.
    dsn_pattern = re.compile(
        r"(?i)\b(?:postgres(?:ql)?(?:\+[a-z0-9_]+)?|mysql|mariadb|mongodb(?:\+srv)?|redis(?:s)?)://"
        r"[^/@:\s]+:[^/@\s]+@[^\s\"'<>]+"
    )
    # Text additions are fully visible in the diff and are the authoritative
    # place to detect a newly introduced DSN.  Scan the full staged blob only
    # when it contains binary bytes; otherwise checked-in development examples
    # from unrelated files would be mistaken for newly added credentials.
    dsn_scan_text = added_diff
    if b"\x00" in staged_content:
        dsn_scan_text += "\n" + staged_content.decode("latin-1")
    for dsn in dsn_pattern.findall(dsn_scan_text):
        # The repository's checked-in development examples intentionally use
        # the Docker-local postgres/postgres credential.  It is not a runtime
        # secret; keep rejecting every other credentialed DSN.
        if is_local_example_dsn(dsn):
            continue
        findings.append("credentialed database URL")
        break
    return list(dict.fromkeys(findings))


def _checkout_index_candidate(destination: Path) -> tuple[bool, str | None]:
    """Materialize the exact index tree for tests, outside the mutable worktree."""

    files = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if files.returncode:
        return False, "could not enumerate staged files for exact-source tests"
    try:
        for raw_path in files.stdout.split(b"\0"):
            if raw_path:
                (destination / os.fsdecode(raw_path)).parent.mkdir(
                    parents=True, exist_ok=True
                )
    except OSError:
        return False, "could not create staged-file directories for exact-source tests"

    result = subprocess.run(
        ["git", "checkout-index", "--all", f"--prefix={destination}{os.sep}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return False, "could not materialize staged index for exact-source tests"
    return True, None


def redact_runner_output(value: str) -> str:
    """Mask credentials before any pytest output is shown in a terminal/log."""

    redacted = value
    secret_names = {name for names in CREDENTIALS.values() for name in names}
    secret_names.update(workflow_secret_environment_names())
    secret_names.update({"DINARI_API_SECRET_KEY", "FINRA_CLIENT_SECRET"})
    for name in secret_names:
        secret = os.getenv(name, "")
        if len(secret) >= 4:
            redacted = redacted.replace(secret, "<redacted>")
    redacted = re.sub(
        r"(?i)([?&](?:api[_-]?key|apikey|access[_-]?(?:key|token)|client_secret|secret|token)=)[^&\s'\"<>]+",
        r"\1<redacted>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)\S+",
        r"\1<redacted>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(authorization\s*:\s*basic\s+)\S+",
        r"\1<redacted>",
        redacted,
    )
    return redacted


def _junit_counts(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {
            "case_count": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "skipped_cases": 0,
        }
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {
        "case_count": sum(int(suite.attrib.get("tests", 0)) for suite in suites),
        "failed_cases": sum(
            int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
            for suite in suites
        ),
        "skipped_cases": sum(int(suite.attrib.get("skipped", 0)) for suite in suites),
    }
    counts["passed_cases"] = max(
        0, counts["case_count"] - counts["failed_cases"] - counts["skipped_cases"]
    )
    return counts


def _junit_case_results(path: Path) -> list[dict[str, str]]:
    """Return sanitized, exact pytest node outcomes from JUnit XML."""

    if not path.is_file():
        return []
    root = ElementTree.parse(path).getroot()
    results: list[dict[str, str]] = []
    for case in root.iter("testcase"):
        name = str(case.attrib.get("name", ""))
        classname = str(case.attrib.get("classname", ""))
        if not name or not classname:
            continue
        if any(child.tag in {"failure", "error"} for child in case):
            outcome = "failed"
        elif any(child.tag == "skipped" for child in case):
            outcome = "skipped"
        else:
            outcome = "passed"
        results.append(
            {
                "module": classname.rsplit(".", 1)[-1] + ".py",
                "name": name,
                "outcome": outcome,
            }
        )
    return results


def _manifest_case_matches(
    result: dict[str, str],
    *,
    relative_path: str,
    function_name: str,
    provider: str,
) -> bool:
    if result.get("module") != relative_path:
        return False
    name = result.get("name", "")
    base_name = name.split("[", 1)[0]
    if base_name != function_name:
        return False
    if function_name == "test_optional_credentialed_provider_small_read":
        return provider in name.split("[", 1)[1].lower() if "[" in name else False
    return True


def _provider_live_evidence(
    *,
    run_id: str,
    providers: set[str],
    junit_cases: list[dict[str, str]],
    ledger_path: Path | None = None,
    account_usage_only: bool = False,
    selected_cases: dict[str, set[str]] | None = None,
    required_operations_override: dict[str, set[str]] | None = None,
) -> dict[str, object]:
    """Correlate exact manifest cases and measured provider operations to one run."""

    usage_path = (
        ledger_path
        or Path(
            os.getenv("PROVIDER_LIVE_USAGE_LEDGER", "").strip()
            or (
                Path.home()
                / ".config"
                / "charting-platform"
                / "provider-live-usage.jsonl"
            )
        ).expanduser()
    )
    expected_scope = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip()
    rows: list[dict[str, object]] = []
    ledger_error = ""
    seen_reservation_ids: set[str] = set()
    seen_case_ids: set[tuple[str, str]] = set()
    seen_reservation_operations: set[tuple[str, str, str]] = set()
    seen_case_operations: set[tuple[str, str, str]] = set()
    try:
        if usage_path.is_file():
            with usage_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        ledger_error = "usage ledger contains malformed JSON"
                        continue
                    if not isinstance(row, dict) or row.get("run_id") != run_id:
                        continue
                    if expected_scope and row.get("usage_scope") != expected_scope:
                        continue
                    reservations = row.get("reservations")
                    if reservations is not None:
                        if not isinstance(reservations, list):
                            ledger_error = (
                                "usage ledger reservations field is malformed"
                            )
                        else:
                            for reservation in reservations:
                                if not isinstance(reservation, dict):
                                    ledger_error = (
                                        "usage ledger reservation entry is malformed"
                                    )
                                    continue
                                reservation_id = str(
                                    reservation.get("reservation_id") or ""
                                ).strip()
                                provider_name = str(row.get("provider") or "")
                                operation_name = str(
                                    reservation.get("operation") or ""
                                ).strip()
                                if not reservation_id or not operation_name:
                                    ledger_error = "usage ledger reservation identity is incomplete"
                                    continue
                                if reservation_id in seen_reservation_ids:
                                    ledger_error = "usage ledger contains duplicate reservation identity"
                                seen_reservation_ids.add(reservation_id)
                                reservation_key = (
                                    provider_name,
                                    operation_name,
                                    reservation_id,
                                )
                                if reservation_key in seen_reservation_operations:
                                    ledger_error = "usage ledger contains duplicate operation receipt"
                                seen_reservation_operations.add(reservation_key)
                    case_usage = row.get("case_usage")
                    if isinstance(case_usage, dict):
                        for case_id, case_row in case_usage.items():
                            case_key = (str(row.get("provider") or ""), str(case_id))
                            if case_key in seen_case_ids:
                                ledger_error = (
                                    "usage ledger contains duplicate case receipt"
                                )
                            seen_case_ids.add(case_key)
                            if not isinstance(case_row, dict):
                                ledger_error = "usage ledger case receipt is malformed"
                                continue
                            for operation_name in case_row.get("operations") or {}:
                                operation_key = (
                                    case_key[0],
                                    case_key[1],
                                    str(operation_name),
                                )
                                if operation_key in seen_case_operations:
                                    ledger_error = "usage ledger contains duplicate case operation receipt"
                                seen_case_operations.add(operation_key)
                    rows.append(row)
        else:
            ledger_error = "same-run usage ledger receipt is missing"
    except OSError:
        ledger_error = "same-run usage ledger is unreadable"

    provider_rows: dict[str, dict[str, object]] = {}
    for row in rows:
        provider = str(row.get("provider", ""))
        if provider not in providers:
            continue
        aggregate = provider_rows.setdefault(
            provider,
            {
                "http_requests": 0,
                "response_bytes": 0,
                "failed_operations": 0,
                "operation_usage": {},
                "case_usage": {},
            },
        )
        aggregate["http_requests"] += max(0, int(row.get("http_requests", 0) or 0))
        aggregate["response_bytes"] += max(0, int(row.get("response_bytes", 0) or 0))
        aggregate["failed_operations"] += max(
            0, int(row.get("failed_operations", 0) or 0)
        )
        for operation, operation_row in (row.get("operation_usage") or {}).items():
            if not isinstance(operation_row, dict):
                continue
            target = aggregate["operation_usage"].setdefault(
                str(operation),
                {
                    "http_requests": 0,
                    "response_bytes": 0,
                    "failed_operations": 0,
                    "dispositions": {},
                    "response_statuses": {},
                },
            )
            for key in ("http_requests", "response_bytes", "failed_operations"):
                target[key] += max(0, int(operation_row.get(key, 0) or 0))
            for dimension in ("dispositions", "response_statuses"):
                for value, count in (operation_row.get(dimension) or {}).items():
                    counts = target[dimension]
                    counts[str(value)] = counts.get(str(value), 0) + max(
                        0, int(count or 0)
                    )
        for case_id, case_row in (row.get("case_usage") or {}).items():
            if not isinstance(case_row, dict):
                continue
            existing = aggregate["case_usage"].setdefault(
                str(case_id),
                {"http_requests": 0, "response_bytes": 0, "operations": {}},
            )
            existing["http_requests"] += max(
                0, int(case_row.get("http_requests", 0) or 0)
            )
            existing["response_bytes"] += max(
                0, int(case_row.get("response_bytes", 0) or 0)
            )
            for operation, operation_row in (case_row.get("operations") or {}).items():
                if not isinstance(operation_row, dict):
                    continue
                target = existing["operations"].setdefault(
                    str(operation),
                    {
                        "http_requests": 0,
                        "response_bytes": 0,
                        "failed_operations": 0,
                        "dispositions": {},
                        "response_statuses": {},
                    },
                )
                for key in ("http_requests", "response_bytes", "failed_operations"):
                    target[key] += max(0, int(operation_row.get(key, 0) or 0))
                for dimension in ("dispositions", "response_statuses"):
                    for value, count in (operation_row.get(dimension) or {}).items():
                        counts = target[dimension]
                        counts[str(value)] = counts.get(str(value), 0) + max(
                            0, int(count or 0)
                        )

    missing: list[str] = []
    case_results: list[dict[str, object]] = []
    operation_results: dict[str, dict[str, object]] = {}
    manifest_cases = {
        provider: tuple(
            (relative_path, function_name)
            for relative_path, function_name in LIVE_PROVIDER_CASES[provider]
            if selected_cases is None
            or function_name in selected_cases.get(provider, set())
            if not account_usage_only or "account_usage" in function_name
        )
        for provider in providers
    }
    required_operations = {
        provider: (
            {"fetch_account_usage"}
            if account_usage_only
            else (
                required_operations_override.get(provider, set())
                if required_operations_override is not None
                else LIVE_REQUIRED_OPERATIONS[provider]
            )
        )
        for provider in providers
    }
    for provider in sorted(providers):
        for relative_path, function_name in manifest_cases[provider]:
            matches = [
                result
                for result in junit_cases
                if _manifest_case_matches(
                    result,
                    relative_path=relative_path,
                    function_name=function_name,
                    provider=provider,
                )
            ]
            match = matches[0] if len(matches) == 1 else None
            if len(matches) > 1:
                missing.append(
                    f"{provider}:{function_name} has ambiguous JUnit case matches"
                )
            case_key = (provider, relative_path, function_name)
            active_no_request_cases = active_live_no_request_cases()
            is_no_request_case = case_key in active_no_request_cases
            expected_denials = LIVE_EXPECTED_ENTITLEMENT_DENIALS.get(case_key, {})
            is_expected_denial_case = bool(expected_denials)
            case_ids = [
                case_id
                for case_id in (provider_rows.get(provider, {}).get("case_usage", {}))
                if _manifest_case_matches(
                    {
                        "module": Path(relative_path).name,
                        "name": str(case_id).split("::", 1)[-1],
                    },
                    relative_path=Path(relative_path).name,
                    function_name=function_name,
                    provider=provider,
                )
            ]
            result: dict[str, object] = {
                "provider": provider,
                "case": f"{relative_path}::{function_name}",
                "disposition": (
                    "intentional_no_request_policy"
                    if is_no_request_case
                    else "expected_entitlement_denial"
                    if is_expected_denial_case
                    else "live_required"
                ),
                "pytest": match["outcome"] if match else "missing",
                "http_requests": sum(
                    int(provider_rows[provider]["case_usage"][case_id]["http_requests"])
                    for case_id in case_ids
                )
                if provider in provider_rows
                else 0,
            }
            if match is None or match["outcome"] != "passed":
                missing.append(
                    f"{provider}:{function_name} did not pass as a manifest case"
                )
            if is_no_request_case:
                result["reason"] = active_no_request_cases[case_key]
                if int(result["http_requests"]):
                    missing.append(
                        f"{provider}:{function_name} unexpectedly made a provider request"
                    )
            elif not case_ids or not int(result["http_requests"]):
                missing.append(
                    f"{provider}:{function_name} has no same-run measured HTTP evidence"
                )
            if is_expected_denial_case and provider in provider_rows:
                for operation, expected_status in expected_denials.items():
                    operation_rows = [
                        provider_rows[provider]["case_usage"][case_id][
                            "operations"
                        ].get(operation, {})
                        for case_id in case_ids
                    ]
                    observed_statuses = {
                        status
                        for operation_row in operation_rows
                        for status in operation_row.get("response_statuses", {})
                    }
                    observed_dispositions = {
                        disposition
                        for operation_row in operation_rows
                        for disposition in operation_row.get("dispositions", {})
                    }
                    result.setdefault("expected_http_statuses", {})[operation] = (
                        expected_status
                    )
                    if "expected_entitlement_denial" not in observed_dispositions:
                        missing.append(
                            f"{provider}:{function_name} did not record the explicit "
                            f"expected_entitlement_denial disposition for {operation}"
                        )
                    if str(expected_status) not in observed_statuses:
                        missing.append(
                            f"{provider}:{function_name} did not observe expected HTTP {expected_status} for {operation}"
                        )
            case_results.append(result)

        observed = provider_rows.get(provider, {})
        observed_operations = observed.get("operation_usage", {})
        provider_operation_results: dict[str, object] = {}
        for operation in sorted(required_operations[provider]):
            operation_row = observed_operations.get(operation, {})
            requests = int(operation_row.get("http_requests", 0) or 0)
            bytes_received = int(operation_row.get("response_bytes", 0) or 0)
            failed = int(operation_row.get("failed_operations", 0) or 0)
            operation_ok = requests > 0 and bytes_received > 0 and failed == 0
            provider_operation_results[operation] = {
                "http_requests": requests,
                "response_bytes": bytes_received,
                "failed_operations": failed,
                "dispositions": operation_row.get("dispositions", {}),
                "response_statuses": operation_row.get("response_statuses", {}),
                "passed": operation_ok,
            }
            if not operation_ok:
                missing.append(
                    f"{provider}:{operation} lacks successful measured HTTP evidence"
                )
        operation_results[provider] = provider_operation_results

    # A provider can have a green bounded case while another adapter method
    # remains unprobed.  Only genuinely unresolved dispositions fail the
    # evidence result.  Expected entitlement denials and explicit no-request
    # policy cases are still emitted as coverage metadata, but are not treated
    # as successful provider data reads.
    for provider in sorted(set(providers) & set(LIVE_OPERATION_DISPOSITIONS)):
        # Account-usage-only runs intentionally validate only the dedicated
        # native introspection case.  Data-operation dispositions belong to
        # the full provider matrix and must not turn a focused baseline refresh
        # into a misleading incomplete result.
        if account_usage_only:
            continue
        for operation, disposition in sorted(
            LIVE_OPERATION_DISPOSITIONS[provider].items()
        ):
            if (
                required_operations_override is not None
                and operation not in required_operations_override.get(provider, set())
            ):
                continue
            kind = live_operation_disposition_kind(disposition)
            if kind not in LIVE_COVERED_DISPOSITION_KINDS:
                missing.append(
                    f"{provider}:{operation} has unresolved live disposition: {disposition}"
                )

    evidence = {
        "run_id": run_id,
        "usage_scope": expected_scope or None,
        "ledger_receipt_rows": len(rows),
        "ledger_error": ledger_error or None,
        "providers": {
            provider: {
                "http_requests": int(row["http_requests"]),
                "response_bytes": int(row["response_bytes"]),
                "failed_operations": int(row["failed_operations"]),
                "operations": operation_results.get(provider, {}),
            }
            for provider, row in sorted(provider_rows.items())
        },
        "operation_dispositions": {
            provider: {
                operation: {
                    "kind": live_operation_disposition_kind(disposition),
                    "reason": disposition,
                }
                for operation, disposition in sorted(dispositions.items())
            }
            for provider, dispositions in sorted(LIVE_OPERATION_DISPOSITIONS.items())
            if provider in providers
        },
        "operation_aliases": dict(sorted(LIVE_OPERATION_METHOD_ALIASES.items())),
        "service_operation_aliases": dict(
            sorted(LIVE_SERVICE_OPERATION_ALIASES.items())
        ),
        "provider_safety_dispositions": {
            provider: {
                "kind": "intentional_no_request_policy",
                "reason": reason,
            }
            for provider, reason in sorted(
                active_live_provider_safety_dispositions().items()
            )
            if provider in providers
        },
        "cases": case_results,
        "selection": "case_subset"
        if selected_cases is not None
        else "provider_or_full_matrix",
        "selected_cases": {
            provider: sorted(names)
            for provider, names in sorted((selected_cases or {}).items())
        },
        "missing": sorted(set(missing)),
        "complete": not missing and not ledger_error,
    }
    if ledger_error:
        evidence["complete"] = False
        evidence["missing"] = sorted(set([*missing, ledger_error]))
    return evidence


def _is_plain_integer(value: object) -> bool:
    """Distinguish numeric JSON counters from booleans (which subclass int)."""

    return isinstance(value, int) and not isinstance(value, bool)


def _dinari_candidate_canary_evidence_errors(
    evidence: object,
) -> list[str]:
    """Validate the exact one-request evidence allowed for Dinari Sandbox."""

    errors: list[str] = []
    if not isinstance(evidence, dict) or evidence.get("complete") is not True:
        return ["Dinari canary same-run evidence is incomplete"]
    providers = evidence.get("providers")
    if not isinstance(providers, dict) or set(providers) != {"dinari"}:
        errors.append("Dinari canary evidence must be isolated to Dinari")
    provider_row = providers.get("dinari") if isinstance(providers, dict) else None
    operations = (
        provider_row.get("operations") if isinstance(provider_row, dict) else None
    )
    if not isinstance(operations, dict) or set(operations) != {DINARI_CANARY_OPERATION}:
        errors.append(
            "Dinari canary evidence must contain only the catalogue operation"
        )
    else:
        operation = operations[DINARI_CANARY_OPERATION]
        if not isinstance(operation, dict):
            errors.append("Dinari catalogue operation evidence is malformed")
        else:
            request_count = operation.get("http_requests")
            response_bytes = operation.get("response_bytes")
            failed_operations = operation.get("failed_operations")
            if (
                operation.get("passed") is not True
                or not _is_plain_integer(request_count)
                or request_count != 1
                or not _is_plain_integer(response_bytes)
                or response_bytes <= 0
                or not _is_plain_integer(failed_operations)
                or failed_operations != 0
            ):
                errors.append(
                    "Dinari catalogue evidence must prove exactly one successful read"
                )

    cases = evidence.get("cases")
    expected_case = f"{DINARI_CANARY_CASE[0]}::{DINARI_CANARY_CASE[1]}"
    if not isinstance(cases, list) or len(cases) != 1:
        errors.append(
            "Dinari canary must execute exactly its single approved manifest case"
        )
    else:
        case = cases[0]
        if not isinstance(case, dict) or (
            case.get("case") != expected_case
            or case.get("pytest") != "passed"
            or not _is_plain_integer(case.get("http_requests"))
            or case.get("http_requests") != 1
            or case.get("disposition") != "live_required"
        ):
            errors.append(
                "Dinari canary manifest case did not prove one successful HTTP read"
            )

    safety = evidence.get("provider_safety_dispositions")
    dinari_safety = safety.get("dinari") if isinstance(safety, dict) else None
    if not isinstance(safety, dict) or set(safety) != {"dinari"}:
        errors.append("Dinari canary safety evidence must be provider-isolated")
    if not isinstance(dinari_safety, dict) or (
        dinari_safety.get("kind") != "intentional_no_request_policy"
        or dinari_safety.get("reason") != DINARI_CANARY_SAFETY_REASON
    ):
        errors.append("Dinari ordinary Sandbox operations are not proven quarantined")
    return errors


def _dinari_candidate_canary_receipt_errors(
    receipt: dict[str, object],
    *,
    candidate_tree_sha: str,
    candidate_parent_sha: str,
) -> list[str]:
    """Validate a Dinari canary receipt without treating it as a full suite."""

    errors: list[str] = []
    if receipt.get("scope") != "provider_candidate_canary":
        errors.append("Dinari canary receipt has the wrong scope")
    if receipt.get("result") != "staged_candidate_canary_passed":
        errors.append("Dinari candidate canary did not pass")
    if receipt.get("canary_mode") != "dinari_sandbox":
        errors.append("Dinari receipt is not tagged as the approved Sandbox canary")
    if receipt.get("canary_max_requests") != 1:
        errors.append("Dinari canary receipt does not record the one-request cap")
    if receipt.get("providers_selected") != ["dinari"] or receipt.get(
        "providers_run"
    ) != ["dinari"]:
        errors.append("Dinari canary receipt is not isolated to Dinari")
    if receipt.get("selected_cases") != {}:
        errors.append("Dinari canary receipt must use the approved fixed manifest case")
    if receipt.get("candidate_unchanged") is not True:
        errors.append("candidate changed during the Dinari canary")
    if receipt.get("candidate_tree_sha") != candidate_tree_sha:
        errors.append(
            "Dinari canary tree differs beyond append-only validation evidence"
        )
    if receipt.get("candidate_parent_sha") != candidate_parent_sha:
        errors.append("Dinari canary parent does not match current HEAD")
    if receipt.get("live_acceptance") is not False:
        errors.append("Dinari canary receipt overstates full live acceptance")
    try:
        counts = {
            name: receipt.get(name)
            for name in ("case_count", "passed_cases", "failed_cases", "skipped_cases")
        }
        exit_code = receipt.get("exit_code")
    except (TypeError, ValueError):
        errors.append("Dinari canary receipt counts are invalid")
    else:
        if (
            any(not _is_plain_integer(value) for value in counts.values())
            or counts
            != {
                "case_count": 1,
                "passed_cases": 1,
                "failed_cases": 0,
                "skipped_cases": 0,
            }
            or not _is_plain_integer(exit_code)
            or exit_code != 0
        ):
            errors.append(
                "Dinari canary receipt must show one passing test and zero failures"
            )
    errors.extend(
        _dinari_candidate_canary_evidence_errors(receipt.get("live_evidence"))
    )
    return errors


def _record_live_validation(
    *,
    providers: list[str] | None,
    exit_code: int,
    missing: dict[str, list[str]],
    counts: dict[str, int],
    approved_deferrals: dict[str, str],
    live_evidence: dict[str, object] | None = None,
    candidate_tree: dict[str, str] | None = None,
    candidate_unchanged: bool = True,
    canary_mode: bool = False,
    selected_cases: dict[str, set[str]] | None = None,
    full_matrix_requested: bool | None = None,
    requested_providers: list[str] | None = None,
    quarantined_providers: list[str] | None = None,
    candidate_receipt_file: Path | None = None,
) -> str:
    """Persist a redacted live-test receipt in the active branch workstream."""

    path = _workstream_validation_path()
    dirty_paths = _dirty_source_paths()
    # ``None`` means the caller requested the complete manifest. An empty
    # list is a real (empty) provider subset, which can occur when every
    # provider is quarantined by its own admission controls.
    full_matrix = (
        providers is None if full_matrix_requested is None else full_matrix_requested
    )
    requested = providers if requested_providers is None else requested_providers
    if candidate_tree is not None:
        if not candidate_unchanged:
            result = "staged_candidate_changed_during_run"
        elif missing:
            result = "staged_candidate_incomplete_preflight"
        elif (
            exit_code != 0
            or counts["case_count"] == 0
            or counts["failed_cases"]
            or counts["skipped_cases"]
        ):
            result = "staged_candidate_failed"
        elif not live_evidence or not live_evidence.get("complete"):
            result = "staged_candidate_missing_live_evidence"
        elif canary_mode:
            canary_errors = _dinari_candidate_canary_evidence_errors(live_evidence)
            result = (
                "staged_candidate_canary_passed"
                if candidate_tree.get("provider") == "dinari" and not canary_errors
                else "staged_candidate_missing_live_evidence"
            )
        elif full_matrix:
            result = "staged_candidate_full_matrix_passed"
        elif candidate_tree.get("provider") and selected_cases:
            result = "staged_candidate_case_passed"
        elif candidate_tree.get("provider"):
            result = "staged_candidate_provider_passed"
        else:
            result = "staged_candidate_not_full_matrix"
    elif dirty_paths:
        result = "not_current_source"
    elif missing:
        result = "incomplete_preflight"
    elif exit_code != 0 or counts["failed_cases"] or counts["skipped_cases"]:
        result = "failed"
    elif not live_evidence or not live_evidence.get("complete"):
        result = "missing_live_evidence"
    elif full_matrix:
        result = "passed"
    else:
        result = "focused_passed"
    receipt = {
        "at": datetime.now(UTC).isoformat(),
        "command": "scripts/run-live-provider-probes.py",
        "kind": "provider_live_matrix",
        "scope": (
            "full_matrix"
            if full_matrix
            else "provider_candidate_canary"
            if candidate_tree is not None and canary_mode
            else "provider_candidate"
            if candidate_tree is not None
            and candidate_tree.get("provider")
            and selected_cases is None
            else "provider_candidate_case"
            if candidate_tree is not None
            and candidate_tree.get("provider")
            and selected_cases is not None
            else "case_focused"
            if selected_cases is not None
            else "focused"
        ),
        "result": result,
        "source_sha": _source_sha(),
        "dirty_source_paths": dirty_paths,
        **counts,
        "missing_environment_names": sorted(
            {
                name
                for names in missing.values()
                for name in names
                if re.fullmatch(r"[A-Z][A-Z0-9_]+", name)
            }
        ),
        "preflight_blockers": {
            key: list(value) for key, value in sorted(missing.items())
        },
        "providers_selected": sorted(requested or []),
        "providers_quarantined": sorted(quarantined_providers or []),
        "selected_cases": {
            provider: sorted(names)
            for provider, names in sorted((selected_cases or {}).items())
        },
        "providers_run": sorted(
            set(providers)
            if providers is not None
            else set(LIVE_PROVIDER_CASES) - set(approved_deferrals)
        ),
        "live_acceptance": result == "staged_candidate_full_matrix_passed",
        "candidate_unchanged": candidate_unchanged,
        "live_evidence": live_evidence
        or {"complete": False, "missing": ["same-run live evidence unavailable"]},
        "approved_deferrals": approved_deferrals if full_matrix else {},
        "exit_code": exit_code,
        **({"canary_mode": "dinari_sandbox"} if canary_mode else {}),
        **({"canary_max_requests": 1} if canary_mode else {}),
    }
    if candidate_tree is not None:
        receipt["candidate_tree_sha"] = candidate_tree["tree_sha"]
        receipt["candidate_parent_sha"] = candidate_tree["parent_sha"]
        receipt["persisted_to_workstream"] = False
        if candidate_receipt_file is not None and result in {
            "staged_candidate_provider_passed",
            "staged_candidate_case_passed",
            "staged_candidate_canary_passed",
        }:
            resolved_receipt_file = candidate_receipt_file.expanduser().resolve()
            if resolved_receipt_file.is_relative_to(ROOT.resolve()):
                raise ValueError(
                    "candidate receipt file must be outside the source worktree"
                )
            resolved_receipt_file.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                resolved_receipt_file,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(receipt, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        print("staged candidate receipt: " + json.dumps(receipt, sort_keys=True))
    elif path is not None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, sort_keys=True) + "\n")
    print(
        "provider live receipt: "
        f"{result} ({counts['passed_cases']}/{counts['case_count']} cases; "
        f"source {candidate_tree['tree_sha'] if candidate_tree else receipt['source_sha'] or 'unknown'})"
    )
    if result in {
        "staged_candidate_provider_passed",
        "staged_candidate_case_passed",
    }:
        print(
            "pre-commit provider/case-slice evidence only; this is not full live acceptance"
        )
    elif result == "staged_candidate_canary_passed":
        print(
            "pre-commit Dinari canary evidence only; ordinary Sandbox operations remain quarantined"
        )
    return result


def verify_candidate_provider_receipts(
    receipt_file: Path,
    *,
    candidate_tree_sha: str,
    candidate_parent_sha: str,
    required_providers: set[str],
) -> dict[str, object]:
    """Verify one complete, same-tree live receipt for every required provider."""

    def workstream_evidence_only_update(previous_tree: str, current_tree: str) -> bool:
        """Allow operational workstream updates without invalidating live slices.

        Provider receipts are bound to the staged candidate. Appending the
        validation ledger or handoff, and updating only routine progress fields
        in session.json, do not change the tested provider implementation or
        acceptance contract. Every other path remains part of the exact source
        snapshot and therefore invalidates prior provider receipts.
        """

        workstream = "ops/workstreams/feat-market-data-provider-platform"
        validation_path = f"{workstream}/validation.jsonl"
        handoff_path = f"{workstream}/handoff.md"
        session_path = f"{workstream}/session.json"
        try:
            changed_paths = subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-only",
                    previous_tree,
                    current_tree,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            changed = set(changed_paths.stdout.splitlines())
            allowed = {validation_path, handoff_path, session_path}
            if not changed or not changed <= allowed:
                return False

            for append_only_path in (validation_path, handoff_path):
                if append_only_path not in changed:
                    continue
                before = subprocess.run(
                    ["git", "show", f"{previous_tree}:{append_only_path}"],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    timeout=10,
                ).stdout
                after = subprocess.run(
                    ["git", "show", f"{current_tree}:{append_only_path}"],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    timeout=10,
                ).stdout
                if len(after) <= len(before) or not after.startswith(before):
                    return False

            if session_path in changed:
                before = json.loads(
                    subprocess.run(
                        ["git", "show", f"{previous_tree}:{session_path}"],
                        cwd=ROOT,
                        check=True,
                        capture_output=True,
                        timeout=10,
                    ).stdout
                )
                after = json.loads(
                    subprocess.run(
                        ["git", "show", f"{current_tree}:{session_path}"],
                        cwd=ROOT,
                        check=True,
                        capture_output=True,
                        timeout=10,
                    ).stdout
                )
                before_progress = before.get("progress")
                after_progress = after.get("progress")
                if not isinstance(before_progress, dict) or not isinstance(
                    after_progress, dict
                ):
                    return False
                before_human_progress = before.get("last_human_progress_update")
                after_human_progress = after.get("last_human_progress_update")
                if isinstance(before_human_progress, str) and isinstance(
                    after_human_progress, str
                ):
                    before.pop("last_human_progress_update", None)
                    after.pop("last_human_progress_update", None)
                for field in (
                    "current_blocker",
                    "current_phase",
                    "next_action",
                    "updated_at",
                ):
                    before_progress.pop(field, None)
                    after_progress.pop(field, None)
                if before != after or before_progress != after_progress:
                    return False
        except (OSError, subprocess.SubprocessError):
            return False
        except (json.JSONDecodeError, AttributeError, TypeError):
            return False
        return True

    path = receipt_file.expanduser().resolve()
    if path.is_relative_to(ROOT.resolve()):
        return {
            "complete": False,
            "missing": ["candidate receipt file must be outside the source worktree"],
            "providers_verified": [],
        }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {
            "complete": False,
            "missing": [f"candidate receipt file cannot be read: {type(exc).__name__}"],
            "providers_verified": [],
        }

    receipts: list[dict[str, object]] = []
    errors: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line {line_number} is not valid JSON")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number} is not a receipt object")
            continue
        receipts.append(value)

    by_provider: dict[str, list[dict[str, object]]] = {}
    for receipt in receipts:
        providers_run = receipt.get("providers_run")
        provider = (
            providers_run[0]
            if isinstance(providers_run, list) and len(providers_run) == 1
            else None
        )
        if not isinstance(provider, str):
            errors.append("receipt is not a single-provider complete-manifest slice")
            continue
        by_provider.setdefault(provider, []).append(receipt)

    verified: list[str] = []
    canaries_verified: list[str] = []
    compatible_candidate_trees = {candidate_tree_sha}
    for provider in sorted(required_providers):
        matches = by_provider.get(provider, [])
        if not matches:
            errors.append(f"{provider}: no successful receipt was recorded")
            continue
        for item in matches:
            receipt_tree = item.get("candidate_tree_sha")
            if (
                isinstance(receipt_tree, str)
                and receipt_tree not in compatible_candidate_trees
                and item.get("candidate_parent_sha") == candidate_parent_sha
                and workstream_evidence_only_update(receipt_tree, candidate_tree_sha)
            ):
                compatible_candidate_trees.add(receipt_tree)
        matching_tree = [
            item
            for item in matches
            if item.get("candidate_tree_sha") in compatible_candidate_trees
            and item.get("candidate_parent_sha") == candidate_parent_sha
        ]
        if not matching_tree:
            errors.append(f"{provider}: no receipt matches the current candidate tree")
            continue
        if provider == "dinari":
            canary_receipts = [
                item
                for item in matching_tree
                if item.get("scope") == "provider_candidate_canary"
            ]
            if canary_receipts:
                routine_receipts = [
                    item
                    for item in matching_tree
                    if item.get("scope")
                    in {"provider_candidate", "provider_candidate_case"}
                ]
                if routine_receipts:
                    errors.append(
                        "dinari: ordinary Sandbox live receipts violate the canary-only policy"
                    )
                    continue
                canary = max(
                    canary_receipts, key=lambda item: str(item.get("at") or "")
                )
                canary_errors = _dinari_candidate_canary_receipt_errors(
                    canary,
                    candidate_tree_sha=candidate_tree_sha,
                    candidate_parent_sha=candidate_parent_sha,
                )
                if canary_errors:
                    errors.extend(f"dinari: {message}" for message in canary_errors)
                else:
                    canaries_verified.append(provider)
                    errors.append(
                        "dinari: one-request Sandbox canary is verified, but it does "
                        "not satisfy full provider acceptance; the complete live "
                        "manifest is still required"
                    )
                continue
        full_receipts = [
            item for item in matching_tree if item.get("scope") == "provider_candidate"
        ]
        case_receipts: dict[str, dict[str, object]] = {}
        if full_receipts:
            selected_receipts = [
                max(full_receipts, key=lambda item: str(item.get("at") or ""))
            ]
            expected_case_operations = set(LIVE_REQUIRED_OPERATIONS.get(provider, ()))
        else:
            for item in matching_tree:
                if (
                    item.get("scope") != "provider_candidate_case"
                    or item.get("result") != "staged_candidate_case_passed"
                ):
                    continue
                raw_selected = item.get("selected_cases")
                selected = (
                    raw_selected.get(provider)
                    if isinstance(raw_selected, dict)
                    else None
                )
                if (
                    not isinstance(raw_selected, dict)
                    or set(raw_selected) != {provider}
                    or not isinstance(selected, list)
                    or not selected
                    or any(not isinstance(name, str) for name in selected)
                ):
                    errors.append(f"{provider}: malformed selected-case receipt")
                    continue
                for case_name in selected:
                    previous = case_receipts.get(case_name)
                    if previous is None or str(item.get("at") or "") > str(
                        previous.get("at") or ""
                    ):
                        case_receipts[case_name] = item
            expected_cases = {
                function_name
                for _path, function_name in LIVE_PROVIDER_CASES.get(provider, ())
            }
            if set(case_receipts) != expected_cases:
                missing_cases = sorted(expected_cases - set(case_receipts))
                unexpected_cases = sorted(set(case_receipts) - expected_cases)
                if missing_cases:
                    errors.append(
                        f"{provider}: missing passing manifest cases: "
                        + ", ".join(missing_cases)
                    )
                if unexpected_cases:
                    errors.append(
                        f"{provider}: receipts contain non-manifest cases: "
                        + ", ".join(unexpected_cases)
                    )
            selected_receipts = list(
                {id(item): item for item in case_receipts.values()}.values()
            )
            expected_case_operations = (
                set().union(
                    *(
                        LIVE_CASE_OPERATIONS.get(provider, {}).get(case_name, set())
                        for case_name in case_receipts
                        if case_name in expected_cases
                    )
                )
                if case_receipts
                else set()
            )

        receipt_errors: list[str] = []
        observed_operations: set[str] = set()
        for receipt in selected_receipts:
            if receipt.get("kind") != "provider_live_matrix":
                receipt_errors.append("receipt kind is not provider_live_matrix")
            expected_result = (
                "staged_candidate_provider_passed"
                if receipt.get("scope") == "provider_candidate"
                else "staged_candidate_case_passed"
            )
            if receipt.get("result") != expected_result:
                receipt_errors.append("provider/case manifest did not pass")
            if receipt.get("providers_selected") != [provider]:
                receipt_errors.append("receipt selection is not provider-specific")
            if receipt.get("candidate_unchanged") is not True:
                receipt_errors.append("candidate changed during its live run")
            if receipt.get("candidate_tree_sha") not in compatible_candidate_trees:
                receipt_errors.append(
                    "candidate tree differs beyond append-only validation evidence"
                )
            if receipt.get("candidate_parent_sha") != candidate_parent_sha:
                receipt_errors.append("candidate parent does not match current HEAD")
            if receipt.get("live_acceptance") is not False:
                receipt_errors.append("slice receipt has invalid acceptance scope")
            try:
                exit_code = int(receipt.get("exit_code", 1))
                case_count = int(receipt.get("case_count", 0))
                failed_cases = int(receipt.get("failed_cases", 0))
                skipped_cases = int(receipt.get("skipped_cases", 0))
            except (TypeError, ValueError):
                receipt_errors.append("receipt case counts are invalid")
                continue
            if exit_code != 0:
                receipt_errors.append("live test process did not exit successfully")
            if case_count <= 0:
                receipt_errors.append("no manifest cases were executed")
            if failed_cases != 0 or skipped_cases != 0:
                receipt_errors.append("manifest contains failed or skipped cases")
            evidence = receipt.get("live_evidence")
            if not isinstance(evidence, dict) or evidence.get("complete") is not True:
                receipt_errors.append("same-run live evidence is incomplete")
                continue
            provider_evidence = evidence.get("providers")
            provider_row = (
                provider_evidence.get(provider)
                if isinstance(provider_evidence, dict)
                else None
            )
            operations = (
                provider_row.get("operations")
                if isinstance(provider_row, dict)
                else None
            )
            if not isinstance(operations, dict):
                receipt_errors.append("operation evidence is missing")
                continue
            for operation, row in operations.items():
                if not isinstance(row, dict) or row.get("passed") is not True:
                    receipt_errors.append(
                        f"operation {operation} lacks passing evidence"
                    )
                observed_operations.add(operation)
        if observed_operations != expected_case_operations:
            missing_operations = sorted(expected_case_operations - observed_operations)
            unexpected_operations = sorted(
                observed_operations - expected_case_operations
            )
            if missing_operations:
                receipt_errors.append(
                    "missing required operation evidence: "
                    + ", ".join(missing_operations)
                )
            if unexpected_operations:
                receipt_errors.append(
                    "unexpected operation evidence: " + ", ".join(unexpected_operations)
                )
        if receipt_errors:
            errors.extend(f"{provider}: {message}" for message in receipt_errors)
        elif full_receipts or set(case_receipts) == expected_cases:
            verified.append(provider)

    unexpected = sorted(set(by_provider) - required_providers)
    if unexpected:
        errors.append("unexpected provider receipts: " + ", ".join(unexpected))
    return {
        "complete": not errors and set(verified) == required_providers,
        "live_acceptance": not errors and set(verified) == required_providers,
        "result": (
            "candidate_provider_receipts_passed"
            if not errors and set(verified) == required_providers
            else "candidate_provider_receipts_incomplete"
        ),
        "candidate_tree_sha": candidate_tree_sha,
        "candidate_parent_sha": candidate_parent_sha,
        "required_providers": sorted(required_providers),
        "providers_verified": verified,
        "provider_canaries_verified": canaries_verified,
        "missing": sorted(set(errors)),
        "provider_http_requests": 0,
    }


def _record_live_preflight(
    *,
    providers: list[str] | None,
    selected: set[str],
    blockers: dict[str, list[str]],
    approved_deferrals: dict[str, str],
    quota_coordinator_ready: bool,
    selected_cases: dict[str, set[str]] | None = None,
    admitted_providers: list[str] | None = None,
    quarantined_providers: dict[str, list[str]] | None = None,
    global_admission_blockers: list[str] | None = None,
) -> None:
    """Record a no-transport admission check; this is never live evidence."""

    path = _workstream_validation_path()
    missing_environment_names = sorted(
        {
            name
            for names in blockers.values()
            for name in names
            if re.fullmatch(r"[A-Z][A-Z0-9_]+", name)
        }
    )
    receipt = {
        "at": datetime.now(UTC).isoformat(),
        "command": "scripts/run-live-provider-probes.py --preflight-only",
        "kind": "provider_live_preflight",
        "scope": (
            "full_matrix"
            if providers is None
            else "case_focused"
            if selected_cases is not None
            else "focused"
        ),
        "result": "blocked_before_transport" if blockers else "clear_no_transport",
        "source_sha": _source_sha(),
        "dirty_source_paths": _dirty_source_paths(),
        "providers_requested": sorted(selected if providers is None else providers),
        "providers_evaluated": sorted(selected),
        "selected_cases": {
            provider: sorted(names)
            for provider, names in sorted((selected_cases or {}).items())
        },
        "approved_deferrals": approved_deferrals if not providers else {},
        "preflight_blockers": {
            key: list(value) for key, value in sorted(blockers.items())
        },
        "missing_environment_names": missing_environment_names,
        "quota_coordinator_ready": quota_coordinator_ready,
        "transport_started": False,
        "provider_http_requests": 0,
        "live_acceptance": False,
        **(
            {
                "provider_admission": {
                    "eligible": sorted(admitted_providers or []),
                    "quarantined": {
                        provider: sorted(set(reasons))
                        for provider, reasons in sorted(
                            (quarantined_providers or {}).items()
                        )
                    },
                    "global_blockers": sorted(set(global_admission_blockers or [])),
                }
            }
            if admitted_providers is not None
            else {}
        ),
    }
    if path is not None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, sort_keys=True) + "\n")
    print(
        "provider preflight receipt: "
        f"{receipt['result']} ({len(selected)} providers evaluated; "
        "0 provider requests; not live acceptance)"
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        action="append",
        choices=sorted(LIVE_PROVIDER_CASES),
        help="run only this provider's manifest-backed cases; repeat to select several",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="PROVIDER:TEST_FUNCTION",
        help=(
            "run one exact manifest case with a pinned provider-operation quota plan; "
            "requires the matching --provider"
        ),
    )
    parser.add_argument(
        "--allow-staged-candidate",
        action="store_true",
        help=(
            "validate a fully staged pre-commit tree; run the full matrix or "
            "one provider's complete manifest or exact case slice. Unstaged/untracked paths "
            "block the run; the receipt is printed, not appended to the workstream"
        ),
    )
    parser.add_argument(
        "--candidate-receipt-file",
        type=Path,
        help=(
            "append redacted staged-candidate provider receipts to a local JSONL "
            "file outside the worktree so slices can be verified together"
        ),
    )
    parser.add_argument(
        "--verify-candidate-receipts",
        type=Path,
        metavar="JSONL",
        help=(
            "verify provider-slice receipts against the exact currently staged "
            "candidate tree without making provider requests"
        ),
    )
    parser.add_argument(
        "--account-usage-only",
        action="store_true",
        help=(
            "run only the provider's dedicated native account-usage case; "
            "requires exactly one --provider and remains a focused receipt"
        ),
    )
    parser.add_argument(
        "--dinari-sandbox-canary",
        action="store_true",
        help=(
            "run only Dinari's non-canonical Sandbox validation through an "
            "operator-authorized one-request local cap; this does not assert "
            "Dinari's unpublished provider quota"
        ),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "evaluate credentials, quota, rights, and live-operation admission, "
            "record a redacted receipt, and always stop before provider tests or HTTP"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    verify_receipt_file = getattr(arguments, "verify_candidate_receipts", None)
    candidate_receipt_file = getattr(arguments, "candidate_receipt_file", None)
    if verify_receipt_file is not None:
        if (
            arguments.allow_staged_candidate
            or arguments.provider
            or arguments.case
            or arguments.account_usage_only
            or arguments.dinari_sandbox_canary
            or candidate_receipt_file is not None
            or arguments.preflight_only
        ):
            print(
                "candidate receipt verification cannot be combined with live-run options"
            )
            return 2
        candidate, candidate_error = _staged_candidate_snapshot()
        if candidate_error or candidate is None:
            print(
                "candidate receipt verification blocked: "
                f"{candidate_error or 'unknown staged candidate error'}"
            )
            return 2
        acceptance = verify_candidate_provider_receipts(
            verify_receipt_file,
            candidate_tree_sha=candidate["tree_sha"],
            candidate_parent_sha=candidate["parent_sha"],
            required_providers=set(LIVE_PROVIDER_CASES)
            - set(approved_live_deferrals()),
        )
        print(
            "provider candidate acceptance: " + json.dumps(acceptance, sort_keys=True)
        )
        return 0 if acceptance["complete"] else 2
    selected_providers = set(arguments.provider or [])
    case_selectors = list(getattr(arguments, "case", []) or [])
    try:
        selected_cases, selected_case_operations = parse_live_case_selectors(
            case_selectors, selected_providers
        )
        selected_case_multipliers = selected_case_operation_multipliers(selected_cases)
    except ValueError as exc:
        print(f"live provider case selection invalid: {exc}")
        return 2
    account_usage_only = bool(getattr(arguments, "account_usage_only", False))
    dinari_sandbox_canary = bool(getattr(arguments, "dinari_sandbox_canary", False))
    preflight_only = bool(getattr(arguments, "preflight_only", False))
    if preflight_only and arguments.allow_staged_candidate:
        print("--preflight-only cannot be combined with --allow-staged-candidate")
        return 2
    if dinari_sandbox_canary and selected_providers != {"dinari"}:
        print("--dinari-sandbox-canary requires exactly one --provider dinari")
        return 2
    if dinari_sandbox_canary and account_usage_only:
        print("--dinari-sandbox-canary cannot be combined with --account-usage-only")
        return 2
    if case_selectors and (account_usage_only or dinari_sandbox_canary):
        print("--case cannot be combined with account-usage-only or Dinari canary mode")
        return 2
    account_usage_providers = account_usage_only_provider_set()
    if account_usage_only and not (
        len(selected_providers) == 1 and selected_providers <= account_usage_providers
    ):
        allowed = ", ".join(sorted(account_usage_providers))
        print(
            "account-usage-only requires exactly one --provider with an "
            f"explicit manifest account-usage case ({allowed})"
        )
        return 2
    if arguments.allow_staged_candidate and (
        len(arguments.provider or []) > 1 or account_usage_only
    ):
        print(
            "staged candidate preflight blocked: choose the full matrix, one provider's "
            "complete manifest, exact manifest case(s), or the Dinari canary"
        )
        return 2
    if candidate_receipt_file is not None:
        receipt_path = candidate_receipt_file.expanduser().resolve()
        if not arguments.allow_staged_candidate or len(arguments.provider or []) != 1:
            print(
                "--candidate-receipt-file requires --allow-staged-candidate and "
                "exactly one --provider"
            )
            return 2
        if receipt_path.is_relative_to(ROOT.resolve()):
            print("--candidate-receipt-file must be outside the source worktree")
            return 2
    # Prefer an operator-owned source outside Git. Worktree runtime setup links
    # the usual ignored paths to this file, but loading it directly also makes
    # this command safe to run before any Make target. Explicit exports retain
    # precedence. Do not print or persist loaded secret values.
    shared_env = Path(
        os.getenv(SHARED_ENV_OVERRIDE, str(DEFAULT_SHARED_ENV))
    ).expanduser()
    if shared_env.exists():
        load_dotenv(shared_env, override=False)
    load_dotenv(ROOT / "backend" / ".env.dev", override=False)
    # Only the explicit CLI mode may enable the local canary policy; an
    # inherited .env value must never affect ordinary provider preflight.
    os.environ.pop("DINARI_SANDBOX_CANARY_RUN", None)
    if arguments.allow_staged_candidate and os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
        print("staged candidate preflight blocked: set RUN_LIVE_PROVIDER_TESTS=1")
        return 2
    if not changed_provider_code():
        if arguments.allow_staged_candidate:
            print(
                "staged candidate preflight blocked: no provider-related source changes"
            )
            return 2
        print("live provider probes: not applicable (no provider-related changes)")
        return 0
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1" and not preflight_only:
        print(
            "live provider probes: disabled; set RUN_LIVE_PROVIDER_TESTS=1 for external calls"
        )
        return 0
    staged_candidate: dict[str, str] | None = None
    if arguments.allow_staged_candidate:
        staged_candidate, candidate_error = _staged_candidate_snapshot()
        if candidate_error or staged_candidate is None:
            print(
                f"staged candidate preflight blocked: {candidate_error or 'unknown error'}"
            )
            return 2
        if arguments.provider:
            staged_candidate = {**staged_candidate, "provider": arguments.provider[0]}
    missing: dict[str, list[str]] = {}
    deferred_providers = approved_live_deferrals()
    selected_for_run = (
        set(arguments.provider)
        if arguments.provider
        else set(LIVE_PROVIDER_CASES) - set(deferred_providers)
    )
    selected_deferred = selected_for_run & set(deferred_providers)
    if selected_deferred:
        missing["explicitly deferred providers"] = sorted(selected_deferred)
    inventory_errors = live_matrix_inventory_errors()
    if inventory_errors:
        missing["live matrix inventory"] = inventory_errors
    required: dict[str, tuple[str, ...]] = {}
    if not selected_providers or "edgar" in selected_providers:
        required["keyless/config"] = KEYLESS
    required.update(
        {
            provider: provider_required_credentials(provider)
            for provider in CREDENTIALS
            if (not selected_providers and provider not in deferred_providers)
            or provider in selected_providers
        }
    )
    for provider, names in required.items():
        absent = [name for name in names if not setting_is_configured(name)]
        if absent:
            missing[provider] = absent
    if staged_candidate is not None:
        source_review_missing = finra_otc_source_review_missing()
        if source_review_missing:
            missing["FINRA OTC source admission"] = source_review_missing
    if not usage_scope_is_configured():
        missing["usage accounting"] = ["PROVIDER_LIVE_USAGE_SCOPE"]
    canary_missing: list[str] = []
    if dinari_sandbox_canary:
        canary_missing = dinari_sandbox_canary_controls_missing()
        if canary_missing:
            missing["Dinari Sandbox canary controls"] = canary_missing
    quota_coordinator_ready, quota_coordinator_missing = durable_quota_preflight()
    live_quota_missing: dict[str, list[str]] = {}
    if not quota_coordinator_ready:
        missing["durable quota admission"] = [
            quota_coordinator_missing
            or "PROVIDER_QUOTA_LEDGER_DATABASE_URL or PROVIDER_QUOTA_LEDGER_PATH"
        ]
    print("live provider credential/usage preflight:")
    if quota_coordinator_ready:
        if dinari_sandbox_canary:
            live_quota_missing = with_dinari_sandbox_canary_policy(
                live_operation_quota_preflight,
                {"dinari"},
                operations_override={"dinari": {"discover_tokenized_assets"}},
                local_operation_cost_overrides={
                    "dinari": {"discover_tokenized_assets": 1}
                },
            )
        elif case_selectors:
            live_quota_missing = live_operation_quota_preflight(
                selected_for_run,
                operations_override=selected_case_operations,
                operation_multipliers=selected_case_multipliers,
            )
        elif account_usage_only:
            live_quota_missing = live_operation_quota_preflight(
                selected_for_run,
                operations_override={
                    provider: {"fetch_account_usage"} for provider in selected_for_run
                },
            )
        else:
            bootstrap_providers = manifest_account_usage_providers(selected_for_run)
            if bootstrap_providers:
                live_quota_missing = live_operation_quota_preflight(
                    selected_for_run,
                    bootstrap_providers=bootstrap_providers,
                )
            else:
                # Keep the helper call shape compatible with focused runner
                # tests and synthetic manifests that have no usage bootstrap.
                live_quota_missing = live_operation_quota_preflight(selected_for_run)
        if live_quota_missing:
            missing["provider-specific quota/cost/baseline admission"] = [
                f"{provider}: {reason}"
                for provider, reasons in sorted(live_quota_missing.items())
                for reason in reasons
            ]
    unresolved_live_coverage = False
    unresolved_operations: list[str] = []
    if not arguments.provider and not account_usage_only:
        unresolved_operations = [
            f"{provider}/{operation}: {reason}"
            for provider in sorted(
                set(selected_for_run) & set(LIVE_OPERATION_DISPOSITIONS)
            )
            for operation, reason in sorted(
                LIVE_OPERATION_DISPOSITIONS[provider].items()
            )
            if live_operation_disposition_kind(reason)
            not in LIVE_COVERED_DISPOSITION_KINDS
        ]
        if unresolved_operations:
            unresolved_live_coverage = True
            missing["unresolved capability live coverage"] = unresolved_operations
    safety_statuses = (
        with_dinari_sandbox_canary_policy(routing_safety_preflight)
        if dinari_sandbox_canary and not canary_missing
        else routing_safety_preflight()
    )
    blocked_live_safety = live_required_safety_blockers(
        selected_for_run,
        safety_statuses,
        account_usage_only=account_usage_only,
        operations_by_provider=(selected_case_operations if case_selectors else None),
    )
    if blocked_live_safety:
        missing["required live capability safety"] = [
            f"{provider}: {status}"
            for provider, statuses in sorted(blocked_live_safety.items())
            for status in statuses
        ]
    partial_live_admission = (
        not arguments.provider
        and staged_candidate is None
        and not account_usage_only
        and not case_selectors
        and not dinari_sandbox_canary
    )
    providers_for_execution = arguments.provider
    receipt_providers = arguments.provider
    eligible_providers = set(selected_for_run)
    provider_admission_blockers: dict[str, list[str]] = {}
    global_admission_blockers: list[str] = []
    if partial_live_admission:
        (
            eligible_providers,
            provider_admission_blockers,
            global_admission_blockers,
        ) = partition_live_provider_admission(
            selected_for_run,
            missing=missing,
            quota_blockers=live_quota_missing,
            safety_blockers=blocked_live_safety,
            unresolved_operations=unresolved_operations,
        )
        if eligible_providers != selected_for_run:
            providers_for_execution = sorted(eligible_providers)
            receipt_providers = providers_for_execution
            print(
                "independent provider admission: testing "
                f"{len(eligible_providers)} eligible provider(s); "
                f"quarantining {len(provider_admission_blockers)} provider(s) with local blockers"
            )
            for provider, reasons in sorted(provider_admission_blockers.items()):
                print(f"  QUARANTINED {provider}: {'; '.join(sorted(set(reasons)))}")
        if global_admission_blockers:
            for reason in global_admission_blockers:
                print(f"  BLOCKED all providers: {reason}")
    if missing:
        for provider, names in missing.items():
            print(f"  BLOCKED {provider}: missing {', '.join(names)}")
    else:
        print("  all manifest credentials present")
    print("routing safety preflight:")
    for provider, status in safety_statuses.items():
        print(f"  {provider}: {status}")
    if account_usage_only:
        print(
            "account-usage-only scope: selected provider controls are checked "
            "for fetch_account_usage; market-data rights and routing remain "
            "separately enforced for data reads"
        )
    if preflight_only:
        _record_live_preflight(
            providers=arguments.provider,
            selected=selected_for_run,
            blockers=missing,
            approved_deferrals=deferred_providers,
            quota_coordinator_ready=quota_coordinator_ready,
            selected_cases=selected_cases if case_selectors else None,
            admitted_providers=sorted(eligible_providers)
            if partial_live_admission
            else None,
            quarantined_providers=provider_admission_blockers
            if partial_live_admission
            else None,
            global_admission_blockers=global_admission_blockers
            if partial_live_admission
            else None,
        )
        if missing:
            print("provider preflight: blocked; transport was not attempted")
            return 2
        print("provider preflight: clear; transport was not attempted")
        return 0
    if staged_candidate is not None and missing:
        print("staged candidate blocked before network calls: preflight is incomplete")
        _record_live_validation(
            providers=arguments.provider,
            exit_code=2,
            missing=missing,
            counts={
                "case_count": 0,
                "passed_cases": 0,
                "failed_cases": 0,
                "skipped_cases": 0,
            },
            approved_deferrals=deferred_providers,
            candidate_tree=staged_candidate,
            canary_mode=dinari_sandbox_canary,
            selected_cases=selected_cases if case_selectors else None,
            full_matrix_requested=partial_live_admission,
            requested_providers=sorted(selected_for_run)
            if partial_live_admission
            else None,
            quarantined_providers=sorted(provider_admission_blockers),
        )
        return 2
    if (
        (
            not partial_live_admission
            and (
                blocked_live_safety
                or selected_deferred
                or live_quota_missing
                or unresolved_live_coverage
            )
        )
        or (
            partial_live_admission
            and (global_admission_blockers or not eligible_providers)
        )
        or (dinari_sandbox_canary and canary_missing)
    ):
        print(
            "live provider probes blocked before network calls: no safe provider subset is admitted"
        )
        _record_live_validation(
            providers=receipt_providers,
            exit_code=2,
            missing=missing,
            counts={
                "case_count": 0,
                "passed_cases": 0,
                "failed_cases": 0,
                "skipped_cases": 0,
            },
            approved_deferrals=deferred_providers,
            candidate_tree=staged_candidate,
            canary_mode=dinari_sandbox_canary,
            selected_cases=selected_cases if case_selectors else None,
            full_matrix_requested=partial_live_admission,
            requested_providers=sorted(selected_for_run)
            if partial_live_admission
            else None,
            quarantined_providers=sorted(provider_admission_blockers),
        )
        return 2
    if not quota_coordinator_ready:
        print(
            "live provider probes blocked before network calls: durable quota admission is unavailable"
        )
        _record_live_validation(
            providers=receipt_providers,
            exit_code=2,
            missing=missing,
            counts={
                "case_count": 0,
                "passed_cases": 0,
                "failed_cases": 0,
                "skipped_cases": 0,
            },
            approved_deferrals=deferred_providers,
            candidate_tree=staged_candidate,
            canary_mode=dinari_sandbox_canary,
            selected_cases=selected_cases if case_selectors else None,
        )
        return 2
    try:
        with provider_live_run_lock() as lock_path:
            print(f"live provider lock: {lock_path}")
            with tempfile.TemporaryDirectory(
                prefix="provider-live-matrix-"
            ) as temp_dir:
                live_run_id = str(uuid4())
                test_root = ROOT
                candidate_dir_context = None
                if staged_candidate is not None:
                    candidate_dir_context = tempfile.TemporaryDirectory(
                        prefix="provider-live-candidate-"
                    )
                    candidate_root = Path(candidate_dir_context.name)
                    materialized, materialize_error = _checkout_index_candidate(
                        candidate_root
                    )
                    if not materialized:
                        candidate_dir_context.cleanup()
                        print(
                            f"staged candidate preflight blocked: {materialize_error}"
                        )
                        return 2
                    test_root = candidate_root
                candidate_env = {**os.environ}
                candidate_uv_flags: list[str] = []
                if staged_candidate is not None:
                    if _candidate_can_reuse_backend_environment(test_root):
                        candidate_env["UV_PROJECT_ENVIRONMENT"] = str(
                            ROOT / "backend" / ".venv"
                        )
                        candidate_uv_flags.append("--no-sync")
                    else:
                        candidate_env["UV_PROJECT_ENVIRONMENT"] = str(
                            Path(temp_dir) / "candidate-backend-venv"
                        )
                isolate_provider_quota_windows = len(eligible_providers) > 1
                provider_batches = live_test_provider_batches(
                    sorted(eligible_providers)
                    if isolate_provider_quota_windows
                    else providers_for_execution,
                    isolate_provider_quota_windows=isolate_provider_quota_windows,
                )
                counts = {
                    "case_count": 0,
                    "passed_cases": 0,
                    "failed_cases": 0,
                    "skipped_cases": 0,
                }
                junit_cases = []
                run_exit_code = 0
                for batch_index, batch_providers in enumerate(provider_batches):
                    junit_path = Path(temp_dir) / f"results-{batch_index}.xml"
                    live_test_arguments = selected_live_test_arguments(
                        batch_providers,
                        deferred_providers=(
                            set(deferred_providers) if not arguments.provider else set()
                        ),
                        account_usage_only=account_usage_only,
                        selected_cases=selected_cases if case_selectors else None,
                        dinari_sandbox_canary=dinari_sandbox_canary,
                    )
                    result = subprocess.run(
                        [
                            "uv",
                            "run",
                            *candidate_uv_flags,
                            "--project",
                            str(test_root / "backend"),
                            "--frozen",
                            "--dev",
                            "pytest",
                            *live_test_arguments,
                            "-m",
                            "live",
                            "--no-header",
                            "-q",
                            "--no-cov",
                            f"--junitxml={junit_path}",
                        ],
                        cwd=test_root / "backend",
                        env={
                            **candidate_env,
                            "RUN_LIVE_PROVIDER_TESTS": "1",
                            "PROVIDER_LIVE_MATRIX_RUN": "1",
                            "PROVIDER_LIVE_RUN_ID": live_run_id,
                            "PROVIDER_LIVE_CASE_ORDER": json.dumps(
                                [item for item in live_test_arguments if "::" in item]
                            ),
                            "DINARI_SANDBOX_CANARY_RUN": "1"
                            if dinari_sandbox_canary
                            else "0",
                            **(
                                {
                                    "PROVIDER_LIVE_ADMISSION_MODE": "dinari_sandbox_canary",
                                }
                                if dinari_sandbox_canary
                                else {}
                            ),
                        },
                        capture_output=True,
                        text=True,
                    )
                    batch_counts = _junit_counts(junit_path)
                    for name in counts:
                        counts[name] += batch_counts[name]
                    junit_cases.extend(_junit_case_results(junit_path))
                    if result.returncode and not run_exit_code:
                        run_exit_code = result.returncode
                    output = redact_runner_output(result.stdout + result.stderr)
                    if output:
                        if len(output) > 20000:
                            output = output[:20000] + "\n...[redacted output truncated]"
                        print(output, end="" if output.endswith("\n") else "\n")
                if candidate_dir_context is not None:
                    candidate_dir_context.cleanup()
            candidate_unchanged = True
            if staged_candidate is not None:
                after_test, after_test_error = _staged_candidate_snapshot()
                candidate_unchanged = _candidate_source_unchanged(
                    staged_candidate, after_test, after_test_error
                )
            live_evidence = _provider_live_evidence(
                run_id=live_run_id,
                providers=eligible_providers,
                junit_cases=junit_cases,
                account_usage_only=account_usage_only,
                selected_cases=selected_cases if case_selectors else None,
                required_operations_override=(
                    {"dinari": {DINARI_CANARY_OPERATION}}
                    if dinari_sandbox_canary
                    else selected_case_operations
                    if case_selectors
                    else None
                ),
            )
            if not live_evidence["complete"]:
                print("live provider evidence preflight: incomplete for this exact run")
                for item in live_evidence["missing"]:
                    print(f"  BLOCKED {item}")
            live_result = _record_live_validation(
                providers=receipt_providers,
                exit_code=run_exit_code,
                missing=missing,
                counts=counts,
                approved_deferrals=deferred_providers,
                live_evidence=live_evidence,
                candidate_tree=staged_candidate,
                candidate_unchanged=candidate_unchanged,
                canary_mode=dinari_sandbox_canary,
                selected_cases=selected_cases if case_selectors else None,
                full_matrix_requested=partial_live_admission,
                requested_providers=sorted(selected_for_run)
                if partial_live_admission
                else None,
                quarantined_providers=sorted(provider_admission_blockers),
                candidate_receipt_file=candidate_receipt_file,
            )
    except ProviderLiveRunAlreadyActive as exc:
        print(f"live provider probes: blocked by local key-use lock: {exc}")
        return 3
    if run_exit_code:
        if missing:
            print(
                "live provider probes: credential preflight incomplete; no acceptance claim"
            )
            return 2
        return run_exit_code
    if not live_evidence["complete"]:
        print(
            "live provider probes: same-run evidence is incomplete; no acceptance claim"
        )
        return 2
    if staged_candidate is not None and live_result not in {
        "staged_candidate_full_matrix_passed",
        "staged_candidate_provider_passed",
        "staged_candidate_case_passed",
    }:
        return 2
    if missing:
        print(
            "live provider probes: credential preflight incomplete; no acceptance claim"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
