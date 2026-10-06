"""Durable content-addressed receipt for a verified Nautilus equity trace."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.strategy_lab_v2.artifacts import artifact_content_digest, verify_artifact_payload
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceReference

NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.nautilus-equity-trace-receipt+json"
)
NAUTILUS_EQUITY_TRACE_RECEIPT_SCHEMA = "strategy-lab.nautilus-equity-trace-receipt.v1"


def _canonical_wire_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class NautilusEquityTraceReceiptArtifact:
    """Small immutable artifact retaining the full scope of one verified trace."""

    manifest: ArtifactManifest
    reference: NautilusAccountEquityTraceReference
    payload: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(self.reference, NautilusAccountEquityTraceReference):
            raise TypeError("reference must be a NautilusAccountEquityTraceReference")
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")
        if (
            self.manifest.media_type != NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE
            or self.manifest.schema_version != NAUTILUS_EQUITY_TRACE_RECEIPT_SCHEMA
            or self.manifest.retention_class is not ArtifactRetention.PINNED_RESULT
        ):
            raise ValueError("equity trace receipt artifact identity is unsupported")
        integrity = verify_artifact_payload(self.manifest, self.payload)
        if not integrity.verified:
            raise ValueError("equity trace receipt bytes differ from their manifest")
        decoded = decode_nautilus_equity_trace_receipt(self.manifest, self.payload)
        if decoded != self.reference:
            raise ValueError("equity trace receipt bytes differ from their typed reference")


def build_nautilus_equity_trace_receipt(
    reference: NautilusAccountEquityTraceReference,
) -> NautilusEquityTraceReceiptArtifact:
    """Encode a previously verified trace reference as a pinned result artifact."""

    if not isinstance(reference, NautilusAccountEquityTraceReference):
        raise TypeError("reference must be a NautilusAccountEquityTraceReference")
    payload = _canonical_wire_json(
        {"reference": reference.to_wire(), "schema": NAUTILUS_EQUITY_TRACE_RECEIPT_SCHEMA}
    )
    digest = artifact_content_digest(payload)
    manifest = ArtifactManifest(
        content_digest=digest,
        byte_length=len(payload),
        media_type=NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE,
        schema_version=NAUTILUS_EQUITY_TRACE_RECEIPT_SCHEMA,
        storage_key=digest,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    return NautilusEquityTraceReceiptArtifact(manifest, reference, payload)


def decode_nautilus_equity_trace_receipt(
    manifest: ArtifactManifest,
    payload: bytes,
) -> NautilusAccountEquityTraceReference:
    """Verify and decode a persisted trace receipt without inferring its scope."""

    if not isinstance(manifest, ArtifactManifest):
        raise TypeError("manifest must be an ArtifactManifest")
    if (
        manifest.media_type != NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE
        or manifest.schema_version != NAUTILUS_EQUITY_TRACE_RECEIPT_SCHEMA
        or manifest.retention_class is not ArtifactRetention.PINNED_RESULT
    ):
        raise ValueError("artifact is not a supported pinned equity trace receipt")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    integrity = verify_artifact_payload(manifest, payload)
    if not integrity.verified:
        raise ValueError("equity trace receipt bytes differ from their manifest")
    try:
        document: Any = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("equity trace receipt is not valid JSON") from error
    if (
        not isinstance(document, dict)
        or set(document) != {"reference", "schema"}
        or document["schema"] != NAUTILUS_EQUITY_TRACE_RECEIPT_SCHEMA
        or _canonical_wire_json(document) != payload
    ):
        raise ValueError("equity trace receipt payload is not canonical or has an invalid schema")
    return NautilusAccountEquityTraceReference.from_wire(document["reference"])


__all__ = [
    "NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE",
    "NAUTILUS_EQUITY_TRACE_RECEIPT_SCHEMA",
    "NautilusEquityTraceReceiptArtifact",
    "build_nautilus_equity_trace_receipt",
    "decode_nautilus_equity_trace_receipt",
]
