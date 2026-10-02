"""Exact isolated Nautilus v2 release-candidate runtime declarations.

The application backend intentionally keeps the legacy Nautilus 1.x dependency
in its own environment.  This module gives an adapter a typed, immutable
declaration for the current v2 RC compatibility runtime without importing
Nautilus, discovering packages, or starting a process.  The adapter must still
provide content digests for the source checkout and runtime image after it has
resolved/builds those artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_RELEASE_PIN_VERSION,
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
    ConformanceCheck,
    EngineReleaseChannel,
    NautilusReleasePin,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class NautilusRcCompatibilityRuntime:
    """One exact v2 RC runtime boundary.

    The package/tag are deliberately not caller-selectable: changing either
    value creates a different release track and requires a new reviewed
    contract.  Runtime/source digests are supplied by the image/build adapter
    and bind the resulting process to immutable material.
    """

    source_digest: str
    runtime_image_digest: str
    python_version: str
    rust_version: str
    legacy_runtime_isolated: bool = True
    contract_version: str = NAUTILUS_RELEASE_PIN_VERSION

    def __post_init__(self) -> None:
        require_sha256_digest(self.source_digest, field_name="source_digest")
        require_sha256_digest(self.runtime_image_digest, field_name="runtime_image_digest")
        for name in ("python_version", "rust_version", "contract_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.legacy_runtime_isolated, bool):
            raise TypeError("legacy_runtime_isolated must be a boolean")
        if not self.legacy_runtime_isolated:
            raise ValueError("the v2 RC runtime must be isolated from the legacy runtime")

    @property
    def package_version(self) -> str:
        return NAUTILUS_V2_RC_PACKAGE_VERSION

    @property
    def release_tag(self) -> str:
        return NAUTILUS_V2_RC_RELEASE_TAG

    @property
    def release_channel(self) -> EngineReleaseChannel:
        return EngineReleaseChannel.RELEASE_CANDIDATE

    @property
    def authoritative(self) -> bool:
        """RC output is never authoritative, even after complete fixtures."""

        return False

    @property
    def release_pin(self) -> NautilusReleasePin:
        """Build the exact release identity consumed by conformance evidence."""

        return NautilusReleasePin(
            package_version=self.package_version,
            release_tag=self.release_tag,
            source_digest=self.source_digest,
            runtime_image_digest=self.runtime_image_digest,
            python_version=self.python_version,
            rust_version=self.rust_version,
            legacy_runtime_isolated=self.legacy_runtime_isolated,
            contract_version=self.contract_version,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusRuntimeProbeEvidence:
    """Typed, non-authoritative receipt emitted by the isolated image probe."""

    runtime_fingerprint: str
    runtime_image_digest: str
    package_version: str
    python_version: str
    platform: str
    implementation: str
    engine_lifecycle: str

    def __post_init__(self) -> None:
        for name in ("runtime_fingerprint", "runtime_image_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "package_version",
            "python_version",
            "platform",
            "implementation",
        ):
            _nonempty(getattr(self, name), name)
        if self.package_version != NAUTILUS_V2_RC_PACKAGE_VERSION:
            raise ValueError("probe evidence must target the exact v2 RC package")
        if self.engine_lifecycle != "passed":
            raise ValueError("probe evidence requires a passed engine lifecycle")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        runtime: NautilusRcCompatibilityRuntime,
    ) -> NautilusRuntimeProbeEvidence:
        """Parse one strict probe JSON object against its declared runtime."""

        if not isinstance(payload, Mapping):
            raise TypeError("probe payload must be a mapping")
        if not isinstance(runtime, NautilusRcCompatibilityRuntime):
            raise TypeError("runtime must be a NautilusRcCompatibilityRuntime")
        required = {
            "engine_lifecycle",
            "implementation",
            "nautilus_package_version",
            "platform",
            "python_version",
        }
        if set(payload) != required:
            raise ValueError("probe payload fields must match the exact runtime schema")
        values = {key: payload[key] for key in required}
        if any(not isinstance(value, str) for value in values.values()):
            raise TypeError("probe payload fields must be strings")
        if values["nautilus_package_version"] != runtime.package_version:
            raise ValueError("probe package version does not match the declared runtime")
        if values["python_version"] != runtime.python_version:
            raise ValueError("probe Python version does not match the declared runtime")
        return cls(
            runtime_fingerprint=runtime.fingerprint,
            runtime_image_digest=runtime.runtime_image_digest,
            package_version=values["nautilus_package_version"],
            python_version=values["python_version"],
            platform=values["platform"],
            implementation=values["implementation"],
            engine_lifecycle=values["engine_lifecycle"],
        )

    @property
    def authoritative(self) -> bool:
        """RC probe output can never authorize published or live results."""

        return False

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusRcFixtureReceipt:
    """Partial real-engine fixture receipt for the non-authoritative RC track."""

    runtime_fingerprint: str
    runtime_image_digest: str
    fixture_digest: str
    passed_checks: frozenset[ConformanceCheck]
    deferred_checks: frozenset[ConformanceCheck]

    def __post_init__(self) -> None:
        for name in ("runtime_fingerprint", "runtime_image_digest", "fixture_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        passed = frozenset(self.passed_checks)
        deferred = frozenset(self.deferred_checks)
        if any(not isinstance(check, ConformanceCheck) for check in passed | deferred):
            raise TypeError("fixture checks must contain ConformanceCheck values")
        if passed & deferred:
            raise ValueError("passed and deferred fixture checks must be disjoint")
        if passed | deferred != frozenset(ConformanceCheck):
            raise ValueError("fixture receipt must account for every conformance check")
        object.__setattr__(self, "passed_checks", passed)
        object.__setattr__(self, "deferred_checks", deferred)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        runtime: NautilusRcCompatibilityRuntime,
    ) -> NautilusRcFixtureReceipt:
        """Parse the real image fixture output without granting authority."""

        if not isinstance(payload, Mapping):
            raise TypeError("fixture payload must be a mapping")
        if not isinstance(runtime, NautilusRcCompatibilityRuntime):
            raise TypeError("runtime must be a NautilusRcCompatibilityRuntime")
        required = {
            "authoritative",
            "deterministic_replay",
            "engine_lifecycle",
            "forward_event_tape_parity",
            "multi_instrument_accounting",
            "native_order_fill_cost",
        }
        if set(payload) != required:
            raise ValueError("fixture payload fields must match the exact receipt schema")
        if payload["authoritative"] is not False:
            raise ValueError("release-candidate fixture receipts cannot be authoritative")
        if payload["engine_lifecycle"] != "passed":
            raise ValueError("fixture engine lifecycle must pass")
        replay = payload["deterministic_replay"]
        multi = payload["multi_instrument_accounting"]
        native = payload["native_order_fill_cost"]
        if not isinstance(replay, Mapping) or replay.get("equal") is not True:
            raise ValueError("deterministic replay fixture did not match")
        if not isinstance(multi, Mapping) or multi.get("instrument_count", 0) < 2:
            raise ValueError("multi-instrument fixture did not cover two instruments")
        if not isinstance(native, Mapping) or native.get("total_orders", 0) < 1:
            raise ValueError("native order/fill fixture did not execute an order")
        if payload["forward_event_tape_parity"] != "deferred_authoritative_fixture":
            raise ValueError("forward event-tape parity must remain explicitly deferred")
        return cls(
            runtime_fingerprint=runtime.fingerprint,
            runtime_image_digest=runtime.runtime_image_digest,
            fixture_digest=content_digest(payload),
            passed_checks=frozenset(
                {
                    ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING,
                    ConformanceCheck.NATIVE_ORDER_FILL_COST,
                    ConformanceCheck.DETERMINISTIC_REPLAY,
                    ConformanceCheck.ENGINE_LIFECYCLE,
                }
            ),
            deferred_checks=frozenset({ConformanceCheck.FORWARD_EVENT_TAPE_PARITY}),
        )

    @property
    def compatible(self) -> bool:
        """Partial RC fixtures are compatible but not complete conformance."""

        return True

    @property
    def authoritative(self) -> bool:
        return False

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


__all__ = [
    "NautilusRcCompatibilityRuntime",
    "NautilusRuntimeProbeEvidence",
    "NautilusRcFixtureReceipt",
]
