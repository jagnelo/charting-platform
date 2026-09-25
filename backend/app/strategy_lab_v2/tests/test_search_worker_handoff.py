from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.search_worker_handoff import AuthenticatedSearchDispatchMaterializer
from app.strategy_lab_v2.tests.test_worker_process import _request
from app.strategy_lab_v2.worker_handoff import encode_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class DispatchStore:
    def __init__(self, record: SearchDispatchRecord | None) -> None:
        self.record = record
        self.request_fingerprints: list[str] = []

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> SearchDispatchRecord | None:
        self.request_fingerprints.append(request_fingerprint)
        return self.record


def _entry_and_payload(tmp_path: Path) -> tuple[RedisStreamEntry, DispatchPayload, SearchDispatchRecord, WorkerExecutionRequest]:
    execution_request = _request(tmp_path)
    payload = DispatchPayload.from_mapping(encode_worker_handoff(execution_request))
    dispatch_request = DispatchRequest(
        "dispatch-key",
        execution_request.authorization.attempt_id,
        payload.payload_digest,
        "strategy-backtest",
        NOW,
    )
    record = SearchDispatchRecord(
        "owner-1",
        content_digest("experiment"),
        0,
        dispatch_request,
    )
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:strategy-backtest",
        "1-0",
        content_digest("message"),
        dispatch_request.attempt_id,
        dispatch_request.payload_digest,
        dispatch_request.fingerprint,
    )
    return entry, payload, record, execution_request


@pytest.mark.asyncio
async def test_authenticated_materializer_binds_entry_before_decoding(tmp_path: Path) -> None:
    entry, payload, record, expected = _entry_and_payload(tmp_path)
    store = DispatchStore(record)
    materializer = AuthenticatedSearchDispatchMaterializer(
        store,
        queue_name="strategy-backtest",
    )

    actual = await materializer(entry, payload)

    assert actual == expected
    assert store.request_fingerprints == [entry.request_fingerprint]


@pytest.mark.asyncio
async def test_authenticated_materializer_rejects_transport_identity_drift(tmp_path: Path) -> None:
    entry, payload, record, _ = _entry_and_payload(tmp_path)
    store = DispatchStore(record)
    materializer = AuthenticatedSearchDispatchMaterializer(
        store,
        queue_name="strategy-backtest",
    )

    with pytest.raises(ValueError, match="attempt identity"):
        await materializer(replace(entry, attempt_id="different-attempt"), payload)

    with pytest.raises(ValueError, match="queue identity"):
        await AuthenticatedSearchDispatchMaterializer(
            store,
            queue_name="different-queue",
        )(entry, payload)


@pytest.mark.asyncio
async def test_authenticated_materializer_rejects_missing_record_and_handoff_drift(
    tmp_path: Path,
) -> None:
    entry, payload, record, expected = _entry_and_payload(tmp_path)
    missing = AuthenticatedSearchDispatchMaterializer(
        DispatchStore(None),
        queue_name="strategy-backtest",
    )
    with pytest.raises(ValueError, match="not available"):
        await missing(entry, payload)

    drifted = replace(
        expected,
        authorization=replace(expected.authorization, attempt_id="different-attempt"),
    )
    drifted_payload = DispatchPayload.from_mapping(encode_worker_handoff(drifted))
    drifted_record = replace(
        record,
        request=replace(record.request, payload_digest=drifted_payload.payload_digest),
    )
    drifted_entry = replace(
        entry,
        payload_digest=drifted_payload.payload_digest,
        request_fingerprint=drifted_record.request.fingerprint,
    )
    with pytest.raises(ValueError, match="different attempt"):
        await AuthenticatedSearchDispatchMaterializer(
            DispatchStore(drifted_record),
            queue_name="strategy-backtest",
        )(drifted_entry, drifted_payload)
