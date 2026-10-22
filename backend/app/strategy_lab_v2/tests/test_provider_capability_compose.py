from __future__ import annotations

import re
from pathlib import Path


def _service_section(compose_text: str, service_name: str) -> str:
    service_line = re.compile(r"(?m)^  [A-Za-z0-9_-]+:\s*$")
    start = next(
        match.start()
        for match in service_line.finditer(compose_text)
        if match.group().strip() == f"{service_name}:"
    )
    following = next(
        (match.start() for match in service_line.finditer(compose_text, start + 1)),
        len(compose_text),
    )
    return compose_text[start:following]


def test_compose_mounts_the_same_read_only_rc_evidence_for_api_and_preparation() -> None:
    root = Path(__file__).resolve().parents[4]
    compose_text = (root / "docker-compose.yml").read_text()
    backend = _service_section(compose_text, "backend")
    preparation = _service_section(compose_text, "strategy-lab-v2-preparation")
    worker = _service_section(compose_text, "strategy-lab-v2-worker")
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

    assert (
        "STRATEGY_LAB_V2_BACKTEST_CAPABILITY_SCOPE: "
        "${STRATEGY_LAB_V2_BACKTEST_CAPABILITY_SCOPE:-}"
    ) in backend
    for section in (backend, preparation):
        assert "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_DIRECTORY: /nautilus-rc-evidence" in section
    for name, value in expected_evidence_environment.items():
        assert f"{name}: {value}" in backend
        assert f"{name}: {value}" in preparation

    mount_source = (
        "source: ${STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_HOST_DIRECTORY:-"
        "./.ai/runtime/strategy-lab-v2/nautilus-rc-evidence}"
    )
    for section in (backend, preparation):
        assert section.count(mount_source) == 1
        assert "target: /nautilus-rc-evidence\n        read_only: true" in section

    assert "NAUTILUS_RC_EVIDENCE" not in worker


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
