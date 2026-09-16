"""Atomic completion of a successful execution and its output artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitDecision,
    ArtifactCommitLedger,
    finalize_artifact_commit,
)
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.execution_summary import build_execution_summary
from app.strategy_lab_v2.outcomes import ExecutionOutcome, OutcomeStatus
from app.strategy_lab_v2.progress import ExecutionProgressState, ProgressPhase
from app.strategy_lab_v2.result_publication import (
    ResultPublicationDecision,
    ResultPublicationPlan,
)
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionPhase,
    RuntimeExecutionState,
)
from app.strategy_lab_v2.submissions import SubmissionReceipt


class ResultCompletionDecision(StrEnum):
    COMPLETE = "complete"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ResultCompletionRecord:
    """Receipt binding terminal execution evidence to committed artifacts."""

    completion_fingerprint: str
    result_fingerprint: str
    attempt_id: str
    runtime_state_fingerprint: str
    outcome_fingerprint: str
    progress_fingerprint: str
    publication_fingerprint: str
    artifact_commit_keys: tuple[str, ...]
    completed_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "completion_fingerprint",
            "result_fingerprint",
            "runtime_state_fingerprint",
            "outcome_fingerprint",
            "progress_fingerprint",
            "publication_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        keys = tuple(self.artifact_commit_keys)
        for key in keys:
            require_sha256_digest(key, field_name="artifact_commit_key")
        if len(keys) != len(set(keys)):
            raise ValueError("artifact commit keys must be unique")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        object.__setattr__(self, "artifact_commit_keys", tuple(sorted(keys)))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ResultCompletionLedger:
    """Deterministically ordered terminal completion receipts."""

    records: tuple[ResultCompletionRecord, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.records)
        if any(not isinstance(item, ResultCompletionRecord) for item in records):
            raise TypeError("records must contain ResultCompletionRecord values")
        completion_ids = [item.completion_fingerprint for item in records]
        if len(completion_ids) != len(set(completion_ids)):
            raise ValueError("completion fingerprints must be unique")
        attempt_ids = [item.attempt_id for item in records]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("an attempt may have only one completion receipt")
        result_ids = [item.result_fingerprint for item in records]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("result fingerprints must be unique")
        object.__setattr__(
            self,
            "records",
            tuple(sorted(records, key=lambda item: item.completion_fingerprint)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ResultCompletionResolution:
    decision: ResultCompletionDecision
    completion_ledger: ResultCompletionLedger
    artifact_commit_ledger: ArtifactCommitLedger
    completion_fingerprint: str
    record: ResultCompletionRecord | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ResultCompletionDecision):
            raise TypeError("decision must be a ResultCompletionDecision")
        if not isinstance(self.completion_ledger, ResultCompletionLedger):
            raise TypeError("completion_ledger must be a ResultCompletionLedger")
        if not isinstance(self.artifact_commit_ledger, ArtifactCommitLedger):
            raise TypeError("artifact_commit_ledger must be an ArtifactCommitLedger")
        require_sha256_digest(self.completion_fingerprint, field_name="completion_fingerprint")
        if self.record is not None and not isinstance(self.record, ResultCompletionRecord):
            raise TypeError("record must be a ResultCompletionRecord")
        if self.decision in {
            ResultCompletionDecision.COMPLETE,
            ResultCompletionDecision.REPLAY_EXISTING,
        } and self.record is None:
            raise ValueError("completed resolutions require a record")
        if self.decision in {
            ResultCompletionDecision.CONFLICT,
            ResultCompletionDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision in {
            ResultCompletionDecision.COMPLETE,
            ResultCompletionDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("completed resolutions cannot contain a rejection reason")


def finalize_execution_result(
    completion_ledger: ResultCompletionLedger,
    artifact_commit_ledger: ArtifactCommitLedger,
    *,
    submission: SubmissionReceipt,
    runtime_state: RuntimeExecutionState,
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    publication: ResultPublicationPlan,
    artifact_plans: Sequence[ArtifactPublicationPlan],
    completed_at: datetime,
) -> ResultCompletionResolution:
    """Finalize terminal evidence and all artifacts as one adapter transaction.

    Every artifact commit is resolved against the original ledger. If one plan
    conflicts or rejects, no partial commit ledger is returned. The function
    does not write bytes, publish a result, or mutate execution states.
    """

    if not isinstance(completion_ledger, ResultCompletionLedger):
        raise TypeError("completion_ledger must be a ResultCompletionLedger")
    if not isinstance(artifact_commit_ledger, ArtifactCommitLedger):
        raise TypeError("artifact_commit_ledger must be an ArtifactCommitLedger")
    if not isinstance(submission, SubmissionReceipt):
        raise TypeError("submission must be a SubmissionReceipt")
    if not isinstance(runtime_state, RuntimeExecutionState):
        raise TypeError("runtime_state must be a RuntimeExecutionState")
    if not isinstance(outcome, ExecutionOutcome):
        raise TypeError("outcome must be an ExecutionOutcome")
    if not isinstance(progress, ExecutionProgressState):
        raise TypeError("progress must be an ExecutionProgressState")
    if not isinstance(publication, ResultPublicationPlan):
        raise TypeError("publication must be a ResultPublicationPlan")
    if not isinstance(artifact_plans, Sequence):
        raise TypeError("artifact_plans must be a sequence")
    plans = tuple(artifact_plans)
    if any(not isinstance(item, ArtifactPublicationPlan) for item in plans):
        raise TypeError("artifact_plans must contain ArtifactPublicationPlan values")
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("completed_at must be timezone-aware")

    if submission.request.attempt_id != runtime_state.attempt_id:
        return _reject(completion_ledger, artifact_commit_ledger, "submission and runtime attempt differ")
    if outcome.attempt_id != runtime_state.attempt_id or progress.attempt_id != runtime_state.attempt_id:
        return _reject(completion_ledger, artifact_commit_ledger, "terminal evidence references different attempts")
    if publication.attempt_id != runtime_state.attempt_id:
        return _reject(completion_ledger, artifact_commit_ledger, "publication references a different attempt")
    if runtime_state.phase is not RuntimeExecutionPhase.SUCCEEDED:
        return _reject(completion_ledger, artifact_commit_ledger, "runtime execution is not successful")
    if outcome.status is not OutcomeStatus.SUCCEEDED:
        return _reject(completion_ledger, artifact_commit_ledger, "execution outcome is not successful")
    if progress.phase is not ProgressPhase.SUCCEEDED or progress.completed_units != progress.total_units:
        return _reject(completion_ledger, artifact_commit_ledger, "execution progress is not complete")
    if outcome.result_digest != publication.result_fingerprint:
        return _reject(completion_ledger, artifact_commit_ledger, "outcome and publication results differ")
    if publication.decision is ResultPublicationDecision.REJECT:
        return _reject(completion_ledger, artifact_commit_ledger, "result publication is rejected")

    summary = build_execution_summary(submission, outcome, progress, publication)
    if summary.status is not OutcomeStatus.SUCCEEDED:
        return _reject(completion_ledger, artifact_commit_ledger, "execution summary is not successful")
    plan_fingerprints = tuple(sorted(content_digest(plan) for plan in plans))
    completion_fingerprint = content_digest(
        {
            "artifact_plans": plan_fingerprints,
            "attempt_id": runtime_state.attempt_id,
            "publication_fingerprint": publication.fingerprint,
            "result_fingerprint": publication.result_fingerprint,
            "runtime_state_fingerprint": runtime_state.fingerprint,
        }
    )
    existing = next(
        (
            item
            for item in completion_ledger.records
            if item.attempt_id == runtime_state.attempt_id
        ),
        None,
    )
    if existing is not None:
        if existing.completion_fingerprint != completion_fingerprint:
            return ResultCompletionResolution(
                ResultCompletionDecision.CONFLICT,
                completion_ledger,
                artifact_commit_ledger,
                completion_fingerprint,
                rejection_reason="attempt is already bound to different completion content",
            )
        if any(
            not any(record.commit_key == key for record in artifact_commit_ledger.records)
            for key in existing.artifact_commit_keys
        ):
            return _reject(
                completion_ledger,
                artifact_commit_ledger,
                "completion receipt is missing an artifact commit",
                completion_fingerprint=completion_fingerprint,
            )
        return ResultCompletionResolution(
            ResultCompletionDecision.REPLAY_EXISTING,
            completion_ledger,
            artifact_commit_ledger,
            completion_fingerprint,
            existing,
        )
    if publication.decision is ResultPublicationDecision.REPLAY_EXISTING:
        return _reject(
            completion_ledger,
            artifact_commit_ledger,
            "published-result replay requires a completion receipt",
            completion_fingerprint=completion_fingerprint,
        )

    next_commits = artifact_commit_ledger
    committed_keys: list[str] = []
    for plan in sorted(plans, key=content_digest):
        commit = finalize_artifact_commit(
            next_commits,
            plan,
            committed_at=completed_at,
        )
        if commit.decision in {
            ArtifactCommitDecision.CONFLICT,
            ArtifactCommitDecision.REJECT,
        }:
            return _reject(
                completion_ledger,
                artifact_commit_ledger,
                commit.rejection_reason or "artifact commit rejected",
                decision=(
                    ResultCompletionDecision.CONFLICT
                    if commit.decision is ArtifactCommitDecision.CONFLICT
                    else ResultCompletionDecision.REJECT
                ),
                completion_fingerprint=completion_fingerprint,
            )
        assert commit.record is not None
        next_commits = commit.ledger
        committed_keys.append(commit.record.commit_key)
    record = ResultCompletionRecord(
        completion_fingerprint=completion_fingerprint,
        result_fingerprint=publication.result_fingerprint,
        attempt_id=runtime_state.attempt_id,
        runtime_state_fingerprint=runtime_state.fingerprint,
        outcome_fingerprint=outcome.fingerprint,
        progress_fingerprint=progress.fingerprint,
        publication_fingerprint=publication.fingerprint,
        artifact_commit_keys=tuple(committed_keys),
        completed_at=completed_at,
    )
    return ResultCompletionResolution(
        ResultCompletionDecision.COMPLETE,
        ResultCompletionLedger(completion_ledger.records + (record,)),
        next_commits,
        completion_fingerprint,
        record,
    )


def _reject(
    completion_ledger: ResultCompletionLedger,
    artifact_commit_ledger: ArtifactCommitLedger,
    reason: str,
    *,
    decision: ResultCompletionDecision = ResultCompletionDecision.REJECT,
    completion_fingerprint: str | None = None,
) -> ResultCompletionResolution:
    return ResultCompletionResolution(
        decision,
        completion_ledger,
        artifact_commit_ledger,
        completion_fingerprint or content_digest({"reason": reason}),
        rejection_reason=reason,
    )
