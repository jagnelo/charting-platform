from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_mounts_the_same_read_only_rc_evidence_for_api_and_preparation() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text())
    services = compose["services"]
    backend = services["backend"]
    preparation = services["strategy-lab-v2-preparation"]
    worker = services["strategy-lab-v2-worker"]
    source = (
        "${STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_HOST_DIRECTORY:-"
        "./.ai/runtime/strategy-lab-v2/nautilus-rc-evidence}"
    )
    expected_evidence_environment = {
        "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_ARTIFACT_SHA256": (
            "${STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_ARTIFACT_SHA256:-}"
        ),
        "STRATEGY_LAB_V2_NAUTILUS_RC_SOURCE_SHA256": (
            "${STRATEGY_LAB_V2_NAUTILUS_RC_SOURCE_SHA256:-}"
        ),
        "STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256": (
            "${STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256:-}"
        ),
    }

    assert backend["environment"]["STRATEGY_LAB_V2_BACKTEST_CAPABILITY_SCOPE"] == (
        "${STRATEGY_LAB_V2_BACKTEST_CAPABILITY_SCOPE:-}"
    )
    assert backend["environment"]["STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_DIRECTORY"] == (
        "/nautilus-rc-evidence"
    )
    assert preparation["environment"]["STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_DIRECTORY"] == (
        "/nautilus-rc-evidence"
    )
    for name, value in expected_evidence_environment.items():
        assert backend["environment"][name] == value
        assert preparation["environment"][name] == value

    for service in (backend, preparation):
        evidence_mount = next(
            mount
            for mount in service["volumes"]
            if isinstance(mount, dict) and mount.get("target") == "/nautilus-rc-evidence"
        )
        assert evidence_mount["type"] == "bind"
        assert evidence_mount["source"] == source
        assert evidence_mount["read_only"] is True
    assert (
        preparation["environment"]["STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256"]
        == (backend["environment"]["STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256"])
    )

    assert all(
        not (isinstance(mount, dict) and mount.get("target") == "/nautilus-rc-evidence")
        for mount in worker["volumes"]
    )
    assert not any("NAUTILUS_RC_EVIDENCE" in name for name in worker["environment"])


def test_examples_keep_capability_scope_and_runtime_pins_disabled_by_default() -> None:
    root = Path(__file__).resolve().parents[4]
    for relative in (".env.example", "backend/.env.example"):
        text = (root / relative).read_text()
        for name in (
            "STRATEGY_LAB_V2_BACKTEST_CAPABILITY_SCOPE",
            "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_ARTIFACT_SHA256",
            "STRATEGY_LAB_V2_NAUTILUS_RC_SOURCE_SHA256",
            "STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256",
        ):
            assert f"{name}=" in text
        assert "STRATEGY_LAB_V2_BACKTEST_CAPABILITY_SCOPE=" in text
    backend_example = (root / "backend/.env.example").read_text()
    assert "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_DIRECTORY=" in backend_example
    assert "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_HOST_DIRECTORY=" in backend_example
