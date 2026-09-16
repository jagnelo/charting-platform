"""Resumable, cancellable search-candidate execution state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class SearchCandidatePhase(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_PHASES = frozenset(
    {SearchCandidatePhase.SUCCEEDED, SearchCandidatePhase.FAILED, SearchCandidatePhase.CANCELLED}
)


@dataclass(frozen=True, slots=True)
class SearchCandidateState:
    """One scientific candidate with infrastructure-attempt lineage."""

    candidate_index: int
    trial_fingerprint: str
    phase: SearchCandidatePhase = SearchCandidatePhase.PENDING
    attempt_id: str | None = None
    attempt_count: int = 0
    result_fingerprint: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_index, int) or isinstance(self.candidate_index, bool) or self.candidate_index < 0:
            raise ValueError("candidate_index must be a non-negative integer")
        require_sha256_digest(self.trial_fingerprint, field_name="trial_fingerprint")
        if not isinstance(self.phase, SearchCandidatePhase):
            raise TypeError("phase must be a SearchCandidatePhase")
        if self.attempt_id is not None:
            _nonempty(self.attempt_id, "attempt_id")
        if not isinstance(self.attempt_count, int) or isinstance(self.attempt_count, bool) or self.attempt_count < 0:
            raise ValueError("attempt_count must be a non-negative integer")
        if self.phase is SearchCandidatePhase.PENDING:
            if self.attempt_id is not None or self.attempt_count != 0 or self.result_fingerprint is not None:
                raise ValueError("pending candidates cannot contain attempts or results")
        elif self.phase is SearchCandidatePhase.RUNNING:
            if self.attempt_id is None or self.attempt_count < 1 or self.result_fingerprint is not None:
                raise ValueError("running candidates require one active attempt and no result")
        elif self.phase is SearchCandidatePhase.SUCCEEDED:
            if self.attempt_id is None or self.attempt_count < 1 or self.result_fingerprint is None:
                raise ValueError("successful candidates require an attempt and result")
            require_sha256_digest(self.result_fingerprint, field_name="result_fingerprint")
        else:
            if self.attempt_id is None or self.attempt_count < 1 or self.result_fingerprint is not None:
                raise ValueError("failed or cancelled candidates require an attempt and no result")
        if self.updated_at is not None:
            _aware(self.updated_at, "updated_at")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class SearchExecutionState:
    """Immutable search queue checkpoint independent of worker transport."""

    experiment_fingerprint: str
    candidates: tuple[SearchCandidateState, ...]
    cancellation_requested: bool = False
    cancellation_request_id: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        if not isinstance(self.candidates, tuple) or not self.candidates:
            raise ValueError("search execution requires at least one candidate")
        for expected, candidate in enumerate(self.candidates):
            if not isinstance(candidate, SearchCandidateState):
                raise TypeError("candidates must contain SearchCandidateState values")
            if candidate.candidate_index != expected:
                raise ValueError("search candidate indices must be contiguous")
        fingerprints = [candidate.trial_fingerprint for candidate in self.candidates]
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("search trial fingerprints must be unique")
        if not isinstance(self.cancellation_requested, bool):
            raise TypeError("cancellation_requested must be a bool")
        if self.cancellation_request_id is not None:
            require_sha256_digest(self.cancellation_request_id, field_name="cancellation_request_id")
        if self.cancellation_requested and self.cancellation_request_id is None:
            raise ValueError("cancelled searches require a cancellation request identity")
        if not self.cancellation_requested and self.cancellation_request_id is not None:
            raise ValueError("uncancelled searches cannot contain a cancellation request identity")
        if self.updated_at is not None:
            _aware(self.updated_at, "updated_at")

    @property
    def pending_candidate_indices(self) -> tuple[int, ...]:
        return tuple(
            candidate.candidate_index
            for candidate in self.candidates
            if candidate.phase is SearchCandidatePhase.PENDING
        )

    @property
    def complete(self) -> bool:
        return all(candidate.phase in _TERMINAL_PHASES for candidate in self.candidates)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def new_search_execution_state(
    experiment_fingerprint: str,
    trial_fingerprints: tuple[str, ...],
    *,
    now: datetime | None = None,
) -> SearchExecutionState:
    """Create a sequence-stable queue from an immutable trial design."""

    require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
    if not isinstance(trial_fingerprints, tuple) or not trial_fingerprints:
        raise ValueError("trial_fingerprints must be a non-empty tuple")
    for fingerprint in trial_fingerprints:
        require_sha256_digest(fingerprint, field_name="trial_fingerprint")
    if len(set(trial_fingerprints)) != len(trial_fingerprints):
        raise ValueError("trial_fingerprints must be unique")
    if now is not None:
        _aware(now, "now")
    return SearchExecutionState(
        experiment_fingerprint,
        tuple(SearchCandidateState(index, fingerprint, updated_at=now) for index, fingerprint in enumerate(trial_fingerprints)),
        updated_at=now,
    )


class SearchStateDecision(StrEnum):
    APPLY = "apply"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class SearchStateResolution:
    decision: SearchStateDecision
    state: SearchExecutionState
    candidate_index: int | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SearchStateDecision):
            raise TypeError("decision must be a SearchStateDecision")
        if not isinstance(self.state, SearchExecutionState):
            raise TypeError("state must be a SearchExecutionState")
        if self.candidate_index is not None and (
            not isinstance(self.candidate_index, int) or isinstance(self.candidate_index, bool)
        ):
            raise ValueError("candidate_index must be an integer when provided")
        if self.decision is SearchStateDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected search transitions require a reason")
        if self.decision is not SearchStateDecision.REJECT and self.rejection_reason:
            raise ValueError("successful search transitions cannot contain a reason")


def _candidate(state: SearchExecutionState, candidate_index: int) -> SearchCandidateState:
    if not isinstance(candidate_index, int) or isinstance(candidate_index, bool):
        raise ValueError("candidate_index must be an integer")
    if candidate_index < 0 or candidate_index >= len(state.candidates):
        raise ValueError("candidate_index is outside the search")
    return state.candidates[candidate_index]


def _replace_candidate(
    state: SearchExecutionState,
    candidate: SearchCandidateState,
    *,
    now: datetime,
) -> SearchExecutionState:
    _aware(now, "now")
    if state.updated_at is not None and now < state.updated_at:
        raise ValueError("search transition time cannot move backwards")
    candidates = list(state.candidates)
    candidates[candidate.candidate_index] = replace(candidate, updated_at=now)
    return replace(state, candidates=tuple(candidates), updated_at=now)


def start_search_candidate(
    state: SearchExecutionState,
    candidate_index: int,
    *,
    attempt_id: str,
    now: datetime,
) -> SearchStateResolution:
    """Start or retry one candidate; the scientific trial identity is retained."""

    if not isinstance(state, SearchExecutionState):
        raise TypeError("state must be a SearchExecutionState")
    _nonempty(attempt_id, "attempt_id")
    _aware(now, "now")
    candidate = _candidate(state, candidate_index)
    if state.cancellation_requested:
        return SearchStateResolution(
            SearchStateDecision.REJECT, state, candidate_index,
            "search cancellation has been requested",
        )
    if candidate.phase is SearchCandidatePhase.RUNNING:
        if candidate.attempt_id == attempt_id:
            return SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, state, candidate_index)
        return SearchStateResolution(
            SearchStateDecision.REJECT, state, candidate_index,
            "candidate already has a different active attempt",
        )
    if candidate.phase in {SearchCandidatePhase.SUCCEEDED, SearchCandidatePhase.CANCELLED}:
        return SearchStateResolution(
            SearchStateDecision.REJECT, state, candidate_index,
            "terminal candidate cannot be started",
        )
    if state.updated_at is not None and now < state.updated_at:
        return SearchStateResolution(
            SearchStateDecision.REJECT, state, candidate_index,
            "candidate start time cannot move backwards",
        )
    running = replace(
        candidate,
        phase=SearchCandidatePhase.RUNNING,
        attempt_id=attempt_id,
        attempt_count=candidate.attempt_count + 1,
        result_fingerprint=None,
    )
    return SearchStateResolution(
        SearchStateDecision.APPLY,
        _replace_candidate(state, running, now=now),
        candidate_index,
    )


def record_search_candidate_terminal(
    state: SearchExecutionState,
    candidate_index: int,
    *,
    attempt_id: str,
    phase: SearchCandidatePhase,
    now: datetime,
    result_fingerprint: str | None = None,
) -> SearchStateResolution:
    """Record an immutable success/failure/cancellation receipt for one attempt."""

    if not isinstance(state, SearchExecutionState):
        raise TypeError("state must be a SearchExecutionState")
    _nonempty(attempt_id, "attempt_id")
    _aware(now, "now")
    if phase not in _TERMINAL_PHASES:
        raise ValueError("terminal candidate records require a terminal phase")
    if phase is SearchCandidatePhase.SUCCEEDED:
        require_sha256_digest(result_fingerprint or "", field_name="result_fingerprint")
    elif result_fingerprint is not None:
        raise ValueError("failed or cancelled candidates cannot contain a result")
    candidate = _candidate(state, candidate_index)
    if candidate.phase in _TERMINAL_PHASES:
        same = (
            candidate.attempt_id == attempt_id
            and candidate.phase is phase
            and candidate.result_fingerprint == result_fingerprint
        )
        if same:
            return SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, state, candidate_index)
        return SearchStateResolution(
            SearchStateDecision.REJECT, state, candidate_index,
            "terminal candidate content conflicts with the existing receipt",
        )
    if candidate.phase is not SearchCandidatePhase.RUNNING or candidate.attempt_id != attempt_id:
        return SearchStateResolution(
            SearchStateDecision.REJECT, state, candidate_index,
            "terminal receipt must match the active candidate attempt",
        )
    if state.cancellation_requested and phase is not SearchCandidatePhase.CANCELLED:
        return SearchStateResolution(
            SearchStateDecision.REJECT, state, candidate_index,
            "cancelled searches require cancelled candidate receipts",
        )
    terminal = replace(candidate, phase=phase, result_fingerprint=result_fingerprint)
    return SearchStateResolution(
        SearchStateDecision.APPLY,
        _replace_candidate(state, terminal, now=now),
        candidate_index,
    )


def request_search_cancellation(
    state: SearchExecutionState,
    *,
    request_id: str,
    now: datetime,
) -> SearchStateResolution:
    """Record one idempotent cancellation request; workers still close candidates."""

    if not isinstance(state, SearchExecutionState):
        raise TypeError("state must be a SearchExecutionState")
    require_sha256_digest(request_id, field_name="request_id")
    _aware(now, "now")
    if state.cancellation_requested:
        if state.cancellation_request_id == request_id:
            return SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, state)
        return SearchStateResolution(
            SearchStateDecision.REJECT, state,
            rejection_reason="search cancellation is already bound to another request",
        )
    if state.complete:
        return SearchStateResolution(
            SearchStateDecision.REJECT, state,
            rejection_reason="completed searches cannot be cancelled",
        )
    if state.updated_at is not None and now < state.updated_at:
        return SearchStateResolution(
            SearchStateDecision.REJECT, state,
            rejection_reason="cancellation time cannot move backwards",
        )
    return SearchStateResolution(
        SearchStateDecision.APPLY,
        replace(state, cancellation_requested=True, cancellation_request_id=request_id, updated_at=now),
    )
