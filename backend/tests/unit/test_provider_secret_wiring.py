import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.config import Settings, provider_required_operation_byte_bounds
from app.providers.registry import _PROVIDERS

ROOT = Path(__file__).resolve().parents[3]

_LIVE_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "provider_live_probe_script", ROOT / "scripts/run-live-provider-probes.py"
)
assert _LIVE_SCRIPT_SPEC and _LIVE_SCRIPT_SPEC.loader
_LIVE_SCRIPT = importlib.util.module_from_spec(_LIVE_SCRIPT_SPEC)
_LIVE_SCRIPT_SPEC.loader.exec_module(_LIVE_SCRIPT)
_RPI_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "rpi_deployment_helper_for_provider_secrets", ROOT / "scripts/rpi.py"
)
assert _RPI_SCRIPT_SPEC and _RPI_SCRIPT_SPEC.loader
_RPI_SCRIPT = importlib.util.module_from_spec(_RPI_SCRIPT_SPEC)
_RPI_SCRIPT_SPEC.loader.exec_module(_RPI_SCRIPT)
routing_safety_preflight = _LIVE_SCRIPT.routing_safety_preflight
setting_is_configured = _LIVE_SCRIPT.setting_is_configured
usage_scope_is_configured = _LIVE_SCRIPT.usage_scope_is_configured
PROVIDER_SECRET_NAMES = {
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "MASSIVE_API_KEY",
    "MARKETDATA_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "COINGECKO_API_KEY",
    "FRED_API_KEY",
    "FINRA_CLIENT_ID",
    "FINRA_CLIENT_SECRET",
    "FINRA_ORF_USERNAME",
    "FINRA_ORF_REFRESH_TOKEN",
    "TIINGO_API_KEY",
    "TWELVE_DATA_API_KEY",
    "FINNHUB_API_KEY",
    "MARKETSTACK_API_KEY",
    "EODHD_API_KEY",
    "FMP_API_KEY",
    "TRADIER_API_KEY",
    "MARKETDATA_APP_API_KEY",
    "XSTOCKS_API_KEY",
    "DINARI_API_KEY_ID",
    "DINARI_API_SECRET_KEY",
    "ONDO_GLOBAL_MARKETS_API_KEY",
    "IBKR_READ_ONLY_SESSION_COOKIE",
    "OPENFIGI_API_KEY",
    "COINBASE_API_KEY",
    "KRAKEN_API_KEY",
    "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
}
PROVIDER_WORKFLOW_CONFIGURATION_SETTINGS = {
    "NASDAQ_USER_AGENT",
    "OPENFIGI_TIMEOUT_SECONDS",
    "FINRA_OTC_SOURCE_KIND",
    "FINRA_OTC_SYMBOL_DIRECTORY_URL",
    "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
    "FINRA_OTC_SOURCE_REVIEWED",
    "FINRA_OTC_SOURCE_EVIDENCE",
    "FINRA_OTC_REVIEWED_SOURCE_URL",
    "FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL",
    "FINRA_TOKEN_URL",
    "FINRA_API_BASE_URL",
    "FINRA_ORF_TOKEN_URL",
    "FINRA_SHORT_INTEREST_URL",
    "FINRA_OTC_DAILY_LIST_URL",
    "MARKETSTACK_DISCOVERY_EXCHANGE",
    "MARKETSTACK_REVIEWED_MONTHLY_LIMIT",
    "MARKETSTACK_REVIEWED_MONTHLY_RESET",
    "MARKETSTACK_QUOTA_EVIDENCE",
    "IBKR_READ_ONLY_URL",
    "IBKR_READ_ONLY_VERIFY_TLS",
    "IBKR_READ_ONLY_TIMEOUT_SECONDS",
    "IBKR_CONID_MAP",
    "DINARI_API_BASE_URL",
    "DINARI_SANDBOX_QUOTA_PROFILE",
    "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED",
    "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS",
}
PROVIDER_SAFETY_SETTINGS = {
    "ALPACA_CORPORATE_ACTIONS_MAX_PAGES",
    "ALPACA_REVIEWED_RESET",
    "ALPACA_QUOTA_EVIDENCE",
    "MASSIVE_CORPORATE_ACTIONS_MAX_PAGES",
    "MASSIVE_REVIEWED_RESET",
    "MASSIVE_QUOTA_EVIDENCE",
    "MASSIVE_MARKET_DATA_USE_AUTHORIZED",
    "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
    "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
    "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
    "MASSIVE_MARKET_DATA_USE_EXPIRES_AT",
    "FINRA_ASYNC_MAX_RESULT_BYTES",
    "FINRA_OTC_OPERATION_COSTS",
    "FINRA_OTC_SOURCE_KIND",
    "FINRA_OTC_SOURCE_REVIEWED",
    "FINRA_OTC_SOURCE_EVIDENCE",
    "FINRA_OTC_REVIEWED_SOURCE_URL",
    "FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL",
    "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
    "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
    "FINRA_OTC_TERMS_REVIEWED",
    "FINRA_OTC_COMPLETENESS_REVIEWED",
    "FINRA_OTC_REDISTRIBUTION_REVIEWED",
    "FINRA_OTC_POLL_INTERVAL_SECONDS",
    "FINRA_ORF_CUSIP_LICENSED",
    "FINRA_ORF_CUSIP_LICENSE_EVIDENCE",
    "ALPHA_VANTAGE_REVIEWED_RESET",
    "ALPHA_VANTAGE_QUOTA_EVIDENCE",
    "EDGAR_REVIEWED_RESET",
    "EDGAR_QUOTA_EVIDENCE",
    "FINNHUB_REVIEWED_MINUTE_RESET",
    "FINNHUB_REVIEWED_SECOND_RESET",
    "FINNHUB_MINUTE_QUOTA_EVIDENCE",
    "FINNHUB_SECOND_QUOTA_EVIDENCE",
    "FRED_REVIEWED_LIMIT_SCOPE",
    "FRED_REVIEWED_REQUESTS_PER_MINUTE",
    "FRED_REVIEWED_QUOTA_EVIDENCE",
    "FRED_REVIEWED_RESET",
    "FRED_RESET_EVIDENCE",
    "FRED_APPLICATION_USER_SCOPE",
    "FRED_APPLICATION_USER_SCOPE_EVIDENCE",
    "FRED_AUTOMATED_USE_AUTHORIZED",
    "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE",
    "FRED_SERIES_RIGHTS_EVIDENCE",
    "COINBASE_MARKET_DATA_USE_AUTHORIZED",
    "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
    "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
    "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
    "COINBASE_MARKET_DATA_USE_EXPIRES_AT",
    "KRAKEN_MARKET_DATA_USE_AUTHORIZED",
    "KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE",
    "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE",
    "KRAKEN_MARKET_DATA_USE_REVIEWED_AT",
    "KRAKEN_MARKET_DATA_USE_EXPIRES_AT",
    "XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
    "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
    "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
    "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
    "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
    "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
    "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
    "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
    "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
    "BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
    "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED",
    "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE",
    "TIINGO_OPERATION_BYTE_BOUNDS",
    "TIINGO_REVIEWED_PLAN",
    "TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH",
    "TIINGO_CUSTOM_REQUESTS_PER_HOUR",
    "TIINGO_CUSTOM_REQUESTS_PER_DAY",
    "TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH",
    "TIINGO_CUSTOM_QUOTA_EVIDENCE",
    "TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
    "TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET",
    "TIINGO_REVIEWED_HOURLY_RESET",
    "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE",
    "TIINGO_HOURLY_QUOTA_EVIDENCE",
    "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
    "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    "FMP_OPERATION_BYTE_BOUNDS",
    "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
    "FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    "FMP_REVIEWED_PLAN",
    "FMP_STOCK_LIST_ENTITLED",
    "FMP_REVIEWED_DAILY_RESET",
    "FMP_REVIEWED_CALL_RESET",
    "FMP_REVIEWED_BANDWIDTH_RESET",
    "FMP_CALL_QUOTA_EVIDENCE",
    "FMP_DAILY_QUOTA_EVIDENCE",
    "FMP_BANDWIDTH_QUOTA_EVIDENCE",
    "EODHD_REVIEWED_MINUTE_LIMIT",
    "EODHD_REVIEWED_MINUTE_RESET",
    "EODHD_MINUTE_QUOTA_EVIDENCE",
    "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED",
    "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE",
    "MARKETDATA_APP_REVIEWED_PLAN",
    "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
    "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
    "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS",
    "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED",
    "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE",
    "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
    "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED",
    "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS",
    "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER",
    "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS",
    "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE",
    "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT",
}
PROVIDER_CONFIGURATION_SETTINGS = {
    "ALPACA_DATA_FEED",
    "ALPACA_TRADING_BASE_URL",
    "FINRA_OTC_SYMBOL_DIRECTORY_URL",
    "FINRA_OTC_SOURCE_KIND",
    "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
    "FINRA_OTC_SOURCE_EVIDENCE",
    "FINRA_OTC_REVIEWED_SOURCE_URL",
    "FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL",
    "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
    "MARKETSTACK_DISCOVERY_EXCHANGE",
    "IBKR_READ_ONLY_URL",
    "ALLOW_PAID_PROVIDER_ROUTING",
    "PROVIDER_FREE_ONLY_CHECKPOINT",
    "PROVIDER_CHECKPOINT_OPERATION_HOLDS",
    "OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY",
    "PROVIDER_RATE_LIMIT_SEEDS",
    "PROVIDER_FRESHNESS_SEEDS",
    "PROVIDER_USAGE_PROFILE_SEEDS",
    "PROVIDER_QUOTA_ACCOUNT_SCOPES",
    "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES",
    "PROVIDER_QUOTA_CONCURRENCY_LEASE_GRACE_SECONDS",
    "PROVIDER_QUOTA_LEDGER_PATH",
    "DINARI_SANDBOX_QUOTA_PROFILE",
}
TOKENIZED_REFRESH_SETTINGS = {
    "TOKENIZED_ASSET_REFRESH_ENABLED",
    "TOKENIZED_ASSET_REFRESH_MAX_ASSETS",
    "TOKENIZED_HISTORICAL_REFRESH_ENABLED",
    "TOKENIZED_HISTORICAL_REFRESH_MAX_ASSETS",
    "TOKENIZED_HISTORICAL_REFRESH_TIMESPAN",
    "TOKENIZED_CATALOG_REFRESH_ENABLED",
    "TOKENIZED_CATALOG_REFRESH_MAX_PAGES",
    "TOKENIZED_CATALOG_REFRESH_PAGE_SIZE",
}
MARKET_OPERATION_SETTINGS = {
    "MARKET_DATA_REFRESH_SCHEDULE_ENABLED",
    "MARKET_DATA_REFRESH_QUEUE_BATCH_SIZE",
    "MARKET_DATA_SHADOW_REPORT_ENABLED",
    "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED",
    "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS",
    "MARKET_UNIVERSE_RECONCILIATION_ENABLED",
    "MARKET_UNIVERSE_MISSING_CONFIRMATIONS",
}
RUNTIME_COORDINATION_SETTINGS = {
    "OHLCV_DISTRIBUTED_LOCK_ENABLED",
    "OHLCV_DISTRIBUTED_LOCK_TTL_SECONDS",
    "OHLCV_DISTRIBUTED_LOCK_WAIT_SECONDS",
    "OHLCV_DISTRIBUTED_LOCK_RETRY_SECONDS",
}
PROVIDER_OPERATION_SETTINGS = {
    "PROVIDER_AVAILABILITY_MONITOR_ENABLED",
    "PROVIDER_AVAILABILITY_LIVE_ENABLED",
    "PROVIDER_AVAILABILITY_NOTIFICATIONS_ENABLED",
    "PROVIDER_AVAILABILITY_NOTIFICATION_COOLDOWN_SECONDS",
    "PROVIDER_AVAILABILITY_PROBE_TIMEOUT_SECONDS",
    "PROVIDER_REQUEST_LOG_RETENTION_DAYS",
    "UNIVERSE_DISCOVERY_SNAPSHOT_RETENTION_DAYS",
    "PROVIDER_SUPPORT_SUPPORTED_TTL_SECONDS",
    "PROVIDER_SUPPORT_UNSUPPORTED_TTL_SECONDS",
}


