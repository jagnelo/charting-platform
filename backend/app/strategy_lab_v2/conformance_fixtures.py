"""Evidence-bound conformance fixture observations for the engine gate."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineConformanceReport,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ConformanceFixtureObservation:
    """One fixture's expected/observed digest comparison."""

    check: ConformanceCheck
    expected_digest: str
    observed_digest: str
    passed: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.check, ConformanceCheck):
            raise TypeError("check must be a ConformanceCheck")
        require_sha256_digest(self.expected_digest, field_name="expected_digest")
        require_sha256_digest(self.observed_digest, field_name="observed_digest")
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be a bool")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string")
        if self.passed and self.expected_digest != self.observed_digest:
            raise ValueError("passed fixtures require matching expected and observed digests")
        if not self.passed and self.expected_digest == self.observed_digest:
            raise ValueError("failed fixtures require differing expected and observed digests")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ConformanceFixtureSuite:
    """Complete, uniquely keyed fixture observations for one engine build."""

    suite_id: str
    observations: tuple[ConformanceFixtureObservation, ...]

    def __post_init__(self) -> None:
        _nonempty(self.suite_id, "suite_id")
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be a tuple")
        if not self.observations:
            raise ValueError("conformance fixture suite requires observations")
        if any(not isinstance(item, ConformanceFixtureObservation) for item in self.observations):
            raise TypeError("observations must contain ConformanceFixtureObservation values")
        checks = [item.check for item in self.observations]
        if len(set(checks)) != len(checks):
            raise ValueError("conformance fixture checks must be unique")
        object.__setattr__(
            self,
            "observations",
            tuple(sorted(self.observations, key=lambda item: item.check.value)),
        )

    @property
    def passed_checks(self) -> frozenset[ConformanceCheck]:
        return frozenset(item.check for item in self.observations if item.passed)

    @property
    def missing_checks(self) -> frozenset[ConformanceCheck]:
        required: frozenset[ConformanceCheck] = frozenset(ConformanceCheck)
        return required - self.passed_checks

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ConformanceExecutionResolution:
    """Evidence and gated report produced by one executable fixture run."""

    suite: ConformanceFixtureSuite
    evidence: EngineConformanceEvidence
    report: EngineConformanceReport

    def __post_init__(self) -> None:
        if not isinstance(self.suite, ConformanceFixtureSuite):
            raise TypeError("suite must be a ConformanceFixtureSuite")
        if not isinstance(self.evidence, EngineConformanceEvidence):
            raise TypeError("evidence must be an EngineConformanceEvidence")
        if not isinstance(self.report, EngineConformanceReport):
            raise TypeError("report must be an EngineConformanceReport")
        if self.evidence.fixture_digest != self.suite.fingerprint:
            raise ValueError("evidence must reference the executed fixture suite")
        if self.report.evidence_fingerprint != self.evidence.fingerprint:
            raise ValueError("report must reference the executed fixture evidence")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def execute_conformance_suite(
    expected_digests: Mapping[ConformanceCheck, str],
    runner: Callable[[ConformanceCheck], Any],
    *,
    suite_id: str,
    engine_id: str,
    engine_version: str,
    build_digest: str,
    release_channel: EngineReleaseChannel,
    tested_at: datetime,
) -> ConformanceExecutionResolution:
    """Run every required fixture through an injected engine boundary.

    The runner returns the JSON-shaped fixture observation, never an engine
    handle.  Exceptions become deterministic failed observations keyed only by
    exception type; missing or extra expected checks fail closed before the
    engine is invoked.  Stable authority still comes only from
    :func:`evaluate_engine_conformance` and a complete suite.
    """

    if not isinstance(expected_digests, Mapping):
        raise TypeError("expected_digests must be a mapping")
    if not callable(runner):
        raise TypeError("runner must be callable")
    all_checks: tuple[ConformanceCheck, ...] = tuple(cast(Any, ConformanceCheck))
    required: frozenset[ConformanceCheck] = frozenset(all_checks)
    raw_keys = tuple(expected_digests.keys())
    if any(not isinstance(key, ConformanceCheck) for key in raw_keys):
        raise TypeError("expected conformance checks must be ConformanceCheck values")
    keys: frozenset[ConformanceCheck] = frozenset(
        cast(tuple[ConformanceCheck, ...], raw_keys)
    )
    if keys != required:
        missing = sorted((required - keys), key=lambda item: item.value)
        extra = sorted((keys - required), key=lambda item: str(item))
        details = []
        if missing:
            details.append("missing=" + ",".join(item.value for item in missing))
        if extra:
            details.append("extra=" + ",".join(str(item) for item in extra))
        raise ValueError("expected conformance checks must be exact: " + "; ".join(details))
    normalized_expected: dict[ConformanceCheck, str] = {}
    for check in all_checks:
        if not isinstance(expected_digests[check], str):
            raise TypeError("expected conformance digests must be strings")
        require_sha256_digest(expected_digests[check], field_name="expected_digest")
        normalized_expected[check] = expected_digests[check]
    observations: list[ConformanceFixtureObservation] = []
    for check in sorted(all_checks, key=lambda item: item.value):
        expected_digest = normalized_expected[check]
        try:
            observed_digest = content_digest(runner(check))
            passed = observed_digest == expected_digest
            detail = "fixture digest matched" if passed else "fixture digest differed"
        except Exception as error:  # pragma: no cover - exercised by focused tests
            observed_digest = content_digest(
                {"check": check.value, "error_type": type(error).__name__}
            )
            passed = False
            detail = f"runner failed: {type(error).__name__}"
        observations.append(
            ConformanceFixtureObservation(
                check,
                expected_digest,
                observed_digest,
                passed,
                detail,
            )
        )
    suite = ConformanceFixtureSuite(suite_id, tuple(observations))
    evidence = build_conformance_evidence(
        engine_id,
        engine_version,
        build_digest,
        release_channel,
        suite,
        tested_at=tested_at,
    )
    return ConformanceExecutionResolution(
        suite,
        evidence,
        evaluate_engine_conformance(evidence),
    )


def build_conformance_evidence(
    engine_id: str,
    engine_version: str,
    build_digest: str,
    release_channel: EngineReleaseChannel,
    suite: ConformanceFixtureSuite,
    *,
    tested_at: datetime,
) -> EngineConformanceEvidence:
    """Convert a complete fixture suite into the existing release-gate evidence."""

    _nonempty(engine_id, "engine_id")
    _nonempty(engine_version, "engine_version")
    require_sha256_digest(build_digest, field_name="build_digest")
    if not isinstance(release_channel, EngineReleaseChannel):
        raise TypeError("release_channel must be an EngineReleaseChannel")
    if not isinstance(suite, ConformanceFixtureSuite):
        raise TypeError("suite must be a ConformanceFixtureSuite")
    _aware(tested_at, "tested_at")
    return EngineConformanceEvidence(
        engine_id=engine_id,
        engine_version=engine_version,
        build_digest=build_digest,
        release_channel=release_channel,
        fixture_digest=suite.fingerprint,
        passed_checks=suite.passed_checks,
        tested_at=tested_at,
    )


def require_complete_conformance_suite(
    suite: ConformanceFixtureSuite,
) -> None:
    """Fail closed when a suite omits any required engine check."""

    if not isinstance(suite, ConformanceFixtureSuite):
        raise TypeError("suite must be a ConformanceFixtureSuite")
    missing = suite.missing_checks
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise ValueError(f"conformance fixture suite is incomplete: {names}")
