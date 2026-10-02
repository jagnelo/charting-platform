from __future__ import annotations

from pathlib import Path


def test_compose_declares_separate_fail_closed_forward_worker_service() -> None:
    compose = Path(__file__).resolve().parents[4].joinpath("docker-compose.yml").read_text()

    service_start = compose.index("  strategy-lab-v2-forward-worker:")
    service_end = compose.index("  # User code never runs", service_start)
    service = compose[service_start:service_end]

    assert 'profiles: ["strategy-lab-v2"]' in service
    assert "python -m app.strategy_lab_v2.forward_worker_entrypoint" in service
    assert "STRATEGY_LAB_V2_FORWARD_CALLBACK_FACTORY:" in service
    assert "${STRATEGY_LAB_V2_FORWARD_CALLBACK_FACTORY:-}" in service
    assert "read_only: true" in service
    assert 'cap_drop: ["ALL"]' in service
    assert "no-new-privileges:true" in service
    assert "STRATEGY_LAB_V2_FORWARD_DATABASE_URL_SYNC:" in service
    assert "\n      DATABASE_URL_SYNC:" not in service
    assert "/var/run/docker.sock" not in service
    assert "strategy_lab_artifacts:/strategy-lab-artifacts" in service
    assert "postgres:" in service and "redis:" in service