def _service_environment(compose: str, service: str) -> str:
    marker = f"  {service}:\n"
    start = compose.index(marker) + len(marker)
    next_service = re.search(r"(?m)^  [A-Za-z][^:\n]*:\s*$", compose[start:])
    return (
        compose[start:] if next_service is None else compose[start : start + next_service.start()]
    )


def test_local_and_rpi_compose_pass_secrets_only_to_trusted_provider_processes():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        for name in PROVIDER_SECRET_NAMES:
            assert f"{name}:" in backend, (relative_path, "backend", name)
            assert f"{name}:" in worker, (relative_path, "worker", name)
            assert f"{name}:" not in research, (relative_path, "research-runner", name)


def test_rpi_secret_inventory_matches_the_provider_secret_manifest():
    assert set(_RPI_SCRIPT.PROVIDER_SECRET_ENV_NAMES) == PROVIDER_SECRET_NAMES
    source = (ROOT / "scripts/rpi.py").read_text()
    assert "optional provider credential names present (values withheld)" in source
    assert "optional provider credential names absent" in source


def test_research_runner_cannot_read_the_durable_provider_quota_ledger():
    """User-supplied research code must not observe or mutate quota state."""

    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        research = _service_environment(compose, "research-runner")
        assert "provider-quota" not in research, (relative_path, "research-runner")
        assert "provider_quota_ledger" not in research, (relative_path, "research-runner")
        assert "/var/lib/charting-platform/provider-quota" not in research, (
            relative_path,
            "research-runner",
        )
        assert "PROVIDER_QUOTA_LEDGER" not in research, (relative_path, "research-runner")


def test_trusted_local_and_rpi_processes_share_the_durable_quota_ledger():
    """Backend/worker reservations must coordinate without exposing the ledger to user code."""

    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        mount = (
            "${PROVIDER_QUOTA_LEDGER_HOST_DIR:-${HOME}/.config/charting-platform/provider-quota}"
            ":/var/lib/charting-platform/provider-quota"
            if relative_path == "docker-compose.yml"
            else "provider_quota_ledger:/var/lib/charting-platform/provider-quota"
        )
        assert mount in backend, (relative_path, "backend")
        assert mount in worker, (relative_path, "worker")
        assert mount not in research, (relative_path, "research-runner")


def test_finra_orf_rotating_token_state_is_shared_only_by_trusted_processes():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        mount = (
            "${FINRA_ORF_REFRESH_TOKEN_STATE_HOST_DIR:-${HOME}/.config/charting-platform/"
            "provider-secrets/finra-orf}:/var/lib/charting-platform/provider-secrets/finra-orf"
            if relative_path == "docker-compose.yml"
            else "${FINRA_ORF_REFRESH_TOKEN_STATE_HOST_DIR:-/var/lib/charting-platform/"
            "provider-secrets/finra-orf}:/var/lib/charting-platform/provider-secrets/finra-orf"
        )
        for name, service in (("backend", backend), ("worker", worker)):
            assert "FINRA_ORF_REFRESH_TOKEN_STATE_FILE:" in service, (relative_path, name)
            assert mount in service, (relative_path, name)
        assert "provider-secrets/finra-orf" not in research


def test_local_and_rpi_compose_pass_provider_safety_settings_to_backend_and_worker_only():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        for name in PROVIDER_SAFETY_SETTINGS:
            assert f"{name}:" in backend, (relative_path, "backend", name)
            assert f"{name}:" in worker, (relative_path, "worker", name)
            assert f"{name}:" not in research, (relative_path, "research-runner", name)


def test_local_and_rpi_compose_pass_provider_configuration_to_backend_and_worker_only():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        for name in PROVIDER_CONFIGURATION_SETTINGS:
            assert f"{name}:" in backend, (relative_path, "backend", name)
            assert f"{name}:" in worker, (relative_path, "worker", name)
            assert f"{name}:" not in research, (relative_path, "research-runner", name)


def test_local_and_rpi_compose_pass_tokenized_refresh_settings_to_backend_and_worker_only():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        for name in TOKENIZED_REFRESH_SETTINGS:
            assert f"{name}:" in backend, (relative_path, "backend", name)
            assert f"{name}:" in worker, (relative_path, "worker", name)
            assert f"{name}:" not in research, (relative_path, "research-runner", name)


def test_local_and_rpi_compose_pass_market_operation_settings_to_backend_and_worker_only():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        for name in MARKET_OPERATION_SETTINGS:
            assert f"{name}:" in backend, (relative_path, "backend", name)
            assert f"{name}:" in worker, (relative_path, "worker", name)
            assert f"{name}:" not in research, (relative_path, "research-runner", name)


def test_local_and_rpi_compose_pass_runtime_coordination_settings_to_backend_and_worker_only():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        for name in RUNTIME_COORDINATION_SETTINGS:
            assert f"{name}:" in backend, (relative_path, "backend", name)
            assert f"{name}:" in worker, (relative_path, "worker", name)
            assert f"{name}:" not in research, (relative_path, "research-runner", name)


def test_local_and_rpi_compose_pass_provider_operation_settings_to_backend_and_worker_only():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        research = _service_environment(compose, "research-runner")
        for name in PROVIDER_OPERATION_SETTINGS:
            assert f"{name}:" in backend, (relative_path, "backend", name)
            assert f"{name}:" in worker, (relative_path, "worker", name)
            assert f"{name}:" not in research, (relative_path, "research-runner", name)


def test_deployment_defaults_keep_new_tokenized_providers_visible():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        assert (
            'TOKENIZED_PROVIDER_PRIORITY:-["robinhood_tokens","xstocks","bybit_xstocks","gate_tradfi","kraken_xstocks","dinari","ondo_global_markets"]'
            in compose
        )
        assert '"tokenized_historical_prices":["dinari","ondo_global_markets"]' in compose


