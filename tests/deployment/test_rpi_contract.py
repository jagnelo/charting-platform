import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "rpi_deployment_helper", ROOT / "scripts" / "rpi.py"
)
assert _SPEC and _SPEC.loader
rpi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rpi)


def test_bundle_contains_pinned_runtime_defaults():
    postgres, redis = rpi.runtime_images({})
    assert postgres.startswith("postgres:16-alpine@sha256:")
    assert redis.startswith("redis:7-alpine@sha256:")


def test_deployment_script_is_project_scoped_and_no_pull_or_build_on_pi():
    source = (ROOT / "scripts" / "rpi.py").read_text()
    assert "docker system prune" not in source
    assert "docker compose -p charting-platform" in source
    assert "--no-build --pull never --wait" in source
    assert "docker build" not in source.split("def _deploy", 1)[1]
    assert "websocket_ping(host" in source
    assert "research_smoke(base, headers" in source
    assert "_write_deployment_attempt" in source
    assert 'status="failed"' in source
    assert "exec -T postgres pg_restore --list" in source
    assert "docker run --rm -i" not in source.split("def _deploy", 1)[1]


def test_release_compose_passes_provider_monitoring_configuration():
    compose = (ROOT / "deploy" / "rpi" / "compose.yml").read_text()
    assert "PROVIDER_AVAILABILITY_MONITOR_ENABLED" in compose
    assert "PROVIDER_AVAILABILITY_LIVE_ENABLED" in compose
    assert "PROVIDER_AVAILABILITY_NOTIFICATION_COOLDOWN_SECONDS" in compose
    assert "PROVIDER_AVAILABILITY_PROBE_TIMEOUT_SECONDS" in compose
    assert '"http://127.0.0.1/health"' in compose


def test_rpi_release_enables_daily_nms_otc_reconciliation_by_default():
    release = (ROOT / "deploy" / "rpi" / "compose.yml").read_text()
    development = (ROOT / "docker-compose.yml").read_text()

    assert (
        release.count(
            "MARKET_UNIVERSE_RECONCILIATION_ENABLED: ${MARKET_UNIVERSE_RECONCILIATION_ENABLED:-true}"
        )
        == 2
    )
    assert (
        "MARKET_UNIVERSE_RECONCILIATION_ENABLED: ${MARKET_UNIVERSE_RECONCILIATION_ENABLED:-true}"
        in development
    )
    worker = (ROOT / "backend" / "app" / "workers" / "arq_worker.py").read_text()
    assert "cron(scheduled_market_universe_reconciliation, hour=21, minute=0)" in worker


def test_preflight_checks_stopped_project_collisions_and_requires_port_probe():
    source = (ROOT / "scripts" / "rpi.py").read_text()
    assert "docker ps -a --format" in source
    assert "command -v ss" in source
    assert "reserved-port preflight" in source
    assert "command -v flock" in source
    assert "flock -n 9" in source


def test_preflight_reports_provider_secret_names_without_reading_values(
    monkeypatch, capsys
):
    captured = {}

    def fake_remote(config, script):
        captured["script"] = script.decode()
        return "RPi preflight passed"

    monkeypatch.setattr(rpi, "remote", fake_remote)
    rpi.preflight(
        {
            "RPI_DEPLOY_ROOT": "/opt/charting-platform",
            "RPI_HTTP_PORT": "8080",
            "RPI_DOCKER_PLATFORM": "linux/arm64",
        }
    )

    remote_script = captured["script"]
    assert "provider_secret_names_present" in remote_script
    assert "provider_secret_names_absent" in remote_script
    assert "ALPACA_API_KEY" in remote_script
    assert "PROVIDER_QUOTA_LEDGER_DATABASE_URL" in remote_script
    assert 'grep -Eq "^$provider_secret_name=.+$" "$env_file"' in remote_script
    assert (
        "optional provider credential names present (values withheld)" in remote_script
    )
    assert "secret-value" not in remote_script
    subprocess.run(["sh", "-n"], input=remote_script, text=True, check=True)
    assert capsys.readouterr().out.strip() == "RPi preflight passed"


def test_release_metadata_is_uploaded_and_verified_as_temporary_parts():
    source = (ROOT / "scripts" / "rpi.py").read_text()
    assert "manifest_bundle_sha" in source
    assert "manifest_compose_sha" in source
    assert "remote_name}.part" in source
    assert 'mv "$root/incoming/$sha.manifest.json.part"' in source


def test_frontend_arm64_image_builds_static_assets_on_native_builder():
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()
    assert "FROM --platform=$BUILDPLATFORM node:20-alpine AS build" in dockerfile
    assert "FROM --platform=$TARGETPLATFORM nginx:alpine" in dockerfile
