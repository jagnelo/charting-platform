#!/usr/bin/env python3
"""Run the explicit, bounded provider live matrix.

Normal CI does not call external services. With ``RUN_LIVE_PROVIDER_TESTS=1``
this command reports every required credential, runs keyless probes, and runs
credentialed probes only when their exact environment is present. Missing
credentials return exit code 2; they are never represented as passing skips.
"""

from __future__ import annotations

import argparse
import inspect
import importlib.util
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
    "finra_otc_directory": ("FINRA_OTC_SYMBOL_DIRECTORY_URL",),
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
            "test_alpaca_credentialed_assets_and_corporate_actions",
        ),
    ),
    "massive": (
        ("test_market_data_providers_live.py", "test_massive_credentialed_reference"),
    ),
    "alpha_vantage": (
        ("test_market_data_providers_live.py", "test_alpha_vantage_credentialed_daily"),
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
    ),
    "fred": (
        (
            "test_market_data_providers_live.py",
            "test_fred_series_requires_persisted_data_rights_before_network_access",
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
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
        ),
        (
            "test_market_data_providers_live.py",
            "test_twelve_data_credentialed_account_usage_snapshot",
        ),
    ),
    "finnhub": (
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
    ),
    "eodhd": (
        (
            "test_market_data_providers_live.py",
            "test_optional_credentialed_provider_small_read",
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
            "test_optional_credentialed_provider_small_read",
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
    "binance": {
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "discover_universe_page",
        "fetch_account_usage",
    },
    "coinbase": {"fetch_latest_ohlcv"},
    "kraken": {
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
        "fetch_ohlcv",
        "fetch_market_holidays",
    },
    "alpha_vantage": {
        "fetch_ohlcv",
        "fetch_market_events",
        "fetch_earnings_calendar",
        "fetch_instrument_events",
    },
    "coingecko": {"search_instruments", "get_instrument_profile"},
    "fred": {"fetch_ohlcv"},
    "finra": {"fetch_short_interest", "fetch_market_events"},
    "finra_otc_directory": {"discover_universe_page"},
    "tiingo": {"fetch_ohlcv", "get_instrument_profile"},
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
        "search_instruments",
        "get_instrument_profile",
        "fetch_instrument_events",
        "fetch_market_events",
        "discover_universe_page",
    },
    "marketstack": {"fetch_ohlcv", "get_current_price"},
    "eodhd": {
        "fetch_ohlcv",
        "get_instrument_profile",
        "get_current_price",
        "discover_universe_page",
        "fetch_account_usage",
    },
    "fmp": {"fetch_ohlcv", "get_instrument_profile", "fetch_market_events"},
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
        # A direct 30-day daily range observed two Binance klines pages in
        # live validation. Keep this ceiling attached to that exact case;
        # wider ranges must use a caller-supplied estimate instead.
        "fetch_ohlcv": 2,
    },
    "coinbase": {
        # The bounded manifest requests one daily candle.  Coinbase's
        # estimator is one 300-candle page for that exact case.
        "fetch_latest_ohlcv": 1,
    },
    "kraken": {
        # The bounded manifest requests one daily candle.  Kraken's 720-row
        # OHLC page therefore has a one-request reviewed test bound.
        "fetch_latest_ohlcv": 1,
    },
    "alpaca": {
        # The manifest exercises a five-day daily range and a five-day
        # five-minute range. The latter can span at most two 1,000-bar pages
        # under the bounded test window; both cases pass this same conservative
        # upper bound to the live reservation helper. Corporate actions are
        # monkeypatched to the same two-page test ceiling. These are test-case
        # bounds, not a claim about Alpaca's provider-wide allowance.
        "fetch_ohlcv": 2,
        "fetch_instrument_events": 2,
    },
    "massive": {
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

# Capability-level operations not executed by the bounded matrix are recorded
# explicitly instead of being mistaken for coverage.  These are current
# acceptance gaps (or deliberate policy blocks), not successful live evidence;
# each entry must be promoted to LIVE_REQUIRED_OPERATIONS or separately
# approved before the branch can be accepted as capability-exhaustive.
LIVE_OPERATION_DISPOSITIONS = {
    "edgar": {
    },
    "fred": {
        "get_current_price": "deferred: current-value path is not separately admitted beyond the series history probe",
    },
    "coingecko": {
        "discover_universe_page": "deferred: bounded crypto-catalog pagination case not yet approved",
    },
    "finra": {
        "submit_async_dataset": "blocked: no reviewed positive FINRA_ASYNC_MAX_RESULT_BYTES bound",
        "poll_async_dataset": "blocked: async dataset flow lacks reviewed result-byte admission",
        "download_async_result": "blocked: signed result download lacks reviewed byte admission",
    },
    "massive": {
        "discover_universe_page": "deferred: complete universe pagination budget not yet approved",
        "fetch_market_events_page": "deferred: cursor continuation case not yet approved",
        # The Basic key is documented at five calls/minute. Corporate actions
        # are two independent paginated reads (splits and dividends), so the
        # compound event operation cannot be placed in the same five-call
        # acceptance window as the bounded metadata/history/calendar reads.
        # Keep it explicit until the live runner gains a separate provider
        # window schedule; never overrun the key to make the matrix green.
        "fetch_instrument_events": "deferred: two-request corporate-action read requires a separate Massive quota window",
    },
    "alpha_vantage": {
        "search_instruments": "deferred: daily-capacity budget not yet approved",
        "get_current_price": "deferred: daily-capacity budget not yet approved",
        "discover_universe_page": "deferred: daily-capacity budget not yet approved",
    },
    "tiingo": {
        "search_instruments": "deferred: bounded search case not yet approved",
        "get_current_price": "deferred: bounded quote case not yet approved",
    },
    "twelve_data": {},
    "finnhub": {
        "fetch_ohlcv": "expected_entitlement_denial: the observed free-plan key returned HTTP 403 for the stock-candle endpoint",
        "get_current_price": "deferred: observed free-plan quote entitlement is not yet admitted",
    },
    "marketstack": {
        "discover_universe_page": "blocked: exchange parameter and discovery completeness remain unreviewed",
    },
    "eodhd": {
    },
    "fmp": {
        "get_current_price": "deferred: bounded quote case not yet approved",
        "discover_universe_page": "deferred: bounded universe case not yet approved",
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
    "coinbase": {
        "fetch_ohlcv": "blocked: Coinbase market-data legal-use authority missing",
        "get_current_price": "blocked: Coinbase market-data legal-use authority missing",
        "discover_universe_page": "blocked: Coinbase market-data legal-use authority missing",
    },
    "kraken": {
        "fetch_ohlcv": "deferred: full-range aggregation case not yet approved",
    },
    "ondo_global_markets": {
        "get_tokenized_asset": "deferred by user: Ondo onboarding/legal review is not admitted",
    },
}

# These are not missing capability implementations. They are explicit
# deployment-safety outcomes whose live case is intentionally prevented from
# reaching provider transport until the operator/legal control is satisfied.
# They remain separate from LIVE_OPERATION_DISPOSITIONS because the operation
# can become a normal required live read once the control is admitted.
LIVE_PROVIDER_SAFETY_DISPOSITIONS = {
    "fred": "intentional_no_request_policy: persisted series use requires reviewed quota, storage, automated-use, and per-series rights",
    "coinbase": "intentional_no_request_policy: automated/persistent Coinbase use requires scoped written authority",
    "finra_otc_directory": "intentional_no_request_policy: OTC source, terms, completeness, polling, and redistribution admission is unresolved",
    "dinari": "intentional_no_request_policy: Sandbox numeric quota and commercial/redistribution terms are unpublished",
    "xstocks": "intentional_no_request_policy: automation/partner terms and deployment jurisdiction are unresolved",
    "bybit_xstocks": "intentional_no_request_policy: provider-restricted egress and automated-use evidence are unresolved",
}

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
            errors.append(f"service operation alias is empty: {operation!r} -> {alias!r}")
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

    for provider, cases in sorted(LIVE_PROVIDER_CASES.items()):
        if not cases:
            errors.append(f"{provider} has no live manifest cases")
        elif len(set(cases)) != len(cases):
            errors.append(f"{provider} has duplicate live manifest cases")
    for provider, operations in sorted(LIVE_REQUIRED_OPERATIONS.items()):
        if not operations:
            errors.append(f"{provider} has no required live operations")

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

    for provider, reason in sorted(LIVE_PROVIDER_SAFETY_DISPOSITIONS.items()):
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
                errors.append(f"{mapping_name} references an unmanifested case: {case_key}")
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
        "coinbase",
        "test_market_data_providers_live.py",
        "test_coinbase_keyless_crypto_history",
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
    "massive": ("massive market-data use",),
    "nasdaq": ("nasdaq",),
    "finra_otc_directory": ("finra otc directory",),
    "dinari": ("dinari sandbox canary quota",),
    "xstocks": ("xstocks",),
    "bybit_xstocks": ("bybit xstocks egress",),
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
    authority_reference = os.getenv("DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE", "").strip()
    if not authority_reference or len(authority_reference) > 256 or not authority_reference.isprintable():
        missing.append("DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE")
    raw_limit = os.getenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "").strip()
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 0
    if limit <= 0:
        missing.append("DINARI_SANDBOX_CANARY_MAX_REQUESTS")
    return missing


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
            reconcile_pending_live_receipts,
            ensure_provider_quota_coordinator,
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
) -> dict[str, list[str]]:
    """Check every selected manifest operation before the first provider call.

    This is a read-only check of reviewed quota plans and current account
    baselines. Individual live tests still reserve atomically immediately
    before transport; the preflight prevents spending one provider's quota
    before discovering that another selected provider cannot be accounted for.
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
        from app.services.provider_runtime import ProviderQuotaUnknownError
    except Exception:
        return {"provider quota accounting": ["quota admission code is unavailable"]}

    blockers: dict[str, list[str]] = {}
    now = datetime.now(UTC)
    for provider in sorted(providers):
        operations = (
            operations_override.get(provider, set())
            if operations_override is not None
            else LIVE_REQUIRED_OPERATIONS.get(provider, set())
        )
        for operation in sorted(operations):
            label = f"{provider}/{operation}"
            try:
                _reset, _dimension_units, specs = _reservation_plan_for_live_probe(
                    provider,
                    operation,
                    usage_identity="LIVE-PREFLIGHT",
                    now=now,
                    operation_cost_override=(
                        LIVE_OPERATION_COST_OVERRIDES.get(provider, {}).get(operation)
                    ),
                )
            except (
                ProviderQuotaAdmissionError,
                ProviderQuotaCoordinatorError,
                ProviderQuotaUnknownError,
            ) as exc:
                blockers.setdefault(provider, []).append(str(exc))
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
            for spec in specs:
                if spec.get("release_only"):
                    continue
                dimension_name = str(spec.get("dimension") or "")
                dimension = dimensions.get(dimension_name)
                if dimension is None:
                    blockers.setdefault(provider, []).append(
                        f"{label}: reviewed dimension {dimension_name or '<missing>'} is absent"
                    )
                    continue
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
                    blockers.setdefault(provider, []).append(
                        f"{label}: active {dimension_name} usage baseline is {state.get('status', 'unknown')}"
                    )
                elif int(state.get("remaining_units") or 0) < int(spec.get("units") or 0):
                    blockers.setdefault(provider, []).append(
                        f"{label}: active {dimension_name} headroom is below the reviewed operation reservation"
                    )
    return blockers


def usage_scope_is_configured() -> bool:
    """Require an attributable, bounded label for quota-consuming live runs."""

    value = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip()
    return bool(value) and len(value) <= 128 and value.isprintable()


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
    if os.getenv("FINRA_OTC_SOURCE_REVIEWED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        missing.append("FINRA_OTC_SOURCE_REVIEWED")
    if not os.getenv("FINRA_OTC_SOURCE_EVIDENCE", "").strip():
        missing.append("FINRA_OTC_SOURCE_EVIDENCE")
    configured = normalized_reviewed_https_source(
        os.getenv("FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
    )
    reviewed = normalized_reviewed_https_source(
        os.getenv("FINRA_OTC_REVIEWED_SOURCE_URL", "")
    )
    if configured is None or reviewed != configured:
        missing.append("FINRA_OTC_REVIEWED_SOURCE_URL")
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
        bybit_xstocks_market_data_use_authority_missing,
        FRED_MAPPED_SERIES_IDS,
        coinbase_market_data_use_authority_missing,
        massive_market_data_use_authority_missing,
        provider_quota_reset_is_admission_safe,
        xstocks_market_data_use_authority_missing,
    )

    def _env_datetime(name: str) -> datetime | None:
        raw = os.getenv(name, "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    live_settings = SimpleNamespace(
        MASSIVE_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED", ""
        ).strip().lower()
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
        COINBASE_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "COINBASE_MARKET_DATA_USE_AUTHORIZED", ""
        ).strip().lower()
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
        XSTOCKS_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "XSTOCKS_MARKET_DATA_USE_AUTHORIZED", ""
        ).strip().lower()
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
        ).strip().lower()
        in {"1", "true", "yes"},
        XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE=os.getenv(
            "XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE", ""
        ),
        BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", ""
        ).strip().lower()
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
        BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", ""
        ).strip().lower()
        in {"1", "true", "yes"},
        BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE=os.getenv(
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE", ""
        ),
    )

    result: dict[str, str] = {}
    raw_alpaca_pages = (
        os.getenv("ALPACA_CORPORATE_ACTIONS_MAX_PAGES", "0").strip() or "0"
    )
    try:
        alpaca_pages = int(raw_alpaca_pages)
    except ValueError:
        alpaca_pages = 0
    result["alpaca corporate actions"] = (
        "routable"
        if alpaca_pages > 0
        else "non-routable: positive reviewed ALPACA_CORPORATE_ACTIONS_MAX_PAGES required"
    )
    alpaca_reset = os.getenv("ALPACA_REVIEWED_RESET", "").strip()
    alpaca_quota_evidence = os.getenv("ALPACA_QUOTA_EVIDENCE", "").strip()
    alpaca_missing: list[str] = []
    if not provider_quota_reset_is_admission_safe(alpaca_reset):
        alpaca_missing.append("ALPACA_REVIEWED_RESET")
    if not alpaca_quota_evidence:
        alpaca_missing.append("ALPACA_QUOTA_EVIDENCE")
    result["alpaca market-data quota"] = (
        "routable"
        if not alpaca_missing
        else "non-routable: the documented 200-requests/minute account pool has no provider-published initial reset boundary; missing/invalid "
        + ", ".join(alpaca_missing)
    )
    raw_massive_pages = (
        os.getenv("MASSIVE_CORPORATE_ACTIONS_MAX_PAGES", "0").strip() or "0"
    )
    try:
        massive_pages = int(raw_massive_pages)
    except ValueError:
        massive_pages = 0
    result["massive corporate actions"] = (
        "routable"
        if massive_pages > 0
        else "non-routable: positive reviewed MASSIVE_CORPORATE_ACTIONS_MAX_PAGES required"
    )
    massive_use_missing = massive_market_data_use_authority_missing(source=live_settings)
    result["massive market-data use"] = (
        "routable"
        if not massive_use_missing
        else "non-routable: missing " + ", ".join(massive_use_missing)
    )
    massive_reset = os.getenv("MASSIVE_REVIEWED_RESET", "").strip()
    massive_quota_evidence = os.getenv("MASSIVE_QUOTA_EVIDENCE", "").strip()
    massive_quota_missing: list[str] = []
    if not provider_quota_reset_is_admission_safe(massive_reset):
        massive_quota_missing.append("MASSIVE_REVIEWED_RESET")
    if not massive_quota_evidence:
        massive_quota_missing.append("MASSIVE_QUOTA_EVIDENCE")
    result["massive market-data quota"] = (
        "routable"
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
    result["edgar quota"] = (
        "routable"
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

    finra_otc_missing: list[str] = []
    raw_finra_otc_costs = os.getenv("FINRA_OTC_OPERATION_COSTS", "").strip()
    try:
        finra_otc_costs = json.loads(raw_finra_otc_costs) if raw_finra_otc_costs else {}
    except json.JSONDecodeError:
        finra_otc_costs = None
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
        "routable"
        if not finra_otc_missing
        else "non-routable: missing/invalid "
        + ", ".join(dict.fromkeys(finra_otc_missing))
    )

    alpha_reset = os.getenv("ALPHA_VANTAGE_REVIEWED_RESET", "").strip()
    alpha_quota_evidence = os.getenv("ALPHA_VANTAGE_QUOTA_EVIDENCE", "").strip()
    alpha_missing: list[str] = []
    if not provider_quota_reset_is_admission_safe(alpha_reset):
        alpha_missing.append("ALPHA_VANTAGE_REVIEWED_RESET")
    if not alpha_quota_evidence:
        alpha_missing.append("ALPHA_VANTAGE_QUOTA_EVIDENCE")
    result["alpha_vantage"] = (
        "routable"
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
    result["finnhub"] = (
        "routable"
        if not finnhub_missing
        else "non-routable: independent minute and second reset boundaries require current review evidence; missing/invalid "
        + ", ".join(finnhub_missing)
    )

    # These providers have a useful live read but still lack one or more
    # provider-specific admission dimensions. Keep the gap visible next to
    # the byte-bound controls rather than letting a passing probe imply safe
    # routing.
    fred_scope = os.getenv("FRED_REVIEWED_LIMIT_SCOPE", "").strip()
    try:
        fred_limit = int(
            os.getenv("FRED_REVIEWED_REQUESTS_PER_MINUTE", "0").strip() or "0"
        )
    except ValueError:
        fred_limit = 0
    fred_quota_evidence = os.getenv("FRED_REVIEWED_QUOTA_EVIDENCE", "").strip()
    fred_storage_authorized = os.getenv(
        "FRED_PERSISTED_STORAGE_AUTHORIZED", ""
    ).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    fred_storage_evidence = os.getenv(
        "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", ""
    ).strip()
    fred_automated_authorized = os.getenv(
        "FRED_AUTOMATED_USE_AUTHORIZED", ""
    ).strip().lower() in {"1", "true", "yes"}
    fred_automated_evidence = os.getenv(
        "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", ""
    ).strip()
    fred_missing: list[str] = []
    if fred_scope not in {"api_key", "account", "ip", "deployment"}:
        fred_missing.append("FRED_REVIEWED_LIMIT_SCOPE")
    if not 0 < fred_limit <= 120:
        fred_missing.append("FRED_REVIEWED_REQUESTS_PER_MINUTE")
    if not fred_quota_evidence:
        fred_missing.append("FRED_REVIEWED_QUOTA_EVIDENCE")
    if not fred_storage_authorized:
        fred_missing.append("FRED_PERSISTED_STORAGE_AUTHORIZED")
    if not fred_storage_evidence:
        fred_missing.append("FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE")
    if not fred_automated_authorized:
        fred_missing.append("FRED_AUTOMATED_USE_AUTHORIZED")
    if not fred_automated_evidence:
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
        "routable"
        if not fred_missing
        else "non-routable: FRED v1 persisted observations require provider-confirmed quota scope and written storage/automated-use rights; missing/invalid "
        + ", ".join(fred_missing)
    )
    coinbase_missing = coinbase_market_data_use_authority_missing(source=live_settings)
    result["coinbase market-data use"] = (
        "routable"
        if not coinbase_missing
        else "non-routable: Coinbase terms require scoped prior written authority for this automated/persisted use; missing/invalid "
        + ", ".join(coinbase_missing)
    )
    result["nasdaq"] = "routable: client-imposed 2 official-file requests per calendar day; vendor quota unpublished"
    result["dinari sandbox canary quota"] = (
        "non-routable: Dinari publishes no numeric Sandbox request quota/reset or reviewed canary admission; no limit is inferred"
    )
    xstocks_missing = xstocks_market_data_use_authority_missing(source=live_settings)
    result["xstocks"] = (
        "routable"
        if not xstocks_missing
        else "non-routable: the live-verified 1000/minute shared public header contract "
        "is accounted for, but xStocks automation/partner terms and deployment "
        "jurisdiction evidence are missing/invalid: "
        + ", ".join(xstocks_missing)
    )
    result["bybit_xstocks"] = (
        "routable: anonymous public calls are bounded by the documented 600/5-second/IP ceiling"
        if not bybit_xstocks_market_data_use_authority_missing(source=live_settings)
        else "non-routable: Bybit documents US/Mainland-China egress restrictions; "
        "automated/persistent use and non-restricted deployment egress are missing/invalid: "
        + ", ".join(
            bybit_xstocks_market_data_use_authority_missing(source=live_settings)
        )
    )
    result["marketstack discovery"] = (
        "routable"
        if os.getenv("MARKETSTACK_DISCOVERY_EXCHANGE", "").strip()
        else "non-routable: MARKETSTACK_DISCOVERY_EXCHANGE is unset"
    )
    try:
        marketstack_limit = int(
            os.getenv("MARKETSTACK_REVIEWED_MONTHLY_LIMIT", "0").strip() or "0"
        )
    except ValueError:
        marketstack_limit = 0
    marketstack_missing: list[str] = []
    if marketstack_limit <= 0:
        marketstack_missing.append("MARKETSTACK_REVIEWED_MONTHLY_LIMIT")
    if not provider_quota_reset_is_admission_safe(
        os.getenv("MARKETSTACK_REVIEWED_MONTHLY_RESET", "").strip()
    ):
        marketstack_missing.append("MARKETSTACK_REVIEWED_MONTHLY_RESET")
    if not os.getenv("MARKETSTACK_QUOTA_EVIDENCE", "").strip():
        marketstack_missing.append("MARKETSTACK_QUOTA_EVIDENCE")
    result["marketstack quota"] = (
        "routable"
        if not marketstack_missing
        else "non-routable: conflicting monthly cap/reset semantics require current account review; missing/invalid "
        + ", ".join(marketstack_missing)
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
    elif marketdata_pair_valid and marketdata_plan in {"starter", "trader"}:
        result["marketdata.app account plan"] = (
            "routable: paid plan reviewed"
            if os.getenv("ALLOW_PAID_PROVIDER_ROUTING", "false").strip().lower()
            == "true"
            else "non-routable: paid plan requires ALLOW_PAID_PROVIDER_ROUTING=true"
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
        "non-routable: response-priced history has no reviewed hard result/credit ceiling; no live request is admitted"
    )

    for provider, operations in BYTE_BOUND_OPERATIONS.items():
        variable = f"{provider.upper()}_OPERATION_BYTE_BOUNDS"
        raw = os.getenv(variable, "").strip()
        if not raw:
            result[provider] = f"non-routable: {variable} is unset"
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            result[provider] = f"non-routable: {variable} is not valid JSON"
            continue
        if not isinstance(parsed, dict):
            result[provider] = f"non-routable: {variable} must be a JSON object"
            continue
        missing = [
            operation
            for operation in operations
            if operation not in parsed
            or not isinstance(parsed[operation], int)
            or isinstance(parsed[operation], bool)
            or parsed[operation] <= 0
        ]
        if provider == "tiingo" and not missing:
            if not provider_quota_reset_is_admission_safe(
                os.getenv("TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "").strip()
            ):
                missing.append("TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET")
            if not provider_quota_reset_is_admission_safe(
                os.getenv("TIINGO_REVIEWED_HOURLY_RESET", "").strip()
            ):
                missing.append("TIINGO_REVIEWED_HOURLY_RESET")
            if not os.getenv("TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "").strip():
                missing.append("TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE")
            if not os.getenv("TIINGO_HOURLY_QUOTA_EVIDENCE", "").strip():
                missing.append("TIINGO_HOURLY_QUOTA_EVIDENCE")
        if provider == "fmp" and not missing:
            if not provider_quota_reset_is_admission_safe(
                os.getenv("FMP_REVIEWED_DAILY_RESET", "").strip()
            ):
                missing.append("FMP_REVIEWED_DAILY_RESET")
            if not provider_quota_reset_is_admission_safe(
                os.getenv("FMP_REVIEWED_BANDWIDTH_RESET", "").strip()
            ):
                missing.append("FMP_REVIEWED_BANDWIDTH_RESET")
            if not os.getenv("FMP_DAILY_QUOTA_EVIDENCE", "").strip():
                missing.append("FMP_DAILY_QUOTA_EVIDENCE")
            if not os.getenv("FMP_BANDWIDTH_QUOTA_EVIDENCE", "").strip():
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
) -> list[str]:
    """Return exact manifest nodes for a provider subset, or the full matrix."""
    deferred = deferred_providers or set()
    if providers is None or not providers:
        selected = set(LIVE_PROVIDER_CASES) - deferred
    else:
        selected = set(providers)
    unknown = sorted(selected - set(LIVE_PROVIDER_CASES))
    if unknown:
        raise ValueError(f"providers have no live manifest cases: {', '.join(unknown)}")
    cases = {
        (relative_path, function_name)
        for provider in selected
        for relative_path, function_name in LIVE_PROVIDER_CASES[provider]
        if not account_usage_only or "account_usage" in function_name
    }
    nodes = sorted(
        f"tests/live/{relative_path}::{function_name}"
        for relative_path, function_name in cases
    )
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
    untracked_output: str,
    staged_paths: tuple[str, ...],
    staged_diff_output: str,
    tree_sha: str,
    parent_sha: str,
    staged_content: bytes = b"",
) -> tuple[dict[str, str] | None, str | None]:
    """Validate that the Git index is an exact, commit-ready source snapshot."""

    if not status_output.strip():
        return None, "no staged candidate changes"
    if unstaged_diff_exit_code != 0:
        return None, "tracked working-tree changes are not fully staged"
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
        if worktree_status != " ":
            return None, "working-tree changes are not fully staged"
        if index_status == " ":
            return None, "Git status contained a path with no staged change"

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
    """Return a pre-commit candidate only when the index exactly matches files."""

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
    candidate = _staged_candidate_from_git_state(
        status_output=status.stdout,
        unstaged_diff_exit_code=diff.returncode,
        untracked_output=untracked.stdout,
        staged_paths=staged_paths,
        staged_diff_output=staged_diff.stdout,
        tree_sha=_git_output("write-tree"),
        parent_sha=_source_sha(),
        staged_content=staged_content,
    )
    return candidate


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

    assignment = re.compile(
        r"(?im)^\+[^+\r\n]*?\b([A-Z0-9_]*(?:API[_-]?KEY|CLIENT[_-]?(?:ID|SECRET)|"
        r"ACCESS[_-]?KEY|PRIVATE[_-]?KEY|SECRET|TOKEN|PASSWORD))\b[\"']?\s*[:=]\s*"
        r"[\"']?([A-Za-z0-9_+/=-]{20,})"
    )
    placeholders = ("your_", "replace_", "example", "placeholder", "changeme", "<")
    safe_values = {"ci-contract-secret"}
    scanned_text = staged_diff + "\n" + staged_content.decode("latin-1")
    for match in assignment.finditer(scanned_text):
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
                            ledger_error = "usage ledger reservations field is malformed"
                        else:
                            for reservation in reservations:
                                if not isinstance(reservation, dict):
                                    ledger_error = "usage ledger reservation entry is malformed"
                                    continue
                                reservation_id = str(reservation.get("reservation_id") or "").strip()
                                provider_name = str(row.get("provider") or "")
                                operation_name = str(reservation.get("operation") or "").strip()
                                if not reservation_id or not operation_name:
                                    ledger_error = "usage ledger reservation identity is incomplete"
                                    continue
                                if reservation_id in seen_reservation_ids:
                                    ledger_error = "usage ledger contains duplicate reservation identity"
                                seen_reservation_ids.add(reservation_id)
                                reservation_key = (provider_name, operation_name, reservation_id)
                                if reservation_key in seen_reservation_operations:
                                    ledger_error = "usage ledger contains duplicate operation receipt"
                                seen_reservation_operations.add(reservation_key)
                    case_usage = row.get("case_usage")
                    if isinstance(case_usage, dict):
                        for case_id, case_row in case_usage.items():
                            case_key = (str(row.get("provider") or ""), str(case_id))
                            if case_key in seen_case_ids:
                                ledger_error = "usage ledger contains duplicate case receipt"
                            seen_case_ids.add(case_key)
                            if not isinstance(case_row, dict):
                                ledger_error = "usage ledger case receipt is malformed"
                                continue
                            for operation_name in (case_row.get("operations") or {}):
                                operation_key = (case_key[0], case_key[1], str(operation_name))
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
            if not account_usage_only or "account_usage" in function_name
        )
        for provider in providers
    }
    required_operations = {
        provider: (
            {"fetch_account_usage"}
            if account_usage_only
            else LIVE_REQUIRED_OPERATIONS[provider]
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
            is_no_request_case = case_key in LIVE_NO_REQUEST_CASES
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
                result["reason"] = LIVE_NO_REQUEST_CASES[case_key]
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
        for operation, disposition in sorted(LIVE_OPERATION_DISPOSITIONS[provider].items()):
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
        "service_operation_aliases": dict(sorted(LIVE_SERVICE_OPERATION_ALIASES.items())),
        "provider_safety_dispositions": {
            provider: {
                "kind": "intentional_no_request_policy",
                "reason": reason,
            }
            for provider, reason in sorted(LIVE_PROVIDER_SAFETY_DISPOSITIONS.items())
            if provider in providers
        },
        "cases": case_results,
        "missing": sorted(set(missing)),
        "complete": not missing and not ledger_error,
    }
    if ledger_error:
        evidence["complete"] = False
        evidence["missing"] = sorted(set([*missing, ledger_error]))
    return evidence


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
) -> str:
    """Persist a redacted live-test receipt in the active branch workstream."""

    path = _workstream_validation_path()
    dirty_paths = _dirty_source_paths()
    full_matrix = not providers
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
        elif full_matrix:
            result = "staged_candidate_full_matrix_passed"
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
        "scope": "full_matrix" if full_matrix else "focused",
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
        "providers_selected": sorted(providers or []),
        "providers_run": sorted(
            set(providers)
            if providers
            else set(LIVE_PROVIDER_CASES) - set(approved_deferrals)
        ),
        "live_evidence": live_evidence
        or {"complete": False, "missing": ["same-run live evidence unavailable"]},
        "approved_deferrals": approved_deferrals if full_matrix else {},
        "exit_code": exit_code,
        **({"canary_mode": "dinari_sandbox"} if canary_mode else {}),
    }
    if candidate_tree is not None:
        receipt["candidate_tree_sha"] = candidate_tree["tree_sha"]
        receipt["candidate_parent_sha"] = candidate_tree["parent_sha"]
        receipt["persisted_to_workstream"] = False
        print("staged candidate receipt: " + json.dumps(receipt, sort_keys=True))
    elif path is not None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, sort_keys=True) + "\n")
    print(
        "provider live receipt: "
        f"{result} ({counts['passed_cases']}/{counts['case_count']} cases; "
        f"source {candidate_tree['tree_sha'] if candidate_tree else receipt['source_sha'] or 'unknown'})"
    )
    return result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        action="append",
        choices=sorted(LIVE_PROVIDER_CASES),
        help="run only this provider's manifest-backed cases; repeat to select several",
    )
    parser.add_argument(
        "--allow-staged-candidate",
        action="store_true",
        help=(
            "validate a fully staged pre-commit tree; any unstaged or untracked "
            "path blocks the run, and the receipt is printed but not appended "
            "to the workstream until the tested tree is committed"
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
            "run only Dinari's non-persisting Sandbox validation through an "
            "explicit operator-authorized per-run request cap"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    selected_providers = set(arguments.provider or [])
    account_usage_only = bool(getattr(arguments, "account_usage_only", False))
    dinari_sandbox_canary = bool(getattr(arguments, "dinari_sandbox_canary", False))
    if dinari_sandbox_canary and selected_providers != {"dinari"}:
        print(
            "--dinari-sandbox-canary requires exactly one --provider dinari"
        )
        return 2
    if dinari_sandbox_canary and account_usage_only:
        print("--dinari-sandbox-canary cannot be combined with --account-usage-only")
        return 2
    if account_usage_only and selected_providers not in (
        {"alpaca"},
        {"marketdata_app"},
        {"twelve_data"},
        {"eodhd"},
        {"binance"},
        {"openfigi"},
    ):
        print(
            "account-usage-only requires exactly one of --provider alpaca, "
            "marketdata_app, --provider twelve_data, --provider eodhd, or "
            "--provider binance, or --provider openfigi"
        )
        return 2
    if arguments.allow_staged_candidate and (
        arguments.provider or account_usage_only
    ):
        print(
            "staged candidate preflight blocked: candidate acceptance requires the full matrix"
        )
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
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
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
            provider: names
            for provider, names in CREDENTIALS.items()
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
            live_quota_missing = {}
        elif account_usage_only:
            live_quota_missing = live_operation_quota_preflight(
                selected_for_run,
                operations_override={
                    provider: {"fetch_account_usage"} for provider in selected_for_run
                },
            )
        else:
            live_quota_missing = live_operation_quota_preflight(selected_for_run)
        if live_quota_missing:
            missing["provider-specific quota/cost/baseline admission"] = [
                f"{provider}: {reason}"
                for provider, reasons in sorted(live_quota_missing.items())
                for reason in reasons
            ]
    unresolved_live_coverage = False
    if not arguments.provider and not account_usage_only:
        unresolved_operations = [
            f"{provider}/{operation}: {reason}"
            for provider in sorted(set(selected_for_run) & set(LIVE_OPERATION_DISPOSITIONS))
            for operation, reason in sorted(LIVE_OPERATION_DISPOSITIONS[provider].items())
            if live_operation_disposition_kind(reason)
            not in LIVE_COVERED_DISPOSITION_KINDS
        ]
        if unresolved_operations:
            unresolved_live_coverage = True
            missing["unresolved capability live coverage"] = unresolved_operations
    safety_statuses = routing_safety_preflight()
    blocked_live_safety: dict[str, list[str]] = {}
    for provider in sorted(selected_for_run):
        for safety_name in LIVE_PREFLIGHT_ROUTING_CONTROLS.get(provider, ()):
            if dinari_sandbox_canary and provider == "dinari":
                continue
            status = safety_statuses.get(
                safety_name, "non-routable: control status is missing"
            )
            if not status.startswith("routable"):
                blocked_live_safety.setdefault(provider, []).append(status)
    if blocked_live_safety:
        missing["required live capability safety"] = [
            f"{provider}: {status}"
            for provider, statuses in sorted(blocked_live_safety.items())
            for status in statuses
        ]
    if missing:
        for provider, names in missing.items():
            print(f"  BLOCKED {provider}: missing {', '.join(names)}")
    else:
        print("  all manifest credentials present")
    print("routing safety preflight:")
    for provider, status in safety_statuses.items():
        print(f"  {provider}: {status}")
    if staged_candidate is not None and missing:
        print("staged candidate blocked before network calls: preflight is incomplete")
        _record_live_validation(
            providers=arguments.provider,
            exit_code=2,
            missing=missing,
            counts={"case_count": 0, "passed_cases": 0, "failed_cases": 0, "skipped_cases": 0},
            approved_deferrals=deferred_providers,
            candidate_tree=staged_candidate,
            canary_mode=dinari_sandbox_canary,
        )
        return 2
    if (
        blocked_live_safety
        or selected_deferred
        or live_quota_missing
        or unresolved_live_coverage
        or (dinari_sandbox_canary and canary_missing)
    ):
        print(
            "live provider probes blocked before network calls: required cases are not safely admitted"
        )
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
        )
        return 2
    if not quota_coordinator_ready:
        print(
            "live provider probes blocked before network calls: durable quota admission is unavailable"
        )
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
        )
        return 2
    try:
        with provider_live_run_lock() as lock_path:
            print(f"live provider lock: {lock_path}")
            with tempfile.TemporaryDirectory(
                prefix="provider-live-matrix-"
            ) as temp_dir:
                junit_path = Path(temp_dir) / "results.xml"
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
                if staged_candidate is not None:
                    candidate_env["UV_PROJECT_ENVIRONMENT"] = str(
                        Path(temp_dir) / "candidate-backend-venv"
                    )
                result = subprocess.run(
                    [
                        "uv",
                        "run",
                        "--project",
                        str(test_root / "backend"),
                        "--frozen",
                        "--dev",
                        "pytest",
                        *selected_live_test_arguments(
                            arguments.provider,
                            deferred_providers=(
                                set(deferred_providers)
                                if not arguments.provider
                                else set()
                            ),
                            account_usage_only=account_usage_only,
                        ),
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
                        **(
                            {
                                "DINARI_SANDBOX_CANARY_RUN": "1",
                                "PROVIDER_LIVE_ADMISSION_MODE": "dinari_sandbox_canary",
                            }
                            if dinari_sandbox_canary
                            else {}
                        ),
                    },
                    capture_output=True,
                    text=True,
                )
                counts = _junit_counts(junit_path)
                junit_cases = _junit_case_results(junit_path)
                if candidate_dir_context is not None:
                    candidate_dir_context.cleanup()
                output = redact_runner_output(result.stdout + result.stderr)
                if output:
                    if len(output) > 20000:
                        output = output[:20000] + "\n...[redacted output truncated]"
                    print(output, end="" if output.endswith("\n") else "\n")
            candidate_unchanged = True
            if staged_candidate is not None:
                after_test, after_test_error = _staged_candidate_snapshot()
                candidate_unchanged = (
                    after_test_error is None and after_test == staged_candidate
                )
            live_evidence = _provider_live_evidence(
                run_id=live_run_id,
                providers=selected_for_run,
                junit_cases=junit_cases,
                account_usage_only=account_usage_only,
            )
            if not live_evidence["complete"]:
                print("live provider evidence preflight: incomplete for this exact run")
                for item in live_evidence["missing"]:
                    print(f"  BLOCKED {item}")
            live_result = _record_live_validation(
                providers=arguments.provider,
                exit_code=result.returncode,
                missing=missing,
                counts=counts,
                approved_deferrals=deferred_providers,
                live_evidence=live_evidence,
                candidate_tree=staged_candidate,
                candidate_unchanged=candidate_unchanged,
                canary_mode=dinari_sandbox_canary,
            )
    except ProviderLiveRunAlreadyActive as exc:
        print(f"live provider probes: blocked by local key-use lock: {exc}")
        return 3
    if result.returncode:
        if missing:
            print(
                "live provider probes: credential preflight incomplete; no acceptance claim"
            )
            return 2
        return result.returncode
    if not live_evidence["complete"]:
        print(
            "live provider probes: same-run evidence is incomplete; no acceptance claim"
        )
        return 2
    if staged_candidate is not None and live_result not in {
        "staged_candidate_full_matrix_passed",
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