def test_owner_private_retention_decision_is_consistent_across_runtime_targets():
    assert Settings(_env_file=None).PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK is True
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        assert (
            "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK: "
            "${PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK:-true}"
        ) in compose
    workflow = (ROOT / ".github/workflows/provider-live.yml").read_text()
    assert 'PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK: "true"' in workflow


def test_checkpoint_operation_holds_are_configurable_across_runtime_targets():
    configured = Settings(_env_file=None)
    assert set(configured.PROVIDER_CHECKPOINT_OPERATION_HOLDS) == {
        "alpha_vantage",
        "cta_plan",
        "eodhd",
        "marketstack",
        "nasdaq",
        "tiingo",
        "dinari",
        "bybit_xstocks",
    }
    assert "fetch_account_usage" not in configured.PROVIDER_CHECKPOINT_OPERATION_HOLDS["eodhd"]
    assert Settings(
        _env_file=None,
        PROVIDER_CHECKPOINT_OPERATION_HOLDS='{"eodhd":{"fetch_ohlcv":"review hold"}}',
    ).PROVIDER_CHECKPOINT_OPERATION_HOLDS == {"eodhd": {"fetch_ohlcv": "review hold"}}
    with pytest.raises(ValueError, match="operation and reason must be non-empty"):
        Settings(
            _env_file=None,
            PROVIDER_CHECKPOINT_OPERATION_HOLDS='{"eodhd":{"fetch_ohlcv":""}}',
        )
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        backend = _service_environment(compose, "backend")
        worker = _service_environment(compose, "worker")
        for service in (backend, worker):
            assert "PROVIDER_FREE_ONLY_CHECKPOINT:" in service
            assert (
                "PROVIDER_CHECKPOINT_OPERATION_HOLDS: "
                "${PROVIDER_CHECKPOINT_OPERATION_HOLDS:-__CODE_DEFAULT__}"
            ) in service


def test_checkpoint_operation_hold_sentinel_and_json_parse_from_env_and_dotenv(
    tmp_path,
    monkeypatch,
):
    default_holds = Settings(_env_file=None).PROVIDER_CHECKPOINT_OPERATION_HOLDS

    monkeypatch.setenv("PROVIDER_CHECKPOINT_OPERATION_HOLDS", "__CODE_DEFAULT__")
    assert Settings(_env_file=None).PROVIDER_CHECKPOINT_OPERATION_HOLDS == default_holds

    monkeypatch.setenv(
        "PROVIDER_CHECKPOINT_OPERATION_HOLDS",
        '{"eodhd":{"fetch_ohlcv":"reviewed environment hold"}}',
    )
    assert Settings(_env_file=None).PROVIDER_CHECKPOINT_OPERATION_HOLDS == {
        "eodhd": {"fetch_ohlcv": "reviewed environment hold"}
    }

    monkeypatch.delenv("PROVIDER_CHECKPOINT_OPERATION_HOLDS")
    dotenv_path = tmp_path / "provider.env"
    dotenv_path.write_text("PROVIDER_CHECKPOINT_OPERATION_HOLDS=__CODE_DEFAULT__\n")
    assert Settings(_env_file=dotenv_path).PROVIDER_CHECKPOINT_OPERATION_HOLDS == default_holds

    dotenv_path.write_text('PROVIDER_CHECKPOINT_OPERATION_HOLDS={"eodhd":{"fetch_ohlcv":""}}\n')
    with pytest.raises(ValueError, match="operation and reason must be non-empty"):
        Settings(_env_file=dotenv_path)


def test_provider_chain_examples_match_backend_tokenized_history_contract():
    """Keep public configuration examples aligned with backend defaults."""

    def chain_seed(relative_path: str) -> dict:
        text = (ROOT / relative_path).read_text()
        match = re.search(r"^PROVIDER_CHAIN_SEEDS=(.*)$", text, re.MULTILINE)
        assert match, relative_path
        return json.loads(match.group(1))

    expected = chain_seed("backend/.env.example")
    assert expected["tokenized_historical_prices"] == ["dinari", "ondo_global_markets"]
    for relative_path in (".env.example", "README.md"):
        assert chain_seed(relative_path) == expected, relative_path


