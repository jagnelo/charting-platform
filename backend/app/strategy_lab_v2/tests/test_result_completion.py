from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.artifact_commit import ArtifactCommitLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outcomes import OutcomeStatus
from app.strategy_lab_v2.progress import ProgressPhase
from app.strategy_lab_v2.result_completion import (
    ResultCompletionDecision,
    ResultCompletionLedger,
    finalize_execution_result,
)
from app.strategy_lab_v2.result_publication import ResultPublicationDecision
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionPhase,
    RuntimeExecutionUpdate,
    apply_runtime_execution_update,
    new_runtime_execution_state,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.tests.test_artifact_commit import _plan as artifact_plan
from app.strategy_lab_v2.tests.test_execution_summary import (
    _outcome,
    _progress,
    _publication,
    _receipt,
)
from app.strategy_lab_v2.tests.test_runtime_execution import _profile, _request

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _runtime_success():
    profile = _profile()
    preflight = preflight_strategy_runtime(_request(profile), profile)
    accepted = new_runtime_execution_state(
        preflight,
        attempt_id="attempt-1",
        output_limit_bytes=100,
        accepted_at=NOW,
    )
    running = apply_runtime_execution_update(
        accepted,
        RuntimeExecutionUpdate(
            preflight.request_fingerprint,
            "attempt-1",
            1,
            RuntimeExecutionPhase.RUNNING,
            NOW + timedelta(seconds=1),
        ),
    )
    return apply_runtime_execution_update(
        running.state,
        RuntimeExecutionUpdate(
            preflight.request_fingerprint,
            "attempt-1",
            2,
            RuntimeExecutionPhase.SUCCEEDED,
            NOW + timedelta(seconds=2),
            content_digest("runtime-output"),
            10,
        ),
    ).state


def _fixture():
    submission = _receipt()
    outcome = _outcome(OutcomeStatus.SUCCEEDED)
    progress = _progress(ProgressPhase.SUCCEEDED, sequence=1)
    return submission, outcome, progress, _runtime_success(), _publication(outcome.result_digest or "")


def test_successful_completion_commits_all_artifacts_and_is_idempotent() -> None:
    submission, outcome, progress, runtime, publication = _fixture()
    plans = (artifact_plan(b"one"), artifact_plan(b"two"))
    first = finalize_execution_result(
        ResultCompletionLedger(),
        ArtifactCommitLedger(),
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=3),
    )

    assert first.decision is ResultCompletionDecision.COMPLETE
    assert first.record is not None
    assert len(first.record.artifact_commit_keys) == 2
    assert len(first.artifact_commit_ledger.records) == 2
    replay = finalize_execution_result(
        first.completion_ledger,
        first.artifact_commit_ledger,
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=4),
    )
    assert replay.decision is ResultCompletionDecision.REPLAY_EXISTING
    assert replay.record == first.record
    assert replay.artifact_commit_ledger == first.artifact_commit_ledger


def test_any_artifact_conflict_rolls_back_the_entire_commit_ledger() -> None:
    submission, outcome, progress, runtime, publication = _fixture()
    first = artifact_plan(b"one")
    conflicting = replace(first, manifest_fingerprint=content_digest("different-manifest"))
    resolution = finalize_execution_result(
        ResultCompletionLedger(),
        ArtifactCommitLedger(),
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=(first, conflicting),
        completed_at=NOW + timedelta(seconds=3),
    )
    assert resolution.decision is ResultCompletionDecision.CONFLICT
    assert resolution.rejection_reason == "storage key is already committed to different manifest content"
    assert resolution.artifact_commit_ledger == ArtifactCommitLedger()
    assert resolution.completion_ledger == ResultCompletionLedger()


def test_completion_requires_terminal_evidence_and_existing_replays() -> None:
    submission, outcome, progress, runtime, publication = _fixture()
    plans = (artifact_plan(),)
    running_runtime = replace(runtime, phase=RuntimeExecutionPhase.RUNNING, output_digest=None, output_bytes=None)
    rejected = finalize_execution_result(
        ResultCompletionLedger(),
        ArtifactCommitLedger(),
        submission=submission,
        runtime_state=running_runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=3),
    )
    assert rejected.decision is ResultCompletionDecision.REJECT
    assert rejected.rejection_reason == "runtime execution is not successful"

    complete = finalize_execution_result(
        ResultCompletionLedger(),
        ArtifactCommitLedger(),
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=3),
    )
    assert complete.record is not None
    missing_artifact = finalize_execution_result(
        complete.completion_ledger,
        ArtifactCommitLedger(),
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=4),
    )
    assert missing_artifact.decision is ResultCompletionDecision.REJECT
    assert missing_artifact.rejection_reason == "completion receipt is missing an artifact commit"


def test_completion_rejects_unpublished_or_mismatched_terminal_identity() -> None:
    submission, outcome, progress, runtime, publication = _fixture()
    plans = (artifact_plan(),)
    replay_without_receipt = replace(publication, decision=ResultPublicationDecision.REPLAY_EXISTING)
    rejected_replay = finalize_execution_result(
        ResultCompletionLedger(),
        ArtifactCommitLedger(),
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=replay_without_receipt,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=3),
    )
    assert rejected_replay.decision is ResultCompletionDecision.REJECT
    assert rejected_replay.rejection_reason == "published-result replay requires a completion receipt"

    wrong_result = replace(publication, result_fingerprint=content_digest("other-result"))
    mismatched = finalize_execution_result(
        ResultCompletionLedger(),
        ArtifactCommitLedger(),
        submission=submission,
        runtime_state=runtime,
        outcome=outcome,
        progress=progress,
        publication=wrong_result,
        artifact_plans=plans,
        completed_at=NOW + timedelta(seconds=3),
    )
    assert mismatched.decision is ResultCompletionDecision.REJECT
    assert mismatched.rejection_reason == "outcome and publication results differ"
