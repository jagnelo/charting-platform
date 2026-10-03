from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
    ConformanceCheck,
    ConformanceDecision,
    EngineConformanceEvidence,
    EngineConformanceReport,
    EngineReleaseChannel,
    NautilusReleasePin,
    evaluate_engine_conformance,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
BUILD = content_digest({"engine": "nautilus", "build": "v2"})
FIXTURE = content_digest({"fixture": "portfolio-event-tape"})
PIN = NautilusReleasePin(
    package_version="2.0.0",
    release_tag="v2.0.0",
    source_digest=content_digest("nautilus-source-v2.0.0"),
    wheel_digest=content_digest("nautilus-wheel-v2.0.0"),
    runtime_image_digest=content_digest("nautilus-runtime-v2.0.0"),
    python_version="3.12.11",
    rust_version="1.88.0",
    legacy_runtime_isolated=True,
)


def _evidence(
    *,
    channel: EngineReleaseChannel = EngineReleaseChannel.STABLE,
    checks: frozenset[ConformanceCheck] = frozenset(ConformanceCheck),
) -> EngineConformanceEvidence:
    version = (
        "2.0.0"
        if channel is EngineReleaseChannel.STABLE
        else NAUTILUS_V2_RC_PACKAGE_VERSION
        if channel is EngineReleaseChannel.RELEASE_CANDIDATE
        else "2.0.0.dev1"
    )
    release_tag = (
        "v2.0.0"
        if channel is EngineReleaseChannel.STABLE
        else NAUTILUS_V2_RC_RELEASE_TAG
        if channel is EngineReleaseChannel.RELEASE_CANDIDATE
        else "v2.0.0.dev1"
    )
    return EngineConformanceEvidence(
        engine_id="nautilus",
        engine_version=version,
        build_digest=BUILD,
        release_channel=channel,
        fixture_digest=FIXTURE,
        passed_checks=checks,
        tested_at=NOW,
        release_pin=replace(PIN, package_version=version, release_tag=release_tag),
    )


def test_complete_stable_conformance_is_authoritative() -> None:
    report = evaluate_engine_conformance(_evidence())
    assert report.decision is ConformanceDecision.PASS
    assert report.compatible
    assert report.authoritative
    assert not report.missing_checks
    assert report.fingerprint.startswith("sha256:")


def test_conformance_evidence_normalizes_offset_equivalent_test_times() -> None:
    offset_time = datetime(2024, 1, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    normalized = _evidence()
    equivalent = EngineConformanceEvidence(
        "nautilus",
        "2.0.0",
        BUILD,
        EngineReleaseChannel.STABLE,
        FIXTURE,
        frozenset(ConformanceCheck),
        offset_time,
        PIN,
    )
    assert equivalent == normalized
    assert equivalent.tested_at.tzinfo is UTC


def test_complete_release_candidate_conformance_can_be_authoritative() -> None:
    report = evaluate_engine_conformance(_evidence(channel=EngineReleaseChannel.RELEASE_CANDIDATE))
    assert report.compatible
    assert report.authoritative
    assert report.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE


def test_current_rc5_pin_can_qualify_only_with_all_conformance_checks() -> None:
    pin = replace(
        PIN,
        package_version=NAUTILUS_V2_RC_PACKAGE_VERSION,
        release_tag=NAUTILUS_V2_RC_RELEASE_TAG,
    )
    evidence = EngineConformanceEvidence(
        "nautilus",
        NAUTILUS_V2_RC_PACKAGE_VERSION,
        BUILD,
        EngineReleaseChannel.RELEASE_CANDIDATE,
        FIXTURE,
        frozenset(ConformanceCheck),
        NOW,
        pin,
    )
    report = evaluate_engine_conformance(evidence)
    assert report.compatible
    assert report.execution_eligible
    assert report.authoritative
    assert report.release_pin_valid

    partial_checks: frozenset[ConformanceCheck] = frozenset(
        check
        for check in ConformanceCheck
        if check is not ConformanceCheck.FORWARD_EVENT_TAPE_PARITY
    )
    partial = evaluate_engine_conformance(
        replace(
            evidence,
            passed_checks=partial_checks,
        )
    )
    assert not partial.compatible
    assert not partial.authoritative
    assert partial.missing_checks == frozenset({ConformanceCheck.FORWARD_EVENT_TAPE_PARITY})


def test_missing_conformance_checks_fail_closed() -> None:
    checks = frozenset(
        {
            ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING,
            ConformanceCheck.DETERMINISTIC_REPLAY,
        }
    )
    report = evaluate_engine_conformance(_evidence(checks=checks))
    assert report.decision is ConformanceDecision.FAIL
    assert not report.compatible
    assert not report.authoritative
    assert report.missing_checks == frozenset(ConformanceCheck) - checks


def test_conformance_contract_rejects_invalid_evidence_and_manual_authority() -> None:
    with pytest.raises(ValueError, match="build_digest"):
        EngineConformanceEvidence(
            "nautilus",
            "2.0.0",
            "bad",
            EngineReleaseChannel.STABLE,
            FIXTURE,
            frozenset(),
            NOW,
        )
    with pytest.raises(ValueError, match="authoritative"):
        EngineConformanceReport(
            evidence_fingerprint=_evidence().fingerprint,
            decision=ConformanceDecision.PASS,
            release_channel=EngineReleaseChannel.RELEASE_CANDIDATE,
            missing_checks=frozenset(),
            authoritative=True,
        )


def test_authority_requires_an_isolated_v2_release_pin_and_matching_channel() -> None:
    missing = evaluate_engine_conformance(
        EngineConformanceEvidence(
            "nautilus",
            "2.0.0",
            BUILD,
            EngineReleaseChannel.STABLE,
            FIXTURE,
            frozenset(ConformanceCheck),
            NOW,
        )
    )
    assert missing.compatible
    assert not missing.authoritative
    assert not missing.release_pin_valid

    shared = evaluate_engine_conformance(
        EngineConformanceEvidence(
            "nautilus",
            "2.0.0",
            BUILD,
            EngineReleaseChannel.STABLE,
            FIXTURE,
            frozenset(ConformanceCheck),
            NOW,
            replace(PIN, legacy_runtime_isolated=False),
        )
    )
    assert not shared.authoritative
    assert not shared.release_pin_valid

    prerelease_pin = replace(PIN, release_tag="v2.0.0rc5")
    prerelease = evaluate_engine_conformance(
        EngineConformanceEvidence(
            "nautilus",
            "2.0.0",
            BUILD,
            EngineReleaseChannel.STABLE,
            FIXTURE,
            frozenset(ConformanceCheck),
            NOW,
            prerelease_pin,
        )
    )
    assert not prerelease.authoritative
    assert not prerelease.release_pin_valid

    development = evaluate_engine_conformance(_evidence(channel=EngineReleaseChannel.DEVELOPMENT))
    assert development.compatible
    assert not development.authoritative
    assert development.release_pin_valid


def test_release_pin_rejects_non_v2_and_engine_version_drift() -> None:
    with pytest.raises(ValueError, match="target v2"):
        replace(PIN, package_version="1.231.0")
    with pytest.raises(ValueError, match="match engine_version"):
        EngineConformanceEvidence(
            "nautilus",
            "2.0.1",
            BUILD,
            EngineReleaseChannel.STABLE,
            FIXTURE,
            frozenset(ConformanceCheck),
            NOW,
            PIN,
        )