def test_live_workflow_is_branch_scoped_environment_isolated_and_maps_each_secret():
    workflow = (ROOT / ".github/workflows/provider-live.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "if: github.ref == 'refs/heads/staging' || github.ref == 'refs/heads/master'" in workflow
    assert "provider-live-staging" in workflow
    assert "provider-live-master" in workflow
    assert "environment: provider-live-validation" not in workflow
    assert "pull_request_target" not in workflow
    assert "schedule:" not in workflow
    assert "PROVIDER_LIVE_USAGE_LEDGER: ${{ runner.temp }}/provider-live-usage.jsonl" in workflow
    assert (
        "PROVIDER_LIVE_USAGE_SCOPE: github:${{ github.repository }}:${{ github.ref_name }}"
        in workflow
    )
    assert (
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL: ${{ secrets.PROVIDER_QUOTA_LEDGER_DATABASE_URL }}"
        in workflow
    )
    assert "PROVIDER_QUOTA_ACCOUNT_SCOPES:" in workflow
    assert "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES:" in workflow
    assert "uses: actions/upload-artifact@v4" in workflow
    assert "name: provider-live-usage-${{ github.run_id }}" in workflow
    assert "if: always()" in workflow
    assert "retention-days: 90" in workflow
    assert "if-no-files-found: ignore" in workflow
    assert (
        "PROVIDER_RATE_LIMIT_SEEDS: ${{ vars.PROVIDER_RATE_LIMIT_SEEDS || '__CODE_DEFAULT__' }}"
        in workflow
    )
    assert (
        "PROVIDER_USAGE_PROFILE_SEEDS: ${{ vars.PROVIDER_USAGE_PROFILE_SEEDS || '__CODE_DEFAULT__' }}"
        in workflow
    )
    assert (
        "DINARI_SANDBOX_QUOTA_PROFILE: ${{ vars.DINARI_SANDBOX_QUOTA_PROFILE || '__CODE_DEFAULT__' }}"
        in workflow
    )
    for name in PROVIDER_SECRET_NAMES:
        assert f"{name}: ${{{{ secrets.{name} }}}}" in workflow
    for name in PROVIDER_SAFETY_SETTINGS:
        assert f"{name}:" in workflow
    for name in PROVIDER_WORKFLOW_CONFIGURATION_SETTINGS:
        assert f"{name}:" in workflow
    assert (
        "ALPACA_TRADING_BASE_URL: ${{ vars.ALPACA_TRADING_BASE_URL || 'https://paper-api.alpaca.markets/v2' }}"
        in workflow
    )
    assert "ALPACA_DATA_FEED: ${{ vars.ALPACA_DATA_FEED || 'iex' }}" in workflow
    assert (
        "ALPACA_CORPORATE_ACTIONS_MAX_PAGES: ${{ vars.ALPACA_CORPORATE_ACTIONS_MAX_PAGES || '0' }}"
        in workflow
    )
    assert (
        "MASSIVE_CORPORATE_ACTIONS_MAX_PAGES: ${{ vars.MASSIVE_CORPORATE_ACTIONS_MAX_PAGES || '0' }}"
        in workflow
    )
    assert "MASSIVE_REVIEWED_RESET: ${{ vars.MASSIVE_REVIEWED_RESET || '' }}" in workflow
    assert "MASSIVE_QUOTA_EVIDENCE: ${{ vars.MASSIVE_QUOTA_EVIDENCE || '' }}" in workflow
    assert (
        "MASSIVE_MARKET_DATA_USE_AUTHORIZED: ${{ vars.MASSIVE_MARKET_DATA_USE_AUTHORIZED || 'false' }}"
        in workflow
    )
    assert (
        "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE: ${{ vars.MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE || '' }}"
        in workflow
    )
    assert (
        "MASSIVE_MARKET_DATA_USE_EXPIRES_AT: ${{ vars.MASSIVE_MARKET_DATA_USE_EXPIRES_AT || '' }}"
        in workflow
    )
    assert (
        "FINRA_ASYNC_MAX_RESULT_BYTES: ${{ vars.FINRA_ASYNC_MAX_RESULT_BYTES || '0' }}" in workflow
    )
    assert "FINRA_EQUITY_DATA_USE_" not in workflow
    assert "FRED_REVIEWED_LIMIT_SCOPE: ${{ vars.FRED_REVIEWED_LIMIT_SCOPE || '' }}" in workflow
    assert (
        "ALPHA_VANTAGE_REVIEWED_RESET: ${{ vars.ALPHA_VANTAGE_REVIEWED_RESET || '' }}" in workflow
    )
    assert (
        "ALPHA_VANTAGE_QUOTA_EVIDENCE: ${{ vars.ALPHA_VANTAGE_QUOTA_EVIDENCE || '' }}" in workflow
    )
    assert "EDGAR_REVIEWED_RESET: ${{ vars.EDGAR_REVIEWED_RESET || '' }}" in workflow
    assert "EDGAR_QUOTA_EVIDENCE: ${{ vars.EDGAR_QUOTA_EVIDENCE || '' }}" in workflow
    assert (
        "FINNHUB_REVIEWED_MINUTE_RESET: ${{ vars.FINNHUB_REVIEWED_MINUTE_RESET || '' }}" in workflow
    )
    assert (
        "FINNHUB_REVIEWED_SECOND_RESET: ${{ vars.FINNHUB_REVIEWED_SECOND_RESET || '' }}" in workflow
    )
    assert (
        "FINNHUB_MINUTE_QUOTA_EVIDENCE: ${{ vars.FINNHUB_MINUTE_QUOTA_EVIDENCE || '' }}" in workflow
    )
    assert (
        "FINNHUB_SECOND_QUOTA_EVIDENCE: ${{ vars.FINNHUB_SECOND_QUOTA_EVIDENCE || '' }}" in workflow
    )
    assert (
        "FRED_REVIEWED_REQUESTS_PER_MINUTE: ${{ vars.FRED_REVIEWED_REQUESTS_PER_MINUTE || '0' }}"
        in workflow
    )
    assert (
        "FRED_REVIEWED_QUOTA_EVIDENCE: ${{ vars.FRED_REVIEWED_QUOTA_EVIDENCE || '' }}" in workflow
    )
    assert "FRED_REVIEWED_RESET: ${{ vars.FRED_REVIEWED_RESET || '' }}" in workflow
    assert "FRED_RESET_EVIDENCE: ${{ vars.FRED_RESET_EVIDENCE || '' }}" in workflow
    assert "FRED_APPLICATION_USER_SCOPE: ${{ vars.FRED_APPLICATION_USER_SCOPE || '' }}" in workflow
    assert (
        "FRED_APPLICATION_USER_SCOPE_EVIDENCE: ${{ vars.FRED_APPLICATION_USER_SCOPE_EVIDENCE || '' }}"
        in workflow
    )
    assert (
        "FRED_AUTOMATED_USE_AUTHORIZED: ${{ vars.FRED_AUTOMATED_USE_AUTHORIZED || 'false' }}"
        in workflow
    )
    assert (
        "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE: ${{ vars.FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE || '' }}"
        in workflow
    )
    assert (
        "FRED_SERIES_RIGHTS_EVIDENCE: ${{ vars.FRED_SERIES_RIGHTS_EVIDENCE || '{}' }}" in workflow
    )
    for name in (
        "COINBASE_MARKET_DATA_USE_AUTHORIZED",
        "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
        "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
        "COINBASE_MARKET_DATA_USE_EXPIRES_AT",
    ):
        assert f"{name}:" in workflow
    for name in (
        "KRAKEN_MARKET_DATA_USE_AUTHORIZED",
        "KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE",
        "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "KRAKEN_MARKET_DATA_USE_REVIEWED_AT",
        "KRAKEN_MARKET_DATA_USE_EXPIRES_AT",
    ):
        assert f"{name}:" in workflow
    for name in (
        "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE",
    ):
        assert f"{name}:" in workflow
    for name in (
        "XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
        "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
        "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
    ):
        assert f"{name}:" in workflow
    assert (
        "TIINGO_OPERATION_BYTE_BOUNDS: ${{ vars.TIINGO_OPERATION_BYTE_BOUNDS || '__CODE_DEFAULT__' }}"
        in workflow
    )
    assert "TIINGO_REVIEWED_PLAN: ${{ vars.TIINGO_REVIEWED_PLAN || 'starter' }}" in workflow
    for name in (
        "TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH",
        "TIINGO_CUSTOM_REQUESTS_PER_HOUR",
        "TIINGO_CUSTOM_REQUESTS_PER_DAY",
        "TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH",
        "TIINGO_CUSTOM_QUOTA_EVIDENCE",
    ):
        assert f"{name}:" in workflow
    for name in (
        "TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
        "TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    ):
        assert f"{name}:" in workflow
    for name in (
        "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
        "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    ):
        assert f"{name}:" in workflow
    assert (
        "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET: ${{ vars.TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET || '' }}"
        in workflow
    )
    assert (
        "TIINGO_REVIEWED_HOURLY_RESET: ${{ vars.TIINGO_REVIEWED_HOURLY_RESET || '' }}" in workflow
    )
    assert (
        "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE: ${{ vars.TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE || '' }}"
        in workflow
    )
    assert (
        "TIINGO_HOURLY_QUOTA_EVIDENCE: ${{ vars.TIINGO_HOURLY_QUOTA_EVIDENCE || '' }}" in workflow
    )
    assert (
        "FMP_OPERATION_BYTE_BOUNDS: ${{ vars.FMP_OPERATION_BYTE_BOUNDS || '__CODE_DEFAULT__' }}"
        in workflow
    )
    assert "FMP_REVIEWED_PLAN: ${{ vars.FMP_REVIEWED_PLAN || 'basic' }}" in workflow
    assert "FMP_STOCK_LIST_ENTITLED: ${{ vars.FMP_STOCK_LIST_ENTITLED || 'false' }}" in workflow
    for name in (
        "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
        "FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    ):
        assert f"{name}:" in workflow
    assert "FMP_REVIEWED_DAILY_RESET: ${{ vars.FMP_REVIEWED_DAILY_RESET || '' }}" in workflow
    assert "FMP_REVIEWED_CALL_RESET: ${{ vars.FMP_REVIEWED_CALL_RESET || '' }}" in workflow
    assert (
        "FMP_REVIEWED_BANDWIDTH_RESET: ${{ vars.FMP_REVIEWED_BANDWIDTH_RESET || '' }}" in workflow
    )
    assert "FMP_DAILY_QUOTA_EVIDENCE: ${{ vars.FMP_DAILY_QUOTA_EVIDENCE || '' }}" in workflow
    assert "FMP_CALL_QUOTA_EVIDENCE: ${{ vars.FMP_CALL_QUOTA_EVIDENCE || '' }}" in workflow
    assert (
        "FMP_BANDWIDTH_QUOTA_EVIDENCE: ${{ vars.FMP_BANDWIDTH_QUOTA_EVIDENCE || '' }}" in workflow
    )
    assert "EODHD_REVIEWED_MINUTE_LIMIT: ${{ vars.EODHD_REVIEWED_MINUTE_LIMIT || '0' }}" in workflow
    assert "EODHD_REVIEWED_MINUTE_RESET: ${{ vars.EODHD_REVIEWED_MINUTE_RESET || '' }}" in workflow
    assert "EODHD_MINUTE_QUOTA_EVIDENCE: ${{ vars.EODHD_MINUTE_QUOTA_EVIDENCE || '' }}" in workflow
    assert "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED:" in workflow
    assert "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE:" in workflow
    assert (
        "MARKETDATA_APP_REVIEWED_PLAN: ${{ vars.MARKETDATA_APP_REVIEWED_PLAN || '' }}" in workflow
    )
    assert (
        "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT: ${{ vars.MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT || '0' }}"
        in workflow
    )
    assert (
        "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT: ${{ vars.MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT || '' }}"
        in workflow
    )
    assert (
        "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS: ${{ vars.MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS || '0' }}"
        in workflow
    )
    for name in (
        "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED",
        "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE",
    ):
        assert f"{name}:" in workflow
    for name in (
        "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
        "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    ):
        assert f"{name}:" in workflow
    assert (
        "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED: ${{ vars.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED || 'false' }}"
        in workflow
    )
    assert (
        "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS: ${{ vars.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS || '50' }}"
        in workflow
    )
    assert (
        "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER: ${{ vars.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER || '100' }}"
        in workflow
    )
    assert (
        "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS: ${{ vars.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS || '0' }}"
        in workflow
    )
    assert (
        "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT: ${{ vars.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT || '0' }}"
        in workflow
    )
    assert (
        "MARKETSTACK_DISCOVERY_EXCHANGE: ${{ vars.MARKETSTACK_DISCOVERY_EXCHANGE || '' }}"
        in workflow
    )
    assert (
        "MARKETSTACK_REVIEWED_MONTHLY_LIMIT: ${{ vars.MARKETSTACK_REVIEWED_MONTHLY_LIMIT || '100' }}"
        in workflow
    )
    assert (
        "MARKETSTACK_REVIEWED_MONTHLY_RESET: ${{ vars.MARKETSTACK_REVIEWED_MONTHLY_RESET || '' }}"
        in workflow
    )
    assert "MARKETSTACK_QUOTA_EVIDENCE: ${{ vars.MARKETSTACK_QUOTA_EVIDENCE || '' }}" in workflow


def test_backend_env_example_preserves_fail_closed_provider_safety_contract():
    example = (ROOT / "backend/.env.example").read_text()
    assert (
        "FINRA_OTC_SYMBOL_DIRECTORY_URL="
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    ) in example
    assert "FINRA_OTC_SOURCE_KIND=finra_otc_query_api" in example
    assert (
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL=https://apidownload.finratraqs.org/"
        "DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF"
    ) in example
    assert "FINRA_ASYNC_MAX_RESULT_BYTES=0" in example
    assert "FINRA_EQUITY_DATA_USE_AUTHORIZED=" not in example
    assert "FINRA_OTC_PERSISTENT_STORAGE_AUTHORIZED=" not in example
    assert "ALPACA_CORPORATE_ACTIONS_MAX_PAGES=0" in example
    assert "ALPACA_REVIEWED_RESET=" in example
    assert "ALPACA_QUOTA_EVIDENCE=" in example
    assert "MASSIVE_CORPORATE_ACTIONS_MAX_PAGES=0" in example
    assert "MASSIVE_MARKET_DATA_USE_AUTHORIZED=false" in example
    assert "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE=" in example
    assert "MASSIVE_MARKET_DATA_USE_EXPIRES_AT=" in example
    assert "KRAKEN_MARKET_DATA_USE_AUTHORIZED=false" in example
    assert "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE=" in example
    assert "FRED_REVIEWED_LIMIT_SCOPE=" in example
    assert "ALPHA_VANTAGE_REVIEWED_RESET=" in example
    assert "ALPHA_VANTAGE_QUOTA_EVIDENCE=" in example
    assert "EDGAR_REVIEWED_RESET=" in example
    assert "EDGAR_QUOTA_EVIDENCE=" in example
    assert "FINNHUB_REVIEWED_MINUTE_RESET=" in example
    assert "FINNHUB_REVIEWED_SECOND_RESET=" in example
    assert "FINNHUB_MINUTE_QUOTA_EVIDENCE=" in example
    assert "FINNHUB_SECOND_QUOTA_EVIDENCE=" in example
    assert "FRED_REVIEWED_REQUESTS_PER_MINUTE=0" in example
    assert "FRED_REVIEWED_QUOTA_EVIDENCE=" in example
    assert "FRED_REVIEWED_RESET=" in example
    assert "FRED_RESET_EVIDENCE=" in example
    assert "FRED_APPLICATION_USER_SCOPE=" in example
    assert "FRED_APPLICATION_USER_SCOPE_EVIDENCE=" in example
    assert "FRED_PERSISTED_STORAGE_AUTHORIZED=" not in example
    assert "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE=" not in example
    assert "FRED_AUTOMATED_USE_AUTHORIZED=false" in example
    assert "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE=" in example
    assert "FRED_SERIES_RIGHTS_EVIDENCE={}" in example
    assert 'TIINGO_OPERATION_BYTE_BOUNDS={"fetch_ohlcv":1048576' in example
    assert "TIINGO_REVIEWED_PLAN=starter" in example
    assert "TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH=0" in example
    assert "TIINGO_CUSTOM_REQUESTS_PER_HOUR=0" in example
    assert "TIINGO_CUSTOM_REQUESTS_PER_DAY=0" in example
    assert "TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH=0" in example
    assert "TIINGO_CUSTOM_QUOTA_EVIDENCE=" in example
    assert "TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=false" in example
    assert "TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE=" in example
    assert "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET=" in example
    assert "TIINGO_REVIEWED_HOURLY_RESET=" in example
    assert "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE=" in example
    assert "TIINGO_HOURLY_QUOTA_EVIDENCE=" in example
    assert "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=false" in example
    assert "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE=" in example
    assert 'FMP_OPERATION_BYTE_BOUNDS={"fetch_ohlcv":1048576' in example
    assert "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=false" in example
    assert "FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE=" in example
    assert "FMP_REVIEWED_PLAN=basic" in example
    assert "FMP_STOCK_LIST_ENTITLED=false" in example
    assert "FMP_REVIEWED_DAILY_RESET=" in example
    assert "FMP_REVIEWED_CALL_RESET=" in example
    assert "FMP_REVIEWED_BANDWIDTH_RESET=" in example
    assert "FMP_DAILY_QUOTA_EVIDENCE=" in example
    assert "FMP_CALL_QUOTA_EVIDENCE=" in example
    assert "FMP_BANDWIDTH_QUOTA_EVIDENCE=" in example
    assert "EODHD_REVIEWED_MINUTE_LIMIT=0" in example
    assert "EODHD_REVIEWED_MINUTE_RESET=" in example
    assert "EODHD_MINUTE_QUOTA_EVIDENCE=" in example
    assert "MARKETDATA_APP_REVIEWED_PLAN=" in example
    assert "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT=0" in example
    assert "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT=" in example
    assert "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS=0" in example
    assert "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED=false" in example
    assert "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE=" in example
    assert "MARKETSTACK_REVIEWED_MONTHLY_LIMIT=100" in example
    assert "MARKETSTACK_REVIEWED_MONTHLY_RESET=" in example
    assert "MARKETSTACK_QUOTA_EVIDENCE=" in example
    assert "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED=false" in example
    assert "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS=[]" in example
    assert "XSTOCKS_MARKET_DATA_USE_AUTHORIZED=false" in example
    assert "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE=" in example
    assert "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED=false" in example
    assert "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED=false" in example
    assert "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED=false" in example
    assert "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS=50" in example
    assert "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER=100" in example
    assert "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS=0" in example
    assert "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE=disabled" in example
    assert "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT=0" in example
    for name in (
        "IBKR_READ_ONLY_URL",
        "COINBASE_API_KEY",
        "KRAKEN_API_KEY",
        "DINARI_API_BASE_URL",
    ):
        assert f"{name}=" in example
    assert (
        'TOKENIZED_PROVIDER_PRIORITY=["robinhood_tokens","xstocks","bybit_xstocks","gate_tradfi","kraken_xstocks","dinari","ondo_global_markets"]'
        in example
    )
    assert '"tokenized_historical_prices":["dinari","ondo_global_markets"]' in example
    for name in (
        PROVIDER_CONFIGURATION_SETTINGS
        | PROVIDER_OPERATION_SETTINGS
        | RUNTIME_COORDINATION_SETTINGS
    ):
        assert f"{name}=" in example


def test_policy_seed_deployment_fallback_preserves_code_defaults():
    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        for name in (
            "PROVIDER_RATE_LIMIT_SEEDS",
            "PROVIDER_FRESHNESS_SEEDS",
            "PROVIDER_USAGE_PROFILE_SEEDS",
            "DINARI_SANDBOX_QUOTA_PROFILE",
        ):
            assert f"{name}: ${{{name}:-__CODE_DEFAULT__}}" in compose
    for relative_path in (".env.example", "backend/.env.example"):
        example = (ROOT / relative_path).read_text()
        for name in (
            "PROVIDER_RATE_LIMIT_SEEDS",
            "PROVIDER_FRESHNESS_SEEDS",
            "PROVIDER_USAGE_PROFILE_SEEDS",
            "DINARI_SANDBOX_QUOTA_PROFILE",
        ):
            assert f"{name}=__CODE_DEFAULT__" in example


def test_dinari_compose_and_live_workflow_defaults_use_documented_sandbox_host():
    sandbox_host = "https://api-enterprise.sandbox.dinari.com/api/v2"
    retired_host = "https://api-enterprise.sbt.dinari.com/api/v2"

    for relative_path in ("docker-compose.yml", "deploy/rpi/compose.yml"):
        compose = (ROOT / relative_path).read_text()
        assert compose.count(sandbox_host) == 2, relative_path
        assert retired_host not in compose, relative_path

    workflow = (ROOT / ".github/workflows/provider-live.yml").read_text()
    assert sandbox_host in workflow
    assert retired_host not in workflow


def test_optional_market_data_use_review_timestamps_accept_blank_compose_values():
    configured = Settings(
        _env_file=None,
        MASSIVE_MARKET_DATA_USE_REVIEWED_AT="",
        MASSIVE_MARKET_DATA_USE_EXPIRES_AT="",
    )

    assert configured.MASSIVE_MARKET_DATA_USE_REVIEWED_AT is None
    assert configured.MASSIVE_MARKET_DATA_USE_EXPIRES_AT is None


def test_dinari_quota_profile_uses_code_default_when_unset_or_sentinel(monkeypatch):
    monkeypatch.delenv("DINARI_SANDBOX_QUOTA_PROFILE", raising=False)
    assert Settings(_env_file=None).DINARI_SANDBOX_QUOTA_PROFILE == {}
    assert (
        Settings(
            _env_file=None, DINARI_SANDBOX_QUOTA_PROFILE="__CODE_DEFAULT__"
        ).DINARI_SANDBOX_QUOTA_PROFILE
        == {}
    )


def test_marketstack_exchange_page_cost_is_unknown_by_default():
    configured = Settings(_env_file=None)

    assert configured.MARKETSTACK_DISCOVERY_MAX_PAGE_COST == 0
    assert configured.MARKETSTACK_DISCOVERY_COST_EVIDENCE == ""


def test_live_preflight_reports_non_routable_safety_controls_without_guessing(monkeypatch):
    # An explicit blank environment value masks any operator .env setting
    # loaded by the Settings singleton and exercises the missing-expiry branch.
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "false")
    monkeypatch.setenv("ALPACA_CORPORATE_ACTIONS_MAX_PAGES", "0")
    monkeypatch.setenv("ALPACA_REVIEWED_RESET", "")
    monkeypatch.setenv("ALPACA_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("FINRA_ASYNC_MAX_RESULT_BYTES", "0")
    monkeypatch.setenv("FINRA_OTC_SOURCE_KIND", "finra_otc_query_api")
    monkeypatch.setenv(
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
    )
    monkeypatch.setenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "86400")
    monkeypatch.setenv("MASSIVE_CORPORATE_ACTIONS_MAX_PAGES", "0")
    monkeypatch.setenv("MASSIVE_REVIEWED_RESET", "")
    monkeypatch.setenv("MASSIVE_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("MASSIVE_MARKET_DATA_USE_AUTHORIZED", "false")
    monkeypatch.setenv("MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
    monkeypatch.setenv("MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
    monkeypatch.setenv("MASSIVE_MARKET_DATA_USE_REVIEWED_AT", "")
    monkeypatch.setenv("MASSIVE_MARKET_DATA_USE_EXPIRES_AT", "")
    monkeypatch.setenv("FRED_REVIEWED_LIMIT_SCOPE", "")
    monkeypatch.setenv("ALPHA_VANTAGE_REVIEWED_RESET", "")
    monkeypatch.setenv("ALPHA_VANTAGE_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("EDGAR_REVIEWED_RESET", "")
    monkeypatch.setenv("EDGAR_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("FINNHUB_REVIEWED_MINUTE_RESET", "")
    monkeypatch.setenv("FINNHUB_REVIEWED_SECOND_RESET", "")
    monkeypatch.setenv("FINNHUB_MINUTE_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("FINNHUB_SECOND_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("FRED_REVIEWED_REQUESTS_PER_MINUTE", "0")
    monkeypatch.setenv("FRED_REVIEWED_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("FRED_REVIEWED_RESET", "")
    monkeypatch.setenv("FRED_RESET_EVIDENCE", "")
    monkeypatch.setenv("FRED_APPLICATION_USER_SCOPE", "")
    monkeypatch.setenv("FRED_APPLICATION_USER_SCOPE_EVIDENCE", "")
    monkeypatch.setenv("FRED_PERSISTED_STORAGE_AUTHORIZED", "false")
    monkeypatch.setenv("FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", "")
    monkeypatch.setenv("FRED_AUTOMATED_USE_AUTHORIZED", "false")
    monkeypatch.setenv("FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "")
    monkeypatch.setenv("FRED_SERIES_RIGHTS_EVIDENCE", "{}")
    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_AUTHORIZED", "false")
    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_REVIEWED_AT", "")
    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_EXPIRES_AT", "")
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_AUTHORIZED", "false")
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_REVIEWED_AT", "")
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_EXPIRES_AT", "")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_AUTHORIZED", "false")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", "")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_EXPIRES_AT", "")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED", "false")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE", "")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", "false")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", "")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT", "")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", "false")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE", "")
    monkeypatch.setenv("TIINGO_OPERATION_BYTE_BOUNDS", "{}")
    monkeypatch.setenv("TIINGO_REVIEWED_PLAN", "")
    monkeypatch.setenv("TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "")
    monkeypatch.setenv("TIINGO_REVIEWED_HOURLY_RESET", "")
    monkeypatch.setenv("TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("TIINGO_HOURLY_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("FMP_OPERATION_BYTE_BOUNDS", "not-json")
    monkeypatch.setenv("FMP_REVIEWED_DAILY_RESET", "")
    monkeypatch.setenv("FMP_REVIEWED_BANDWIDTH_RESET", "")
    monkeypatch.setenv("FMP_DAILY_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("FMP_BANDWIDTH_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("MARKETSTACK_REVIEWED_MONTHLY_LIMIT", "0")
    monkeypatch.setenv("MARKETSTACK_REVIEWED_MONTHLY_RESET", "")
    monkeypatch.setenv("MARKETSTACK_QUOTA_EVIDENCE", "")
    monkeypatch.setenv("MARKETSTACK_DISCOVERY_MAX_PAGE_COST", "")
    monkeypatch.setenv("MARKETSTACK_DISCOVERY_COST_EVIDENCE", "")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN", "")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "0")
    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "0")
    statuses = routing_safety_preflight()
    assert statuses["finra async result bytes"].startswith("non-routable:")
    assert statuses["alpaca corporate actions"].startswith("routable:")
    assert statuses["alpaca market-data quota"].startswith("routable:")
    assert statuses["massive corporate actions"].startswith("routable:")
    assert statuses["massive market-data use"].startswith("non-routable:")
    assert "provider-license restriction" in statuses["massive market-data use"]
    assert "not missing owner permission" in statuses["massive market-data use"]
    assert statuses["finra otc directory"].startswith("routable:")
    assert "official OTC Symbol Directory Query API" in statuses["finra otc directory"]
    assert "lossless record-total pagination" in statuses["finra otc directory"]
    assert statuses["fred"].startswith("non-routable:")
    assert statuses["alpha_vantage"].startswith("routable:")
    assert statuses["edgar quota"].startswith("routable: contract verified;")
    assert "10-minute throttle recovery hold" in statuses["edgar quota"]
    assert "active shared-scope usage baseline is checked separately" in statuses["edgar quota"]
    assert statuses["finnhub"].startswith("routable:")
    assert statuses["coinbase market-data use"].startswith("non-routable:")
    assert statuses["nasdaq"].startswith("routable:")
    assert statuses["dinari sandbox canary quota"].startswith("non-routable:")
    assert statuses["xstocks"].startswith("non-routable:")
    assert statuses["bybit_xstocks"].startswith("non-routable:")
    assert _LIVE_SCRIPT.LIVE_PREFLIGHT_ROUTING_CONTROLS["bybit_xstocks"] == ("bybit_xstocks",)
    assert statuses["marketstack discovery"].startswith("non-routable:")
    for missing in (
        "MARKETSTACK_DISCOVERY_EXCHANGE",
        "MARKETSTACK_DISCOVERY_MAX_PAGE_COST",
        "MARKETSTACK_DISCOVERY_COST_EVIDENCE",
        "MARKETSTACK_REVIEWED_MONTHLY_LIMIT",
        "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
    ):
        assert missing in statuses["marketstack discovery"]
    assert statuses["marketstack quota"].startswith("non-routable:")
    assert statuses["tiingo provider controls"].startswith("non-routable:")
    assert statuses["tiingo account plan"].startswith("non-routable:")
    assert statuses["fmp"] == (
        "non-routable: missing reviewed controls for FMP_OPERATION_BYTE_BOUNDS is not valid JSON, "
        "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED, FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE"
    )
    assert (
        statuses["marketdata.app account plan"]
        == "non-routable: explicit reviewed plan/limit pair required"
    )
    assert statuses["marketdata.app option chain"].startswith("non-routable:")
    assert statuses["marketdata.app option quote history"].startswith("routable for bounded calls:")
    assert "xstocks" in _LIVE_SCRIPT.LIVE_PREFLIGHT_ROUTING_CONTROLS
    assert _LIVE_SCRIPT.LIVE_PREFLIGHT_ROUTING_CONTROLS["edgar"] == ("edgar quota",)

    monkeypatch.setenv("FRED_REVIEWED_LIMIT_SCOPE", "api_key")
    monkeypatch.setenv("FRED_REVIEWED_REQUESTS_PER_MINUTE", "120")
    monkeypatch.setenv("FRED_REVIEWED_QUOTA_EVIDENCE", "provider-confirmed scope")
    monkeypatch.setenv("FRED_REVIEWED_RESET", "rolling")
    monkeypatch.setenv("FRED_RESET_EVIDENCE", "current provider/account review")
    monkeypatch.setenv("FRED_APPLICATION_USER_SCOPE", "owner_personal_only")
    monkeypatch.setenv(
        "FRED_APPLICATION_USER_SCOPE_EVIDENCE", "single owner uses their own FRED key"
    )
    monkeypatch.setenv("FRED_PERSISTED_STORAGE_AUTHORIZED", "false")
    monkeypatch.setenv("FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", "")
    monkeypatch.setenv("FRED_AUTOMATED_USE_AUTHORIZED", "true")
    monkeypatch.setenv("FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "written automated-use permission")
    from app.config import FRED_MAPPED_SERIES_IDS

    monkeypatch.setenv(
        "FRED_SERIES_RIGHTS_EVIDENCE",
        json.dumps({series_id: "written series rights" for series_id in FRED_MAPPED_SERIES_IDS}),
    )
    statuses = routing_safety_preflight()
    assert statuses["fred"] == "routable"

    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_AUTHORIZED", "true")
    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "terms amendment")
    monkeypatch.setenv(
        "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "internal_automated_persistent_nonredistributed",
    )
    monkeypatch.setenv("COINBASE_MARKET_DATA_USE_REVIEWED_AT", "2026-09-16T00:00:00+00:00")
    statuses = routing_safety_preflight()
    assert statuses["coinbase market-data use"] != "routable"

    monkeypatch.setenv(
        "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "internal_ai_automated_persistent_nonredistributed",
    )
    statuses = routing_safety_preflight()
    assert statuses["coinbase market-data use"] == "routable"

    statuses = routing_safety_preflight()
    assert statuses["kraken market-data use"].startswith("non-routable:")
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_AUTHORIZED", "true")
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE", "written Kraken approval")
    monkeypatch.setenv(
        "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "single_user_personal_automated_internal_persistent_archive_nonredistributed",
    )
    monkeypatch.setenv("KRAKEN_MARKET_DATA_USE_REVIEWED_AT", "2026-09-16T00:00:00+00:00")
    statuses = routing_safety_preflight()
    assert statuses["kraken market-data use"] == "routable"

    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_AUTHORIZED", "true")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "terms amendment")
    monkeypatch.setenv(
        "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "internal_automated_persistent_nonredistributed",
    )
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", "2026-09-16T00:00:00+00:00")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED", "true")
    monkeypatch.setenv("XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE", "deployment review")
    statuses = routing_safety_preflight()
    assert statuses["xstocks"] == "routable"

    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", "true")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "terms amendment")
    monkeypatch.setenv(
        "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "internal_automated_persistent_nonredistributed",
    )
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", "2026-09-16T00:00:00+00:00")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", "true")
    monkeypatch.setenv(
        "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE",
        "deployment outside restricted egress",
    )
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_AUTHORIZED", "true")
    monkeypatch.setenv(
        "BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_EVIDENCE",
        "verified user jurisdiction review",
    )
    statuses = routing_safety_preflight()
    assert (
        statuses["bybit_xstocks"]
        == "routable: anonymous public calls are bounded by the documented 600/5-second/IP ceiling"
    )

    monkeypatch.setenv("ALPACA_CORPORATE_ACTIONS_MAX_PAGES", "0")
    monkeypatch.setenv("ALPACA_REVIEWED_RESET", "")
    monkeypatch.setenv("ALPACA_QUOTA_EVIDENCE", "")
    statuses = routing_safety_preflight()
    assert statuses["alpaca corporate actions"].startswith("routable:")
    assert statuses["alpaca market-data quota"].startswith("routable:")
    monkeypatch.setenv("EDGAR_REVIEWED_RESET", "rolling")
    monkeypatch.setenv("EDGAR_QUOTA_EVIDENCE", "current SEC/account review")
    statuses = routing_safety_preflight()
    assert statuses["edgar quota"] == (
        "routable: contract configured with reviewed reset evidence; active shared-scope usage baseline is checked separately"
    )
    monkeypatch.setenv("MASSIVE_CORPORATE_ACTIONS_MAX_PAGES", "0")
    monkeypatch.setenv("MASSIVE_MARKET_DATA_USE_AUTHORIZED", "true")
    monkeypatch.setenv(
        "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "Massive personal-use terms review"
    )
    monkeypatch.setenv(
        "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "written_automated_persistent_archive_and_audience",
    )
    monkeypatch.setenv("MASSIVE_MARKET_DATA_USE_REVIEWED_AT", "2026-09-16T00:00:00+00:00")
    statuses = routing_safety_preflight()
    assert statuses["massive corporate actions"].startswith("routable:")
    assert statuses["massive market-data use"] == "routable"

    monkeypatch.setenv("FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setenv(
        "FINRA_OTC_OPERATION_COSTS",
        '{"discover_universe_page": 3, "reconcile_universe_page": 3}',
    )
    monkeypatch.setenv("FINRA_OTC_SOURCE_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_SOURCE_EVIDENCE", "FINRA support case 123")
    active_orf_url = (
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?"
        "action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF"
    )
    inactive_orf_url = (
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?"
        "action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF"
    )
    monkeypatch.setenv("FINRA_OTC_SYMBOL_DIRECTORY_URL", active_orf_url)
    monkeypatch.setenv("FINRA_OTC_REVIEWED_SOURCE_URL", active_orf_url)
    monkeypatch.setenv("FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", inactive_orf_url)
    monkeypatch.setenv("FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL", inactive_orf_url)
    monkeypatch.setenv("FINRA_OTC_TERMS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_COMPLETENESS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_REDISTRIBUTION_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "900")
    monkeypatch.setenv("FINRA_ORF_CUSIP_LICENSED", "true")
    monkeypatch.setenv("FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "unit-test CGS license")
    statuses = routing_safety_preflight()
    assert statuses["finra otc directory"] == "routable"

    monkeypatch.setenv(
        "TIINGO_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "get_current_price": 1, "bulk_fetch": 1, "search_instruments": 1, "get_instrument_profile": 1}',
    )
    monkeypatch.setenv("TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", "true")
    monkeypatch.setenv("TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE", "reviewed provider archive terms")
    monkeypatch.setenv(
        "FMP_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "get_current_price": 1, "bulk_fetch": 1, "get_instrument_profile": 1, "fetch_market_events": 1, "discover_universe_page": 1, "fetch_account_usage": 65536}',
    )
    monkeypatch.setenv("FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", "true")
    monkeypatch.setenv("FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE", "reviewed provider archive terms")
    statuses = routing_safety_preflight()
    assert statuses["tiingo provider controls"] == "routable"
    assert statuses["fmp"] == "routable"

    monkeypatch.setenv("TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "calendar_month_est")
    monkeypatch.setenv("TIINGO_REVIEWED_HOURLY_RESET", "rolling")
    monkeypatch.setenv("TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "symbol review")
    monkeypatch.setenv("TIINGO_HOURLY_QUOTA_EVIDENCE", "hourly review")
    statuses = routing_safety_preflight()
    assert statuses["tiingo provider controls"] == "routable"

    monkeypatch.setenv("FMP_REVIEWED_DAILY_RESET", "unrecognized_reset")
    statuses = routing_safety_preflight()
    assert statuses["fmp"] == (
        "non-routable: missing reviewed controls for FMP_REVIEWED_DAILY_RESET"
    )

    monkeypatch.setenv("FMP_REVIEWED_DAILY_RESET", "calendar_day_utc")
    monkeypatch.setenv("FMP_REVIEWED_BANDWIDTH_RESET", "rolling_30_days")
    statuses = routing_safety_preflight()
    assert statuses["fmp"] == "routable"

    monkeypatch.setenv(
        "TIINGO_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "get_current_price": true, "bulk_fetch": 1, "search_instruments": 1, "get_instrument_profile": 1}',
    )
    statuses = routing_safety_preflight()
    assert statuses["tiingo provider controls"].startswith(
        "non-routable: missing reviewed controls for"
    )

    monkeypatch.setenv("MARKETSTACK_DISCOVERY_EXCHANGE", "XNAS")
    monkeypatch.setenv("MARKETSTACK_REVIEWED_MONTHLY_LIMIT", "100")
    monkeypatch.setenv("MARKETSTACK_REVIEWED_MONTHLY_RESET", "calendar_month_utc")
    monkeypatch.setenv("MARKETSTACK_QUOTA_EVIDENCE", "current account review")
    monkeypatch.setenv("MARKETSTACK_DISCOVERY_MAX_PAGE_COST", "1000")
    monkeypatch.setenv("MARKETSTACK_DISCOVERY_COST_EVIDENCE", "current provider billing review")
    monkeypatch.setenv("MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", "true")
    monkeypatch.setenv(
        "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE", "reviewed provider archive terms"
    )
    monkeypatch.setenv("ALLOW_PAID_PROVIDER_ROUTING", "true")
    monkeypatch.setenv("PROVIDER_FREE_ONLY_CHECKPOINT", "false")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "10000")
    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "25")
    statuses = routing_safety_preflight()
    assert statuses["marketstack discovery"] == "routable"
    assert statuses["marketstack quota"] == "routable"
    assert statuses["marketdata.app account plan"] == "routable: paid plan reviewed"
    assert statuses["marketdata.app option chain"] == "routable"
    monkeypatch.delenv("ALLOW_PAID_PROVIDER_ROUTING", raising=False)

    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "10000")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", "")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app account plan"] == (
        "non-routable: trial requires a timezone-aware " "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT"
    )
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "100")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app account plan"] == (
        "non-routable: explicit reviewed plan/limit pair required"
    )
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "10000")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", "2030-01-01T00:00:00+00:00")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app account plan"].startswith("non-routable: temporary trial")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", "2020-01-01T00:00:00+00:00")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app account plan"].startswith(
        "routable: configured trial expired; effective quota automatically falls back"
    )

    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "1")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app option chain"].startswith("non-routable:")
    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "not-an-integer")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app option chain"].startswith("non-routable:")


