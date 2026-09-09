import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

_LIVE_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "provider_live_probe_script", ROOT / "scripts/run-live-provider-probes.py"
)
assert _LIVE_SCRIPT_SPEC and _LIVE_SCRIPT_SPEC.loader
_LIVE_SCRIPT = importlib.util.module_from_spec(_LIVE_SCRIPT_SPEC)
_LIVE_SCRIPT_SPEC.loader.exec_module(_LIVE_SCRIPT)
routing_safety_preflight = _LIVE_SCRIPT.routing_safety_preflight
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
}
PROVIDER_SAFETY_SETTINGS = {
    "FINRA_ASYNC_MAX_RESULT_BYTES",
    "TIINGO_OPERATION_BYTE_BOUNDS",
    "FMP_OPERATION_BYTE_BOUNDS",
}
PROVIDER_CONFIGURATION_SETTINGS = {
    "FINRA_OTC_SYMBOL_DIRECTORY_URL",
    "MARKETSTACK_DISCOVERY_EXCHANGE",
}
TOKENIZED_REFRESH_SETTINGS = {
    "TOKENIZED_ASSET_REFRESH_ENABLED",
    "TOKENIZED_ASSET_REFRESH_MAX_ASSETS",
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


def test_live_workflow_is_manual_environment_scoped_and_maps_each_secret():
    workflow = (ROOT / ".github/workflows/provider-live.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "environment: provider-live-validation" in workflow
    assert "pull_request_target" not in workflow
    assert "schedule:" not in workflow
    for name in PROVIDER_SECRET_NAMES:
        assert f"{name}: ${{{{ secrets.{name} }}}}" in workflow
    for name in PROVIDER_SAFETY_SETTINGS:
        assert f"{name}:" in workflow
    assert "FINRA_ASYNC_MAX_RESULT_BYTES: ${{ vars.FINRA_ASYNC_MAX_RESULT_BYTES || '0' }}" in workflow
    assert "TIINGO_OPERATION_BYTE_BOUNDS: ${{ vars.TIINGO_OPERATION_BYTE_BOUNDS || '{}' }}" in workflow
    assert "FMP_OPERATION_BYTE_BOUNDS: ${{ vars.FMP_OPERATION_BYTE_BOUNDS || '{}' }}" in workflow
    assert "MARKETSTACK_DISCOVERY_EXCHANGE: ${{ vars.MARKETSTACK_DISCOVERY_EXCHANGE || '' }}" in workflow


def test_backend_env_example_preserves_fail_closed_provider_safety_contract():
    example = (ROOT / "backend/.env.example").read_text()
    assert "FINRA_OTC_SYMBOL_DIRECTORY_URL=" in example
    assert "FINRA_OTC_SYMBOL_DIRECTORY_URL=https://" not in example
    assert "FINRA_ASYNC_MAX_RESULT_BYTES=0" in example
    assert "TIINGO_OPERATION_BYTE_BOUNDS={}" in example
    assert "FMP_OPERATION_BYTE_BOUNDS={}" in example
    for name in ("IBKR_READ_ONLY_URL", "COINBASE_API_KEY", "KRAKEN_API_KEY"):
        assert f"{name}=" in example


def test_live_preflight_reports_non_routable_safety_controls_without_guessing(monkeypatch):
    monkeypatch.setenv("FINRA_ASYNC_MAX_RESULT_BYTES", "0")
    monkeypatch.setenv("TIINGO_OPERATION_BYTE_BOUNDS", "{}")
    monkeypatch.setenv("FMP_OPERATION_BYTE_BOUNDS", "not-json")
    statuses = routing_safety_preflight()
    assert statuses["finra async result bytes"].startswith("non-routable:")
    assert statuses["fred"].startswith("non-routable:")
    assert statuses["nasdaq"].startswith("non-routable:")
    assert statuses["xstocks"].startswith("non-routable:")
    assert statuses["bybit_xstocks"].startswith("non-routable:")
    assert statuses["marketstack discovery"] == "non-routable: MARKETSTACK_DISCOVERY_EXCHANGE is unset"
    assert statuses["tiingo"].startswith("non-routable:")
    assert statuses["fmp"] == "non-routable: FMP_OPERATION_BYTE_BOUNDS is not valid JSON"

    monkeypatch.setenv(
        "TIINGO_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "search_instruments": 1, "get_instrument_profile": 1}',
    )
    monkeypatch.setenv(
        "FMP_OPERATION_BYTE_BOUNDS",
        '{"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1, "get_instrument_profile": 1, "discover_universe_page": 1}',
    )
    statuses = routing_safety_preflight()
    assert statuses["tiingo"] == "routable"
    assert statuses["fmp"] == "routable"

    monkeypatch.setenv("MARKETSTACK_DISCOVERY_EXCHANGE", "XNAS")
    statuses = routing_safety_preflight()
    assert statuses["marketstack discovery"] == "routable"
