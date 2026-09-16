"""Fail-closed runtime-isolation preflight for strategy execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class RuntimeIsolationDecision(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class RuntimeIsolationProfile:
    """Pinned sandbox settings required before trusted strategy code runs."""

    runtime_image_digest: str
    runtime_abi: str
    network_disabled: bool = True
    read_only_root: bool = True
    capabilities_dropped: bool = True
    secrets_disabled: bool = True
    wall_timeout_seconds: int = 300
    cpu_limit_seconds: int = 300
    memory_limit_bytes: int = 512 * 1024 * 1024
    output_limit_bytes: int = 16 * 1024 * 1024
    allowed_dependency_digests: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        require_sha256_digest(self.runtime_image_digest, field_name="runtime_image_digest")
        _nonempty(self.runtime_abi, "runtime_abi")
        for name in (
            "wall_timeout_seconds",
            "cpu_limit_seconds",
            "memory_limit_bytes",
            "output_limit_bytes",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in (
            "network_disabled",
            "read_only_root",
            "capabilities_dropped",
            "secrets_disabled",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")
        dependencies = frozenset(self.allowed_dependency_digests)
        for digest in dependencies:
            require_sha256_digest(digest, field_name="allowed_dependency_digest")
        object.__setattr__(self, "allowed_dependency_digests", dependencies)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class RuntimeIsolationRequest:
    """Execution claims evaluated against an isolation profile."""

    attempt_id: str
    dependency_digests: tuple[str, ...] = ()
    network_requested: bool = False
    writable_paths_requested: tuple[str, ...] = ()
    secret_names_requested: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.attempt_id, "attempt_id")
        dependencies = tuple(self.dependency_digests)
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("dependency digests must be unique")
        for digest in dependencies:
            require_sha256_digest(digest, field_name="dependency_digest")
        object.__setattr__(self, "dependency_digests", dependencies)
        if not isinstance(self.network_requested, bool):
            raise TypeError("network_requested must be a boolean")
        for name, values in (
            ("writable_paths_requested", self.writable_paths_requested),
            ("secret_names_requested", self.secret_names_requested),
        ):
            normalized = tuple(values)
            if any(not isinstance(value, str) or not value.strip() for value in normalized):
                raise ValueError(f"{name} must contain non-empty strings")
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, normalized)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class RuntimeIsolationReport:
    """Evidence for an allow/reject decision, without secrets or process state."""

    decision: RuntimeIsolationDecision
    profile_fingerprint: str
    request_fingerprint: str
    rejection_reasons: tuple[str, ...] = ()
    missing_dependency_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RuntimeIsolationDecision):
            raise TypeError("decision must be a RuntimeIsolationDecision")
        require_sha256_digest(self.profile_fingerprint, field_name="profile_fingerprint")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(not reason.strip() for reason in reasons):
            raise ValueError("rejection reasons must be unique and non-empty")
        missing = tuple(self.missing_dependency_digests)
        for digest in missing:
            require_sha256_digest(digest, field_name="missing_dependency_digest")
        if len(missing) != len(set(missing)):
            raise ValueError("missing dependency digests must be unique")
        if self.decision is RuntimeIsolationDecision.ALLOW and reasons:
            raise ValueError("allowed isolation reports cannot contain rejection reasons")
        if self.decision is RuntimeIsolationDecision.ALLOW and missing:
            raise ValueError("allowed isolation reports cannot contain missing dependencies")
        object.__setattr__(self, "rejection_reasons", reasons)
        object.__setattr__(self, "missing_dependency_digests", missing)

    @property
    def accepted(self) -> bool:
        return self.decision is RuntimeIsolationDecision.ALLOW

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def preflight_runtime_isolation(
    profile: RuntimeIsolationProfile,
    request: RuntimeIsolationRequest,
) -> RuntimeIsolationReport:
    """Evaluate sandbox controls and dependency pins without starting a process."""

    if not isinstance(profile, RuntimeIsolationProfile):
        raise TypeError("profile must be a RuntimeIsolationProfile")
    if not isinstance(request, RuntimeIsolationRequest):
        raise TypeError("request must be a RuntimeIsolationRequest")
    reasons: list[str] = []
    if not profile.network_disabled:
        reasons.append("network_must_be_disabled")
    if not profile.read_only_root:
        reasons.append("root_filesystem_must_be_read_only")
    if not profile.capabilities_dropped:
        reasons.append("container_capabilities_must_be_dropped")
    if not profile.secrets_disabled:
        reasons.append("runtime_secrets_must_be_disabled")
    if request.network_requested:
        reasons.append("strategy_requested_network_access")
    if request.writable_paths_requested:
        reasons.append("strategy_requested_writable_paths")
    if request.secret_names_requested:
        reasons.append("strategy_requested_secrets")
    missing = tuple(
        sorted(set(request.dependency_digests) - profile.allowed_dependency_digests)
    )
    if missing:
        reasons.append("dependency_digest_not_vetted")
    decision = RuntimeIsolationDecision.REJECT if reasons else RuntimeIsolationDecision.ALLOW
    return RuntimeIsolationReport(
        decision=decision,
        profile_fingerprint=profile.fingerprint,
        request_fingerprint=request.fingerprint,
        rejection_reasons=tuple(reasons),
        missing_dependency_digests=missing,
    )
