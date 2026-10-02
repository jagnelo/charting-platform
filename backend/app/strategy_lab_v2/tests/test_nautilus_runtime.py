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
from app.strategy_lab_v2.nautilus_runtime import (
    NautilusRcCompatibilityRuntime,
    NautilusRuntimeProbeEvidence,
)


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


def test_probe_evidence_binds_exact_runtime_and_is_non_authoritative() -> None:
    runtime = _runtime()
    evidence = NautilusRuntimeProbeEvidence.from_mapping(
        {
            "engine_lifecycle": "passed",
            "implementation": "cpython",
            "nautilus_package_version": "2.0.0rc5",
            "platform": "Linux-x86_64",
            "python_version": "3.12.11",
        },
        runtime,
    )

    assert evidence.runtime_fingerprint == runtime.fingerprint
    assert evidence.runtime_image_digest == runtime.runtime_image_digest
    assert evidence.authoritative is False
    assert evidence.fingerprint == content_digest(evidence)


def test_probe_evidence_rejects_schema_version_and_runtime_mismatches() -> None:
    runtime = _runtime()
    payload = {
        "engine_lifecycle": "passed",
        "implementation": "cpython",
        "nautilus_package_version": "2.0.0rc5",
        "platform": "Linux-x86_64",
        "python_version": "3.12.11",
    }
    with pytest.raises(ValueError, match="exact runtime schema"):
        NautilusRuntimeProbeEvidence.from_mapping({**payload, "unexpected": "x"}, runtime)
    with pytest.raises(ValueError, match="package version"):
        NautilusRuntimeProbeEvidence.from_mapping(
            {**payload, "nautilus_package_version": "2.0.0rc4"}, runtime
        )
    with pytest.raises(ValueError, match="Python version"):
        NautilusRuntimeProbeEvidence.from_mapping({**payload, "python_version": "3.13.0"}, runtime)
    with pytest.raises(ValueError, match="lifecycle"):
        NautilusRuntimeProbeEvidence.from_mapping(
            {**payload, "engine_lifecycle": "failed"}, runtime
        )
