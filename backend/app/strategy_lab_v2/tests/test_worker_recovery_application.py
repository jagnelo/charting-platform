from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.dispatch import (
    DispatchDecision,
    DispatchRequest,
    DispatchResolution,
    build_dispatch_envelope,
)
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationKind,
    apply_lease_observation,
)
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.recovery import RecoveryReason
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.result_completion import (
    ResultCompletionLedger,
    ResultCompletionRecord,
)
from app.strategy_lab_v2.search_dispatch import (
    SearchDispatchDecision,
    SearchDispatchResolution,
)
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchStateDecision,
    new_search_execution_state,
    record_search_candidate_terminal,
    request_search_cancellation,
    start_search_candidate,
)
from app.strategy_lab_v2.tests.test_worker_process import NOW, _request
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision
from app.strategy_lab_v2.worker_recovery import (
    WorkerRecoveryLedger,
    WorkerRecoveryResolution,
    resolve_worker_recovery,
)
from app.strategy_lab_v2.worker_recovery_application import WorkerRecoveryApplication
from app.strategy_lab_v2.worker_service import WorkerRecoveryContext
from app.strategy_lab_v2.worker_settlement import (
    WorkerSettlementLedger,
    WorkerSettlementRecord,
)
from app.strategy_lab_v2.workers import release_worker_slot


class _DispatchStore:
    def __init__(
        self,
        record: SearchDispatchRecord,
        admission_ledger: ExecutionAdmissionLedger,
    ) -> None:
        self.record = record
        self.admission_ledger = admission_ledger

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> SearchDispatchRecord | None:
        return self.record if request_fingerprint == self.record.request.fingerprint else None

    async def load_admission_ledger(self, *, principal: Any) -> ExecutionAdmissionLedger:
        assert principal == self.record.owner_id
        return self.admission_ledger


class _Resources:
    def __init__(self, attempts: tuple[RunAttempt, ...]) -> None:
        self.attempts = list(attempts)

    async def get_run_attempt_by_attempt_id(
        self, *, principal: Any, attempt_id: str
    ) -> RunAttempt | None:
        assert principal == "owner-1"
        return next((item for item in self.attempts if item.attempt_id == attempt_id), None)

    async def get_run_attempts_for_trial(
        self, *, principal: Any, trial_id: str
    ) -> tuple[RunAttempt, ...]:
        assert principal == "owner-1"
        return tuple(item for item in self.attempts if item.trial_id == trial_id)


class _SearchState:
    def __init__(self, state: Any) -> None:
        self.state = state

    async def load(self, *, principal: Any, experiment_fingerprint: str) -> Any:
        assert principal == "owner-1"
        assert experiment_fingerprint == self.state.experiment_fingerprint
        return self.state

    async def record_terminal(self, **kwargs: Any) -> Any:
        resolution = record_search_candidate_terminal(
            self.state,
            kwargs["candidate_index"],
            attempt_id=kwargs["attempt_id"],
            phase=kwargs["phase"],
            now=kwargs["now"],
            result_fingerprint=kwargs.get("result_fingerprint"),
        )
        if resolution.decision is SearchStateDecision.APPLY:
            self.state = resolution.state
        return resolution


class _RecoveryStore:
    def __init__(self, request: Any) -> None:
        self.ledger = WorkerRecoveryLedger()
        self.request = request

    async def load_ledger(self, *, principal: Any) -> WorkerRecoveryLedger:
        assert principal == "owner-1"
        return self.ledger

    async def recover(self, **kwargs: Any) -> WorkerRecoveryResolution:
        attempts = kwargs["prior_attempts"]
        prior = next(
            (item for item in self.ledger.records if item.attempt_id == attempts[-1].attempt_id),
            None,
        )
        next_attempt_id = kwargs["next_attempt_id"]
        if prior is not None:
            next_attempt_id = prior.next_attempt_id
        resolution = resolve_worker_recovery(
            attempts,
            admission_ledger=kwargs["admission_ledger"],
            lease_state=self.request.lease_state,
            pool=self.request.worker_pool,
            ledger=self.ledger,
            reason=kwargs["reason"],
            observed_at=kwargs["observed_at"],
            next_attempt_id=next_attempt_id,
        )
        if resolution.release_observation is not None:
            self.ledger = resolution.ledger
        return resolution


class _TerminalCompletionStore:
    def __init__(self) -> None:
        self.ledger = ResultCompletionLedger()

    async def load_completion_ledger(self, *, principal: Any) -> ResultCompletionLedger:
        assert principal == "owner-1"
        return self.ledger


class _SettlementStore:
    def __init__(self) -> None:
        self.ledger = WorkerSettlementLedger()

    async def load_ledger(self, *, principal: Any) -> WorkerSettlementLedger:
        assert principal == "owner-1"
        return self.ledger