def test_live_marketdata_plan_preflight_honors_checkpoint_and_trial_denials(monkeypatch):
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "10000")
    monkeypatch.setenv("ALLOW_PAID_PROVIDER_ROUTING", "true")
    monkeypatch.setenv("PROVIDER_FREE_ONLY_CHECKPOINT", "true")

    # Paid opt-in cannot override the shared free-only checkpoint.
    status = routing_safety_preflight()["marketdata.app account plan"]
    assert status == "non-routable: shared free-only checkpoint blocks paid plans"

    # Full-roadmap opt-in remains independently available outside checkpoint
    # mode; no probe transport is invoked by this safety-only function.
    monkeypatch.setenv("PROVIDER_FREE_ONLY_CHECKPOINT", "false")
    assert routing_safety_preflight()["marketdata.app account plan"] == (
        "routable: paid plan reviewed"
    )

    # Temporary trial access is not routable even when represented as free or
    # when paid routing is enabled. An expired trial is a different, explicitly
    # configured effective Free Forever entitlement.
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "10000")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", "2030-01-01T00:00:00+00:00")
    assert routing_safety_preflight()["marketdata.app account plan"].startswith(
        "non-routable: temporary trial"
    )
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", "2020-01-01T00:00:00+00:00")
    assert routing_safety_preflight()["marketdata.app account plan"].startswith(
        "routable: configured trial expired; effective quota automatically falls back"
    )


