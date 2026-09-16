from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.conformance_fixtures import (
    ConformanceFixtureObservation,
    ConformanceFixtureSuite,
    build_conformance_evidence,
    require_complete_conformance_suite,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _suite(*, failed: ConformanceCheck | None = None) -> ConformanceFixtureSuite:
    observations = []
    for check in ConformanceCheck:
        expected = content_digest({"check": check.value, "expected": True})
        observed = expected if check is not failed else content_digest({"check": check.value, "observed": False})
        observations.append(
            ConformanceFixtureObservation(
                check, expected, observed, check is not failed, "fixture evidence"
            )
        )
    return ConformanceFixtureSuite("nautilus-v2-suite", tuple(observations))


def test_complete_suite_builds_evidence_and_authoritative_report_when_stable() -> None:
    suite = _suite()
    require_complete_conformance_suite(suite)
    evidence = build_conformance_evidence(
        "nautilus", "2.0.0", content_digest("build"),
        EngineReleaseChannel.STABLE, suite, tested_at=NOW,
    )
    report = evaluate_engine_conformance(evidence)
    assert report.authoritative is True
    assert report.missing_checks == frozenset()
    assert evidence.fixture_digest == suite.fingerprint


def test_failed_fixture_is_compatible_evidence_but_not_a_pass() -> None:
    suite = _suite(failed=ConformanceCheck.NATIVE_ORDER_FILL_COST)
    evidence = build_conformance_evidence(
        "nautilus", "2.0.0-rc1", content_digest("build"),
        EngineReleaseChannel.RELEASE_CANDIDATE, suite, tested_at=NOW,
    )
    report = evaluate_engine_conformance(evidence)
    assert report.authoritative is False
    assert report.compatible is False
    assert ConformanceCheck.NATIVE_ORDER_FILL_COST in report.missing_checks


def test_incomplete_suite_fails_closed_before_evidence_creation() -> None:
    suite = ConformanceFixtureSuite(
        "partial",
        (ConformanceFixtureObservation(
            ConformanceCheck.DETERMINISTIC_REPLAY,
            content_digest("expected"), content_digest("expected"), True,
        ),),
    )
    with pytest.raises(ValueError, match="incomplete"):
        require_complete_conformance_suite(suite)


def test_fixture_observation_rejects_untruthful_pass_claims() -> None:
    with pytest.raises(ValueError, match="matching"):
        ConformanceFixtureObservation(
            ConformanceCheck.ENGINE_LIFECYCLE,
            content_digest("expected"), content_digest("observed"), True,
        )
    with pytest.raises(ValueError, match="differing"):
        ConformanceFixtureObservation(
            ConformanceCheck.ENGINE_LIFECYCLE,
            content_digest("same"), content_digest("same"), False,
        )


def test_suite_order_and_identity_are_deterministic() -> None:
    first = _suite()
    second = ConformanceFixtureSuite("nautilus-v2-suite", tuple(reversed(first.observations)))
    assert first == second
    assert first.fingerprint == second.fingerprint
    assert tuple(item.check.value for item in first.observations) == tuple(
        sorted(item.check.value for item in first.observations)
    )


def test_invalid_types_and_timestamp_fail_closed() -> None:
    with pytest.raises(TypeError, match="suite"):
        build_conformance_evidence("nautilus", "2", content_digest("build"), EngineReleaseChannel.STABLE, "bad", tested_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        build_conformance_evidence("nautilus", "2", content_digest("build"), EngineReleaseChannel.STABLE, _suite(), tested_at=datetime(2024, 1, 1))

