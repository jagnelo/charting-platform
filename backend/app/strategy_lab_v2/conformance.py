"""Engine conformance evidence and exact-build authority gating."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class EngineReleaseChannel(StrEnum):
    STABLE = "stable"
    RELEASE_CANDIDATE = "release_candidate"
    DEVELOPMENT = "development"


NAUTILUS_RELEASE_PIN_VERSION = "strategy-lab.nautilus-release-pin.v2"
# The current v2 release-candidate track is intentionally exact rather than a
# floating ``--pre`` install. Runtime/source/image digests are still supplied
# by the isolated deployment adapter when it constructs NautilusReleasePin.
NAUTILUS_V2_RC_PACKAGE_VERSION = "2.0.0rc5"
NAUTILUS_V2_RC_RELEASE_TAG = "v2.0.0rc5"
NAUTILUS_V2_RC_WHEEL_SHA256 = (
    "sha256:eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe"
)


@dataclass(frozen=True, slots=True)
class NautilusReleasePin:
    """Exact, isolated runtime material used for one Nautilus build.

    The release pin is evidence supplied by the deployment/runtime adapter; it
    never discovers packages or starts an engine. An authoritative local
    backtest needs this identity and all four simulator checks; full/forward
    scope also needs event-tape parity. Stable or release-candidate builds may
    qualify, while development builds cannot be authoritative.
    """

    package_version: str
    release_tag: str
    source_digest: str
    wheel_digest: str
    runtime_image_digest: str
    python_version: str
    rust_version: str
    legacy_runtime_isolated: bool
    contract_version: str = NAUTILUS_RELEASE_PIN_VERSION

    def __post_init__(self) -> None:
        for name in (
            "package_version",
            "release_tag",
            "python_version",
            "rust_version",
            "contract_version",
        ):
            _nonempty(getattr(self, name), name)
        require_sha256_digest(self.source_digest, field_name="source_digest")
        require_sha256_digest(self.wheel_digest, field_name="wheel_digest")
        require_sha256_digest(self.runtime_image_digest, field_name="runtime_image_digest")
        if not isinstance(self.legacy_runtime_isolated, bool):
            raise TypeError("legacy_runtime_isolated must be a boolean")
        if not self.package_version.startswith("2."):
            raise ValueError("Nautilus release pin must target v2")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusResultProvenance:
    """Exact engine materials and gates bound to one Nautilus result."""

    release_pin: NautilusReleasePin
    release_channel: EngineReleaseChannel
    conformance_evidence_fingerprint: str
    conformance_report_fingerprint: str
    execution_plan_fingerprint: str
    execution_scope: str

    def __post_init__(self) -> None:
        if not isinstance(self.release_pin, NautilusReleasePin):
            raise TypeError("release_pin must be a NautilusReleasePin")
        if not isinstance(self.release_channel, EngineReleaseChannel):
            raise TypeError("release_channel must be an EngineReleaseChannel")
        for name in (
            "conformance_evidence_fingerprint",
            "conformance_report_fingerprint",
            "execution_plan_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.execution_scope, str) or self.execution_scope not in {
            "full",
            "backtest_compatibility",
            "backtest_authoritative",
            "forward_compatibility",
        }:
            raise ValueError("execution_scope is not a supported Nautilus scope")
        if not self.release_pin.package_version.startswith("2."):
            raise ValueError("Nautilus result provenance must target v2")
        if self.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE and not (
            re.search(
                r"(?:alpha|beta|rc|pre)(?:[-._]?\d+)?",
                self.release_pin.package_version,
                re.IGNORECASE,
            )
        ):
            raise ValueError("release-candidate provenance requires a prerelease version")
        if self.release_channel is EngineReleaseChannel.STABLE and not _stable_release_version(
            self.release_pin.package_version, self.release_pin.release_tag
        ):
            raise ValueError("stable provenance cannot identify a prerelease")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def _stable_release_version(version: str, release_tag: str) -> bool:
    """Reject prerelease labels from a claim of stable v2 authority."""

    prerelease = re.compile(r"(?:alpha|beta|rc|dev|pre)(?:[-._]?\d+)?", re.IGNORECASE)
    return not prerelease.search(version) and not prerelease.search(release_tag)


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
    release_pin: NautilusReleasePin | None = None

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
        if self.release_pin is not None:
            if not isinstance(self.release_pin, NautilusReleasePin):
                raise TypeError("release_pin must be a NautilusReleasePin")
            if self.release_pin.package_version != self.engine_version:
                raise ValueError("release pin package version must match engine_version")
        object.__setattr__(self, "tested_at", self.tested_at.astimezone(UTC))
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
    release_pin_valid: bool = False

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
        if not isinstance(self.release_pin_valid, bool):
            raise TypeError("release_pin_valid must be a boolean")
        if self.authoritative and (
            self.decision is not ConformanceDecision.PASS
            or self.release_channel is EngineReleaseChannel.DEVELOPMENT
            or missing
            or not self.release_pin_valid
        ):
            raise ValueError(
                "only a complete stable or release-candidate conformance pass with a "
                "valid isolated release pin can be authoritative"
            )
        object.__setattr__(self, "missing_checks", missing)

    @property
    def compatible(self) -> bool:
        """Whether all fixture checks passed, regardless of release channel."""

        return self.decision is ConformanceDecision.PASS

    @property
    def execution_eligible(self) -> bool:
        """Whether the evidence may start an isolated engine process.

        Compatibility execution is allowed for a complete release candidate,
        but every actual process still needs a valid isolated v2 release pin.
        This keeps an RC useful for local replay/backtest parity without
        allowing an untracked package or shared legacy runtime to execute.
        """

        return self.compatible and self.release_pin_valid

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
    release_pin_valid = _release_pin_valid(evidence)
    return EngineConformanceReport(
        evidence_fingerprint=evidence.fingerprint,
        decision=decision,
        release_channel=evidence.release_channel,
        missing_checks=missing,
        authoritative=(
            decision is ConformanceDecision.PASS
            and evidence.release_channel is not EngineReleaseChannel.DEVELOPMENT
            and release_pin_valid
        ),
        release_pin_valid=release_pin_valid,
    )


def _release_pin_valid(evidence: EngineConformanceEvidence) -> bool:
    pin = evidence.release_pin
    if pin is None or not pin.legacy_runtime_isolated:
        return False
    if pin.release_tag.removeprefix("v") != pin.package_version:
        return False
    if evidence.release_channel is EngineReleaseChannel.STABLE:
        return _stable_release_version(pin.package_version, pin.release_tag)
    if evidence.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE:
        prerelease = re.compile(r"(?:alpha|beta|rc|pre)(?:[-._]?\d+)?", re.IGNORECASE)
        return bool(
            prerelease.search(pin.package_version)
            and prerelease.search(pin.release_tag)
            and not re.search(r"dev", pin.package_version, re.IGNORECASE)
        )
    return bool(
        re.search(r"dev", pin.package_version, re.IGNORECASE)
        and re.search(r"dev", pin.release_tag, re.IGNORECASE)
    )
