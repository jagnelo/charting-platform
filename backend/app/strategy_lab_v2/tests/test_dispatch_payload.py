from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload


def test_dispatch_payload_round_trips_immutable_canonical_values() -> None:
    payload = {"symbol": "AAPL", "parameters": {"threshold": Decimal("1.25")}}
    record = DispatchPayload.from_mapping(payload)

    assert record.payload_digest == content_digest(payload)
    assert record.payload_json == canonical_json(payload)
    assert record.byte_length == len(record.payload_json.encode("utf-8"))
    assert record.value["symbol"] == "AAPL"
    assert record.value["parameters"]["threshold"] == Decimal("1.25")
    assert record.fingerprint.startswith("sha256:")


def test_dispatch_payload_rejects_tampered_bytes_and_non_object_roots() -> None:
    record = DispatchPayload.from_mapping({"symbol": "AAPL"})
    with pytest.raises(ValueError, match="digest"):
        DispatchPayload(record.payload_digest, canonical_json({"symbol": "MSFT"}), record.byte_length)

    list_json = canonical_json(["not", "an", "object"])
    with pytest.raises(ValueError, match="root must be a mapping"):
        DispatchPayload(content_digest(["not", "an", "object"]), list_json, len(list_json.encode()))


def test_dispatch_payload_rejects_noncanonical_or_duplicate_mapping_bytes() -> None:
    record = DispatchPayload.from_mapping({"symbol": "AAPL"})
    with pytest.raises(ValueError, match="canonical"):
        DispatchPayload(
            record.payload_digest,
            record.payload_json.replace("AAPL", "MSFT"),
            len(record.payload_json.replace("AAPL", "MSFT").encode()),
        )

    duplicate = '["mapping",[["symbol",["str","AAPL"]],["symbol",["str","AAPL"]]]]'
    with pytest.raises(ValueError, match="duplicate"):
        digest = "sha256:" + hashlib.sha256(duplicate.encode()).hexdigest()
        DispatchPayload(digest, duplicate, len(duplicate.encode()))
