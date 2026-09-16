"""Engine conformance evidence and authoritative-release gating."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class EngineReleaseChannel(StrEnum):
    STABLE = "stable"
    RELEASE_CANDIDATE = "release_candidate"
    DEVELOPMENT = "development"


class ConformanceCheck(StrEnum):
    MULTI_INSTRUMENT_ACCOUNTING = "multi_instrument_accounting"
    NATIVE_ORDER_FILL_COST = "native_order_fill_cost"
    DETERMINISTIC_REPLAY = "deterministic_replay"
    ENGINE_LIFECYCLE = "engine_lifecycle"
    FORWARD_EVENT_TAPE_PARITY = "forward_event_tape_parity"


_REQUIRED_CHECKS: frozenset[ConformanceCheck] = frozenset(ConformanceCheck)


@dataclass(frozen=True, slots=True)
class EngineConformanceEvidence:
    """Observed fixture results for one pinned engine build."""

    engine_id: str
    engine_version: str
    build_digest: str
    release_channel: EngineReleaseChannel
    fixture_digest: str
    passed_checks: frozenset[ConformanceCheck]
    tested_at: datetime

    def __post_init__(self) -> None:
        _nonempty(self.engine_id, "engine_id")
        _nonempty(self.engine_version, "engine_version")
        require_sha256_digest(self.build_digest, field_name="build_digest")
        if not isinstance(self.release_channel, EngineReleaseChannel):
            raise TypeError("release_channel must be an EngineReleaseChannel")
        require_sha256_digest(self.fixture_digest, field_name="fixture_digest")
        checks = frozenset(self.passed_checks)
        if any(not isinstance(check, ConformanceCheck) for check in checks):
            raise TypeError("passed_checks must contain ConformanceCheck values")
        if self.tested_at.tzinfo is None or self.tested_at.utcoffset() is None:
            raise ValueError("tested_at must be timezone-aware")
        object.__setattr__(self, "passed_checks", checks)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ConformanceDecision(StrEnum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class EngineConformanceReport:
    """Gated interpretation of conformance evidence."""

    evidence_fingerprint: str
    decision: ConformanceDecision
    release_channel: EngineReleaseChannel
    missing_checks: frozenset[ConformanceCheck]
    authoritative: bool

    def __post_init__(self) -> None:
        require_sha256_digest(self.evidence_fingerprint, field_name="evidence_fingerprint")
        if not isinstance(self.decision, ConformanceDecision):
            raise TypeError("decision must be a ConformanceDecision")
        if not isinstance(self.release_channel, EngineReleaseChannel):
            raise TypeError("release_channel must be an EngineReleaseChannel")
        missing = frozenset(self.missing_checks)
        if any(not isinstance(check, ConformanceCheck) for check in missing):
            raise TypeError("missing_checks must contain ConformanceCheck values")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        if self.authoritative and (
            self.decision is not ConformanceDecision.PASS
            or self.release_channel is not EngineReleaseChannel.STABLE
            or missing
        ):
            raise ValueError("only a complete stable conformance pass can be authoritative")
        object.__setattr__(self, "missing_checks", missing)

    @property
    def compatible(self) -> bool:
        """Whether all fixture checks passed, regardless of release channel."""

        return self.decision is ConformanceDecision.PASS

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def evaluate_engine_conformance(
    evidence: EngineConformanceEvidence,
) -> EngineConformanceReport:
    """Evaluate fixture evidence without importing or starting an engine."""

    if not isinstance(evidence, EngineConformanceEvidence):
        raise TypeError("evidence must be an EngineConformanceEvidence")
    missing: frozenset[ConformanceCheck] = _REQUIRED_CHECKS - evidence.passed_checks
    decision = ConformanceDecision.FAIL if missing else ConformanceDecision.PASS
    return EngineConformanceReport(
        evidence_fingerprint=evidence.fingerprint,
        decision=decision,
        release_channel=evidence.release_channel,
        missing_checks=missing,
        authoritative=(
            decision is ConformanceDecision.PASS
            and evidence.release_channel is EngineReleaseChannel.STABLE
        ),
    )
