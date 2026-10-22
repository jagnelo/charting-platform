"""Engine-neutral strategy-runtime request and receipt contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.runtime import (
    RuntimeIsolationProfile,
    RuntimeIsolationReport,
    RuntimeIsolationRequest,
    preflight_runtime_isolation,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _entrypoint(value: str) -> None:
    parts = value.split(":")
    if len(parts) != 2 or any(
        not part or any(not token.isidentifier() for token in part.split("."))
        for part in parts
    ):
        raise ValueError("entrypoint must use module.path:callable syntax")


@dataclass(frozen=True, slots=True)
class StrategyRuntimeRequest:
    """Immutable request containing only digests and declared runtime inputs."""

    request_id: str
    attempt_id: str
    package_fingerprint: str
    source_digest: str
    input_bundle_digest: str
    runtime_profile_fingerprint: str
    entrypoint: str
    isolation_request: RuntimeIsolationRequest
    submitted_at: datetime

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_id, field_name="request_id")
        _nonempty(self.attempt_id, "attempt_id")
        for name in (
            "package_fingerprint",
            "source_digest",
            "input_bundle_digest",
            "runtime_profile_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        _entrypoint(self.entrypoint)
        if not isinstance(self.isolation_request, RuntimeIsolationRequest):
            raise TypeError("isolation_request must be a RuntimeIsolationRequest")
        if self.isolation_request.attempt_id != self.attempt_id:
            raise ValueError("isolation request must reference the runtime attempt")
        _aware(self.submitted_at, "submitted_at")
        object.__setattr__(self, "submitted_at", self.submitted_at.astimezone(UTC))

    @property
    def fingerprint(self) -> str:
        """Request identity excludes submission transport time."""

        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "entrypoint": self.entrypoint,
                "input_bundle_digest": self.input_bundle_digest,
                "isolation_request": self.isolation_request,
                "package_fingerprint": self.package_fingerprint,
                "request_id": self.request_id,
                "runtime_profile_fingerprint": self.runtime_profile_fingerprint,
                "source_digest": self.source_digest,
            }
        )


class StrategyRuntimeDecision(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class StrategyRuntimePreflight:
    request_fingerprint: str
    profile_fingerprint: str
    isolation_report: RuntimeIsolationReport
    decision: StrategyRuntimeDecision
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        require_sha256_digest(self.profile_fingerprint, field_name="profile_fingerprint")
        if not isinstance(self.isolation_report, RuntimeIsolationReport):
            raise TypeError("isolation_report must be a RuntimeIsolationReport")
        if not isinstance(self.decision, StrategyRuntimeDecision):
            raise TypeError("decision must be a StrategyRuntimeDecision")
        reasons = tuple(self.rejection_reasons)
        if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise ValueError("runtime rejection reasons must be non-empty strings")
        if len(set(reasons)) != len(reasons):
            raise ValueError("runtime rejection reasons must be unique")
        if self.decision is StrategyRuntimeDecision.ALLOW and reasons:
            raise ValueError("allowed runtime preflights cannot contain rejection reasons")
        if self.decision is StrategyRuntimeDecision.REJECT and not reasons:
            raise ValueError("rejected runtime preflights require rejection reasons")
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def accepted(self) -> bool:
        return self.decision is StrategyRuntimeDecision.ALLOW

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def preflight_strategy_runtime(
    request: StrategyRuntimeRequest,
    profile: RuntimeIsolationProfile,
) -> StrategyRuntimePreflight:
    """Bind a strategy request to a pinned isolation profile without starting it."""

    if not isinstance(request, StrategyRuntimeRequest):
        raise TypeError("request must be a StrategyRuntimeRequest")
    if not isinstance(profile, RuntimeIsolationProfile):
        raise TypeError("profile must be a RuntimeIsolationProfile")
    report = preflight_runtime_isolation(profile, request.isolation_request)
    rejection_reasons = list(report.rejection_reasons)
    if request.runtime_profile_fingerprint != profile.fingerprint:
        rejection_reasons.append("runtime_profile_identity_mismatch")
    reasons = tuple(sorted(set(rejection_reasons)))
    decision = StrategyRuntimeDecision.ALLOW if not reasons else StrategyRuntimeDecision.REJECT
    return StrategyRuntimePreflight(
        request.fingerprint,
        profile.fingerprint,
        report,
        decision,
        reasons,
    )


class RuntimeExecutionPhase(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_PHASES = frozenset(
    {RuntimeExecutionPhase.SUCCEEDED, RuntimeExecutionPhase.FAILED, RuntimeExecutionPhase.CANCELLED}
)


@dataclass(frozen=True, slots=True)
class RuntimeExecutionUpdate:
    request_fingerprint: str
    attempt_id: str
    sequence: int
    phase: RuntimeExecutionPhase
    observed_at: datetime
    output_digest: str | None = None
    output_bytes: int | None = None
    error_digest: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        _nonempty(self.attempt_id, "attempt_id")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("runtime sequence must be a positive integer")
        if not isinstance(self.phase, RuntimeExecutionPhase):
            raise TypeError("phase must be a RuntimeExecutionPhase")
        _aware(self.observed_at, "observed_at")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        if self.output_digest is not None:
            require_sha256_digest(self.output_digest, field_name="output_digest")
        if self.output_bytes is not None and (
            not isinstance(self.output_bytes, int)
            or isinstance(self.output_bytes, bool)
            or self.output_bytes < 0
        ):
            raise ValueError("output_bytes must be a non-negative integer")
        if self.error_digest is not None:
            require_sha256_digest(self.error_digest, field_name="error_digest")
        if self.phase is RuntimeExecutionPhase.SUCCEEDED:
            if self.output_digest is None or self.output_bytes is None or self.error_digest is not None:
                raise ValueError("successful runtime updates require output identity and size")
        elif self.phase is RuntimeExecutionPhase.FAILED:
            if self.error_digest is None or self.output_digest is not None or self.output_bytes is not None:
                raise ValueError("failed runtime updates require an error and no output")
        elif self.output_digest is not None or self.output_bytes is not None or self.error_digest is not None:
            raise ValueError("non-terminal runtime updates cannot contain output or error")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class RuntimeExecutionState:
    request_fingerprint: str
    attempt_id: str
    profile_fingerprint: str
    output_limit_bytes: int
    sequence: int
    phase: RuntimeExecutionPhase
    updated_at: datetime
    output_digest: str | None = None
    output_bytes: int | None = None
    error_digest: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        _nonempty(self.attempt_id, "attempt_id")
        require_sha256_digest(self.profile_fingerprint, field_name="profile_fingerprint")
        if not isinstance(self.output_limit_bytes, int) or isinstance(self.output_limit_bytes, bool) or self.output_limit_bytes <= 0:
            raise ValueError("output_limit_bytes must be a positive integer")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise ValueError("runtime state sequence must be non-negative")
        if not isinstance(self.phase, RuntimeExecutionPhase):
            raise TypeError("phase must be a RuntimeExecutionPhase")
        _aware(self.updated_at, "updated_at")
        object.__setattr__(self, "updated_at", self.updated_at.astimezone(UTC))
        if self.sequence == 0 and self.phase is not RuntimeExecutionPhase.ACCEPTED:
            raise ValueError("sequence-zero runtime state must be accepted")
        if self.output_bytes is not None and (
            not isinstance(self.output_bytes, int)
            or isinstance(self.output_bytes, bool)
            or self.output_bytes < 0
            or self.output_bytes > self.output_limit_bytes
        ):
            raise ValueError("runtime output exceeds the declared limit")
        if self.phase is RuntimeExecutionPhase.SUCCEEDED:
            if self.output_digest is None or self.output_bytes is None or self.error_digest is not None:
                raise ValueError("successful runtime state requires output identity and size")
            require_sha256_digest(self.output_digest, field_name="output_digest")
        elif self.phase is RuntimeExecutionPhase.FAILED:
            if self.error_digest is None or self.output_digest is not None or self.output_bytes is not None:
                raise ValueError("failed runtime state requires an error and no output")
            require_sha256_digest(self.error_digest, field_name="error_digest")
        elif self.output_digest is not None or self.output_bytes is not None or self.error_digest is not None:
            raise ValueError("non-terminal runtime state cannot contain output or error")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def new_runtime_execution_state(
    preflight: StrategyRuntimePreflight,
    *,
    attempt_id: str,
    output_limit_bytes: int,
    accepted_at: datetime,
) -> RuntimeExecutionState:
    """Create a sequence-zero accepted state only after an allowed preflight."""

    if not isinstance(preflight, StrategyRuntimePreflight):
        raise TypeError("preflight must be a StrategyRuntimePreflight")
    if preflight.decision is not StrategyRuntimeDecision.ALLOW:
        raise ValueError("runtime execution requires an allowed preflight")
    _nonempty(attempt_id, "attempt_id")
    if not isinstance(output_limit_bytes, int) or isinstance(output_limit_bytes, bool) or output_limit_bytes <= 0:
        raise ValueError("output_limit_bytes must be a positive integer")
    _aware(accepted_at, "accepted_at")
    return RuntimeExecutionState(
        preflight.request_fingerprint,
        attempt_id,
        preflight.profile_fingerprint,
        output_limit_bytes,
        0,
        RuntimeExecutionPhase.ACCEPTED,
        accepted_at,
    )


class RuntimeExecutionDecision(StrEnum):
    APPLY = "apply"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class RuntimeExecutionResolution:
    decision: RuntimeExecutionDecision
    state: RuntimeExecutionState

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RuntimeExecutionDecision):
            raise TypeError("decision must be a RuntimeExecutionDecision")
        if not isinstance(self.state, RuntimeExecutionState):
            raise TypeError("state must be a RuntimeExecutionState")


def apply_runtime_execution_update(
    state: RuntimeExecutionState,
    update: RuntimeExecutionUpdate,
) -> RuntimeExecutionResolution:
    """Apply a monotonic receipt; adapters own process/container enforcement."""

    if not isinstance(state, RuntimeExecutionState):
        raise TypeError("state must be a RuntimeExecutionState")
    if not isinstance(update, RuntimeExecutionUpdate):
        raise TypeError("update must be a RuntimeExecutionUpdate")
    if update.request_fingerprint != state.request_fingerprint or update.attempt_id != state.attempt_id:
        raise ValueError("runtime update must reference the same request and attempt")
    if update.observed_at < state.updated_at:
        raise ValueError("runtime update time cannot move backwards")
    if update.sequence <= state.sequence:
        same = (
            update.sequence == state.sequence
            and update.phase is state.phase
            and update.observed_at == state.updated_at
            and update.output_digest == state.output_digest
            and update.output_bytes == state.output_bytes
            and update.error_digest == state.error_digest
        )
        if same:
            return RuntimeExecutionResolution(RuntimeExecutionDecision.REPLAY_EXISTING, state)
        raise ValueError("runtime update sequence conflicts with the existing state")
    if state.phase in _TERMINAL_PHASES:
        raise ValueError("terminal runtime state cannot receive updates")
    if update.phase is RuntimeExecutionPhase.SUCCEEDED:
        assert update.output_bytes is not None
        if update.output_bytes > state.output_limit_bytes:
            raise ValueError("runtime output exceeds the declared limit")
    next_state = RuntimeExecutionState(
        state.request_fingerprint,
        state.attempt_id,
        state.profile_fingerprint,
        state.output_limit_bytes,
        update.sequence,
        update.phase,
        update.observed_at,
        update.output_digest,
        update.output_bytes,
        update.error_digest,
    )
    return RuntimeExecutionResolution(RuntimeExecutionDecision.APPLY, next_state)
