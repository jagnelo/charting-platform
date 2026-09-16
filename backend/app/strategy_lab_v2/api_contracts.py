"""Engine-neutral REST boundary values for Strategy Lab v2.

The application router and persistence adapters are intentionally out of scope
for this package.  These immutable values keep cursor pagination and typed
errors stable across those future integrations.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class ApiErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    AUTHORIZATION_REQUIRED = "authorization_required"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    CAPABILITY_UNSUPPORTED = "capability_unsupported"
    PRECONDITION_FAILED = "precondition_failed"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class ApiError:
    """Stable machine-readable error returned by a future v2 route."""

    code: ApiErrorCode
    message: str
    request_id: str
    status_code: int
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, ApiErrorCode):
            raise TypeError("code must be an ApiErrorCode")
        _nonempty(self.message, "message")
        _nonempty(self.request_id, "request_id")
        if (
            not isinstance(self.status_code, int)
            or isinstance(self.status_code, bool)
            or not 400 <= self.status_code <= 599
        ):
            raise ValueError("status_code must be an HTTP error status")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")
        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")
        frozen_details = freeze_json(self.details)
        if not isinstance(frozen_details, Mapping):
            raise TypeError("details must be a mapping")
        object.__setattr__(self, "details", frozen_details)

    @property
    def type(self) -> str:
        """Expose the stable error code for JSON:API/problem-style adapters."""

        return self.code.value

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ApiCursor:
    """Opaque, deterministic cursor bound to a resource snapshot."""

    resource: str
    snapshot_digest: str
    sort_value: str
    item_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("resource", "sort_value", "item_id"):
            _nonempty(getattr(self, name), name)
        require_sha256_digest(self.snapshot_digest, field_name="snapshot_digest")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version < 1
        ):
            raise ValueError("schema_version must be a positive integer")

    def _payload(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "resource": self.resource,
            "schema_version": self.schema_version,
            "snapshot_digest": self.snapshot_digest,
            "sort_value": self.sort_value,
        }

    @property
    def token(self) -> str:
        """Return a URL-safe opaque token with an accidental-tamper checksum.

        The checksum is an integrity aid, not an authentication mechanism.  A
        route must still validate authorization and snapshot ownership.
        """

        envelope = {"digest": content_digest(self._payload()), "payload": self._payload()}
        encoded = json.dumps(
            envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")

    @classmethod
    def from_token(cls, token: str) -> ApiCursor:
        if not isinstance(token, str) or not token.strip():
            raise ValueError("cursor token must not be empty")
        padded = token + "=" * (-len(token) % 4)
        try:
            decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
            envelope = json.loads(decoded.decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("cursor token is not valid base64 JSON") from error
        if not isinstance(envelope, Mapping) or set(envelope) != {"digest", "payload"}:
            raise ValueError("cursor token envelope is invalid")
        payload = envelope["payload"]
        digest = envelope["digest"]
        if not isinstance(payload, Mapping) or not isinstance(digest, str):
            raise ValueError("cursor token payload is invalid")
        require_sha256_digest(digest, field_name="cursor digest")
        payload_dict = dict(payload)
        if digest != content_digest(payload_dict):
            raise ValueError("cursor token digest does not match its payload")
        if set(payload_dict) != {
            "item_id",
            "resource",
            "schema_version",
            "snapshot_digest",
            "sort_value",
        }:
            raise ValueError("cursor token payload fields are invalid")
        return cls(
            resource=payload_dict["resource"],
            snapshot_digest=payload_dict["snapshot_digest"],
            sort_value=payload_dict["sort_value"],
            item_id=payload_dict["item_id"],
            schema_version=payload_dict["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class CursorPage:
    """A stable page envelope; adapters supply already-authorized items."""

    resource: str
    items: tuple[Any, ...]
    has_more: bool
    next_cursor: ApiCursor | None = None

    def __post_init__(self) -> None:
        _nonempty(self.resource, "resource")
        if not isinstance(self.items, tuple):
            object.__setattr__(self, "items", tuple(self.items))
        if not isinstance(self.has_more, bool):
            raise TypeError("has_more must be a boolean")
        if self.next_cursor is not None:
            if not isinstance(self.next_cursor, ApiCursor):
                raise TypeError("next_cursor must be an ApiCursor")
            if self.next_cursor.resource != self.resource:
                raise ValueError("next_cursor must reference the page resource")
        if self.has_more and self.next_cursor is None:
            raise ValueError("a page with more items requires next_cursor")
        if not self.has_more and self.next_cursor is not None:
            raise ValueError("a final page must not expose next_cursor")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)
