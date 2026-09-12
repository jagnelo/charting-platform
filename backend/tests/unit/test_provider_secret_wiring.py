import importlib.util
import re
from pathlib import Path

from app.config import provider_required_operation_byte_bounds

ROOT = Path(__file__).resolve().parents[3]

_LIVE_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "provider_live_probe_script", ROOT / "scripts/run-live-provider-probes.py"
)
assert _LIVE_SCRIPT_SPEC and _LIVE_SCRIPT_SPEC.loader
_LIVE_SCRIPT = importlib.util.module_from_spec(_LIVE_SCRIPT_SPEC)
_LIVE_SCRIPT_SPEC.loader.exec_module(_LIVE_SCRIPT)
routing_safety_preflight = _LIVE_SCRIPT.routing_safety_preflight
setting_is_configured = _LIVE_SCRIPT.setting_is_configured
usage_scope_is_configured = _LIVE_SCRIPT.usage_scope_is_configured
PROVIDER_SECRET_NAMES = {
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "MASSIVE_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "COINGECKO_API_KEY",
    "FRED_API_KEY",
    "FINRA_CLIENT_ID",
    "FINRA_CLIENT_SECRET",
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
}
PROVIDER_SAFETY_SETTINGS = {
    "ALPACA_CORPORATE_ACTIONS_MAX_PAGES",
    "FINRA_ASYNC_MAX_RESULT_BYTES",
    "FINRA_OTC_OPERATION_COSTS",
    "FINRA_OTC_TERMS_REVIEWED",
    "FINRA_OTC_COMPLETENESS_REVIEWED",
    "FINRA_OTC_REDISTRIBUTION_REVIEWED",
    "FINRA_OTC_POLL_INTERVAL_SECONDS",
    "FRED_REVIEWED_LIMIT_SCOPE",
    "FRED_REVIEWED_REQUESTS_PER_MINUTE",
    "FRED_SERIES_TERMS_REVIEWED",
    "TIINGO_OPERATION_BYTE_BOUNDS",
    "FMP_OPERATION_BYTE_BOUNDS",
    "MARKETDATA_APP_REVIEWED_PLAN",
    "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
    "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS",
    "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE",
}
PROVIDER_CONFIGURATION_SETTINGS = {
    "ALPACA_DATA_FEED",
    "ALPACA_TRADING_BASE_URL",
    "FINRA_OTC_SYMBOL_DIRECTORY_URL",
    "MARKETSTACK_DISCOVERY_EXCHANGE",
    "IBKR_READ_ONLY_URL",
    "ALLOW_PAID_PROVIDER_ROUTING",
    "OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY",
}
TOKENIZED_REFRESH_SETTINGS = {
    "TOKENIZED_ASSET_REFRESH_ENABLED",
    "TOKENIZED_ASSET_REFRESH_MAX_ASSETS",
}
MARKET_OPERATION_SETTINGS = {
    "MARKET_DATA_REFRESH_SCHEDULE_ENABLED",
    "MARKET_DATA_SHADOW_REPORT_ENABLED",
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
        assert 'TOKENIZED_PROVIDER_PRIORITY:-["robinhood_tokens","xstocks","bybit_xstocks","gate_tradfi","kraken_xstocks","dinari","ondo_global_markets"]' in compose


def test_live_workflow_is_manual_environment_scoped_and_maps_each_secret():
    workflow = (ROOT / ".github/workflows/provider-live.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "environment: provider-live-validation" in workflow
    assert "pull_request_target" not in workflow
    assert "schedule:" not in workflow
    assert "PROVIDER_LIVE_USAGE_LEDGER: ${{ runner.temp }}/provider-live-usage.jsonl" in workflow
    assert "PROVIDER_LIVE_USAGE_SCOPE: github:${{ github.repository }}:${{ github.environment }}" in workflow
    assert "uses: actions/upload-artifact@v4" in workflow
    assert "name: provider-live-usage-${{ github.run_id }}" in workflow
    assert "if: always()" in workflow
    assert "retention-days: 90" in workflow
    assert "if-no-files-found: ignore" in workflow
    for name in PROVIDER_SECRET_NAMES:
        assert f"{name}: ${{{{ secrets.{name} }}}}" in workflow
    for name in PROVIDER_SAFETY_SETTINGS:
        assert f"{name}:" in workflow
    assert "ALPACA_TRADING_BASE_URL: ${{ vars.ALPACA_TRADING_BASE_URL || 'https://paper-api.alpaca.markets/v2' }}" in workflow
    assert "ALPACA_DATA_FEED: ${{ vars.ALPACA_DATA_FEED || 'iex' }}" in workflow
    assert "ALPACA_CORPORATE_ACTIONS_MAX_PAGES: ${{ vars.ALPACA_CORPORATE_ACTIONS_MAX_PAGES || '0' }}" in workflow
    assert "FINRA_ASYNC_MAX_RESULT_BYTES: ${{ vars.FINRA_ASYNC_MAX_RESULT_BYTES || '0' }}" in workflow
    assert "FRED_REVIEWED_LIMIT_SCOPE: ${{ vars.FRED_REVIEWED_LIMIT_SCOPE || '' }}" in workflow
    assert "FRED_REVIEWED_REQUESTS_PER_MINUTE: ${{ vars.FRED_REVIEWED_REQUESTS_PER_MINUTE || '0' }}" in workflow
    assert "FRED_SERIES_TERMS_REVIEWED: ${{ vars.FRED_SERIES_TERMS_REVIEWED || 'false' }}" in workflow
    assert "TIINGO_OPERATION_BYTE_BOUNDS: ${{ vars.TIINGO_OPERATION_BYTE_BOUNDS || '{}' }}" in workflow
    assert "FMP_OPERATION_BYTE_BOUNDS: ${{ vars.FMP_OPERATION_BYTE_BOUNDS || '{}' }}" in workflow
    assert "MARKETDATA_APP_REVIEWED_PLAN: ${{ vars.MARKETDATA_APP_REVIEWED_PLAN || '' }}" in workflow
    assert "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT: ${{ vars.MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT || '0' }}" in workflow
    assert "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS: ${{ vars.MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS || '0' }}" in workflow
    assert "MARKETSTACK_DISCOVERY_EXCHANGE: ${{ vars.MARKETSTACK_DISCOVERY_EXCHANGE || '' }}" in workflow


def test_backend_env_example_preserves_fail_closed_provider_safety_contract():
    example = (ROOT / "backend/.env.example").read_text()
    assert "FINRA_OTC_SYMBOL_DIRECTORY_URL=" in example
    assert "FINRA_OTC_SYMBOL_DIRECTORY_URL=https://" not in example
    assert "FINRA_ASYNC_MAX_RESULT_BYTES=0" in example
    assert "ALPACA_CORPORATE_ACTIONS_MAX_PAGES=0" in example
    assert "FRED_REVIEWED_LIMIT_SCOPE=" in example
    assert "FRED_REVIEWED_REQUESTS_PER_MINUTE=0" in example
    assert "FRED_SERIES_TERMS_REVIEWED=false" in example
    assert "TIINGO_OPERATION_BYTE_BOUNDS={}" in example
    assert "FMP_OPERATION_BYTE_BOUNDS={}" in example
    assert "MARKETDATA_APP_REVIEWED_PLAN=" in example
    assert "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT=0" in example
    assert "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS=0" in example
    assert "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE=disabled" in example
    for name in (
        "IBKR_READ_ONLY_URL",
        "COINBASE_API_KEY",
        "KRAKEN_API_KEY",
        "DINARI_API_BASE_URL",
    ):
        assert f"{name}=" in example
    assert 'TOKENIZED_PROVIDER_PRIORITY=["robinhood_tokens","xstocks","bybit_xstocks","gate_tradfi","kraken_xstocks","dinari","ondo_global_markets"]' in example
    for name in (
        PROVIDER_CONFIGURATION_SETTINGS
        | PROVIDER_OPERATION_SETTINGS
        | RUNTIME_COORDINATION_SETTINGS
    ):
        assert f"{name}=" in example


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


def test_live_preflight_reports_non_routable_safety_controls_without_guessing(monkeypatch):
    monkeypatch.setenv("ALPACA_CORPORATE_ACTIONS_MAX_PAGES", "0")
    monkeypatch.setenv("FINRA_ASYNC_MAX_RESULT_BYTES", "0")
    monkeypatch.setenv("FRED_REVIEWED_LIMIT_SCOPE", "")
    monkeypatch.setenv("FRED_REVIEWED_REQUESTS_PER_MINUTE", "0")
    monkeypatch.setenv("FRED_SERIES_TERMS_REVIEWED", "false")
    monkeypatch.setenv("TIINGO_OPERATION_BYTE_BOUNDS", "{}")
    monkeypatch.setenv("FMP_OPERATION_BYTE_BOUNDS", "not-json")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN", "")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "0")
    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "0")
    statuses = routing_safety_preflight()
    assert statuses["finra async result bytes"].startswith("non-routable:")
    assert statuses["alpaca corporate actions"].startswith("non-routable:")
    assert statuses["finra otc directory"].startswith("non-routable:")
    assert statuses["fred"].startswith("non-routable:")
    assert statuses["nasdaq"].startswith("non-routable:")
    assert statuses["xstocks"].startswith("non-routable:")
    assert statuses["bybit_xstocks"].startswith("non-routable:")
    assert statuses["marketstack discovery"] == "non-routable: MARKETSTACK_DISCOVERY_EXCHANGE is unset"
    assert statuses["tiingo"].startswith("non-routable:")
    assert statuses["fmp"] == "non-routable: FMP_OPERATION_BYTE_BOUNDS is not valid JSON"
    assert statuses["marketdata.app account plan"] == "non-routable: explicit reviewed plan/limit pair required"
    assert statuses["marketdata.app option chain"].startswith("non-routable:")

    monkeypatch.setenv("FRED_REVIEWED_LIMIT_SCOPE", "api_key")
    monkeypatch.setenv("FRED_REVIEWED_REQUESTS_PER_MINUTE", "60")
    monkeypatch.setenv("FRED_SERIES_TERMS_REVIEWED", "true")
    statuses = routing_safety_preflight()
    assert statuses["fred"] == "routable"

    monkeypatch.setenv("ALPACA_CORPORATE_ACTIONS_MAX_PAGES", "4")
    statuses = routing_safety_preflight()
    assert statuses["alpaca corporate actions"] == "routable"

    monkeypatch.setenv(
        "FINRA_OTC_OPERATION_COSTS",
        '{"discover_universe_page": 3, "reconcile_universe_page": 3}',
    )
    monkeypatch.setenv("FINRA_OTC_TERMS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_COMPLETENESS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_REDISTRIBUTION_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "900")
    statuses = routing_safety_preflight()
    assert statuses["finra otc directory"] == "routable"

    monkeypatch.setenv(
        "TIINGO_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "get_current_price": 1, "bulk_fetch": 1, "search_instruments": 1, "get_instrument_profile": 1}',
    )
    monkeypatch.setenv(
        "FMP_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "get_current_price": 1, "bulk_fetch": 1, "get_instrument_profile": 1, "fetch_market_events": 1, "discover_universe_page": 1}',
    )
    statuses = routing_safety_preflight()
    assert statuses["tiingo"] == "routable"
    assert statuses["fmp"] == "routable"

    monkeypatch.setenv(
        "TIINGO_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "get_current_price": true, "bulk_fetch": 1, "search_instruments": 1, "get_instrument_profile": 1}',
    )
    statuses = routing_safety_preflight()
    assert statuses["tiingo"].startswith("non-routable: missing positive bounds")

    monkeypatch.setenv("MARKETSTACK_DISCOVERY_EXCHANGE", "XNAS")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setenv("MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", "10000")
    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "25")
    statuses = routing_safety_preflight()
    assert statuses["marketstack discovery"] == "routable"
    assert statuses["marketdata.app account plan"] == "routable"
    assert statuses["marketdata.app option chain"] == "routable"

    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "1")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app option chain"].startswith("non-routable:")

    monkeypatch.setenv("MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", "not-an-integer")
    statuses = routing_safety_preflight()
    assert statuses["marketdata.app option chain"].startswith("non-routable:")


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
        stdout = " M backend/app/config.py\n"

    monkeypatch.setattr(_LIVE_SCRIPT.subprocess, "run", lambda *args, **kwargs: _Status())

    assert _LIVE_SCRIPT.changed_provider_code() is True