class _WorkerState:
    def __init__(self, request: Any) -> None:
        self.pool = request.worker_pool
        self.lease = request.lease_state

    async def load_pool(self, _profile: Any) -> Any:
        return self.pool

    async def load_lease(self, _lease_id: str) -> Any:
        return self.lease


class _Persistence:
    def __init__(self, request: Any, record: SearchDispatchRecord, state: Any) -> None:
        self.search_dispatch = _DispatchStore(
            record,
            ExecutionAdmissionLedger((request.admission,)),
        )
        self.resources = _Resources(
            (
                RunAttempt(
                    request.runtime_request.attempt_id,
                    "trial-1",
                    1,
                    AttemptState.QUEUED,
                    NOW,
                ),
            )
        )
        self.search_state = _SearchState(state)
        self.worker_recoveries = _RecoveryStore(request)
        self.result_completion = _TerminalCompletionStore()
        self.worker_settlements = _SettlementStore()
        self.worker_state = _WorkerState(request)

    async def persist_retry_attempt(
        self,
        *,
        principal: Any,
        attempt: RunAttempt,
        recovery_fingerprint: str,
        accepted_at: datetime,
    ) -> RunAttempt:
        assert principal == "owner-1"
        assert recovery_fingerprint.startswith("sha256:")
        assert accepted_at.tzinfo is not None
        existing = next(
            (item for item in self.resources.attempts if item.attempt_id == attempt.attempt_id),
            None,
        )
        if existing is None:
            self.resources.attempts.append(attempt)
        else:
            assert existing == attempt
        return attempt


def _setup(
    tmp_path: Any,
) -> tuple[WorkerRecoveryApplication, WorkerRecoveryContext, _Persistence, list[dict[str, Any]]]:
    request = _request(tmp_path)
    experiment_fingerprint = content_digest("experiment")
    payload_digest = content_digest("payload")
    dispatch_request = DispatchRequest(
        "initial-dispatch",
        request.runtime_request.attempt_id,
        payload_digest,
        "strategy-backtest",
        NOW,
    )
    record = SearchDispatchRecord(
        "owner-1",
        experiment_fingerprint,
        0,
        dispatch_request,
    )
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:backtest",
        "1-0",
        content_digest("redis-message"),
        request.runtime_request.attempt_id,
        payload_digest,
        dispatch_request.fingerprint,
    )
    state = new_search_execution_state(
        experiment_fingerprint,
        (content_digest("trial-fingerprint"),),
        now=NOW,
    )
    state = start_search_candidate(
        state,
        0,
        attempt_id=request.runtime_request.attempt_id,
        now=NOW,
    ).state
    persistence = _Persistence(request, record, state)
    calls: list[dict[str, Any]] = []
    should_fail = True

    async def dispatch_client(**kwargs: Any) -> SearchDispatchResolution:
        nonlocal should_fail
        calls.append(kwargs)
        if should_fail:
            should_fail = False
            raise RuntimeError("simulated interruption after retry persistence")
        intent = kwargs["dispatch_intent"]
        dispatch = DispatchRequest(
            intent.idempotency_key,
            intent.attempt_id,
            content_digest("retry-payload"),
            intent.queue_name,
            intent.created_at,
        )
        started = start_search_candidate(
            persistence.search_state.state,
            kwargs["candidate_index"],
            attempt_id=intent.attempt_id,
            now=intent.created_at,
        )
        if started.decision is SearchStateDecision.APPLY:
            persistence.search_state.state = started.state
        return SearchDispatchResolution(
            SearchDispatchDecision.ENQUEUE,
            persistence.search_state.state,
            persistence.search_dispatch.admission_ledger,
            request.worker_pool,
            DispatchResolution(DispatchDecision.ENQUEUE, dispatch.fingerprint),
            build_dispatch_envelope(dispatch),
        )

    app = WorkerRecoveryApplication(
        persistence,
        queue_name="strategy-backtest",
        dispatch_client=dispatch_client,
    )
    context = WorkerRecoveryContext(
        entry,
        request,
        RecoveryReason.WORKER_CRASH,
        NOW + timedelta(seconds=2),
    )
    return app, context, persistence, calls