def test_live_preflight_control_aliases_resolve_to_reported_statuses():
    statuses = routing_safety_preflight()
    missing = {
        provider: [name for name in control_names if name not in statuses]
        for provider, control_names in _LIVE_SCRIPT.LIVE_PREFLIGHT_ROUTING_CONTROLS.items()
        if any(name not in statuses for name in control_names)
    }
    assert missing == {}


def test_live_credential_preflight_rejects_placeholder_sec_contact(monkeypatch):
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    assert setting_is_configured("EDGAR_USER_AGENT") is False
    monkeypatch.setenv("EDGAR_USER_AGENT", "charting-platform contact@example.com")
    assert setting_is_configured("EDGAR_USER_AGENT") is False
    monkeypatch.setenv("EDGAR_USER_AGENT", "charting-platform your.email@example.com")
    assert setting_is_configured("EDGAR_USER_AGENT") is False
    monkeypatch.setenv("EDGAR_USER_AGENT", "ChartingPlatform <real contact email>")
    assert setting_is_configured("EDGAR_USER_AGENT") is False
    monkeypatch.setenv("EDGAR_USER_AGENT", "charting-platform ops@example.invalid")
    assert setting_is_configured("EDGAR_USER_AGENT") is True


def test_live_preflight_requires_bounded_usage_scope(monkeypatch):
    monkeypatch.delenv("PROVIDER_LIVE_USAGE_SCOPE", raising=False)
    assert usage_scope_is_configured() is False
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "local-dev")
    assert usage_scope_is_configured() is True
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "x" * 129)
    assert usage_scope_is_configured() is False
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "local\nworktree")
    assert usage_scope_is_configured() is False


