"""Storage-neutral retention and pinning decisions for immutable artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ArtifactRetentionPin:
    """An immutable owner-scoped retention pin with optional expiry/release."""

    pin_id: str
    artifact_manifest_fingerprint: str
    owner_type: str
    owner_id: str
    created_at: datetime
    expires_at: datetime | None = None
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.pin_id, field_name="pin_id")
        require_sha256_digest(
            self.artifact_manifest_fingerprint,
            field_name="artifact_manifest_fingerprint",
        )
        for name in ("owner_type", "owner_id"):
            _nonempty(getattr(self, name), name)
        _aware(self.created_at, "created_at")
        for name in ("expires_at", "released_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
                if value < self.created_at:
                    raise ValueError(f"{name} must not precede created_at")

    @property
    def active(self) -> bool:
        """Whether this pin is currently active without using a wall clock."""

        return self.released_at is None and self.expires_at is None

    def active_at(self, observed_at: datetime) -> bool:
        """Evaluate activity at an explicit instant, including expiry boundaries."""

        _aware(observed_at, "observed_at")
        return (
            self.created_at <= observed_at
            and (self.expires_at is None or observed_at < self.expires_at)
            and (self.released_at is None or observed_at < self.released_at)
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ArtifactRetentionState:
    """Retention metadata for one manifest, with deterministic pin ordering."""

    manifest_fingerprint: str
    content_digest: str
    retention_class: ArtifactRetention
    retention_eligible_at: datetime | None = None
    pins: tuple[ArtifactRetentionPin, ...] = ()

    def __post_init__(self) -> None:
        require_sha256_digest(self.manifest_fingerprint, field_name="manifest_fingerprint")
        require_sha256_digest(self.content_digest, field_name="content_digest")
        if not isinstance(self.retention_class, ArtifactRetention):
            raise TypeError("retention_class must be an ArtifactRetention")
        if self.retention_eligible_at is not None:
            _aware(self.retention_eligible_at, "retention_eligible_at")
        if self.retention_class in {
            ArtifactRetention.TIERED_RESULT,
            ArtifactRetention.EPHEMERAL,
        } and self.retention_eligible_at is None:
            raise ValueError("tiered and ephemeral artifacts require retention_eligible_at")
        pins = tuple(self.pins)
        if any(not isinstance(pin, ArtifactRetentionPin) for pin in pins):
            raise TypeError("pins must contain ArtifactRetentionPin values")
        if any(pin.artifact_manifest_fingerprint != self.manifest_fingerprint for pin in pins):
            raise ValueError("retention pins must reference this manifest")
        pin_ids = [pin.pin_id for pin in pins]
        if len(pin_ids) != len(set(pin_ids)):
            raise ValueError("retention pin ids must be unique")
        object.__setattr__(self, "pins", tuple(sorted(pins, key=lambda pin: pin.pin_id)))

    @classmethod
    def from_manifest(
        cls,
        manifest: ArtifactManifest,
        *,
        retention_eligible_at: datetime | None = None,
        pins: tuple[ArtifactRetentionPin, ...] = (),
    ) -> ArtifactRetentionState:
        """Build retention state while binding it to the exact manifest identity."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("artifact manifest must be an ArtifactManifest")
        return cls(
            manifest_fingerprint=content_digest(manifest),
            content_digest=manifest.content_digest,
            retention_class=manifest.retention_class,
            retention_eligible_at=retention_eligible_at,
            pins=pins,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class RetentionDecision(StrEnum):
    RETAIN_PERMANENT = "retain_permanent"
    RETAIN_PINNED = "retain_pinned"
    PIN_REQUIRED = "pin_required"
    RETAIN_TIERED = "retain_tiered"
    TIER_ELIGIBLE = "tier_eligible"
    RETAIN_EPHEMERAL = "retain_ephemeral"
    EXPIRE_ELIGIBLE = "expire_eligible"


@dataclass(frozen=True, slots=True)
class ArtifactRetentionResolution:
    decision: RetentionDecision
    state: ArtifactRetentionState
    observed_at: datetime
    active_pin_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RetentionDecision):
            raise TypeError("decision must be a RetentionDecision")
        if not isinstance(self.state, ArtifactRetentionState):
            raise TypeError("state must be an ArtifactRetentionState")
        _aware(self.observed_at, "observed_at")
        pin_ids = tuple(self.active_pin_ids)
        if tuple(sorted(pin_ids)) != pin_ids or len(pin_ids) != len(set(pin_ids)):
            raise ValueError("active pin ids must be sorted and unique")
        for pin_id in pin_ids:
            require_sha256_digest(pin_id, field_name="active_pin_id")
        known = {pin.pin_id for pin in self.state.pins}
        if not set(pin_ids) <= known:
            raise ValueError("active pin ids must reference state pins")


