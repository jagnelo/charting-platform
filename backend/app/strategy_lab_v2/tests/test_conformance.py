from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    ConformanceDecision,
    EngineConformanceEvidence,
    EngineConformanceReport,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
BUILD = content_digest({"engine": "nautilus", "build": "v2"})
FIXTURE = content_digest({"fixture": "portfolio-event-tape"})


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
