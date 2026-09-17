from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
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
    return EngineConformanceEvidence(
        engine_id="nautilus",
        engine_version="2.0.0",
        build_digest=BUILD,
        release_channel=channel,
        fixture_digest=FIXTURE,
        passed_checks=checks,
        tested_at=NOW,
        release_pin=PIN,
    )


def test_complete_stable_conformance_is_authoritative() -> None:
    report = evaluate_engine_conformance(_evidence())
    assert report.decision is ConformanceDecision.PASS
    assert report.compatible
    assert report.authoritative
    assert not report.missing_checks
    assert report.fingerprint.startswith("sha256:")


def test_release_candidate_can_be_compatible_but_never_authoritative() -> None:
    report = evaluate_engine_conformance(
        _evidence(channel=EngineReleaseChannel.RELEASE_CANDIDATE)
    )
    assert report.compatible
    assert not report.authoritative
    assert report.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE


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


def test_stable_authority_requires_an_isolated_v2_release_pin() -> None:
    missing = evaluate_engine_conformance(
        EngineConformanceEvidence(
            "nautilus", "2.0.0", BUILD, EngineReleaseChannel.STABLE,
            FIXTURE, frozenset(ConformanceCheck), NOW,
        )
    )
    assert missing.compatible
    assert not missing.authoritative
    assert not missing.release_pin_valid

    shared = evaluate_engine_conformance(
        EngineConformanceEvidence(
            "nautilus", "2.0.0", BUILD, EngineReleaseChannel.STABLE,
            FIXTURE, frozenset(ConformanceCheck), NOW,
            replace(PIN, legacy_runtime_isolated=False),
        )
    )
    assert not shared.authoritative
    assert not shared.release_pin_valid

    prerelease_pin = replace(PIN, release_tag="v2.0.0-rc5")
    prerelease = evaluate_engine_conformance(
        EngineConformanceEvidence(
            "nautilus", "2.0.0", BUILD, EngineReleaseChannel.STABLE,
            FIXTURE, frozenset(ConformanceCheck), NOW, prerelease_pin,
        )
    )
    assert not prerelease.authoritative
    assert not prerelease.release_pin_valid


def test_release_pin_rejects_non_v2_and_engine_version_drift() -> None:
    with pytest.raises(ValueError, match="target v2"):
        replace(PIN, package_version="1.231.0")
    with pytest.raises(ValueError, match="match engine_version"):
        EngineConformanceEvidence(
            "nautilus", "2.0.1", BUILD, EngineReleaseChannel.STABLE,
            FIXTURE, frozenset(ConformanceCheck), NOW, PIN,
        )