def _persist_terminal_success(
    context: WorkerRecoveryContext,
    persistence: _Persistence,
    *,
    released_at: datetime,
    release_capacity: bool,
) -> ResultCompletionRecord:
    request = context.request
    attempt_id = context.entry.attempt_id
    completion = ResultCompletionRecord(
        content_digest("terminal-completion"),
        content_digest("terminal-result"),
        attempt_id,
        content_digest("terminal-runtime"),
        content_digest("terminal-outcome"),
        content_digest("terminal-progress"),
        content_digest("terminal-publication"),
        (),
        released_at,
    )
    persistence.result_completion.ledger = ResultCompletionLedger((completion,))
    observation = LeaseObservation(
        content_digest("terminal-release-observation"),
        request.lease_state.lease.lease_id,
        request.lease_state.lease.worker_id,
        attempt_id,
        1,
        LeaseObservationKind.RELEASE,
        released_at,
    )
    persistence.worker_settlements.ledger = WorkerSettlementLedger(
        (
            WorkerSettlementRecord(
                content_digest("terminal-settlement"),
                request.admission.fingerprint,
                content_digest("terminal-worker-execution"),
                attempt_id,
                request.admission.reservation_id,
                request.admission.worker_id,
                observation.fingerprint,
                released_at,
            ),
        )
    )
    if release_capacity:
        lease_resolution = apply_lease_observation(
            persistence.worker_state.lease,
            observation,
        )
        persistence.worker_state.lease = lease_resolution.state
        persistence.worker_state.pool = release_worker_slot(
            persistence.worker_state.pool,
            reservation_id=request.admission.reservation_id,
            released_at=released_at,
        )
    return completion


@pytest.mark.asyncio
async def test_retry_replay_recovers_crash_between_attempt_persistence_and_dispatch(
    tmp_path: Any,
) -> None:
    app, context, persistence, calls = _setup(tmp_path)

    with pytest.raises(RuntimeError, match="simulated interruption"):
        await app(context)

    assert len(persistence.resources.attempts) == 2
    first_retry = persistence.resources.attempts[-1]
    assert first_retry.trial_id == persistence.resources.attempts[0].trial_id
    assert first_retry.ordinal == 2
    assert persistence.search_state.state.candidates[0].phase is SearchCandidatePhase.FAILED

    result = await app(context)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert len(persistence.resources.attempts) == 2
    assert len(calls) == 2
    assert calls[0]["attempt_id"] == calls[1]["attempt_id"] == first_retry.attempt_id
    assert calls[0]["dispatch_intent"] == calls[1]["dispatch_intent"]
    assert persistence.search_state.state.candidates[0].attempt_id == first_retry.attempt_id
    assert persistence.search_state.state.candidates[0].phase is SearchCandidatePhase.RUNNING


@pytest.mark.asyncio
async def test_terminal_recovery_receipt_replays_and_acknowledges_cancelled_candidate(
    tmp_path: Any,
) -> None:
    app, context, persistence, calls = _setup(tmp_path)
    del calls
    cancelled = request_search_cancellation(
        persistence.search_state.state,
        request_id=content_digest("cancel-search"),
        now=NOW + timedelta(seconds=1),
    )
    persistence.search_state.state = cancelled.state

    first = await app(context)
    replay = await app(context)

    assert first.decision is WorkerHandleDecision.COMPLETE
    assert replay.decision is WorkerHandleDecision.COMPLETE
    assert first.receipt_digest == replay.receipt_digest
    candidate = persistence.search_state.state.candidates[0]
    assert candidate.phase is SearchCandidatePhase.CANCELLED
    assert candidate.attempt_id == context.entry.attempt_id


@pytest.mark.asyncio
async def test_committed_terminal_result_redelivery_closes_candidate_without_retry(
    tmp_path: Any,
) -> None:
    app, context, persistence, calls = _setup(tmp_path)
    released_at = NOW + timedelta(seconds=2)
    completion = _persist_terminal_success(
        context,
        persistence,
        released_at=released_at,
        release_capacity=True,
    )
    observed = replace(context, observed_at=released_at + timedelta(seconds=1))

    result = await app(observed)
    replay = await app(replace(observed, observed_at=released_at + timedelta(seconds=10)))

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert replay.decision is WorkerHandleDecision.COMPLETE
    assert result.receipt_digest == replay.receipt_digest
    assert calls == []
    assert len(persistence.resources.attempts) == 1
    candidate = persistence.search_state.state.candidates[0]
    assert candidate.phase is SearchCandidatePhase.SUCCEEDED
    assert candidate.attempt_id == context.entry.attempt_id
    assert candidate.result_fingerprint == completion.result_fingerprint


@pytest.mark.asyncio
async def test_partial_terminal_completion_stays_pending_without_scheduling_retry(
    tmp_path: Any,
) -> None:
    app, context, persistence, calls = _setup(tmp_path)
    _persist_terminal_success(
        context,
        persistence,
        released_at=NOW + timedelta(seconds=2),
        release_capacity=False,
    )

    result = await app(replace(context, observed_at=NOW + timedelta(seconds=3)))

    assert result.decision is WorkerHandleDecision.RETRY
    assert "capacity release" in (result.rejection_reason or "")
    assert calls == []
    assert len(persistence.resources.attempts) == 1
    assert persistence.search_state.state.candidates[0].phase is SearchCandidatePhase.RUNNING
