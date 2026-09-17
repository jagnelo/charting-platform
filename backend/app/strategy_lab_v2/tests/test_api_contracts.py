from __future__ import annotations

import base64
import json

import pytest

from app.strategy_lab_v2.api_contracts import (
    ApiCursor,
    ApiError,
    ApiErrorCode,
    CursorPage,
)
from app.strategy_lab_v2.canonical import content_digest

SNAPSHOT = content_digest({"snapshot": "one"})


def _cursor() -> ApiCursor:
    return ApiCursor(
        resource="trials",
        snapshot_digest=SNAPSHOT,
        sort_value="2024-01-01T00:00:00Z",
        item_id="trial-1",
    )


def test_cursor_token_is_deterministic_and_round_trips() -> None:
    cursor = _cursor()
    assert cursor.token == _cursor().token
    decoded = ApiCursor.from_token(cursor.token)
    assert decoded == cursor
    assert decoded.token == cursor.token


def test_cursor_tampering_and_malformed_tokens_fail_closed() -> None:
    cursor = _cursor()
    raw = base64.urlsafe_b64decode(cursor.token + "=" * (-len(cursor.token) % 4))
    envelope = json.loads(raw.decode("utf-8"))
    envelope["payload"]["item_id"] = "other-trial"
    tampered = base64.urlsafe_b64encode(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="digest"):
        ApiCursor.from_token(tampered)
    with pytest.raises(ValueError, match="base64 JSON"):
        ApiCursor.from_token("not-a-cursor")


def test_cursor_token_rejects_duplicate_fields_and_non_finite_constants() -> None:
    duplicate = (
        '{"digest":"sha256:'
        + "0" * 64
        + '","digest":"sha256:'
        + "0" * 64
        + '","payload":{}}'
    )
    duplicate_token = base64.urlsafe_b64encode(duplicate.encode("utf-8")).decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="base64 JSON"):
        ApiCursor.from_token(duplicate_token)

    non_finite = (
        '{"digest":"sha256:'
        + "0" * 64
        + '","payload":{"item_id":"trial-1","resource":"trials",'
        '"schema_version":1,"snapshot_digest":"sha256:'
        + "0" * 64
        + '","sort_value":NaN}}'
    )
    non_finite_token = base64.urlsafe_b64encode(non_finite.encode("utf-8")).decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="base64 JSON"):
        ApiCursor.from_token(non_finite_token)


def test_cursor_page_requires_consistent_next_cursor() -> None:
    cursor = _cursor()
    page = CursorPage("trials", ("trial-1",), True, cursor)
    assert page.items == ("trial-1",)
    assert page.fingerprint.startswith("sha256:")
    final = CursorPage("trials", ("trial-2",), False)
    assert final.next_cursor is None
    with pytest.raises(ValueError, match="requires next_cursor"):
        CursorPage("trials", (), True)
    with pytest.raises(ValueError, match="page resource"):
        CursorPage("attempts", (), True, cursor)
    with pytest.raises(ValueError, match="final page"):
        CursorPage("trials", (), False, cursor)


def test_api_error_is_typed_immutable_and_fingerprinted() -> None:
    error = ApiError(
        code=ApiErrorCode.CAPABILITY_UNSUPPORTED,
        message="requested product is not supported",
        request_id="request-1",
        status_code=422,
        details={"product_class": "option", "reason": "missing model"},
    )
    assert error.type == "capability_unsupported"
    assert error.details["product_class"] == "option"
    assert error.fingerprint.startswith("sha256:")
    with pytest.raises(TypeError):
        error.details["reason"] = "changed"  # type: ignore[index]


def test_api_contract_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="status"):
        ApiError(ApiErrorCode.CONFLICT, "conflict", "request-1", 200)
    with pytest.raises(ValueError, match="snapshot_digest"):
        ApiCursor("trials", "bad", "sort", "trial-1")
    with pytest.raises(ValueError, match="more items"):
        CursorPage("trials", (), True)
