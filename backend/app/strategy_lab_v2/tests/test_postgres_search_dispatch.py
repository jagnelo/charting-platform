from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.postgres_search_dispatch import (
    PostgresSearchDispatchAdapter,
    PostgresSearchDispatchSchema,
)
from app.strategy_lab_v2.postgres_search_state import PostgresSearchStateAdapter
from app.strategy_lab_v2.postgres_worker_state import PostgresWorkerStateAdapter
from app.strategy_lab_v2.search_dispatch import SearchDispatchDecision
from app.strategy_lab_v2.search_state import new_search_execution_state
from app.strategy_lab_v2.tests.test_admission import _fixture, _reservation

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
EXPERIMENT = content_digest("experiment")


class FakeResult:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return iter(self._rows)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    """SQL-shape fake covering all rows touched by the atomic adapter."""

    def __init__(self) -> None:
        self.searches: dict[tuple[str, str], dict[str, Any]] = {}
        self.candidates: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.reservations: dict[str, dict[str, Any]] = {}
        self.admissions: dict[tuple[str, str], dict[str, Any]] = {}
        self.dispatches: dict[tuple[str, str], dict[str, Any]] = {}
        self.outboxes: dict[str, dict[str, Any]] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        normalized = sql.lstrip()
        if "FROM strategy_lab_v2_search_states" in sql:
            row = self.searches.get((values["owner_id"], values["experiment_fingerprint"]))
            return FakeResult([] if row is None else [row])
        if "FROM strategy_lab_v2_search_candidates" in sql:
            rows = [
                row
                for (owner, experiment, _), row in self.candidates.items()
                if owner == values["owner_id"] and experiment == values["experiment_fingerprint"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["candidate_index"]))
        if normalized.startswith("SELECT worker_id"):
            row = self.profiles.get(values["worker_id"])
            return FakeResult([] if row is None else [row])
        if normalized.startswith("SELECT reservation_id"):
            rows = [
                row
                for row in self.reservations.values()
                if row["worker_id"] == values["worker_id"]
                and row.get("reservation_id") == values.get("reservation_id", row["reservation_id"])
            ]
            return FakeResult(sorted(rows, key=lambda row: row["reservation_id"]))
        if "FROM strategy_lab_v2_execution_admissions" in sql:
            rows = [row for (owner, _), row in self.admissions.items() if owner == values["owner_id"]]
            return FakeResult(sorted(rows, key=lambda row: row["request_fingerprint"]))
        if "FROM strategy_lab_v2_search_dispatches" in sql:
            rows = [
                row
                for (owner, _), row in self.dispatches.items()
                if owner == values["owner_id"]
                and row["experiment_fingerprint"] == values["experiment_fingerprint"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["request_fingerprint"]))
        if normalized.startswith("INSERT INTO strategy_lab_v2_search_states"):
            key = (values["owner_id"], values["experiment_fingerprint"])
            if key in self.searches:
                return FakeResult(rowcount=0)
            self.searches[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_search_candidates"):
            key = (values["owner_id"], values["experiment_fingerprint"], values["candidate_index"])
            if key in self.candidates:
                return FakeResult(rowcount=0)
            self.candidates[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_worker_profiles"):
            if values["worker_id"] in self.profiles:
                return FakeResult(rowcount=0)
            self.profiles[values["worker_id"]] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_worker_reservations"):
            if values["reservation_id"] in self.reservations:
                return FakeResult(rowcount=0)
            self.reservations[values["reservation_id"]] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_execution_admissions"):
            key = (values["owner_id"], values["request_fingerprint"])
            if key in self.admissions:
                return FakeResult(rowcount=0)
            self.admissions[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_search_dispatches"):
            key = (values["owner_id"], values["idempotency_key"])
            if key in self.dispatches:
                return FakeResult(rowcount=0)
            self.dispatches[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_execution_outbox"):
            key = values["message_id"]
            if key in self.outboxes:
                return FakeResult(rowcount=0)
            self.outboxes[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "strategy_lab_v2_search_candidates" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"], values["candidate_index"])
            row = self.candidates.get(key)
            if row is None or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            self.candidates[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "strategy_lab_v2_search_states" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"])
            row = self.searches.get(key)
            if row is None or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            self.searches[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_postgres_search_dispatch_stages_and_replays_all_rows_atomically() -> None:
    session = FakeSession()
    search_state = PostgresSearchStateAdapter(lambda: session)
    worker_state = PostgresWorkerStateAdapter(lambda: session)
    adapter = PostgresSearchDispatchAdapter(
        lambda: session, search_state=search_state, worker_state=worker_state
    )
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    await search_state.initialize(
        principal="owner-1",
        state=new_search_execution_state(
            EXPERIMENT, (content_digest("trial-1"),), now=NOW
        ),
    )
    await worker_state.ensure_profile(pool.profile)
    request = DispatchRequest(
        "dispatch-key",
        authorization.attempt_id,
        content_digest("payload"),
        "strategy-backtest",
        NOW,
    )

    first = await adapter.dispatch(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id=authorization.attempt_id,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        reservation_id=_reservation("one"),
        dispatch_request=request,
        now=NOW,
    )
    assert first.decision is SearchDispatchDecision.ENQUEUE
    assert len(session.admissions) == 1
    assert len(session.reservations) == 1
    assert len(session.dispatches) == 1
    assert len(session.outboxes) == 1
    assert session.candidates[("owner-1", EXPERIMENT, 0)]["phase"] == "running"

    replay = await adapter.dispatch(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id=authorization.attempt_id,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        reservation_id=_reservation("one"),
        dispatch_request=request,
        now=NOW,
    )
    assert replay.decision is SearchDispatchDecision.REPLAY_EXISTING
    assert len(session.admissions) == 1
    assert len(session.reservations) == 1
    assert len(session.dispatches) == 1
    assert len(session.outboxes) == 1


def test_postgres_search_dispatch_schema_is_additive_and_safe() -> None:
    schema = PostgresSearchDispatchSchema()
    assert len(schema.statements) == 2
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresSearchDispatchSchema(dispatch_table="unsafe;drop")
