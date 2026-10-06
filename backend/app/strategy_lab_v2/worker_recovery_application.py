"""Authenticated application orchestration for durable worker recovery."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.lease_observations import (
    LeaseObservationKind,
    LeaseObservationState,
)
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.recovery import RecoveryDisposition, RecoveryReason
from app.strategy_lab_v2.result_completion import ResultCompletionLedger
from app.strategy_lab_v2.search_dispatch import SearchDispatchDecision, SearchDispatchResolution
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchStateDecision,
)
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.worker_recovery import (
    WorkerRecoveryDecision,
    WorkerRecoveryRecord,
    WorkerRecoveryResolution,
)
from app.strategy_lab_v2.worker_service import WorkerRecoveryContext
from app.strategy_lab_v2.worker_settlement import WorkerSettlementLedger

SearchDispatchClient = Callable[..., Awaitable[SearchDispatchResolution]]


class WorkerRecoveryApplication:
    """Turn an authenticated process failure into a durable same-trial retry.

    Recovery receipts, immutable retry-attempt resources, search candidate
    transitions, and the search dispatch/outbox are intentionally idempotent
    across separate transactions. Redis acknowledges the failed entry only
    after the terminal recovery receipt or replacement dispatch is durable.
    """

    def __init__(
        self,
        persistence: Any,
        *,
        queue_name: str,
        dispatch_client: SearchDispatchClient,
    ) -> None:
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        if not callable(dispatch_client):
            raise TypeError("dispatch_client must be callable")
        self._persistence = persistence
        self._queue_name = queue_name.strip()
        self._dispatch_client = dispatch_client

    async def __call__(self, context: WorkerRecoveryContext) -> WorkerHandleResult:
        if not isinstance(context, WorkerRecoveryContext):
            raise TypeError("context must be a WorkerRecoveryContext")

        request = context.request
        attempt_id = request.runtime_request.attempt_id
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            return _retry(context, "worker recovery attempt does not match its dispatch")
        dispatch = await _dispatch_for_entry(
            self._persistence.search_dispatch,
            context.entry,
            attempt_id=attempt_id,
        )
        if not isinstance(dispatch, SearchDispatchRecord):
            return _retry(context, "authenticated worker dispatch was not found")
        if dispatch.request.attempt_id != attempt_id:
            return _retry(context, "authenticated dispatch references a different attempt")

        completed = await self._complete_committed_terminal(
            entry=context.entry,
            request=request,
            observed_at=context.observed_at,
            dispatch=dispatch,
        )
        if completed is not None:
            return completed

        attempt = await self._persistence.resources.get_run_attempt_by_attempt_id(
            principal=dispatch.owner_id,
            attempt_id=attempt_id,
        )
        if not isinstance(attempt, RunAttempt):
            return _retry(context, "authenticated attempt resource was not found")
        attempts = await self._persistence.resources.get_run_attempts_for_trial(
            principal=dispatch.owner_id,
            trial_id=attempt.trial_id,
        )
        chain = _attempt_chain_through(attempts, attempt)

        search_state = await self._persistence.search_state.load(
            principal=dispatch.owner_id,
            experiment_fingerprint=dispatch.experiment_fingerprint,
        )
        if search_state is None or dispatch.candidate_index >= len(search_state.candidates):
            return _retry(context, "search candidate state is unavailable")
        candidate = search_state.candidates[dispatch.candidate_index]
        receipt_ledger = await self._persistence.worker_recoveries.load_ledger(
            principal=dispatch.owner_id
        )
        existing = next(
            (record for record in receipt_ledger.records if record.attempt_id == attempt_id),
            None,
        )
        reason = existing.reason if existing is not None else context.reason
        if existing is None and search_state.cancellation_requested:
            reason = RecoveryReason.CANCELLED
        observed_at = existing.released_at if existing is not None else context.observed_at
        latest = chain[-1]
        if latest.updated_at is not None and latest.updated_at > observed_at:
            return _retry(context, "worker clock precedes the persisted attempt update")
        normalized_chain = _terminalize_recovered_attempts(chain, receipt_ledger.records)
        current = normalized_chain[-1]
        if current.state in {AttemptState.QUEUED, AttemptState.RUNNING}:
            terminal_state = (
                AttemptState.CANCELLED
                if reason is RecoveryReason.CANCELLED
                else AttemptState.FAILED
            )
            normalized_chain = normalized_chain[:-1] + (
                replace(current, state=terminal_state, updated_at=observed_at),
            )

        admission_ledger = await self._persistence.search_dispatch.load_admission_ledger(
            principal=dispatch.owner_id
        )
        if not any(item == request.admission for item in admission_ledger.admissions):
            return _retry(context, "worker admission does not match its persisted receipt")
        next_attempt_id = (
            None
            if existing is not None
            else _retry_attempt_id(dispatch.request.fingerprint, attempt_id, reason)
        )
        recovery = await self._persistence.worker_recoveries.recover(
            principal=dispatch.owner_id,
            prior_attempts=normalized_chain,
            admission_ledger=admission_ledger,
            profile=request.worker_pool.profile,
            lease_id=request.lease_state.lease.lease_id,
            reason=reason,
            observed_at=observed_at,
            next_attempt_id=next_attempt_id,
        )
        if not isinstance(recovery, WorkerRecoveryResolution):
            return _retry(context, "worker recovery adapter returned an invalid resolution")
        if recovery.decision in {WorkerRecoveryDecision.REJECT, WorkerRecoveryDecision.CONFLICT}:
            return _retry(context, "worker recovery receipt could not be applied")
        receipt = _receipt_for_attempt(recovery, attempt_id)
        if receipt is None:
            return _retry(context, "worker recovery did not return its durable receipt")

        if recovery.decision is WorkerRecoveryDecision.NOOP or (
            recovery.decision is WorkerRecoveryDecision.REPLAY_EXISTING
            and recovery.plan is not None
            and recovery.plan.disposition is RecoveryDisposition.NOOP
        ):
            if candidate.phase is SearchCandidatePhase.SUCCEEDED:
                return _complete(context, receipt, None)
            return _retry(context, "successful attempt has no terminal search receipt")

        if recovery.decision is WorkerRecoveryDecision.TERMINAL or (
            recovery.decision is WorkerRecoveryDecision.REPLAY_EXISTING
            and recovery.plan is not None
            and recovery.plan.disposition is RecoveryDisposition.TERMINAL
        ):
            phase = (
                SearchCandidatePhase.CANCELLED
                if receipt.reason is RecoveryReason.CANCELLED
                else SearchCandidatePhase.FAILED
            )
            terminal = await self._record_prior_terminal(
                context=context,
                owner_id=dispatch.owner_id,
                dispatch=dispatch,
                prior_attempt_id=attempt_id,
                phase=phase,
                terminal_at=receipt.released_at,
                allowed_next_attempt_id=None,
                allowed_next_attempt_ordinal=None,
            )
            if not terminal:
                return _retry(context, "terminal recovery could not close its search candidate")
            return _complete(context, receipt, None)

        if (
            recovery.decision
            not in {
                WorkerRecoveryDecision.RETRY_SCHEDULED,
                WorkerRecoveryDecision.REPLAY_EXISTING,
            }
            or recovery.next_attempt is None
        ):
            return _retry(context, "worker recovery did not produce a retry attempt")
        retry_attempt = recovery.next_attempt
        if (
            retry_attempt.trial_id != attempt.trial_id
            or retry_attempt.ordinal != attempt.ordinal + 1
        ):
            return _retry(context, "worker recovery changed the immutable trial lineage")
        persisted = await self._persistence.persist_retry_attempt(
            principal=dispatch.owner_id,
            attempt=retry_attempt,
            recovery_fingerprint=receipt.recovery_fingerprint,
            accepted_at=receipt.released_at,
        )
        if persisted != retry_attempt:
            return _retry(context, "persisted retry attempt differs from its recovery receipt")

        terminal = await self._record_prior_terminal(
            context=context,
            owner_id=dispatch.owner_id,
            dispatch=dispatch,
            prior_attempt_id=attempt_id,
            phase=SearchCandidatePhase.FAILED,
            terminal_at=receipt.released_at,
            allowed_next_attempt_id=retry_attempt.attempt_id,
            allowed_next_attempt_ordinal=retry_attempt.ordinal,
        )
        if not terminal:
            return _retry(context, "failed attempt could not be closed before retry dispatch")

        intent = SearchDispatchIntent(
            idempotency_key=f"worker-retry:{receipt.recovery_fingerprint}",
            attempt_id=retry_attempt.attempt_id,
            queue_name=self._queue_name,
            created_at=receipt.released_at,
        )
        dispatch_resolution = await self._dispatch_client(
            principal=dispatch.owner_id,
            request_id=_retry_request_id(receipt.recovery_fingerprint),
            experiment_fingerprint=dispatch.experiment_fingerprint,
            candidate_index=dispatch.candidate_index,
            attempt_id=retry_attempt.attempt_id,
            dispatch_intent=intent,
        )
        if not isinstance(dispatch_resolution, SearchDispatchResolution):
            return _retry(context, "retry dispatch returned an invalid resolution")
        if dispatch_resolution.decision not in {
            SearchDispatchDecision.ENQUEUE,
            SearchDispatchDecision.REPLAY_EXISTING,
        }:
            return _retry(context, "retry dispatch has not been durably accepted")
        return _complete(context, receipt, retry_attempt.attempt_id, dispatch_resolution)

    async def complete_terminal_if_persisted(
        self,
        *,
        entry: Any,
        request: Any,
        observed_at: datetime,
    ) -> WorkerHandleResult | None:
        """Finalize search state from a fully committed successful terminal result.

        The normal terminal callback invokes this before Redis acknowledgement;
        the recovery callback invokes the same idempotent operation when an
        acknowledged terminal write is later redelivered under its released
        lease. A completion record without its terminal settlement/release is
        deliberately left pending rather than being mistaken for a retryable
        infrastructure failure.
        """

        attempt_id = getattr(getattr(request, "runtime_request", None), "attempt_id", None)
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise TypeError("request must expose a runtime attempt_id")
        dispatch = await _dispatch_for_entry(
            self._persistence.search_dispatch,
            entry,
            attempt_id=attempt_id,
        )
        if not isinstance(dispatch, SearchDispatchRecord):
            return _retry_entry(entry, "authenticated worker dispatch was not found")
        if dispatch.request.attempt_id != attempt_id:
            return _retry_entry(entry, "authenticated dispatch references a different attempt")
        return await self._complete_committed_terminal(
            entry=entry,
            request=request,
            observed_at=observed_at,
            dispatch=dispatch,
        )

    async def _complete_committed_terminal(
        self,
        *,
        entry: Any,
        request: Any,
        observed_at: datetime,
        dispatch: SearchDispatchRecord,
    ) -> WorkerHandleResult | None:
        owner_id = dispatch.owner_id
        attempt_id = dispatch.request.attempt_id
        completion_ledger = await self._persistence.result_completion.load_completion_ledger(
            principal=owner_id
        )
        if not isinstance(completion_ledger, ResultCompletionLedger):
            return _retry_entry(entry, "terminal completion ledger is unavailable")
        completion = next(
            (record for record in completion_ledger.records if record.attempt_id == attempt_id),
            None,
        )
        if completion is None:
            return None
        if completion.completed_at > observed_at:
            return _retry_entry(entry, "terminal completion is newer than the worker observation")

        settlement_ledger = await self._persistence.worker_settlements.load_ledger(
            principal=owner_id
        )
        if not isinstance(settlement_ledger, WorkerSettlementLedger):
            return _retry_entry(entry, "terminal settlement ledger is unavailable")
        settlement = next(
            (record for record in settlement_ledger.records if record.attempt_id == attempt_id),
            None,
        )
        if (
            settlement is None
            or settlement.reservation_id != request.admission.reservation_id
            or settlement.worker_id != request.admission.worker_id
        ):
            return _retry_entry(entry, "terminal result has no matching worker settlement")

        worker_state = self._persistence.worker_state
        pool = await worker_state.load_pool(request.worker_pool.profile)
        reservation = next(
            (
                item
                for item in pool.reservations
                if item.reservation_id == settlement.reservation_id
            ),
            None,
        )
        if (
            reservation is None
            or reservation.active
            or reservation.released_at != settlement.released_at
        ):
            return _retry_entry(entry, "terminal result capacity release is not durable")
        lease_state = await worker_state.load_lease(request.lease_state.lease.lease_id)
        if not isinstance(lease_state, LeaseObservationState):
            return _retry_entry(entry, "terminal result lease release is unavailable")
        if (
            lease_state.lease.attempt_id != attempt_id
            or lease_state.lease.worker_id != request.admission.worker_id
            or lease_state.lease.released_at != settlement.released_at
            or lease_state.lease.status_at(observed_at) is not AttemptLeaseStatus.RELEASED
        ):
            return _retry_entry(
                entry, "terminal result lease release does not match its settlement"
            )
        release_observation = next(
            (
                observation
                for observation in lease_state.applied_observations
                if observation.fingerprint == settlement.lease_observation_fingerprint
            ),
            None,
        )
        if (
            release_observation is None
            or release_observation.kind is not LeaseObservationKind.RELEASE
            or release_observation.observed_at != settlement.released_at
        ):
            return _retry_entry(entry, "terminal settlement release observation is unavailable")

        search_state = await self._persistence.search_state.load(
            principal=owner_id,
            experiment_fingerprint=dispatch.experiment_fingerprint,
        )
        if search_state is None or dispatch.candidate_index >= len(search_state.candidates):
            return _retry_entry(entry, "terminal search candidate state is unavailable")
        candidate = search_state.candidates[dispatch.candidate_index]
        if candidate.phase is SearchCandidatePhase.SUCCEEDED:
            if (
                candidate.attempt_id != attempt_id
                or candidate.result_fingerprint != completion.result_fingerprint
            ):
                return _retry_entry(entry, "terminal search receipt conflicts with its completion")
        elif candidate.phase is SearchCandidatePhase.RUNNING and candidate.attempt_id == attempt_id:
            resolution = await self._persistence.search_state.record_terminal(
                principal=owner_id,
                experiment_fingerprint=dispatch.experiment_fingerprint,
                candidate_index=dispatch.candidate_index,
                attempt_id=attempt_id,
                phase=SearchCandidatePhase.SUCCEEDED,
                result_fingerprint=completion.result_fingerprint,
                now=completion.completed_at,
            )
            if resolution.decision not in {
                SearchStateDecision.APPLY,
                SearchStateDecision.REPLAY_EXISTING,
            }:
                return _retry_entry(entry, "terminal result could not close its search candidate")
            search_state = resolution.state
        else:
            return _retry_entry(entry, "terminal result no longer owns its search candidate")

        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest(
                {
                    "completion_fingerprint": completion.fingerprint,
                    "dispatch_fingerprint": dispatch.request.fingerprint,
                    "entry_fingerprint": entry.fingerprint,
                    "search_state_fingerprint": search_state.fingerprint,
                    "settlement_fingerprint": settlement.fingerprint,
                    "terminal_release_observation": release_observation.fingerprint,
                }
            ),
        )

    async def _record_prior_terminal(
        self,
        *,
        context: WorkerRecoveryContext,
        owner_id: str,
        dispatch: SearchDispatchRecord,
        prior_attempt_id: str,
        phase: SearchCandidatePhase,
        terminal_at: datetime,
        allowed_next_attempt_id: str | None,
        allowed_next_attempt_ordinal: int | None,
    ) -> bool:
        state = await self._persistence.search_state.load(
            principal=owner_id,
            experiment_fingerprint=dispatch.experiment_fingerprint,
        )
        if state is None or dispatch.candidate_index >= len(state.candidates):
            return False
        candidate = state.candidates[dispatch.candidate_index]
        if candidate.attempt_id == prior_attempt_id and candidate.phase is phase:
            return True
        if candidate.attempt_id == allowed_next_attempt_id and allowed_next_attempt_id is not None:
            return candidate.phase in {
                SearchCandidatePhase.RUNNING,
                SearchCandidatePhase.FAILED,
                SearchCandidatePhase.CANCELLED,
                SearchCandidatePhase.SUCCEEDED,
            }
        if (
            allowed_next_attempt_ordinal is not None
            and candidate.attempt_count >= allowed_next_attempt_ordinal
            and candidate.phase
            in {
                SearchCandidatePhase.RUNNING,
                SearchCandidatePhase.FAILED,
                SearchCandidatePhase.CANCELLED,
                SearchCandidatePhase.SUCCEEDED,
            }
        ):
            return True
        if (
            candidate.attempt_id != prior_attempt_id
            or candidate.phase is not SearchCandidatePhase.RUNNING
        ):
            return False
        resolution = await self._persistence.search_state.record_terminal(
            principal=owner_id,
            experiment_fingerprint=dispatch.experiment_fingerprint,
            candidate_index=dispatch.candidate_index,
            attempt_id=prior_attempt_id,
            phase=phase,
            now=terminal_at,
        )
        return resolution.decision in {
            SearchStateDecision.APPLY,
            SearchStateDecision.REPLAY_EXISTING,
        }


def create_worker_recovery_application(
    persistence: Any,
    *,
    queue_name: str,
    dispatch_client: SearchDispatchClient,
) -> WorkerRecoveryApplication:
    """Validate persistence capabilities and create the worker recovery seam."""

    required = {
        "search_dispatch": (
            "load_by_request_fingerprint",
            "load_admission_ledger",
        ),
        "search_state": ("load", "record_terminal"),
        "worker_recoveries": ("load_ledger", "recover"),
        "result_completion": ("load_completion_ledger",),
        "worker_settlements": ("load_ledger",),
        "worker_state": ("load_pool", "load_lease"),
        "resources": ("get_run_attempt_by_attempt_id", "get_run_attempts_for_trial"),
    }
    for adapter_name, methods in required.items():
        adapter = getattr(persistence, adapter_name, None)
        if adapter is None or any(
            not callable(getattr(adapter, method, None)) for method in methods
        ):
            raise TypeError(f"persistence.{adapter_name} lacks worker recovery methods")
    if not callable(getattr(persistence, "persist_retry_attempt", None)):
        raise TypeError("persistence must expose persist_retry_attempt()")
    return WorkerRecoveryApplication(
        persistence,
        queue_name=queue_name,
        dispatch_client=dispatch_client,
    )


async def _dispatch_for_entry(
    dispatch_store: Any,
    entry: Any,
    *,
    attempt_id: str,
) -> SearchDispatchRecord | None:
    """Authenticate an OOS dispatch from the payload identity on Redis."""

    payload_digest = getattr(entry, "payload_digest", None)
    loader = getattr(dispatch_store, "load_by_payload_digest", None)
    if callable(loader) and isinstance(payload_digest, str):
        dispatch = await loader(payload_digest)
    else:
        dispatch = await dispatch_store.load_by_request_fingerprint(entry.request_fingerprint)
    if not isinstance(dispatch, SearchDispatchRecord):
        return None
    if dispatch.request.attempt_id != attempt_id or (
        payload_digest is not None and dispatch.request.payload_digest != payload_digest
    ):
        return None
    return dispatch


def _attempt_chain_through(
    attempts: Any,
    current: RunAttempt,
) -> tuple[RunAttempt, ...]:
    values = tuple(attempts)
    if any(not isinstance(item, RunAttempt) for item in values):
        raise TypeError("attempt lineage must contain RunAttempt values")
    chain = tuple(
        sorted(
            (item for item in values if item.ordinal <= current.ordinal),
            key=lambda item: item.ordinal,
        )
    )
    if not chain or chain[-1].attempt_id != current.attempt_id:
        raise ValueError("authenticated attempt is missing from its trial lineage")
    if [item.ordinal for item in chain] != list(range(1, current.ordinal + 1)):
        raise ValueError("authenticated attempt lineage has missing ordinals")
    if any(item.trial_id != current.trial_id for item in chain):
        raise ValueError("authenticated attempt lineage crosses trial identities")
    return chain


def _terminalize_recovered_attempts(
    chain: tuple[RunAttempt, ...],
    records: tuple[WorkerRecoveryRecord, ...],
) -> tuple[RunAttempt, ...]:
    by_attempt = {item.attempt_id: item for item in records}
    resolved: list[RunAttempt] = []
    for attempt in chain:
        record = by_attempt.get(attempt.attempt_id)
        if record is None or attempt.state is AttemptState.SUCCEEDED:
            resolved.append(attempt)
            continue
        state = (
            AttemptState.CANCELLED
            if record.reason is RecoveryReason.CANCELLED
            else AttemptState.FAILED
        )
        resolved.append(replace(attempt, state=state, updated_at=record.released_at))
    return tuple(resolved)


def _receipt_for_attempt(
    resolution: WorkerRecoveryResolution,
    attempt_id: str,
) -> WorkerRecoveryRecord | None:
    if resolution.release_observation is None:
        return None
    return next(
        (item for item in resolution.ledger.records if item.attempt_id == attempt_id),
        None,
    )


def _retry_attempt_id(request_fingerprint: str, attempt_id: str, reason: RecoveryReason) -> str:
    digest = content_digest(
        {"attempt_id": attempt_id, "reason": reason, "request_fingerprint": request_fingerprint}
    )
    return f"retry-{digest.removeprefix('sha256:')}"


def _retry_request_id(recovery_fingerprint: str) -> str:
    return f"retry-{recovery_fingerprint.removeprefix('sha256:')[:48]}"


def _retry(context: WorkerRecoveryContext, reason: str) -> WorkerHandleResult:
    return _retry_entry(context.entry, reason)


def _retry_entry(entry: Any, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(
        entry.fingerprint,
        WorkerHandleDecision.RETRY,
        rejection_reason=reason,
    )


def _complete(
    context: WorkerRecoveryContext,
    receipt: WorkerRecoveryRecord,
    retry_attempt_id: str | None,
    dispatch: SearchDispatchResolution | None = None,
) -> WorkerHandleResult:
    return WorkerHandleResult(
        context.entry.fingerprint,
        WorkerHandleDecision.COMPLETE,
        content_digest(
            {
                "dispatch_fingerprint": (
                    None
                    if dispatch is None or dispatch.dispatch_resolution is None
                    else dispatch.dispatch_resolution.request_fingerprint
                ),
                "entry_fingerprint": context.entry.fingerprint,
                "recovery_fingerprint": receipt.recovery_fingerprint,
                "retry_attempt_id": retry_attempt_id,
            }
        ),
    )


__all__ = [
    "SearchDispatchClient",
    "WorkerRecoveryApplication",
    "create_worker_recovery_application",
]
