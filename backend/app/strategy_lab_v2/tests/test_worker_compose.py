from __future__ import annotations

from pathlib import Path


def test_compose_declares_isolated_backtest_worker_boundary() -> None:
    compose = Path(__file__).resolve().parents[4].joinpath("docker-compose.yml").read_text()

    service_start = compose.index("  strategy-lab-v2-worker:")
    service_end = compose.index("  # ── Strategy Lab v2 forward-event worker", service_start)
    service = compose[service_start:service_end]

    assert 'profiles: ["strategy-lab-v2"]' in service
    assert "python -m app.strategy_lab_v2.worker_entrypoint" in service
    assert "STRATEGY_LAB_V2_DATABASE_URL_SYNC:" in service
    assert "\n      DATABASE_URL_SYNC:" not in service
    assert "STRATEGY_LAB_V2_CALLBACK_FACTORY:" in service
    assert "STRATEGY_LAB_V2_EVIDENCE_RESOLVER:" in service
    assert "read_only: true" in service
    assert 'cap_drop: ["ALL"]' in service
    assert "no-new-privileges:true" in service
    assert "strategy_lab_artifacts:/strategy-lab-artifacts" in service
    assert "target: /var/run/docker.sock" in service
    assert "postgres:" in service and "redis:" in service
    # Compose --scale requires anonymous service containers and no host-port
    # collision. Each replica inherits the same Redis group but must derive its
    # own consumer name from Compose's per-container HOSTNAME.
    assert "container_name:" not in service
    assert "\n    ports:" not in service
    assert "STRATEGY_LAB_V2_GROUP:" in service
    assert "STRATEGY_LAB_V2_CONSUMER_NAME:" not in service
