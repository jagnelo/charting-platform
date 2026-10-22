from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.forward_worker_handoff import (
    AuthenticatedForwardEventDispatchMaterializer,
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class DispatchStore:
    def __init__(self, record: ForwardEventDispatchRecord | None) -> None:
        self.record = record
        self.request_fingerprints: list[str] = []

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> ForwardEventDispatchRecord | None:
        self.request_fingerprints.append(request_fingerprint)
        return self.record


def _entry_and_payload() -> tuple[
    RedisStreamEntry,
    DispatchPayload,
    ForwardEventDispatchRecord,
    ForwardEventWorkItem,
]:
    event_fingerprint = content_digest("canonical-live-event")
    payload = DispatchPayload.from_mapping(
        {
            "event_fingerprint": event_fingerprint,
            "replay_plan_fingerprint": None,
        }
    )
    request = DispatchRequest(
        "forward-dispatch-key",
        "forward-instance-1",
        payload.payload_digest,
        "forward-events",
        NOW,
    )
    record = ForwardEventDispatchRecord(
        "owner-1",
        "forward-instance-1",
        event_fingerprint,
        request,
    )
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:forward-events",
        "1-0",
        content_digest("message"),
        request.attempt_id,
        request.payload_digest,
        request.fingerprint,
    )
    return entry, payload, record, ForwardEventWorkItem(
        record,
        ForwardEventDispatchPayload(event_fingerprint),
    )


@pytest.mark.asyncio
async def test_authenticated_forward_materializer_binds_transport_and_payload() -> None:
    entry, payload, record, expected = _entry_and_payload()
    store = DispatchStore(record)
    materializer = AuthenticatedForwardEventDispatchMaterializer(
        store,
        queue_name="forward-events",
    )

    actual = await materializer(entry, payload)

    assert actual == expected
    assert store.request_fingerprints == [entry.request_fingerprint]


@pytest.mark.asyncio
async def test_authenticated_forward_materializer_rejects_identity_drift() -> None:
    entry, payload, record, _ = _entry_and_payload()
    store = DispatchStore(record)
    materializer = AuthenticatedForwardEventDispatchMaterializer(
        store,
        queue_name="forward-events",
    )

    with pytest.raises(ValueError, match="instance identity"):
        await materializer(replace(entry, attempt_id="other-instance"), payload)

    with pytest.raises(ValueError, match="queue identity"):
        await AuthenticatedForwardEventDispatchMaterializer(
            store,
            queue_name="other-queue",
        )(entry, payload)


@pytest.mark.asyncio
async def test_authenticated_forward_materializer_rejects_missing_or_mismatched_record() -> None:
    entry, payload, record, _ = _entry_and_payload()
    with pytest.raises(ValueError, match="not available"):
        await AuthenticatedForwardEventDispatchMaterializer(
            DispatchStore(None),
            queue_name="forward-events",
        )(entry, payload)

    mismatched = replace(record, event_fingerprint=content_digest("other-event"))
    with pytest.raises(ValueError, match="event identity"):
        await AuthenticatedForwardEventDispatchMaterializer(
            DispatchStore(mismatched),
            queue_name="forward-events",
        )(entry, payload)