def test_fmp_byte_bound_preflight_covers_market_events_operation():
    assert "fetch_market_events" in _LIVE_SCRIPT.BYTE_BOUND_OPERATIONS["fmp"]


def test_live_runner_byte_bound_operation_sets_match_runtime_policy():
    for provider, operations in _LIVE_SCRIPT.BYTE_BOUND_OPERATIONS.items():
        assert tuple(operations) == provider_required_operation_byte_bounds(provider)


def test_live_runner_treats_provider_configuration_changes_as_provider_changes(monkeypatch):
    monkeypatch.delenv("FORCE_LIVE_PROVIDER_PROBES", raising=False)

    class _Status:
        returncode = 0

        def __init__(self, path: str):
            self.stdout = f" M {path}\n"

    for path in (
        "backend/app/config.py",
        "docs/data-providers.md",
        "docs/provider-live-validation.md",
        ".env.example",
        ".github/workflows/provider-live.yml",
    ):
        monkeypatch.setattr(
            _LIVE_SCRIPT.subprocess,
            "run",
            lambda *args, _path=path, **kwargs: _Status(_path),
        )
        assert _LIVE_SCRIPT.changed_provider_code() is True, path


def test_live_runner_can_select_only_manifest_cases_for_a_provider():
    bybit_arguments = _LIVE_SCRIPT.selected_live_test_arguments(["bybit_xstocks"])
    assert bybit_arguments[:-2] == [
        "tests/live/test_tokenized_providers_live.py::test_bybit_public_xstocks_asset_and_price",
        "tests/live/test_tokenized_providers_live.py::test_bybit_public_xstocks_cursor_page",
    ]
    assert bybit_arguments[-2] == "-k"
    assert set(bybit_arguments[-1].split(" or ")) == {
        "bybit_public_xstocks_asset_and_price",
        "bybit_public_xstocks_cursor_page",
        "bybit_xstocks",
    }
    arguments = _LIVE_SCRIPT.selected_live_test_arguments(["marketdata_app"])
    assert (
        "tests/live/test_market_data_providers_live.py::test_optional_credentialed_provider_small_read"
        in arguments
    )
    assert "marketdata_app" in arguments[-1]
    all_arguments = _LIVE_SCRIPT.selected_live_test_arguments(None)
    expected_nodes = list(
        dict.fromkeys(
            f"tests/live/{relative_path}::{function_name}"
            for provider in sorted(_LIVE_SCRIPT.LIVE_PROVIDER_CASES)
            for relative_path, function_name in _LIVE_SCRIPT.LIVE_PROVIDER_CASES[provider]
        )
    )
    expected_filter_terms = set(_LIVE_SCRIPT.LIVE_PROVIDER_CASES)
    expected_filter_terms.update(
        function_name.removeprefix("test_")
        for cases in _LIVE_SCRIPT.LIVE_PROVIDER_CASES.values()
        for _relative_path, function_name in cases
        if function_name != "test_optional_credentialed_provider_small_read"
    )
    assert all_arguments[:-2] == expected_nodes
    assert all_arguments[-2] == "-k"
    assert set(all_arguments[-1].split(" or ")) == expected_filter_terms


