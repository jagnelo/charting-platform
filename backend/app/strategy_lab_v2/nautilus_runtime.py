"""Exact isolated Nautilus v2 release-candidate runtime declarations.

The application backend intentionally keeps the legacy Nautilus 1.x dependency
in its own environment.  This module gives an adapter a typed, immutable
declaration for the current v2 RC compatibility runtime without importing
Nautilus, discovering packages, or starting a process.  The adapter must still
provide content digests for the source checkout and runtime image after it has
resolved/builds those artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_RELEASE_PIN_VERSION,
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
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


__all__ = ["NautilusRcCompatibilityRuntime"]
