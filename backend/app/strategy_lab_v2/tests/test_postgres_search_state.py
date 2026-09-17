from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_search_state import (
    PostgresSearchStateAdapter,
    PostgresSearchStateSchema,
)
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchStateDecision,
    new_search_execution_state,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
EXPERIMENT = content_digest("experiment")
TRIALS = (content_digest("trial-1"), content_digest("trial-2"))


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
    def __init__(self) -> None:
        self.searches: dict[tuple[str, str], dict[str, Any]] = {}
        self.candidates: dict[tuple[str, str, int], dict[str, Any]] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
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
        if sql.lstrip().startswith("INSERT INTO") and "cancellation_requested" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"])
            if key in self.searches:
                return FakeResult(rowcount=0)
            self.searches[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "candidate_index" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"], values["candidate_index"])
            if key in self.candidates:
                return FakeResult(rowcount=0)
            self.candidates[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE") and "candidate_index" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"], values["candidate_index"])
            row = self.candidates.get(key)
            if row is None or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            self.candidates[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE") and "cancellation_requested" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"])
            row = self.searches.get(key)
            if row is None or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            self.searches[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _state():
    return new_search_execution_state(EXPERIMENT, TRIALS, now=NOW)


@pytest.mark.asyncio
async def test_search_state_adapter_registers_loads_and_replays() -> None:
    session = FakeSession()
    adapter = PostgresSearchStateAdapter(lambda: session)
    state = _state()
    created = await adapter.initialize(principal="owner-1", state=state)
    assert created.decision is SearchStateDecision.APPLY
    replay = await adapter.initialize(principal="owner-1", state=state)
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    loaded = await adapter.load(principal="owner-1", experiment_fingerprint=EXPERIMENT)
    assert loaded == state


@pytest.mark.asyncio
async def test_search_state_adapter_persists_candidate_terminal_and_cancel_transitions() -> None:
    session = FakeSession()
    adapter = PostgresSearchStateAdapter(lambda: session)
    await adapter.initialize(principal="owner-1", state=_state())
    started = await adapter.start_candidate(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id="attempt-1",
        now=NOW + timedelta(seconds=1),
    )
    assert started.decision is SearchStateDecision.APPLY
    replay = await adapter.start_candidate(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id="attempt-1",
        now=NOW + timedelta(seconds=1),
    )
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    terminal = await adapter.record_terminal(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.SUCCEEDED,
        now=NOW + timedelta(seconds=2),
        result_fingerprint=content_digest("result"),
    )
    assert terminal.decision is SearchStateDecision.APPLY
    cancelled = await adapter.cancel(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        request_id=content_digest("cancel"),
        now=NOW + timedelta(seconds=3),
    )
    assert cancelled.decision is SearchStateDecision.APPLY
    cancel_replay = await adapter.cancel(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        request_id=content_digest("cancel"),
        now=NOW + timedelta(seconds=4),
    )
    assert cancel_replay.decision is SearchStateDecision.REPLAY_EXISTING
    loaded = await adapter.load(principal="owner-1", experiment_fingerprint=EXPERIMENT)
    assert loaded is not None
    assert loaded.cancellation_requested
    assert loaded.candidates[0].phase is SearchCandidatePhase.SUCCEEDED


@pytest.mark.asyncio
async def test_search_state_adapter_rejects_tampered_candidate_and_conflicting_definition() -> None:
    session = FakeSession()
    adapter = PostgresSearchStateAdapter(lambda: session)
    state = _state()
    await adapter.initialize(principal="owner-1", state=state)
    session.candidates[("owner-1", EXPERIMENT, 0)]["state_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="candidate fingerprint"):
        await adapter.load(principal="owner-1", experiment_fingerprint=EXPERIMENT)


def test_search_state_schema_is_explicit_and_safe() -> None:
    schema = PostgresSearchStateSchema()
    assert len(schema.statements) == 2
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresSearchStateSchema(candidate_table="unsafe;drop")