def test_massive_live_cases_preserve_quota_safe_manifest_order():
    arguments = _LIVE_SCRIPT.selected_live_test_arguments(["massive"])
    assert arguments[:-2] == [
        "tests/live/test_market_data_providers_live.py::test_massive_credentialed_reference",
        "tests/live/test_market_data_providers_live.py::test_massive_credentialed_corporate_actions_complete",
        "tests/live/test_market_data_providers_live.py::test_massive_credentialed_ipo_cursor_continuation",
        "tests/live/test_market_data_providers_live.py::test_massive_credentialed_otc_ticker_universe_pagination_is_complete",
    ]


def test_live_runner_uses_staging_merge_base_after_metadata_commit(monkeypatch):
    """A trailing workstream commit must not suppress provider probes."""

    monkeypatch.delenv("FORCE_LIVE_PROVIDER_PROBES", raising=False)
    monkeypatch.delenv("INTEGRATION_BASE_SHA", raising=False)

    class _Status:
        def __init__(self, *, stdout: str = "", returncode: int = 0):
            self.returncode = returncode
            self.stdout = stdout

    def fake_run(args, **kwargs):
        del kwargs
        if args[:2] == ["git", "status"]:
            return _Status()
        if args[:2] == ["git", "merge-base"]:
            return _Status(stdout="staging-base\n")
        if args[:2] == ["git", "diff"]:
            assert args == ["git", "diff", "--name-only", "staging-base..HEAD"]
            return _Status(stdout="backend/app/providers/alpaca.py\n")
        raise AssertionError(args)

    monkeypatch.setattr(_LIVE_SCRIPT.subprocess, "run", fake_run)

    assert _LIVE_SCRIPT.changed_provider_code() is True


def test_every_registered_provider_has_live_case_or_explicit_exclusion():
    """Keep the external acceptance matrix synchronized with the registry."""

    declared = set(_LIVE_SCRIPT.LIVE_PROVIDER_CASES) | set(_LIVE_SCRIPT.LIVE_PROVIDER_EXCLUSIONS)
    assert declared == set(_PROVIDERS), sorted(set(_PROVIDERS) - declared)
    assert not (set(_LIVE_SCRIPT.LIVE_PROVIDER_CASES) & set(_LIVE_SCRIPT.LIVE_PROVIDER_EXCLUSIONS))

    function_cache: dict[str, set[str]] = {}
    for provider, cases in _LIVE_SCRIPT.LIVE_PROVIDER_CASES.items():
        assert cases, provider
        for relative_path, function_name in cases:
            path = ROOT / "backend" / "tests" / "live" / relative_path
            assert path.is_file(), (provider, relative_path)
            functions = function_cache.setdefault(
                relative_path,
                {
                    node.name
                    for node in ast.walk(ast.parse(path.read_text()))
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                },
            )
            assert function_name in functions, (provider, relative_path, function_name)

    for provider, reason in _LIVE_SCRIPT.LIVE_PROVIDER_EXCLUSIONS.items():
        assert reason.strip(), provider


def test_external_provider_adapters_use_the_quota_guarded_httpx_transport():
    """Require a transport guard before an adapter can bypass live admission."""

    unguarded_network_modules = {
        "aiohttp",
        "ccxt",
        "curl_cffi",
        "httpcore",
        "http.client",
        "requests",
        "socket",
        "urllib.request",
        "urllib3",
        "websocket",
        "websockets",
    }
    source_roots = (
        ROOT / "backend" / "app" / "providers",
        ROOT / "backend" / "tests" / "live",
    )
    for source_root in source_roots:
        for path in sorted(source_root.rglob("*.py")):
            # yfinance remains an explicitly excluded legacy adapter and is
            # never selected by default or in the external acceptance matrix.
            if source_root.name == "providers" and path.name == "yfinance.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported_modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.add(node.module)
            unguarded = sorted(
                module
                for module in imported_modules
                if module in unguarded_network_modules
                or any(module.startswith(f"{blocked}.") for blocked in unguarded_network_modules)
            )
            assert not unguarded, (path.relative_to(ROOT), unguarded)