class RetentionPinDecision(StrEnum):
    ADD = "add"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class RetentionPinResolution:
    decision: RetentionPinDecision
    state: ArtifactRetentionState
    pin_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RetentionPinDecision):
            raise TypeError("decision must be a RetentionPinDecision")
        if not isinstance(self.state, ArtifactRetentionState):
            raise TypeError("state must be an ArtifactRetentionState")
        require_sha256_digest(self.pin_id, field_name="pin_id")


def add_retention_pin(
    state: ArtifactRetentionState, pin: ArtifactRetentionPin
) -> RetentionPinResolution:
    """Resolve an idempotent pin add without mutating storage."""

    if not isinstance(state, ArtifactRetentionState):
        raise TypeError("state must be an ArtifactRetentionState")
    if not isinstance(pin, ArtifactRetentionPin):
        raise TypeError("pin must be an ArtifactRetentionPin")
    if pin.artifact_manifest_fingerprint != state.manifest_fingerprint:
        raise ValueError("retention pin must reference the state manifest")
    existing = next((item for item in state.pins if item.pin_id == pin.pin_id), None)
    if existing is not None:
        decision = (
            RetentionPinDecision.REPLAY_EXISTING
            if existing.fingerprint == pin.fingerprint
            else RetentionPinDecision.CONFLICT
        )
        return RetentionPinResolution(decision, state, pin.pin_id)
    return RetentionPinResolution(
        RetentionPinDecision.ADD,
        replace(state, pins=state.pins + (pin,)),
        pin.pin_id,
    )


def release_retention_pin(
    state: ArtifactRetentionState, *, pin_id: str, released_at: datetime
) -> ArtifactRetentionState:
    """Release a pin idempotently; expiry and release never delete an artifact."""

    if not isinstance(state, ArtifactRetentionState):
        raise TypeError("state must be an ArtifactRetentionState")
    require_sha256_digest(pin_id, field_name="pin_id")
    _aware(released_at, "released_at")
    for index, pin in enumerate(state.pins):
        if pin.pin_id != pin_id:
            continue
        if pin.released_at is not None:
            return state
        updated = replace(pin, released_at=released_at)
        return replace(state, pins=state.pins[:index] + (updated,) + state.pins[index + 1 :])
    raise ValueError("pin_id is not present in retention state")


def resolve_artifact_retention(
    state: ArtifactRetentionState, *, observed_at: datetime
) -> ArtifactRetentionResolution:
    """Classify retention at an explicit time without performing tiering/deletion."""

    if not isinstance(state, ArtifactRetentionState):
        raise TypeError("state must be an ArtifactRetentionState")
    _aware(observed_at, "observed_at")
    active_pin_ids = tuple(
        sorted(pin.pin_id for pin in state.pins if pin.active_at(observed_at))
    )
    if active_pin_ids:
        decision = RetentionDecision.RETAIN_PINNED
    elif state.retention_class is ArtifactRetention.PERMANENT_MANIFEST:
        decision = RetentionDecision.RETAIN_PERMANENT
    elif state.retention_class in {
        ArtifactRetention.PINNED_INPUT,
        ArtifactRetention.PINNED_RESULT,
    }:
        decision = RetentionDecision.PIN_REQUIRED
    elif state.retention_class is ArtifactRetention.TIERED_RESULT:
        decision = (
            RetentionDecision.TIER_ELIGIBLE
            if observed_at >= state.retention_eligible_at  # type: ignore[operator]
            else RetentionDecision.RETAIN_TIERED
        )
    else:
        decision = (
            RetentionDecision.EXPIRE_ELIGIBLE
            if observed_at >= state.retention_eligible_at  # type: ignore[operator]
            else RetentionDecision.RETAIN_EPHEMERAL
        )
    return ArtifactRetentionResolution(decision, state, observed_at, active_pin_ids)
