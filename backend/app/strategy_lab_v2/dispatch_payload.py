"""Authenticated durable payloads for queued Strategy Lab dispatches.

Redis entries intentionally carry only content identities.  This module keeps
the corresponding canonical bytes storage-neutral and gives worker adapters a
small, immutable value to authenticate before handing payloads to execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import (
    canonical_json,
    content_digest,
    freeze_json,
    require_sha256_digest,
)


@dataclass(frozen=True, slots=True)
class DispatchPayload:
    """Immutable canonical payload bytes bound to a content digest."""

    payload_digest: str
    payload_json: str
    byte_length: int

    def __post_init__(self) -> None:
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        if not isinstance(self.payload_json, str) or not self.payload_json.strip():
            raise ValueError("payload_json must not be empty")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool):
            raise ValueError("payload byte_length must be an integer")
        encoded_length = len(self.payload_json.encode("utf-8"))
        if self.byte_length != encoded_length:
            raise ValueError("payload byte_length does not match canonical bytes")
        if _payload_digest(self.payload_json) != self.payload_digest:
            raise ValueError("payload digest does not match canonical bytes")
        value = _decode_payload(self.payload_json)
        if not isinstance(value, Mapping):
            raise ValueError("dispatch payload root must be a mapping")
        if content_digest(value) != self.payload_digest:
            raise ValueError("payload digest does not match decoded content")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DispatchPayload:
        """Canonicalize one API payload without retaining mutable caller data."""

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        frozen = freeze_json(payload)
        if not isinstance(frozen, Mapping):  # pragma: no cover - mapping guard above
            raise TypeError("payload must be a mapping")
        encoded = canonical_json(frozen)
        return cls(
            content_digest(frozen),
            encoded,
            len(encoded.encode("utf-8")),
        )

    @property
    def value(self) -> Mapping[str, Any]:
        """Return a recursively frozen payload reconstructed from its bytes."""

        decoded = freeze_json(_decode_payload(self.payload_json))
        if not isinstance(decoded, Mapping):  # pragma: no cover - constructor guard
            raise ValueError("dispatch payload root must be a mapping")
        if content_digest(decoded) != self.payload_digest:
            raise ValueError("payload digest does not match decoded content")
        return decoded

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class DispatchPayloadLoader(Protocol):
    """Worker-facing lookup contract for content-addressed dispatch payloads."""

    async def load_payload(self, payload_digest: str) -> DispatchPayload | None: ...


def _payload_digest(payload_json: str) -> str:
    return "sha256:" + hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _decode_payload(payload_json: str) -> Any:
    try:
        raw = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("payload bytes are not valid JSON") from error
    decoded = _decode_canonical(raw)
    if canonical_json(decoded) != payload_json:
        raise ValueError("payload bytes are not canonical")
    return decoded


def _decode_canonical(value: Any) -> Any:
    if value == ["null"]:
        return None
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], str):
        raise ValueError("canonical payload value is malformed")
    tag, payload = value
    if tag == "bool":
        if not isinstance(payload, bool):
            raise ValueError("canonical bool payload is malformed")
        return payload
    if tag == "int":
        if not isinstance(payload, str):
            raise ValueError("canonical int payload is malformed")
        try:
            return int(payload)
        except ValueError as error:
            raise ValueError("canonical int payload is malformed") from error
    if tag == "float":
        if not isinstance(payload, str):
            raise ValueError("canonical float payload is malformed")
        try:
            return float.fromhex(payload)
        except ValueError as error:
            raise ValueError("canonical float payload is malformed") from error
    if tag == "str":
        if not isinstance(payload, str):
            raise ValueError("canonical string payload is malformed")
        return payload
    if tag in {"tuple", "list", "set"}:
        if not isinstance(payload, list):
            raise ValueError("canonical sequence payload is malformed")
        decoded = tuple(_decode_canonical(item) for item in payload)
        return decoded if tag != "list" else list(decoded)
    if tag == "mapping":
        if not isinstance(payload, list):
            raise ValueError("canonical mapping payload is malformed")
        values: dict[str, Any] = {}
        for item in payload:
            if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
                raise ValueError("canonical mapping entry is malformed")
            if item[0] in values:
                raise ValueError("canonical mapping contains duplicate keys")
            values[item[0]] = _decode_canonical(item[1])
        if [item[0] for item in payload] != sorted(values):
            raise ValueError("canonical mapping keys are not ordered")
        return MappingProxyType(values)
    if tag == "decimal":
        if not isinstance(payload, str):
            raise ValueError("canonical decimal payload is malformed")
        try:
            sign, digits, exponent = payload.split(":")
            if not digits:
                raise ValueError
            return Decimal((int(sign), tuple(int(item) for item in digits), int(exponent)))
        except (TypeError, ValueError) as error:
            raise ValueError("canonical decimal payload is malformed") from error
    if tag == "datetime":
        if not isinstance(payload, str):
            raise ValueError("canonical datetime payload is malformed")
        try:
            return datetime.fromisoformat(payload.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("canonical datetime payload is malformed") from error
    if tag == "date":
        if not isinstance(payload, str):
            raise ValueError("canonical date payload is malformed")
        try:
            return date.fromisoformat(payload)
        except ValueError as error:
            raise ValueError("canonical date payload is malformed") from error
    raise ValueError(f"unsupported canonical payload tag: {tag}")


__all__ = ["DispatchPayload", "DispatchPayloadLoader"]
