from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.nautilus_runtime import NautilusRcCompatibilityRuntime


def _runtime() -> NautilusRcCompatibilityRuntime:
    return NautilusRcCompatibilityRuntime(
        source_digest=content_digest("nautilus-v2-rc5-source"),
        runtime_image_digest=content_digest("nautilus-v2-rc5-image"),
        python_version="3.12.11",
        rust_version="1.88.0",
    )


def test_rc_runtime_declaration_binds_exact_pin_and_non_authority() -> None:
    runtime = _runtime()

    assert runtime.package_version == NAUTILUS_V2_RC_PACKAGE_VERSION
    assert runtime.release_tag == NAUTILUS_V2_RC_RELEASE_TAG
    assert runtime.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE
    assert runtime.authoritative is False
    assert runtime.release_pin.package_version == runtime.package_version
    assert runtime.release_pin.fingerprint.startswith("sha256:")
    assert runtime.fingerprint.startswith("sha256:")


def test_rc_runtime_pin_produces_compatible_non_authoritative_evidence() -> None:
    runtime = _runtime()
    evidence = EngineConformanceEvidence(
        engine_id="nautilus",
        engine_version=runtime.package_version,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        release_channel=runtime.release_channel,
        fixture_digest=content_digest("nautilus-v2-rc5-fixture"),
        passed_checks=frozenset(ConformanceCheck),
        tested_at=datetime(2026, 10, 2, tzinfo=UTC),
        release_pin=runtime.release_pin,
    )

    report = evaluate_engine_conformance(evidence)

    assert report.compatible
    assert report.execution_eligible
    assert not report.authoritative


def test_rc_runtime_rejects_shared_legacy_environment() -> None:
    with pytest.raises(ValueError, match="isolated"):
        NautilusRcCompatibilityRuntime(
            source_digest=content_digest("nautilus-v2-rc5-source"),
            runtime_image_digest=content_digest("nautilus-v2-rc5-image"),
            python_version="3.12.11",
            rust_version="1.88.0",
            legacy_runtime_isolated=False,
        )
