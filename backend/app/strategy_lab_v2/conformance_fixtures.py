"""Evidence-bound conformance fixture observations for the engine gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineReleaseChannel,
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
